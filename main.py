import os
import io
import base64
import threading
from pathlib import Path
import re  # Find the preference summary in feedback text

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser, simpledialog
import tkinter.font as tkfont

from PIL import Image, ImageTk, ImageDraw, ImageFont, ImageColor


from dotenv import load_dotenv
load_dotenv("keys.env")

from openai import OpenAI
client = OpenAI(api_key="OPENAI_API_KEY")



# ----------------------------
# Theme / constants
# ----------------------------
BG = "#12131A"
PANEL = "#1B1E28"
PANEL_2 = "#232735"
TEXT = "#F2F4F8"
MUTED = "#A8B0C0"
ACCENT = "#7C9BFF"
ACCENT_2 = "#5879E8"
BORDER = "#32384A"
ENTRY_BG = "#0E1016"

APP_TITLE = "Motivational Wallpaper Studio"

MODEL_NAME = "gpt-image-1.5"
VARIATION_COUNT = 4

DEVICE_CONFIG = {
    "Phone": {
        "api_size": "1024x1536",
        "export_size": (2160, 3840),
        "ratio_text": "portrait phone wallpaper",
    },
    "Computer": {
        "api_size": "1536x1024",
        "export_size": (3840, 2160),
        "ratio_text": "landscape desktop wallpaper",
    },
}

PRESET_QUOTES = [
    "Discipline will take you places motivation never could.",
    "Small steps every day still move you forward.",
    "You do not need permission to become who you want to be.",
    "Progress is quiet. Keep going.",
    "The life you want is built one decision at a time.",
    "Hard days count too.",
    "You are closer than you think.",
    "Create the future you want to wake up to.",
]

FONT_HINTS = {
    "arial": ["arial.ttf", "arialbd.ttf"],
    "georgia": ["georgia.ttf", "georgiab.ttf"],
    "verdana": ["verdana.ttf", "verdanab.ttf"],
    "timesnewroman": ["times.ttf", "timesbd.ttf", "times new roman.ttf"],
    "tahoma": ["tahoma.ttf", "tahomabd.ttf"],
    "impact": ["impact.ttf"],
    "calibri": ["calibri.ttf", "calibrib.ttf"],
    "cambria": ["cambria.ttc", "cambriab.ttf"],
    "segoeui": ["segoeui.ttf", "segoeuib.ttf"],
    "garamond": ["gara.ttf", "garabd.ttf", "ebgaramond.ttf"],
    "helvetica": ["helvetica.ttf", "arial.ttf"],
}

_FONT_CACHE = {}


# ----------------------------
# Helpers
# ----------------------------
def try_load_env():
    if not load_dotenv:
        return

    # Try the common filenames people usually use.
    possible = [
        Path("keys.env"),
        Path(".env"),
        Path(__file__).with_name("keys.env"),
        Path(__file__).with_name(".env"),
    ]

    seen = set()
    for path in possible:
        path_str = str(path.resolve()) if path.exists() else str(path)
        if path_str in seen:
            continue
        seen.add(path_str)
        try:
            load_dotenv(path, override=False)
        except Exception:
            pass


def get_api_key():
    try_load_env()
    return os.environ.get("OPENAI_API_KEY", "").strip()


def save_api_key_to_file(api_key):
    if not api_key:
        return

    try:
        target = Path(__file__).with_name("keys.env")
        target.write_text(f"OPENAI_API_KEY={api_key}\n", encoding="utf-8")
    except Exception:
        pass


def normalize_name(s):
    return "".join(ch.lower() for ch in s if ch.isalnum())


def common_font_dirs():
    home = Path.home()
    dirs = [
        Path("C:/Windows/Fonts"),
        home / "AppData/Local/Microsoft/Windows/Fonts",
        home / "Library/Fonts",
        Path("/Library/Fonts"),
        Path("/System/Library/Fonts"),
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        home / ".fonts",
    ]
    return [d for d in dirs if d.exists()]


