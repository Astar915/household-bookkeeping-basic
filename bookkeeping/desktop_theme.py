"""Shared native desktop appearance, aligned with the mobile application's palette.

Only presentation lives here. Appearance changes recolor existing controls;
open financial forms are never rebuilt or interrupted.
"""
from __future__ import annotations

import os
import base64
import math
import struct
import zlib
from .appearance import load_appearance
import tkinter as tk
from tkinter import ttk
from .desktop_frame import defer_during_interactive_resize


def system_dark_mode() -> bool:
    override = os.environ.get("HOUSEHOLD_BOOKKEEPING_APPEARANCE", "").lower()
    if override in {"light", "dark"}:
        return override == "dark"
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except (ImportError, OSError):
        return False


APPEARANCE_MODE = load_appearance()
DARK = system_dark_mode() if APPEARANCE_MODE == "system" else APPEARANCE_MODE == "dark"

def make_palette(dark: bool) -> dict[str, str]:
    DARK = dark
    return {
    "background": "#11131b" if DARK else "#f5f6fa",
    "surface": "#1d202c" if DARK else "#ffffff",
    "text": "#edf0f8" if DARK else "#192438",
    "muted": "#a1acc1" if DARK else "#68768d",
    "border": "#353c50" if DARK else "#e3e8f1",
    "accent": "#64a8ff" if DARK else "#007aff",
    "selected": "#273b5a" if DARK else "#eaf2ff",
    "table_selected": "#3b354c" if DARK else "#eeeaf6",
    "table_stripe": "#242732" if DARK else "#f5f6f8",
    "hover": "#292e3f" if DARK else "#eef2f9",
    "favorite_hover": "#292e3f" if DARK else "#f0f2f6",
    "favorite_remove_text": "#ff8c96" if DARK else "#d92d20",
    "hero": "#152645" if DARK else "#182e55",
    "income": "#6bc9a9" if DARK else "#168363",
    "expense": "#ee8890" if DARK else "#d85863",
}

PALETTE = make_palette(DARK)

_PIL_TK_MODE: str | None = None


def pillow_photo_image(image, master=None):
    """Create a Tk photo, bypassing Pillow's blocked _imagingtk bridge when needed."""
    global _PIL_TK_MODE
    if _PIL_TK_MODE != "native-png":
        try:
            from PIL import ImageTk
            photo = ImageTk.PhotoImage(image, master=master)
            _PIL_TK_MODE = "pillow"
            return photo
        except Exception:
            # Windows may block Pillow's optional _imagingtk DLL even though
            # Pillow can still render and Tk can still load PNG files itself.
            _PIL_TK_MODE = "native-png"
    try:
        from io import BytesIO
        stream = BytesIO()
        image.save(stream, format="PNG")
        encoded = base64.b64encode(stream.getvalue()).decode("ascii")
        return tk.PhotoImage(master=master, data=encoded, format="png")
    except Exception:
        _PIL_TK_MODE = "unavailable"
        return None


def pillow_photo_available() -> bool:
    return _PIL_TK_MODE != "unavailable"


def color(value: str) -> str:
    """Translate legacy presentation colors without changing financial values."""
    value = value.lower()
    groups = {
        "background": {"#f3f5f8", "#f2f4f7"},
        "surface": {"#ffffff"},
        "text": {"#182230", "#101828", "#344054", "#1d2939"},
        "muted": {"#667085", "#475467", "#98a2b3", "#728096"},
        "border": {"#d0d5dd", "#e4e7ec", "#e6eaf0"},
        "accent": {"#175cd3", "#1849a9", "#84adff", "#3976b8", "#173b63"},
        "selected": {"#eff4ff", "#eaf2ff"},
        "table_stripe": {"#edf5ff"},
    }
    for role, values in groups.items():
        if value in values:
            return PALETTE[role]
    if DARK:
        return {
            "#039855": "#66d6ad", "#16803c": "#66d6ad",
            "#c62828": "#ff8c96", "#d92d20": "#ff8c96",
            "#b54708": "#f5ba71",
        }.get(value, value)
    return value


