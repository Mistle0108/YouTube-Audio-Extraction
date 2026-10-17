"""Appearance and main-window layout; extraction stays in app.py."""
import customtkinter as ctk
import tkinter as tk
from pathlib import Path
from PIL import Image, ImageDraw, ImageOps, ImageTk

BACKGROUND = "#f5f7fa"
SURFACE = "#ffffff"
TEXT = "#172033"
MUTED = "#7b8496"
BORDER = "#e1e6ed"
BLUE = "#3478f6"
DARK = "#24334b"
FONT = "맑은 고딕"
ctk.set_appearance_mode("light")


class ToggleSwitch(tk.Canvas):
    """A keyboard-operable switch with an inset circular thumb."""
    def __init__(self, parent, variable, command, background=SURFACE):
        super().__init__(parent, width=52, height=30, bg=background, borderwidth=0,
                         highlightthickness=2, highlightbackground=background, highlightcolor=BLUE,
                         takefocus=True, cursor="hand2")
        self.variable = variable
        self.command = command
        self.trace = variable.trace_add("write", self._draw)
        self.bind("<Configure>", self._draw)
        self.bind("<Button-1>", lambda event: self.toggle())
        self.bind("<space>", self._key_toggle)
        self.bind("<Return>", self._key_toggle)
        self._draw()

    def _draw(self, *args):
        self.delete("all")
        border = int(self.cget("highlightthickness"))
        width = self.winfo_width() - 2 * border
        height = self.winfo_height() - 2 * border
        if width < 1 or height < 1:
            width, height = int(self.cget("width")), int(self.cget("height"))

        def render(track, thumb):
            scale = 4
            image = Image.new("RGB", (width * scale, height * scale), self.cget("background"))
            draw = ImageDraw.Draw(image)
            x, y = width * scale / 52, height * scale / 30
            draw.rounded_rectangle((2 * x, 2 * y, 50 * x, 28 * y), radius=13 * min(x, y), fill=track)
            center = 37 if self.variable.get() else 15
            draw.ellipse(((center - 9) * x, 6 * y, (center + 9) * x, 24 * y), fill=thumb)
            return ImageTk.PhotoImage(image.resize((width, height), Image.Resampling.LANCZOS), master=self)

        self.normal_image = render(BLUE if self.variable.get() else "#bfc9d8", SURFACE)
        self.disabled_image = render("#e0e6f0", "#f8fafc")
        self.create_image(0, 0, anchor="nw", image=self.normal_image, disabledimage=self.disabled_image)

    def get(self):
        return self.variable.get()

    def toggle(self):
        if self.cget("state") != "disabled":
            self.variable.set(not self.variable.get())
            self.command()

    def _key_toggle(self, event):
        self.toggle()
        return "break"

    def destroy(self):
        self.variable.trace_remove("write", self.trace)
        super().destroy()


class SmoothRadioButton(tk.Radiobutton):
    """Native radio behavior with antialiased selection indicators."""
    def __init__(self, parent, text, variable, value, command):
        def render(selected):
            scale = 4
            image = Image.new("RGB", (20 * scale, 20 * scale), SURFACE)
            draw = ImageDraw.Draw(image)
            bounds = (scale, scale, 19 * scale, 19 * scale)
            if selected:
                draw.ellipse(bounds, fill=BLUE)
                draw.ellipse((6 * scale, 6 * scale, 14 * scale, 14 * scale), fill=SURFACE)
            else:
                draw.ellipse(bounds, outline="#bac5d5", width=scale)
            return ImageTk.PhotoImage(image.resize((20, 20), Image.Resampling.LANCZOS), master=parent)

        self.off_image = render(False)
        self.on_image = render(True)
        super().__init__(parent, text="  " + text, variable=variable, value=value, command=command,
                         image=self.off_image, selectimage=self.on_image, indicatoron=False, compound="left",
                         font=(FONT, 10), bg=SURFACE, fg=TEXT, activebackground=SURFACE,
                         activeforeground=TEXT, selectcolor=SURFACE, disabledforeground="#99a4b5",
                         borderwidth=0, relief="flat", offrelief="flat", overrelief="flat",
                         highlightthickness=1, highlightbackground=SURFACE, highlightcolor=BLUE,
                         padx=0, pady=0, anchor="w", takefocus=True, cursor="hand2")


