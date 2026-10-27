from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from typing import Callable


def confirm_delete_once(
    parent: tk.Misc,
    *,
    title: str,
    target: str,
    impact: str,
    translate_text: Callable[[str], str] | None = None,
) -> bool:
    """Ask once before removing user data or settings."""
    if translate_text is None:
        # Import lazily: localization imports Tk widgets and can itself import
        # helpers that are used while the desktop UI is being initialized.
        from .localization import translate

        localize = translate
    else:
        localize = translate_text

    prompt = localize("确认删除：{target}？\n\n{impact}").format(
        target=target,
        impact=localize(impact),
    )
    return messagebox.askyesno(localize(title), prompt, parent=parent)