def _round_check_indicator_png(accent: str, outline: str, *, selected: bool) -> str:
    """Build a small antialiased PNG indicator without adding an image dependency."""
    width = height = 20
    supersample = 4
    center = width / 2
    outer_radius = 8.0
    inner_radius = 6.35
    dot_radius = 3.15
    accent_rgb = tuple(int(accent[index:index + 2], 16) for index in (1, 3, 5))
    outline_rgb = tuple(int(outline[index:index + 2], 16) for index in (1, 3, 5))
    rows = bytearray()

    for y in range(height):
        rows.append(0)  # PNG filter: None
        for x in range(width):
            red = green = blue = alpha = 0
            for sy in range(supersample):
                sample_y = y + (sy + 0.5) / supersample - center
                for sx in range(supersample):
                    sample_x = x + (sx + 0.5) / supersample - center
                    radius = math.hypot(sample_x, sample_y)
                    sample_color = None
                    if selected and radius <= dot_radius:
                        sample_color = accent_rgb
                    elif inner_radius <= radius <= outer_radius:
                        sample_color = accent_rgb if selected else outline_rgb
                    if sample_color is not None:
                        red += sample_color[0]
                        green += sample_color[1]
                        blue += sample_color[2]
                        alpha += 255
            samples = supersample * supersample
            if alpha:
                covered = alpha / 255
                rows.extend((
                    round(red / covered),
                    round(green / covered),
                    round(blue / covered),
                    round(alpha / samples),
                ))
            else:
                rows.extend((0, 0, 0, 0))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">2I5B", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(rows), 9))
        + chunk(b"IEND", b"")
    )
    return base64.b64encode(png).decode("ascii")


def _configure_round_checkbutton(root: tk.Misc, style: ttk.Style) -> None:
    """Replace every ttk checkbox square with a consistent circular indicator."""
    palette = PALETTE
    dark = DARK
    element_name = f"RoundCheckbutton{int(dark)}.indicator"
    image_cache = getattr(root, "_bk_round_checkbutton_images", None)
    if image_cache is None:
        image_cache = {}
        root._bk_round_checkbutton_images = image_cache

    if element_name not in image_cache:
        unchecked = tk.PhotoImage(
            master=root,
            data=_round_check_indicator_png(palette["muted"], palette["border"], selected=False),
            format="png",
        )
        checked = tk.PhotoImage(
            master=root,
            data=_round_check_indicator_png(palette["accent"], palette["border"], selected=True),
            format="png",
        )
        disabled_outline = palette["border"]
        disabled_accent = palette["muted"]
        disabled_unchecked = tk.PhotoImage(
            master=root,
            data=_round_check_indicator_png(disabled_outline, disabled_outline, selected=False),
            format="png",
        )
        disabled_checked = tk.PhotoImage(
            master=root,
            data=_round_check_indicator_png(disabled_accent, disabled_outline, selected=True),
            format="png",
        )
        image_cache[element_name] = (unchecked, checked, disabled_unchecked, disabled_checked)

    unchecked, checked, disabled_unchecked, disabled_checked = image_cache[element_name]
    try:
        style.element_create(
            element_name,
            "image",
            unchecked,
            ("disabled", "selected", disabled_checked),
            ("disabled", disabled_unchecked),
            ("selected", checked),
            sticky="",
        )
    except tk.TclError:
        # The themed element already exists when appearance settings are reapplied.
        pass

    def replace_indicator(layout: list[tuple[str, dict]]) -> list[tuple[str, dict]]:
        updated = []
        for element, options in layout:
            options = dict(options)
            if "children" in options:
                options["children"] = replace_indicator(options["children"])
            if element == "Checkbutton.indicator" or (
                element.startswith("RoundCheckbutton") and element.endswith(".indicator")
            ):
                element = element_name
            updated.append((element, options))
        return updated

    layout = replace_indicator(style.layout("TCheckbutton"))
    if layout != style.layout("TCheckbutton"):
        style.layout("TCheckbutton", layout)