def label(parent, text="", *, size=14, bold=False, muted=False, **kwargs):
    kwargs.setdefault("height", 22)
    return ctk.CTkLabel(parent, text=text, anchor="w", font=(FONT, size, "bold" if bold else "normal"),
                        text_color=MUTED if muted else TEXT, **kwargs)


def button(parent, text, command, *, kind="secondary", icon=None, **kwargs):
    color, hover, foreground = {"secondary": (SURFACE, "#eef3f9", TEXT),
                                "primary": (BLUE, "#2467df", SURFACE), "dark": (DARK, "#18273e", SURFACE)}[kind]
    options = dict(height=42, corner_radius=8, border_width=1 if kind == "secondary" else 0,
                   border_color=BORDER, fg_color=color, hover_color=hover, text_color=foreground,
                   text_color_disabled="#99a4b5", font=(FONT, 14))
    options.update(kwargs)
    if icon:
        with Image.open(Path(__file__).resolve().parent / "assets" / "icons" / f"{icon}.png") as source:
            image = source.convert("RGBA")
        bounds = image.getchannel("A").getbbox()
        if bounds:
            image = image.crop(bounds)
        image = ImageOps.contain(image, (128, 128), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (128, 128))
        canvas.paste(image, ((128 - image.width) // 2, (128 - image.height) // 2))
        options["image"] = ctk.CTkImage(light_image=canvas, dark_image=canvas, size=(22, 22))
        options["compound"] = "left"
    return ctk.CTkButton(parent, text=text, command=command, **options)


def entry(parent, variable, *, placeholder="", height=42, **kwargs):
    return ctk.CTkEntry(parent, textvariable=variable, placeholder_text=placeholder, height=height,
                        corner_radius=8, border_width=1, border_color=BORDER, fg_color=SURFACE,
                        text_color=TEXT, placeholder_text_color=MUTED, font=(FONT, 14), **kwargs)


def build_layout(window):
    window.rowconfigure(0, weight=1)
    window.columnconfigure(0, weight=1, minsize=650)
    window.columnconfigure(2, minsize=0)

    body = ctk.CTkFrame(window, corner_radius=0, fg_color=BACKGROUND)
    body.grid(row=0, column=0, sticky="nsew", padx=28, pady=20)
    body.columnconfigure(0, weight=1)
    heading = ctk.CTkFrame(body, fg_color="transparent")
    heading.grid(row=0, column=0, sticky="ew")
    heading.columnconfigure(0, weight=1)
    label(heading, "음원 추출", size=24, bold=True).grid(row=0, column=0, sticky="w")
    label(heading, "메타데이터", size=13).grid(row=0, column=1, padx=(12, 8))
    window.metadata_toggle = ToggleSwitch(heading, window.metadata_visible, window.toggle_metadata, background=BACKGROUND)
    window.metadata_toggle.grid(row=0, column=2, sticky="e")
    label(body, "유튜브 링크를 입력하세요.", muted=True).grid(row=1, column=0, sticky="w", pady=(2, 20))
    label(body, "유튜브 링크", bold=True).grid(row=2, column=0, sticky="w", pady=(0, 7))
    link_row = ctk.CTkFrame(body, fg_color="transparent")
    link_row.grid(row=3, column=0, sticky="ew")
    link_row.columnconfigure(0, weight=1)
    window.link_input = entry(link_row, window.url, placeholder="https://www.youtube.com/watch?v=...")
    window.link_input.grid(row=0, column=0, sticky="ew", padx=(0, 10))
    window.paste_button = button(link_row, "붙여넣기", window.paste, icon="paste", width=110)
    window.paste_button.grid(row=0, column=1)
    folder_heading = ctk.CTkFrame(body, fg_color="transparent")
    folder_heading.grid(row=4, column=0, sticky="ew", pady=(16, 7))
    folder_heading.columnconfigure(0, weight=1)
    label(folder_heading, "저장 위치", bold=True).grid(row=0, column=0, sticky="w")
    window.open_folder_button = button(folder_heading, "폴더 열기", window.open_folder, width=96, height=26,
                                       fg_color=BACKGROUND, border_width=0, text_color=BLUE, font=(FONT, 13))
    window.open_folder_button.grid(row=0, column=1, sticky="e")
    folder_row = ctk.CTkFrame(body, fg_color="transparent")
    folder_row.grid(row=5, column=0, sticky="ew")
    folder_row.columnconfigure(0, weight=1)
    window.folder_input = entry(folder_row, window.folder)
    window.folder_input.grid(row=0, column=0, sticky="ew", padx=(0, 10))
    window.folder_button = button(folder_row, "폴더 선택", window.choose_folder, icon="folder-open", width=110)
    window.folder_button.grid(row=0, column=1)

    options = ctk.CTkFrame(body, corner_radius=10, fg_color=SURFACE, border_width=1, border_color=BORDER)
    options.grid(row=6, column=0, sticky="ew", pady=(20, 0))
    options.columnconfigure(0, weight=1)
    label(options, "자동 저장", size=15, bold=True).grid(row=0, column=0, sticky="w", padx=18, pady=(13, 0))
    window.auto_save_description = label(options, muted=True, size=13)
    window.auto_save_description.grid(row=1, column=0, sticky="w", padx=18, pady=(0, 13))
    window.auto_save_check = ToggleSwitch(options, window.auto_save, window.remember_settings)
    window.auto_save_check.grid(row=0, column=1, rowspan=2, padx=18)
    window.auto_save.trace_add("write", lambda *args: window.update_auto_save_description())
    window.update_auto_save_description()

    body.rowconfigure(7, weight=0, minsize=12)
    window.status_card = ctk.CTkFrame(body, corner_radius=10, fg_color=SURFACE, border_width=1, border_color=BORDER)
    window.status_card.grid(row=8, column=0, sticky="ew")
    window.status_card.columnconfigure(1, weight=1)
    window.status_badge_background = ctk.CTkFrame(window.status_card, width=44, height=44, corner_radius=22, fg_color="#edf3ff")
    window.status_badge_background.grid(row=0, column=0, rowspan=2, padx=(18, 14), pady=(15, 10))
    window.status_badge = label(window.status_badge_background, "↓", size=24, bold=True)
    window.status_badge.configure(anchor="center", text_color=BLUE)
    window.status_badge.place(relx=.5, rely=.5, anchor="center")
    window.status_heading = label(window.status_card, "추출 준비", size=17, bold=True)
    window.status_heading.grid(row=0, column=1, sticky="w", pady=(13, 0), padx=(0, 18))
    window.status_label = label(window.status_card, "링크를 입력한 후 MP3를 추출하세요.", muted=True, size=13, wraplength=470)
    window.status_label.grid(row=1, column=1, sticky="w", padx=(0, 18))
    window.status_card.bind("<Configure>", lambda event: window.status_label.configure(wraplength=max(250, event.width - 110)))
    window.progress = ctk.CTkProgressBar(window.status_card, height=6, corner_radius=3, fg_color="#e9edf5", progress_color=BLUE)
    window.progress.grid(row=2, column=0, columnspan=2, sticky="ew", padx=18, pady=(4, 15))
    window.progress.set(0)

    actions = ctk.CTkFrame(body, fg_color="transparent")
    actions.grid(row=9, column=0, sticky="ew", pady=(14, 0))
    actions.columnconfigure((0, 1), weight=1, uniform="actions")
    window.start_button = button(actions, "MP3 추출", window.start, kind="dark", height=48, font=(FONT, 16, "bold"))
    window.start_button.grid(row=0, column=0, sticky="ew", padx=(0, 7))
    window.save_button = button(actions, "저장", window.save, kind="primary", state="disabled", height=48,
                                fg_color="#e0e6f0", font=(FONT, 16, "bold"))
    window.save_button.grid(row=0, column=1, sticky="ew", padx=(7, 0))
    window.link_input.bind("<Return>", lambda event: window.start() if not window.busy else None)
    window.save_button.bind("<Return>", lambda event: window.save())
    window.link_input.focus_set()
    window.metadata_separator = ctk.CTkFrame(window, width=1, corner_radius=0, fg_color=BORDER)
    window.metadata_separator.grid(row=0, column=1, sticky="ns")
    window.metadata_panel = ctk.CTkFrame(window, width=440, corner_radius=0, fg_color=SURFACE)
    window.metadata_panel.grid(row=0, column=2, sticky="nsew")
    window.metadata_panel.grid_propagate(False)
    window.metadata_panel.columnconfigure(0, weight=1)
    window.metadata_panel.rowconfigure(1, weight=1)
    toolbar = ctk.CTkFrame(window.metadata_panel, fg_color="transparent")
    toolbar.grid(row=0, column=0, sticky="ew", padx=12, pady=(20, 0))
    toolbar.columnconfigure(0, weight=1)
    window.metadata_title = label(toolbar, "메타데이터", size=21, bold=True)
    window.metadata_title.grid(row=0, column=0, sticky="w", padx=(12, 0))