def resolve_font_path(font_family, custom_font_path=None):
    cache_key = (font_family, custom_font_path)
    if cache_key in _FONT_CACHE:
        return _FONT_CACHE[cache_key]

    if custom_font_path and Path(custom_font_path).exists():
        _FONT_CACHE[cache_key] = str(custom_font_path)
        return _FONT_CACHE[cache_key]

    family_norm = normalize_name(font_family)
    hints = FONT_HINTS.get(family_norm, [])

    for directory in common_font_dirs():
        for hint in hints:
            candidate = directory / hint
            if candidate.exists():
                _FONT_CACHE[cache_key] = str(candidate)
                return _FONT_CACHE[cache_key]

    exact = []
    contains = []

    for directory in common_font_dirs():
        for ext in ("*.ttf", "*.otf", "*.ttc"):
            for path in directory.rglob(ext):
                stem_norm = normalize_name(path.stem)
                file_norm = normalize_name(path.name)
                if stem_norm == family_norm or file_norm == family_norm:
                    exact.append(path)
                elif family_norm and family_norm in file_norm:
                    contains.append(path)

    if exact:
        _FONT_CACHE[cache_key] = str(exact[0])
    elif contains:
        _FONT_CACHE[cache_key] = str(contains[0])
    else:
        _FONT_CACHE[cache_key] = None

    return _FONT_CACHE[cache_key]


def get_pil_font(font_family, size, custom_font_path=None):
    resolved = resolve_font_path(font_family, custom_font_path)
    fallback_names = ["DejaVuSans.ttf", "arial.ttf"]

    if resolved:
        try:
            return ImageFont.truetype(resolved, size=size)
        except Exception:
            pass

    for name in fallback_names:
        try:
            return ImageFont.truetype(name, size=size)
        except Exception:
            pass

    return ImageFont.load_default()


