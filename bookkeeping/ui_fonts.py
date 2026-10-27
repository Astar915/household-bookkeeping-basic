"""Shared, readable font defaults for the desktop interface."""

from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from tkinter import font as tkfont


FONT_FAMILY_PREFERENCES = (
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "Noto Sans CJK SC",
    "Noto Sans SC",
    "PingFang SC",
    "Yu Gothic UI",
    "Meiryo",
)

DEFAULT_FONT_SIZES = {
    "TkDefaultFont": 10,
    "TkTextFont": 11,
    "TkFixedFont": 10,
    "TkMenuFont": 10,
    "TkHeadingFont": 11,
    "TkCaptionFont": 10,
    "TkSmallCaptionFont": 10,
    "TkIconFont": 10,
    "TkTooltipFont": 10,
}


def enable_windows_gdi_text_scaling() -> bool:
    """Ask Windows to sharpen GDI text while preserving Tk's existing layout.

    Tk 8.6 reports 96 DPI and uses that for window geometry. Marking this app
    fully DPI-aware makes those pixel-based layouts shrink on scaled displays.
    Windows' GDI-scaled unaware mode keeps Tk's geometry intact and improves
    the quality of its text and other GDI-drawn primitives.
    """
    if sys.platform != "win32":
        return False
    try:
        set_awareness = ctypes.WinDLL("user32", use_last_error=True).SetProcessDpiAwarenessContext
        set_awareness.argtypes = [ctypes.c_void_p]
        set_awareness.restype = ctypes.c_bool
        return bool(set_awareness(ctypes.c_void_p(-5)))  # DPI_AWARENESS_CONTEXT_UNAWARE_GDISCALED
    except (AttributeError, OSError):
        # Windows versions before GDI scaling keep the previous DPI behavior.
        return False


def choose_ui_font_family(root: tk.Misc) -> str:
    """Choose an installed font with broad Chinese/Japanese glyph coverage."""
    try:
        installed = {family.casefold(): family for family in tkfont.families(root)}
    except tk.TclError:
        installed = {}
    for preferred in FONT_FAMILY_PREFERENCES:
        if preferred.casefold() in installed:
            return installed[preferred.casefold()]
    try:
        return str(tkfont.nametofont("TkDefaultFont", root=root).actual("family"))
    except tk.TclError:
        return "TkDefaultFont"


def configure_global_fonts(root: tk.Misc) -> str:
    """Set Tk's named defaults so native widgets share readable sizing."""
    family = choose_ui_font_family(root)
    for name, size in DEFAULT_FONT_SIZES.items():
        try:
            tkfont.nametofont(name, root=root).configure(family=family, size=size)
        except tk.TclError:
            continue
    # Native widgets already use TkDefaultFont. A broad *Font option also sets
    # ttk's widget-level font and silently overrides heading/button styles.
    root.option_add("*Text.Font", "TkTextFont")
    return family
