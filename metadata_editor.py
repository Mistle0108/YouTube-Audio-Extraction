"""Collapsible metadata form and native image-file drop target."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

from PIL import Image, ImageOps, ImageTk
from tkinterdnd2 import COPY, DND_FILES, REFUSE_DROP

from metadata import TrackMetadata, normalize_cover
from ui import SURFACE, MUTED, BORDER, FONT, SmoothRadioButton, button, entry, label


class MetadataEditor(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, corner_radius=0, fg_color=SURFACE, width=440)
        self.columnconfigure(0, weight=1)
        self.fields = {key: tk.StringVar(self) for key in ("title", "artist", "album", "year", "track", "genre")}
        self.source_defaults = {}
        self.cover_mode = tk.StringVar(self, value="thumbnail")
        self.thumbnail = None
        self.custom_cover = None
        self.preview_image = None
        self.busy = False
        self.controls = []

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.grid(row=0, column=0, sticky="nsew", padx=24, pady=(4, 16))
        form.columnconfigure(0, weight=1)
        label(form, "저장할 파일에 적용됩니다.", muted=True, size=13).grid(row=0, column=0, sticky="w", pady=(0, 12))
        label(form, "앨범 커버", bold=True).grid(row=2, column=0, sticky="w", pady=(0, 8))
        cover = ctk.CTkFrame(form, fg_color="transparent")
        cover.grid(row=3, column=0, sticky="ew")
        cover.columnconfigure(1, weight=1)
        slot = ctk.CTkFrame(cover, width=104, height=104, corner_radius=10, fg_color="#f3f6fb", border_width=1, border_color=BORDER)
        slot.grid(row=0, column=0, padx=(0, 16), sticky="n")
        slot.grid_propagate(False)
        self.preview = tk.Label(slot, text="이미지를 여기에\n드래그하세요", bg="#f3f6fb", fg=MUTED,
                                font=(FONT, 9), borderwidth=0, cursor="hand2")
        self.preview.place(x=4, y=4, width=96, height=96)
        self.preview.drop_target_register(DND_FILES)
        self.preview.dnd_bind("<<Drop>>", self.on_drop)
        self.preview.dnd_bind("<<DropEnter>>", lambda event: REFUSE_DROP if self.busy else COPY)
        self.preview.bind("<Button-1>", lambda event: self.choose_image())
        choices = ctk.CTkFrame(cover, fg_color="transparent")
        choices.grid(row=0, column=1, sticky="nw")
        for value, text in (("none", "없음"), ("thumbnail", "유튜브 썸네일"), ("file", "이미지 직접 선택")):
            radio = SmoothRadioButton(choices, text, self.cover_mode, value, self.refresh_cover)
            radio.pack(anchor="w", pady=(0, 2))
            self.controls.append(radio)
        self.image_button = button(choices, "이미지 선택", self.choose_image, icon="image-add", height=30, width=116, font=(FONT, 13))
        self.image_button.pack(anchor="w")
        self.cover_hint = label(form, "이미지 파일을 커버 위에 드래그해도 됩니다.", muted=True, size=12, wraplength=390)
        self.cover_hint.grid(row=4, column=0, sticky="w", pady=(5, 8))

        row = 5
        for key, text, placeholder in (("title", "제목", "영상 제목"), ("artist", "아티스트", "아티스트 입력"), ("album", "앨범", "앨범명 입력")):
            label(form, text, bold=True).grid(row=row, column=0, sticky="w", pady=(0, 4))
            field = entry(form, self.fields[key], placeholder=placeholder, height=34)
            field.grid(row=row + 1, column=0, sticky="ew", pady=(0, 8))
            self.controls.append(field)
            row += 2
        numbers = ctk.CTkFrame(form, fg_color="transparent")
        numbers.grid(row=row, column=0, sticky="ew")
        numbers.columnconfigure((0, 1, 2), weight=1, uniform="numbers")
        for column, key, text, placeholder in ((0, "year", "연도", "YYYY"), (1, "track", "트랙", "1"), (2, "genre", "장르", "장르 입력")):
            padding = (0, 8) if column < 2 else (0, 0)
            label(numbers, text, bold=True).grid(row=0, column=column, sticky="w", pady=(0, 5), padx=padding)
            field = entry(numbers, self.fields[key], placeholder=placeholder, height=36, width=100)
            field.grid(row=1, column=column, sticky="ew", padx=padding)
            self.controls.append(field)
        label(form, "자동 저장 시 추출 전에 정보를 입력하세요.", muted=True, size=12).grid(row=row + 1, column=0, sticky="w", pady=(10, 0))

    def refresh_cover(self):
        mode = self.cover_mode.get()
        data = self.custom_cover if mode == "file" else self.thumbnail if mode == "thumbnail" else None
        if data:
            with Image.open(BytesIO(data)) as image:
                preview = ImageOps.contain(image.convert("RGB"), (96, 96), Image.Resampling.LANCZOS)
                canvas = Image.new("RGB", (96, 96), "#f5f8fc")
                canvas.paste(preview, ((96 - preview.width) // 2, (96 - preview.height) // 2))
            self.preview_image = ImageTk.PhotoImage(canvas, master=self)
            self.preview.configure(image=self.preview_image, text="", width=96, height=96)
        else:
            self.preview_image = None
            self.preview.configure(image="", text="이미지를 여기에\n드래그하세요", width=17, height=7)
        hints = {"none": "커버 없이 저장합니다. 이미지를 드래그하면 적용됩니다.",
                 "thumbnail": "유튜브 썸네일을 커버로 저장합니다." if data else "추출 후 유튜브 썸네일이 표시됩니다.",
                 "file": "선택한 이미지를 커버로 저장합니다." if data else "이미지를 선택하거나 왼쪽 영역에 드래그하세요."}
        self.cover_hint.configure(text=hints[mode])
        self.image_button.configure(state="disabled" if self.busy else "normal")

    def use_image(self, path: Path) -> bool:
        if self.busy:
            return False
        try:
            data = normalize_cover(path.read_bytes())
        except (OSError, ValueError, Image.DecompressionBombError):
            messagebox.showwarning("커버 이미지", "이미지를 읽을 수 없습니다. JPG, PNG, WEBP 등의 이미지 파일을 선택해 주세요.", parent=self.winfo_toplevel())
            return False
        self.custom_cover = data
        self.cover_mode.set("file")
        self.refresh_cover()
        self.cover_hint.configure(text=path.name)
        return True

    def choose_image(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(parent=self.winfo_toplevel(), title="앨범 커버 이미지 선택",
                                          filetypes=[("이미지 파일", "*.jpg *.jpeg *.png *.webp *.bmp *.gif"), ("모든 파일", "*.*")])
        if path:
            self.use_image(Path(path))

    def on_drop(self, event):
        if self.busy:
            return REFUSE_DROP
        paths = self.tk.splitlist(event.data)
        if len(paths) != 1:
            messagebox.showwarning("커버 이미지", "커버 이미지 파일 하나를 드래그해 주세요.", parent=self.winfo_toplevel())
            return REFUSE_DROP
        return COPY if self.use_image(Path(paths[0])) else REFUSE_DROP

    def begin_extract(self):
        self.thumbnail = None
        self.refresh_cover()

    def apply_source(self, source):
        for key, variable in self.fields.items():
            value = str(source.get(key) or "")
            if not variable.get().strip() or variable.get() == self.source_defaults.get(key):
                variable.set(value)
            self.source_defaults[key] = value
        self.thumbnail = source.get("thumbnail")
        self.refresh_cover()

    def snapshot(self, fallback_title: str, require_cover=True) -> TrackMetadata:
        values = {key: value.get().strip() for key, value in self.fields.items()}
        values["title"] = values["title"] or fallback_title
        mode = self.cover_mode.get()
        cover = self.custom_cover if mode == "file" else self.thumbnail if mode == "thumbnail" else None
        if require_cover and mode != "none" and not cover:
            raise ValueError("커버 이미지가 없습니다. 이미지를 선택하거나 커버를 ‘없음’으로 바꿔 주세요.")
        result = TrackMetadata(**values, cover=cover)
        result.validate()
        return result

    def set_busy(self, busy):
        self.busy = busy
        for control in self.controls:
            control.configure(state="disabled" if busy else "normal")
        self.image_button.configure(state="disabled" if busy else "normal")