def measure_text(draw, text, font, stroke_width=0):
    if not text:
        return 0, 0
    box = draw.multiline_textbbox(
        (0, 0),
        text,
        font=font,
        align="center",
        spacing=max(4, getattr(font, "size", 24) // 4),
        stroke_width=stroke_width,
    )
    return box[2] - box[0], box[3] - box[1]


def wrap_text(draw, text, font, max_width, stroke_width=0):
    words = text.split()
    if not words:
        return ""

    lines = []
    current = words[0]

    for word in words[1:]:
        test = f"{current} {word}"
        w, _ = measure_text(draw, test, font, stroke_width=stroke_width)
        if w <= max_width:
            current = test
        else:
            lines.append(current)
            current = word

    lines.append(current)
    return "\n".join(lines)


def fit_and_crop(image, target_size):
    target_w, target_h = target_size
    scale = max(target_w / image.width, target_h / image.height)
    new_size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
    resized = image.resize(new_size, Image.LANCZOS)

    left = (resized.width - target_w) // 2
    top = (resized.height - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def hex_to_rgb(hex_color):
    return ImageColor.getrgb(hex_color)


def relative_luminance(rgb):
    r, g, b = [x / 255.0 for x in rgb]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def best_stroke_color(fill_hex):
    return "#000000" if relative_luminance(hex_to_rgb(fill_hex)) > 0.58 else "#FFFFFF"


def preview_image(image, max_w, max_h):
    ratio = min(max_w / image.width, max_h / image.height)
    ratio = min(ratio, 1.0)
    size = (max(1, int(image.width * ratio)), max(1, int(image.height * ratio)))
    return image.resize(size, Image.LANCZOS)


def build_generation_prompt(user_description, device_name):
    cfg = DEVICE_CONFIG[device_name]
    return (
        "Create a beautiful, stunning image based on the user's description. "
        "This must be a premium-quality wallpaper background only. "
        "Do not add any text, letters, logos, symbols, captions, signatures, or watermarks. "
        "Make it cinematic, visually striking, polished, elegant, and suitable as a motivational wallpaper. "
        "Keep important visual elements safely away from the edges because text will be placed in the center later "
        "and the image may be slightly cropped for wallpaper export. "
        f"Compose it as a {cfg['ratio_text']}. "
        f"User description: {user_description.strip()}"
    )


def add_centered_quote(image, quote, font_family, fill_color, font_size, custom_font_path=None):
    canvas = image.copy().convert("RGBA")
    draw = ImageDraw.Draw(canvas)

    max_text_width = int(canvas.width * 0.78)
    max_text_height = int(canvas.height * 0.65)
    chosen_size = max(12, int(font_size))
    wrapped = quote
    font = None
    stroke_width = 2

    while chosen_size >= 12:
        font = get_pil_font(font_family, chosen_size, custom_font_path=custom_font_path)
        stroke_width = max(2, chosen_size // 18)
        wrapped = wrap_text(draw, quote, font, max_text_width, stroke_width=stroke_width)
        w, h = measure_text(draw, wrapped, font, stroke_width=stroke_width)
        if w <= max_text_width and h <= max_text_height:
            break
        chosen_size -= 2

    w, h = measure_text(draw, wrapped, font, stroke_width=stroke_width)
    x = (canvas.width - w) // 2
    y = (canvas.height - h) // 2

    draw.multiline_text(
        (x, y),
        wrapped,
        font=font,
        fill=fill_color,
        align="center",
        spacing=max(4, chosen_size // 4),
        stroke_width=stroke_width,
        stroke_fill=best_stroke_color(fill_color),
    )
    return canvas.convert("RGB")


class WallpaperApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1400x900")
        self.minsize(1200, 780)
        self.configure(bg=BG)

        self.client = None
        self.generated_images = []
        self.selected_index = None
        self.thumb_refs = []
        self.preview_ref = None
        self.custom_font_path = None

        self.device_var = tk.StringVar(value="Phone")
        self.quote_var = tk.StringVar(value=PRESET_QUOTES[0])
        self.font_family_var = tk.StringVar(value="Arial")
        self.font_size_var = tk.IntVar(value=92)
        self.font_color_var = tk.StringVar(value="#FFFFFF")
        self.custom_font_label_var = tk.StringVar(value="No custom font selected")
        self.status_var = tk.StringVar(value="Enter a description and click Generate.")
        self.progress_var = tk.StringVar(value="")
        self.generating = False

        self._build_ui()
        self._refresh_font_list()
        self.preview_holder.bind("<Configure>", lambda e: self._update_preview())
        self._update_preview()

    def _build_ui(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        left = tk.Frame(self, bg=PANEL, bd=0, highlightthickness=1, highlightbackground=BORDER)
        left.grid(row=0, column=0, sticky="nsw", padx=(16, 8), pady=16)
        left.configure(width=420)
        left.grid_propagate(False)

        right = tk.Frame(self, bg=PANEL, bd=0, highlightthickness=1, highlightbackground=BORDER)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 16), pady=16)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        title = tk.Label(left, text=APP_TITLE, bg=PANEL, fg=TEXT, font=("Segoe UI", 20, "bold"))
        title.pack(anchor="w", padx=18, pady=(16, 8))

        subtitle = tk.Label(
            left,
            text="Generate a wallpaper, choose a quote, style it, then save as PNG.",
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 10),
            wraplength=380,
            justify="left",
        )
        subtitle.pack(anchor="w", padx=18, pady=(0, 16))

        self._section_label(left, "0) Format")
        format_frame = tk.Frame(left, bg=PANEL)
        format_frame.pack(fill="x", padx=18, pady=(0, 12))

        ttk.Radiobutton(
            format_frame,
            text="Phone",
            value="Phone",
            variable=self.device_var,
            command=self._update_preview,
        ).pack(side="left", padx=(0, 16))
        ttk.Radiobutton(
            format_frame,
            text="Computer",
            value="Computer",
            variable=self.device_var,
            command=self._update_preview,
        ).pack(side="left")

        self._section_label(left, "1) Describe the wallpaper background")
        self.prompt_text = tk.Text(
            left,
            height=8,
            wrap="word",
            bg=ENTRY_BG,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            padx=10,
            pady=10,
            font=("Segoe UI", 10),
        )
        self.prompt_text.pack(fill="x", padx=18, pady=(0, 12))

        self.generate_btn = tk.Button(
            left,
            text="Generate 4 Variations",
            command=self.start_generate,
            bg=ACCENT,
            fg="white",
            activebackground=ACCENT_2,
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=10,
            pady=10,
            font=("Segoe UI", 11, "bold"),
            cursor="hand2",
        )
        self.generate_btn.pack(fill="x", padx=18, pady=(0, 8))

        tk.Label(left, textvariable=self.progress_var, bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(
            anchor="w", padx=18, pady=(0, 14)
        )

        self._section_label(left, "3) Pick a motivational quote")
        quote_combo = ttk.Combobox(left, textvariable=self.quote_var, values=PRESET_QUOTES, state="readonly")
        quote_combo.pack(fill="x", padx=18, pady=(0, 12))
        quote_combo.bind("<<ComboboxSelected>>", lambda e: self._update_preview())

        self._section_label(left, "4) Quote styling")
        style_wrap = tk.Frame(left, bg=PANEL)
        style_wrap.pack(fill="x", padx=18, pady=(0, 10))
        style_wrap.columnconfigure(0, weight=1)
        style_wrap.columnconfigure(1, weight=1)

        tk.Label(style_wrap, text="Font family", bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
        tk.Label(style_wrap, text="Font size", bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).grid(
            row=0, column=1, sticky="w", padx=(12, 0), pady=(0, 4)
        )

        self.font_combo = ttk.Combobox(style_wrap, textvariable=self.font_family_var, state="readonly")
        self.font_combo.grid(row=1, column=0, sticky="ew")
        self.font_combo.bind("<<ComboboxSelected>>", lambda e: self._update_preview())

        size_spin = ttk.Spinbox(
            style_wrap,
            from_=24,
            to=240,
            textvariable=self.font_size_var,
            width=8,
            command=self._update_preview,
        )
        size_spin.grid(row=1, column=1, sticky="ew", padx=(12, 0))
        size_spin.bind("<KeyRelease>", lambda e: self._update_preview())

        font_file_row = tk.Frame(left, bg=PANEL)
        font_file_row.pack(fill="x", padx=18, pady=(8, 4))
        tk.Button(
            font_file_row,
            text="Load Custom Font (.ttf/.otf)",
            command=self.pick_custom_font,
            bg=PANEL_2,
            fg=TEXT,
            activebackground="#2B3142",
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            padx=10,
            pady=8,
            cursor="hand2",
        ).pack(side="left")
        tk.Label(
            font_file_row,
            textvariable=self.custom_font_label_var,
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 8),
        ).pack(side="left", padx=(8, 0))

        color_row = tk.Frame(left, bg=PANEL)
        color_row.pack(fill="x", padx=18, pady=(8, 16))
        tk.Label(color_row, text="Color", bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(side="left")
        self.color_preview = tk.Label(color_row, bg=self.font_color_var.get(), width=3, height=1, relief="flat")
        self.color_preview.pack(side="left", padx=(8, 8))
        tk.Button(
            color_row,
            text="Choose Color",
            command=self.choose_color,
            bg=PANEL_2,
            fg=TEXT,
            activebackground="#2B3142",
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            padx=10,
            pady=8,
            cursor="hand2",
        ).pack(side="left")

        self._section_label(left, "6) Save")
        tk.Button(
            left,
            text="SAVE PNG",
            command=self.save_png,
            bg="#22A36A",
            fg="white",
            activebackground="#1D8C5A",
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=10,
            pady=11,
            font=("Segoe UI", 11, "bold"),
            cursor="hand2",
        ).pack(fill="x", padx=18, pady=(0, 8))

        tk.Label(
            left,
            textvariable=self.status_var,
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 9),
            wraplength=380,
            justify="left",
        ).pack(anchor="w", padx=18, pady=(0, 16))

        topbar = tk.Frame(right, bg=PANEL)
        topbar.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        topbar.columnconfigure(0, weight=1)

        tk.Label(topbar, text="Wallpaper Preview", bg=PANEL, fg=TEXT, font=("Segoe UI", 16, "bold")).grid(
            row=0, column=0, sticky="w"
        )

        self.preview_holder = tk.Label(
            right,
            bg=ENTRY_BG,
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER,
            anchor="center",
        )
        self.preview_holder.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 12))

        thumbs_wrap = tk.Frame(right, bg=PANEL)
        thumbs_wrap.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 16))
        for i in range(4):
            thumbs_wrap.columnconfigure(i, weight=1)

        self.thumb_buttons = []
        for i in range(4):
            btn = tk.Button(
                thumbs_wrap,
                text=f"Variation {i + 1}",
                command=lambda idx=i: self.select_image(idx),
                bg=PANEL_2,
                fg=TEXT,
                activebackground="#2B3142",
                activeforeground=TEXT,
                relief="flat",
                bd=0,
                width=20,
                height=10,
                compound="top",
                cursor="hand2",
                wraplength=180,
                highlightthickness=1,
                highlightbackground=BORDER,
            )
            btn.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 8, 0))
            self.thumb_buttons.append(btn)

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TCombobox", fieldbackground=ENTRY_BG, background=PANEL_2, foreground=TEXT)
        style.configure("TSpinbox", fieldbackground=ENTRY_BG, background=PANEL_2, foreground=TEXT)
        style.configure("TRadiobutton", background=PANEL, foreground=TEXT)

    def _section_label(self, parent, text):
        lbl = tk.Label(parent, text=text, bg=PANEL, fg=TEXT, font=("Segoe UI", 11, "bold"))
        lbl.pack(anchor="w", padx=18, pady=(0, 6))
        return lbl

    def _refresh_font_list(self):
        families = sorted(set(tkfont.families()))
        preferred = [
            "Arial", "Georgia", "Verdana", "Tahoma", "Times New Roman",
            "Calibri", "Cambria", "Segoe UI", "Impact"
        ]
        available = [f for f in preferred if f in families]
        remaining = [f for f in families if f not in available]
        final = available + remaining if (available + remaining) else ["Arial"]

        self.font_combo["values"] = final
        if self.font_family_var.get() not in final:
            self.font_family_var.set(final[0])

    def pick_custom_font(self):
        path = filedialog.askopenfilename(
            title="Choose a font file",
            filetypes=[("Font files", "*.ttf *.otf *.ttc"), ("All files", "*.*")]
        )
        if path:
            self.custom_font_path = path
            self.custom_font_label_var.set(Path(path).name)
            self._update_preview()

    def choose_color(self):
        chosen = colorchooser.askcolor(color=self.font_color_var.get(), title="Choose quote color")
        if chosen and chosen[1]:
            self.font_color_var.set(chosen[1])
            self.color_preview.configure(bg=chosen[1])
            self._update_preview()

    def current_export_size(self):
        return DEVICE_CONFIG[self.device_var.get()]["export_size"]

    def current_api_size(self):
        return DEVICE_CONFIG[self.device_var.get()]["api_size"]

    def select_image(self, index):
        if 0 <= index < len(self.generated_images):
            self.selected_index = index
            self.status_var.set(f"Selected variation {index + 1}.")
            self._highlight_selected_thumb()
            self._update_preview()

    def _highlight_selected_thumb(self):
        for i, btn in enumerate(self.thumb_buttons):
            if i == self.selected_index:
                btn.configure(highlightthickness=2, highlightbackground=ACCENT, highlightcolor=ACCENT)
            else:
                btn.configure(highlightthickness=1, highlightbackground=BORDER, highlightcolor=BORDER)

    def _composed_export_image(self):
        if self.selected_index is None or not self.generated_images:
            return None

        base = self.generated_images[self.selected_index]
        export_base = fit_and_crop(base, self.current_export_size())
        quote = self.quote_var.get().strip()

        if quote:
            return add_centered_quote(
                export_base,
                quote=quote,
                font_family=self.font_family_var.get(),
                fill_color=self.font_color_var.get(),
                font_size=self.font_size_var.get(),
                custom_font_path=self.custom_font_path,
            )
        return export_base

    def _update_preview(self):
        preview_area_w = max(500, self.preview_holder.winfo_width() - 20)
        preview_area_h = max(360, self.preview_holder.winfo_height() - 20)

        image = self._composed_export_image()
        if image is None:
            placeholder = Image.new("RGB", (1000, 600), "#10131B")
            draw = ImageDraw.Draw(placeholder)
            msg = "Generate images and select one to preview it here."
            font = get_pil_font(self.font_family_var.get(), 32, self.custom_font_path)
            w, h = measure_text(draw, msg, font)
            draw.text(
                ((placeholder.width - w) / 2, (placeholder.height - h) / 2),
                msg,
                fill="#B8C0D4",
                font=font,
            )
            image = placeholder

        shown = preview_image(image, preview_area_w, preview_area_h)
        self.preview_ref = ImageTk.PhotoImage(shown)
        self.preview_holder.configure(image=self.preview_ref)

    def start_generate(self):
        if self.generating:
            return

        prompt = self.prompt_text.get("1.0", "end").strip()
        if not prompt:
            messagebox.showwarning("Missing description", "Please describe the wallpaper you want first.")
            return

        api_key = get_api_key()
        if not api_key:
            api_key = simpledialog.askstring(
                "OpenAI API key",
                "Paste your OpenAI API key:",
                show="*",
                parent=self,
            )

            if not api_key:
                messagebox.showerror(
                    "Missing API key",
                    "No API key was entered."
                )
                return

            api_key = api_key.strip()

            if messagebox.askyesno(
                "Save API key",
                "Save this key to keys.env in the same folder as the script for future launches?"
            ):
                save_api_key_to_file(api_key)

        self.client = OpenAI(api_key=api_key)
        self.generating = True
        self.generate_btn.configure(state="disabled")
        self.progress_var.set("Generating 4 image variations...")
        self.status_var.set("Talking to the image model...")
        self.generated_images = []
        self.selected_index = None
        self._highlight_selected_thumb()
        self._clear_thumbnails()
        self._update_preview()

        threading.Thread(target=self._generate_worker, args=(prompt,), daemon=True).start()

    def _generate_worker(self, user_prompt):
        try:
            response = self.client.images.generate(
                model=MODEL_NAME,
                prompt=build_generation_prompt(user_prompt, self.device_var.get()),
                n=VARIATION_COUNT,
                size=self.current_api_size(),
                quality="high",
                output_format="png",
            )

            images = []
            for item in response.data:
                raw = base64.b64decode(item.b64_json)
                img = Image.open(io.BytesIO(raw)).convert("RGB")
                images.append(img)

            self.after(0, lambda: self._on_generate_success(images))

        except Exception as exc:
            self.after(0, lambda: self._on_generate_error(exc))

    def _on_generate_success(self, images):
        self.generating = False
        self.generate_btn.configure(state="normal")
        self.progress_var.set("")
        self.generated_images = images
        self.selected_index = 0 if images else None
        self._populate_thumbnails()
        self._highlight_selected_thumb()
        self._update_preview()

        if images:
            self.status_var.set("Done. Pick the variation you like, adjust the quote styling, then save.")
        else:
            self.status_var.set("No images were returned.")

    def _on_generate_error(self, exc):
        self.generating = False
        self.generate_btn.configure(state="normal")
        self.progress_var.set("")
        self.status_var.set("Generation failed.")
        messagebox.showerror("Generation failed", str(exc))

    def _clear_thumbnails(self):
        self.thumb_refs = []
        for i, btn in enumerate(self.thumb_buttons):
            btn.configure(image="", text=f"Variation {i + 1}")

    def _populate_thumbnails(self):
        self.thumb_refs = []
        for i, btn in enumerate(self.thumb_buttons):
            if i < len(self.generated_images):
                thumb = preview_image(self.generated_images[i], 210, 120)
                ref = ImageTk.PhotoImage(thumb)
                self.thumb_refs.append(ref)
                btn.configure(image=ref, text=f"Variation {i + 1}")
            else:
                btn.configure(image="", text=f"Variation {i + 1}")

    def save_png(self):
        composed = self._composed_export_image()
        if composed is None:
            messagebox.showwarning("Nothing to save", "Generate images and select one first.")
            return

        default_name = f"motivational_wallpaper_{self.device_var.get().lower()}.png"
        path = filedialog.asksaveasfilename(
            title="Save wallpaper",
            defaultextension=".png",
            initialfile=default_name,
            filetypes=[("PNG image", "*.png")],
        )
        if not path:
            return

        try:
            if not path.lower().endswith(".png"):
                path += ".png"
            composed.save(path, format="PNG")
            self.status_var.set(f"Saved: {path}")
            messagebox.showinfo("Saved", f"Wallpaper saved successfully:\n{path}")
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc))


if __name__ == "__main__":
    app = WallpaperApp()
    app.mainloop()
