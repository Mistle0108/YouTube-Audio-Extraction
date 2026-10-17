"""Single-window Windows application. Run with python app.py."""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import queue
import shutil
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinterdnd2 import TkinterDnD

from extractor import Cancelled, extract_mp3, save_unique, validate_url
from metadata import apply_metadata
from metadata_editor import MetadataEditor
from ui import BACKGROUND, BLUE, build_layout


SETTINGS = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "YouTubeMP3Extractor" / "settings.json"
VERSION = "1.0.0"


def load_settings() -> dict:
    settings = {"folder": str(Path.home() / "Music"), "auto_save": False}
    try:
        value = json.loads(SETTINGS.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            return settings
        if isinstance(value.get("folder"), str) and value["folder"]:
            settings["folder"] = value["folder"]
        if isinstance(value.get("auto_save"), bool):
            settings["auto_save"] = value["auto_save"]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return settings


def save_settings(folder: str, auto_save: bool):
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    temporary = SETTINGS.with_suffix(".tmp")
    temporary.write_text(json.dumps({"folder": folder, "auto_save": auto_save}, ensure_ascii=False), encoding="utf-8")
    temporary.replace(SETTINGS)


class App(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"유튜브 MP3 추출기 {VERSION}")
        self.iconbitmap(str(Path(__file__).resolve().parent / "assets" / "app-icon.ico"))
        self.geometry("740x570")
        self.minsize(650, 570)
        self.configure(bg=BACKGROUND)
        self.url = tk.StringVar()
        settings = load_settings()
        self.folder = tk.StringVar(value=settings["folder"])
        self.auto_save = tk.BooleanVar(value=settings["auto_save"])
        self.status = tk.StringVar(value="추출 준비 완료")
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.worker = None
        self.job_active = False
        self.pending = None
        self.pending_directory = None
        self.pending_saved = False
        self.closing = False
        self.indeterminate = False
        self.metadata_open = False
        self.metadata_visible = tk.BooleanVar(self, value=False)
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(100, self.poll)

    def _build(self):
        build_layout(self)
        self.metadata_editor = MetadataEditor(self.metadata_panel)
        self.metadata_editor.grid(row=1, column=0, sticky="nsew")
        self.metadata_panel.grid_remove()
        self.metadata_separator.grid_remove()

    def update_auto_save_description(self):
        self.auto_save_description.configure(text="추출이 끝나면 지정한 폴더에 저장" if self.auto_save.get() else "추출 후 ‘저장’ 버튼을 눌러 저장")

    def toggle_metadata(self):
        self.update_idletasks()
        height = max(570, self.winfo_height())
        if self.metadata_open:
            self.metadata_panel.grid_remove()
            self.metadata_separator.grid_remove()
            self.columnconfigure(2, minsize=0)
            self.minsize(650, 570)
            self.geometry(f"{max(650, self.winfo_width() - 441)}x{height}")
        else:
            self.metadata_panel.grid()
            self.metadata_separator.grid()
            self.columnconfigure(2, minsize=440)
            self.minsize(1100, 570)
            self.geometry(f"{self.winfo_width() + 441}x{height}")
        self.metadata_open = not self.metadata_open
        self.metadata_visible.set(self.metadata_open)

    @property
    def busy(self):
        return self.job_active

    def remember_settings(self):
        try:
            save_settings(self.folder.get(), self.auto_save.get())
        except OSError:
            self.status.set("설정을 기억하지 못했습니다. 현재 설정으로 작업은 가능합니다.")

    def paste(self):
        try:
            self.url.set(self.clipboard_get().strip())
        except tk.TclError:
            self.status.set("클립보드에 복사된 링크가 없습니다.")

    def choose_folder(self):
        chosen = filedialog.askdirectory(parent=self, title="MP3 저장 폴더 선택", initialdir=self.folder.get(), mustexist=True)
        if chosen:
            self.folder.set(str(Path(chosen)))
            self.remember_settings()

    def open_folder(self):
        try:
            folder = self.selected_folder()
            if not folder.is_dir():
                raise ValueError("저장 폴더가 없습니다. 폴더를 선택하거나 먼저 저장해 주세요.")
            os.startfile(str(folder))
        except (OSError, ValueError) as error:
            messagebox.showwarning("폴더 열기", str(error), parent=self)

    def set_busy(self, value):
        self.job_active = value
        for widget in (self.link_input, self.folder_input, self.paste_button, self.folder_button, self.start_button, self.auto_save_check):
            widget.configure(state="disabled" if value else "normal")
        can_save = self.pending is not None and not value
        self.save_button.configure(state="normal" if can_save else "disabled", fg_color=BLUE if can_save else "#e0e6f0")
        self.start_button.configure(text="작업 중…" if value else "MP3 추출")
        self.metadata_editor.set_busy(value)

    def selected_folder(self):
        raw_folder = self.folder.get().strip()
        if not raw_folder or not Path(raw_folder).is_absolute():
            raise ValueError("저장 폴더를 전체 경로로 지정해 주세요.")
        return Path(raw_folder)

    def clear_pending(self):
        if self.pending_directory is not None:
            self.pending_directory.cleanup()
        self.pending_directory = None
        self.pending = None
        self.pending_saved = False

    def start(self):
        if self.busy or self.closing:
            return
        try:
            url = validate_url(self.url.get())
            folder = self.selected_folder() if self.auto_save.get() else None
            if self.auto_save.get():
                self.metadata_editor.snapshot("", require_cover=False)
        except ValueError as error:
            messagebox.showwarning("입력 확인", str(error), parent=self)
            return
        if self.pending and not self.pending_saved and not messagebox.askyesno("새로 추출", "아직 저장하지 않은 MP3가 있습니다. 이전 결과를 지우고 새로 추출할까요?", parent=self):
            return
        self.clear_pending()
        self.metadata_editor.begin_extract()
        self.remember_settings()
        self.cancel.clear()
        self.set_busy(True)
        self.update_progress(None, "추출을 준비하고 있습니다…")
        self.worker = threading.Thread(target=self.run_job, args=(url, folder), daemon=True)
        self.worker.start()

    def run_job(self, url, folder):
        temporary = None
        try:
            temporary = tempfile.TemporaryDirectory(prefix="youtube-mp3-")
            result = extract_mp3(url, Path(temporary.name), lambda kind, value: self.events.put((kind, value)), self.cancel)
            self.events.put(("extracted", (temporary, result, folder)))
            temporary = None  # The UI owns the result until it is saved or discarded.
        except Cancelled:
            self.events.put(("cancelled", None))
        except Exception as error:
            self.events.put(("error", str(error)))
        finally:
            if temporary is not None:
                temporary.cleanup()

    def save(self, folder=None):
        if self.busy or self.closing or self.pending is None:
            return
        try:
            folder = folder if folder is not None else self.selected_folder()
            metadata = self.metadata_editor.snapshot(self.pending.stem)
        except ValueError as error:
            messagebox.showwarning("입력 확인", str(error), parent=self)
            return
        self.remember_settings()
        self.set_busy(True)
        self.update_progress(None, "지정한 폴더에 저장하고 있습니다…")
        self.worker = threading.Thread(target=self.run_save, args=(self.pending, folder, metadata), daemon=True)
        self.worker.start()

    def run_save(self, source, folder, metadata):
        try:
            folder.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="tagged-", dir=source.parent) as temporary:
                tagged = Path(temporary) / "tagged.mp3"
                shutil.copyfile(source, tagged)
                apply_metadata(tagged, metadata)
                result = save_unique(tagged, folder, source.stem)
            self.events.put(("saved", result))
        except Exception as error:
            self.events.put(("save_error", str(error)))

    def update_progress(self, percent, text):
        self.status.set(text)
        complete = text.startswith(("추출 완료", "저장 완료"))
        warning = "못했습니다" in text
        heading = text.split(" · ", 1)[0] if complete else "확인 필요" if warning else "작업 중" if percent is None else "추출 준비"
        self.status_heading.configure(text=heading)
        self.status_label.configure(text=text.split(" · ", 1)[-1] if complete else text)
        self.status_badge.configure(text="✓" if complete else "!" if warning else "↓",
                                    text_color="#22894a" if complete else "#bd6b0d" if warning else BLUE)
        self.status_badge_background.configure(fg_color="#eaf8ef" if complete else "#fff5e8" if warning else "#edf3ff")
        if percent is None:
            if not self.indeterminate:
                self.progress.configure(mode="indeterminate")
                self.progress.start()
                self.indeterminate = True
        else:
            self.progress.stop()
            self.indeterminate = False
            self.progress.configure(mode="determinate")
            self.progress.set(percent / 100)

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "progress":
                    self.update_progress(*value)
                elif kind == "metadata":
                    self.metadata_editor.apply_source(value)
                else:
                    if kind == "extracted":
                        self.pending_directory, self.pending, folder = value
                        self.set_busy(False)
                        self.update_progress(100, f"추출 완료 · {self.pending.name} · 저장 버튼을 눌러 주세요.")
                        if folder is not None and not self.closing:
                            self.save(folder)
                    elif kind == "saved":
                        self.pending_saved = True
                        self.set_busy(False)
                        self.update_progress(100, f"저장 완료 · {value.name}")
                    elif kind == "cancelled":
                        self.set_busy(False)
                        self.update_progress(0, "추출을 취소했습니다.")
                    else:
                        self.set_busy(False)
                        self.update_progress(100 if kind == "save_error" else 0,
                                             "저장하지 못했습니다. 폴더를 바꾸고 다시 저장할 수 있습니다." if kind == "save_error"
                                             else "추출하지 못했습니다. 링크와 연결 상태를 확인해 주세요.")
                        if not self.closing:
                            messagebox.showerror("저장 실패" if kind == "save_error" else "추출 실패", value[:1600], parent=self)
        except queue.Empty:
            pass
        if self.closing and not self.busy:
            self.clear_pending()
            self.destroy()
            return
        self.after(100, self.poll)

    def close(self):
        if self.busy:
            if self.closing or not messagebox.askyesno("프로그램 종료", "진행 중인 작업을 정리하고 종료할까요?", parent=self):
                return
            self.closing = True
            self.cancel.set()
            self.status.set("추출을 정리하고 종료하는 중입니다…")
        else:
            if self.pending and not self.pending_saved and not messagebox.askyesno("프로그램 종료", "저장하지 않은 MP3가 있습니다. 저장하지 않고 종료할까요?", parent=self):
                return
            self.clear_pending()
            self.destroy()


if __name__ == "__main__":
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("YouTubeMP3Extractor")
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    App().mainloop()