def configure_styles(root: tk.Misc, family: str) -> None:
    """Use a deterministic ttk theme rather than Windows' uncolorable buttons."""
    p = PALETTE
    s = ttk.Style(root)
    if s.theme_use() != "clam":
        s.theme_use("clam")
    s.configure(".", font=(family, 10), background=p["background"], foreground=p["text"],
                bordercolor=p["border"], lightcolor=p["border"], darkcolor=p["border"])
    s.configure("TFrame", background=p["background"])
    s.configure("TLabel", background=p["background"], foreground=p["text"])
    s.configure("TButton", padding=(12, 6), background=p["surface"], foreground=p["text"],
                borderwidth=1, relief="flat", focusthickness=2, focuscolor=p["accent"])
    s.map("TButton", background=[("disabled", p["background"]), ("pressed", p["selected"]),
                                 ("active", p["hover"])],
          foreground=[("disabled", p["muted"])])
    s.configure("Send.TButton", font=(family, 11, "bold"), padding=(20, 12),
                background="#1664df", foreground="#ffffff", borderwidth=0)
    s.map("Send.TButton", background=[("disabled", p["border"]), ("pressed", "#124eae"),
                                      ("active", "#2877f1")],
          foreground=[("disabled", p["muted"]), ("!disabled", "#ffffff")])
    s.configure("Settings.TButton", padding=(10, 5))
    s.configure("HeaderPrimary.TButton", font=(family, 10, "bold"), padding=(16, 9), foreground="#ffffff")
    s.map("HeaderPrimary.TButton", foreground=[("!disabled", "#ffffff")])
    for name in ("TEntry", "TCombobox", "TSpinbox"):
        s.configure(name, padding=(8, 5), fieldbackground=p["surface"],
                    foreground=p["text"], insertcolor=p["text"], arrowsize=13)
        s.map(name, fieldbackground=[("readonly", p["surface"]), ("disabled", p["background"])],
              foreground=[("disabled", p["muted"]), ("readonly", p["text"])],
              bordercolor=[("focus", p["accent"])], selectbackground=[("!disabled", p["selected"])],
              selectforeground=[("!disabled", p["text"])])
    for name in ("TCheckbutton", "TRadiobutton"):
        s.configure(name, padding=(3, 5), indicatorbackground=p["surface"])
        s.map(name, background=[("active", p["hover"])],
              foreground=[("disabled", p["muted"])],
              indicatorbackground=[("selected", p["accent"])])
    _configure_round_checkbutton(root, s)
    s.configure("TNotebook", background=p["background"], borderwidth=0, tabmargins=(0, 6, 0, 12))
    s.configure("TNotebook.Tab", padding=(14, 7), background=p["background"], borderwidth=0)
    s.map("TNotebook.Tab", background=[("selected", p["surface"]), ("active", p["hover"])],
          foreground=[("selected", p["accent"])])
    s.configure("Treeview", background=p["surface"], fieldbackground=p["surface"],
                foreground=p["text"], rowheight=29, borderwidth=0)
    s.map("Treeview", background=[("selected", p["table_selected"])],
          foreground=[("selected", p["text"])])
    if not getattr(root, "_bk_treeview_selection_tint_bound", False):
        selection_tag = "__bk_table_selected__"

        def tint_selected_rows(event: tk.Event) -> None:
            tree = event.widget
            if not isinstance(tree, ttk.Treeview):
                return
            try:
                tree.tag_configure(selection_tag, background=PALETTE["table_selected"])
                selected = set(tree.selection())

                def visit(parent: str = "") -> None:
                    for item_id in tree.get_children(parent):
                        tags = tuple(tree.item(item_id, "tags") or ())
                        has_tint = selection_tag in tags
                        should_tint = item_id in selected
                        if should_tint and not has_tint:
                            tree.item(item_id, tags=(*tags, selection_tag))
                        elif has_tint and not should_tint:
                            tree.item(item_id, tags=tuple(tag for tag in tags if tag != selection_tag))
                        visit(item_id)

                visit()
            except tk.TclError:
                pass

        root.bind_class("Treeview", "<<TreeviewSelect>>", tint_selected_rows, add="+")
        root._bk_treeview_selection_tint_bound = True
    s.configure("Treeview.Heading", font=(family, 10, "bold"), background=p["background"],
                foreground=p["muted"], padding=(12, 10), relief="flat")
    s.map("Treeview.Heading", background=[("active", p["hover"])])
    for orient in ("Vertical", "Horizontal"):
        s.configure(f"{orient}.TScrollbar", background=p["border"], troughcolor=p["background"],
                    borderwidth=0, arrowsize=10, relief="flat", arrowcolor=p["muted"])
        s.map(f"{orient}.TScrollbar", background=[("active", p["muted"]), ("!active", p["border"])])
    s.configure("Budget.Horizontal.TProgressbar", thickness=7, borderwidth=0, background=p["accent"], troughcolor=p["selected"], bordercolor=p["selected"], lightcolor=p["selected"], darkcolor=p["selected"])
    s.configure("TProgressbar", background=p["accent"], troughcolor=p["selected"], borderwidth=0,
                thickness=4)
    s.configure("TLabelframe", background=p["background"], bordercolor=p["border"], relief="flat")
    s.configure("TLabelframe.Label", foreground=p["muted"], background=p["background"])
    for name, role in (("App", "background"), ("Surface", "surface")):
        s.configure(f"{name}.TFrame", background=p[role])
    s.configure("Title.TLabel", background=p["background"], foreground=p["text"],
                font=(family, 24, "bold"))
    s.configure("ManagementTitle.TLabel", background=p["background"], foreground=p["text"], font=(family, 18, "bold"))
    s.configure("ManagementSection.TLabel", background=p["background"], foreground=p["text"], font=(family, 12, "bold"))
    s.configure("Hint.TLabel", background=p["background"], foreground=p["muted"], font=(family, 10))
    s.configure("SurfaceHint.TLabel", background=p["surface"], foreground=p["muted"], font=(family, 10))
    s.configure("Status.TLabel", background=p["background"], foreground=p["accent"], font=(family, 10))
    s.configure("Nav.TButton", background=p["background"], borderwidth=0, anchor="w", padding=(14, 11))
    s.configure("Hero.TLabel", background=p["hero"], foreground="#ffffff", font=(family, 23, "bold"))
    s.configure("HeroHint.TLabel", background=p["hero"], foreground="#b8cce8", font=(family, 10))
    s.configure("Agent.TButton", padding=(16, 12), anchor="w", font=(family, 11, "bold"))
    s.configure("Selected.Agent.TButton", background=p["selected"], foreground=p["accent"])
    s.map("Selected.Agent.TButton", background=[("active", p["selected"]), ("!active", p["selected"])],
          foreground=[("disabled", p["muted"]), ("!disabled", p["accent"])])
    for name, role, size, bold in (
        ("SettingsTitle", "text", 20, True), ("SettingsSection", "text", 11, True),
        ("SettingsPath", "muted", 10, False), ("SettingsHint", "muted", 10, False),
        ("SettingsStatus", "accent", 10, True),
    ):
        s.configure(name+".TLabel", background=p["surface"], foreground=p[role],
                    font=(family, size, "bold") if bold else (family, size))
    s.configure("SettingsPanel.TFrame", background=p["surface"])
    s.configure("CaptionIcon.TLabel", background=p["surface"], foreground=p["muted"],
                padding=(6, 6), font=(family, 12), anchor="center")
    s.configure("CaptionIconHover.TLabel", background=p["hover"], foreground=p["text"],
                padding=(6, 6), font=(family, 12), anchor="center")
    s.configure("CaptionCloseHover.TLabel", background="#c42b3a", foreground="#ffffff",
                padding=(6, 6), font=(family, 12), anchor="center")
    s.configure("Brand.TLabel", background=p["surface"], foreground=p["text"], font=(family, 14, "bold"))
    s.configure("BrandIcon.TLabel", background="#007aff", foreground="#ffffff", font=(family, 17, "bold"), padding=5)
    s.configure("Local.TLabel", background=p["surface"], foreground=p["income"], font=(family, 9))
    s.configure("Soft.TButton", background=p["selected"], foreground=p["accent"], padding=(12, 6))
    s.configure("Circle.TButton", padding=(10, 10), font=(family, 14))
    s.configure("Dock.TButton", padding=(10, 9), anchor="w", font=(family, 10), foreground=p["muted"])
    s.configure("Selected.Dock.TButton", padding=(10, 9), anchor="w", font=(family, 10, "bold"), foreground=p["accent"])
    s.map("Selected.Dock.TButton", foreground=[("!disabled", p["accent"])])
    s.configure("FavoriteAdd.TButton", padding=(3, 1), font=(family, 11, "bold"),
                foreground=p["accent"], background=p["surface"], borderwidth=0)
    s.map("FavoriteAdd.TButton", background=[("active", p["selected"]), ("!active", p["surface"])])
    s.configure("HeroPrimary.TButton", padding=(12, 9), font=(family, 10, "bold"), foreground="#203b60")
    s.map("HeroPrimary.TButton", foreground=[("!disabled", "#203b60")])
    s.configure("HeroSecondary.TButton", padding=(12, 9), font=(family, 10, "bold"), foreground="#ffffff")
    s.map("HeroSecondary.TButton", foreground=[("!disabled", "#ffffff")])
    _rounded_button_styles(root, s)
    root.option_add("*Text.background", p["surface"])
    root.option_add("*Text.foreground", p["text"])
    root.option_add("*Text.insertBackground", p["text"])
    root.option_add("*Text.selectBackground", p["selected"])
    root.option_add("*Text.selectForeground", p["text"])
    root.option_add("*Listbox.background", p["surface"])
    root.option_add("*Listbox.foreground", p["text"])
    root.option_add("*Listbox.selectBackground", p["selected"])
    root.option_add("*Listbox.selectForeground", p["text"])


class RoundedPanel(tk.Frame):
    """Native card with antialiased corners when Pillow is available.

    Content uses regular Tk widgets, retaining keyboard, focus, selection and
    existing scroll bindings. No image is generated on scroll or on keypress.
    """
    def __init__(self, master: tk.Misc, *, padding: int = 18, radius: int = 22,
                 surface: str | None = None, **kwargs):
        super().__init__(master, bg=PALETTE["background"], bd=0, **kwargs)
        self.surface = surface or PALETTE["surface"]
        self.padding, self.radius = padding, radius
        self.canvas = tk.Canvas(self, bg=PALETTE["background"], bd=0, highlightthickness=0)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.body = tk.Frame(self, bg=self.surface, bd=0)
        self.body.place(x=padding, y=padding, relwidth=1, relheight=1,
                        width=-2*padding, height=-2*padding)
        self.body.bind("<Configure>", self._request_height, add="+")
        self.bind("<Configure>", self._paint, add="+")
        self._image = None
        self._size = None

    def _request_height(self, _event=None):
        if not self.winfo_exists():
            return
        if defer_during_interactive_resize(
                self, (self, "rounded-panel-height"), self._request_height):
            return
        wanted = self.body.winfo_reqheight() + 2*self.padding
        if int(self.cget("height")) != wanted:
            self.configure(height=wanted)

    def _paint(self, event):
        if getattr(self, "_paint_pending", None) is not None:
            self.after_cancel(self._paint_pending)
            self._paint_pending = None
        if defer_during_interactive_resize(
                self, (self, "rounded-panel-paint"), self._render):
            return
        self._paint_pending = self.after(16, self._render)

    def _render(self):
        self._paint_pending = None
        if not self.winfo_exists():
            return
        if defer_during_interactive_resize(
                self, (self, "rounded-panel-paint"), self._render):
            return
        size = (self.winfo_width(), self.winfo_height())
        if size == self._size or min(size) < 2:
            return
        self._size = size
        self.canvas.delete("all")
        try:
            from PIL import Image, ImageDraw
            scale = 2
            bitmap = Image.new("RGB", (size[0]*scale, size[1]*scale), PALETTE["background"])
            draw = ImageDraw.Draw(bitmap)
            draw.rounded_rectangle((0, 0, size[0]*scale-1, size[1]*scale-1),
                                   radius=self.radius*scale, fill=self.surface,
                                   outline=PALETTE["border"], width=scale)
            bitmap = bitmap.resize(size, Image.Resampling.LANCZOS)
            self._image = pillow_photo_image(bitmap, master=self)
            if self._image is not None:
                self.canvas.create_image(0, 0, anchor="nw", image=self._image)
                return
        except Exception:
            pass
        r = min(self.radius*2, size[0]//2, size[1]//2)
        w, h = size
        self.canvas.create_polygon(r, 0, w-r, 0, w, 0, w, r, w, h-r,
                                   w, h, w-r, h, r, h, 0, h, 0, h-r,
                                   0, r, 0, 0, smooth=True,
                                   fill=self.surface, outline=PALETTE["border"])


def _rounded_button_styles(root, style):
    """Nine-slice images retain native ttk keyboard/focus/disabled semantics."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        Image = ImageDraw = None
    cache = getattr(root, "_rounded_button_images", {})
    for kind, normal, hover, pressed, foreground in (
        ("base", PALETTE["surface"], PALETTE["hover"], PALETTE["selected"], PALETTE["text"]),
        ("primary", "#007aff", "#238cff", "#0063d1", "#ffffff"),
        ("primaryheader", "#007aff", "#238cff", "#0063d1", "#ffffff"),
        ("nav", PALETTE["background"], PALETTE["selected"], PALETTE["selected"], PALETTE["text"]),
        ("agent", PALETTE["selected"], PALETTE["selected"], PALETTE["selected"], PALETTE["accent"]),
        ("dock", PALETTE["surface"], PALETTE["selected"], PALETTE["selected"], PALETTE["muted"]),
        ("dockselected", PALETTE["selected"], PALETTE["selected"], PALETTE["selected"], PALETTE["accent"]),
        ("heroprimary", "#f5f8fc", "#ffffff", "#e5effa", "#203b60"),
        ("herosecondary", "#314d71", "#3d5d83", "#244261", "#ffffff"),
    ):
        key = (kind, DARK)
        element = f"Modern{kind}{'Dark' if DARK else 'Light'}.button"
        if key not in cache:
            images = []
            for fill, border in ((normal, normal), (PALETTE["background"], PALETTE["background"]),
                                 (pressed, pressed), (hover, hover), (normal, PALETTE["accent"])):
                corner = "#213c60" if kind.startswith("hero") else PALETTE["surface"] if kind in {"primary", "dock", "dockselected"} else PALETTE["background"]
                photo = None
                if Image is not None and ImageDraw is not None and pillow_photo_available():
                    try:
                        bitmap = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
                        ImageDraw.Draw(bitmap).rounded_rectangle((2, 2, 93, 93), radius=34,
                                                                fill=fill, outline=border, width=3)
                        photo = pillow_photo_image(
                            bitmap.resize((32, 32), Image.Resampling.LANCZOS), master=root
                        )
                    except Exception:
                        photo = None
                images.append(photo if photo is not None else _native_round_image(root, fill, border, corner))
            style.element_create(element, "image", images[0], ("disabled", images[1]),
                                 ("pressed", images[2]), ("active", images[3]), ("focus", images[4]),
                                 border=13, padding=0, sticky="nswe")
            cache[key] = images
        names = {"base": ("TButton", "Settings.TButton", "Agent.TButton", "Circle.TButton"),
                 "primary": ("Send.TButton",), "primaryheader": ("HeaderPrimary.TButton",), "nav": ("Nav.TButton",),
                 "agent": ("Selected.Agent.TButton", "Soft.TButton"),
                 "dock": ("Dock.TButton", "Surface.Settings.TButton"), "dockselected": ("Selected.Dock.TButton",),
                 "heroprimary": ("HeroPrimary.TButton",), "herosecondary": ("HeroSecondary.TButton",)}[kind]
        for name in names:
            backing = PALETTE["background"] if name in {"Agent.TButton", "Selected.Agent.TButton", "Circle.TButton", "Nav.TButton"} else PALETTE["surface"]
            style.configure(name, background=backing, borderwidth=0, relief="flat")
            style.map(name, background=[("!disabled",backing),("disabled",backing)])
            style.layout(name, [(element, {"sticky": "nswe", "children": [
                ("Button.padding", {"sticky": "nswe", "children": [
                    ("Button.label", {"sticky": "nswe"})]})]})])
    root._rounded_button_images = cache
    if not getattr(root, "_button_backing_bound", False):
        root.bind_all("<Map>", lambda event: match_button_backing(event.widget), add="+")
        root._button_backing_bound = True


def wrap_management_toolbar(frame):
    """Keep every existing command visible by flowing controls across rows."""
    pending=[None]
    last=[None]
    def arrange():
        pending[0]=None
        if defer_during_interactive_resize(frame, (frame, "toolbar-arrange"), arrange):
            return
        if not frame.winfo_exists() or frame.winfo_width()<20:
            return
        children=frame.winfo_children()
        signature=(frame.winfo_width(),tuple((str(child),child.winfo_reqwidth()) for child in children))
        if signature==last[0]:
            return
        last[0]=signature
        # Tk forbids mixing pack and grid within the same parent.
        for child in children:
            if child.winfo_manager()=="pack":
                child.pack_forget()
        row=column=used=0
        for child in children:
            width=child.winfo_reqwidth()+8
            if column and used+width>frame.winfo_width():
                row+=1;column=used=0
            child.grid(row=row,column=column,sticky="w",padx=(0,8),pady=2)
            used+=width;column+=1
    def schedule(_event=None):
        if defer_during_interactive_resize(frame, (frame, "toolbar-arrange"), arrange):
            return
        if pending[0] is None:
            pending[0]=frame.after_idle(arrange)
    def cleanup(_event=None):
        if pending[0] is not None:
            try:frame.after_cancel(pending[0])
            except tk.TclError:pass
            pending[0]=None
    frame.bind("<Configure>",schedule,add="+")
    frame.bind("<Destroy>",cleanup,add="+")
    schedule()


def fit_management_text(panel):
    """Wrap existing explanations to their panel without changing their text."""
    pending = [None]
    def apply():
        pending[0] = None
        if defer_during_interactive_resize(panel, (panel, "management-text"), apply):
            return
        if not panel.winfo_exists():
            return
        def visit(parent):
            for child in parent.winfo_children():
                if isinstance(child,(tk.Label,ttk.Label)):
                    try:
                        if float(child.cget("wraplength") or 0)>0:
                            width=max(160,parent.winfo_width()-16)
                            if abs(float(child.cget("wraplength"))-width)>2:
                                child.configure(wraplength=width)
                    except (tk.TclError,ValueError):
                        pass
                visit(child)
        visit(panel)
    def schedule(event=None):
        if event is not None and event.widget is not panel:
            return
        if defer_during_interactive_resize(panel, (panel, "management-text"), apply):
            return
        if pending[0] is None:
            pending[0]=panel.after_idle(apply)
    def cleanup(_event=None):
        if pending[0] is not None:
            try:panel.after_cancel(pending[0])
            except tk.TclError:pass
            pending[0]=None
    panel.bind("<Configure>",schedule,add="+")
    panel.bind("<Destroy>",cleanup,add="+")
    schedule()


def match_button_backing(widget):
    """Match transparent corner pixels to the actual parent panel."""
    if not isinstance(widget, ttk.Button):
        return
    try:
        style = ttk.Style(widget)
        parent = widget.master
        if isinstance(parent, ttk.Widget):
            parent_style = str(parent.cget("style")) or parent.winfo_class()
            backing = style.lookup(parent_style, "background")
        else:
            backing = str(parent.cget("background"))
        if not backing:
            return
        base = str(widget.cget("style")) or "TButton"
        if base.startswith("PanelBacking"):
            base = base.split(".",1)[1]
        if base in {"Caption.TButton", "CaptionClose.TButton"} or base.endswith(("HeroPrimary.TButton", "HeroSecondary.TButton")):
            return
        backed = "PanelBacking"+backing.lstrip("#")+"."+base
        style.configure(backed, background=backing)
        style.map(backed, background=[("!disabled",backing),("disabled",backing)])
        widget.configure(style=backed)
    except (tk.TclError, AttributeError):
        pass


def apply_appearance(root, family: str, mode: str) -> None:
    """Recolor existing widgets in place; preserve edits, focus and scroll position."""
    global DARK, APPEARANCE_MODE
    APPEARANCE_MODE = mode if mode in {"light", "dark", "system"} else "system"
    dark = system_dark_mode() if APPEARANCE_MODE == "system" else APPEARANCE_MODE == "dark"
    old = dict(PALETTE)
    if dark == DARK:
        return
    old_colors = {value.lower(): role for role, value in old.items()}
    for literal in ("#039855", "#16803c", "#c62828", "#d92d20", "#b54708"):
        old_colors[color(literal)] = literal
    DARK = dark
    PALETTE.update(make_palette(dark))
    configure_styles(root, family)
    def translated(value):
        role = old_colors.get(str(value).lower())
        return PALETTE.get(role, color(role)) if role else None
    def visit(widget):
        try:
            if isinstance(widget, (tk.Tk, tk.Toplevel)):
                apply_titlebar(widget)
            options = widget.keys()
            changes = {}
            for key in ("background", "foreground", "insertbackground", "selectbackground",
                        "selectforeground", "activebackground", "activeforeground",
                        "disabledforeground", "highlightbackground", "highlightcolor"):
                if key not in options:
                    continue
                value = str(widget.cget(key))
                # White ink on a colored action or hero is deliberately constant.
                if key.endswith("foreground") and value.lower() == "#ffffff":
                    continue
                replacement = translated(value)
                if replacement:
                    changes[key] = replacement
            if changes:
                widget.configure(**changes)
            if isinstance(widget, ttk.Button):
                match_button_backing(widget)
            if isinstance(widget, RoundedPanel):
                widget.surface = translated(widget.surface) or widget.surface
                widget._size = None
                widget._paint(None)
            if isinstance(widget, (tk.Text, ttk.Treeview)):
                for tag in widget.tag_names() if isinstance(widget, tk.Text) else widget.tk.call(widget, "tag", "names"):
                    for option in ("background", "foreground"):
                        value = widget.tag_cget(tag, option) if isinstance(widget, tk.Text) else widget.tag_configure(tag).get(option)
                        replacement = translated(value)
                        if replacement and not (option == "foreground" and str(value).lower() == "#ffffff"):
                            widget.tag_configure(tag, **{option: replacement})
            if isinstance(widget, tk.Canvas) and not isinstance(widget.master, RoundedPanel) and not getattr(widget, "_appearance_fixed_artwork", False):
                for item in widget.find_all():
                    for option in ("fill", "outline"):
                        try:
                            replacement = translated(widget.itemcget(item, option))
                            if replacement:
                                widget.itemconfigure(item, **{option: replacement})
                        except tk.TclError:
                            pass
            for child in widget.winfo_children():
                visit(child)
        except tk.TclError:
            pass
    visit(root)


def apply_titlebar(window) -> None:
    """Ask supported Windows versions to match the app's title bar appearance."""
    if os.name != "nt":
        return
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        setting = ctypes.c_int(int(DARK))
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd), 20, ctypes.byref(setting), ctypes.sizeof(setting))
    except (AttributeError, OSError, tk.TclError):
        pass


def _native_round_image(root, fill, border, background):
    """Antialiased RGBA corners without Pillow; no opaque corner matte."""
    import math
    import struct
    import zlib
    def rgb(value):
        return tuple(int(value[index:index+2], 16) for index in (1,3,5))
    fill_rgb, border_rgb = rgb(fill), rgb(border)
    pixels = bytearray()
    for y in range(32):
        pixels.append(0)  # PNG filter: none.
        for x in range(32):
            qx, qy = abs(x-15.5)-4.5, abs(y-15.5)-4.5
            distance = math.hypot(max(qx,0),max(qy,0))+min(max(qx,qy),0)-11
            coverage = max(0,min(1,.5-distance))
            ink = border_rgb if distance > -1.3 else fill_rgb
            pixels.extend((*ink, round(255*coverage)))
    def chunk(kind, data):
        return struct.pack(">I",len(data))+kind+data+struct.pack(">I",zlib.crc32(kind+data)&0xffffffff)
    png = (b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",32,32,8,6,0,0,0))
           +chunk(b"IDAT",zlib.compress(bytes(pixels),9))+chunk(b"IEND",b""))
    return tk.PhotoImage(master=root, data=png, format="PNG")
