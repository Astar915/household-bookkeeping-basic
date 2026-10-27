"""Small delayed hover labels for native desktop controls."""
from __future__ import annotations
import tkinter as tk
from .desktop_theme import PALETTE
from .localization import translate


class Tooltip:
    def __init__(self, widget, text, *, delay=450):
        self.widget, self.text, self.delay = widget, text, delay
        self.pending = None
        self.popup = None
        widget.bind("<Enter>", self.schedule, add="+")
        for event in ("<Leave>", "<ButtonPress>", "<FocusOut>", "<Unmap>", "<Destroy>"):
            widget.bind(event, self.hide, add="+")
        # The binding callbacks keep this instance alive with its widget.

    def schedule(self, _event=None):
        self.hide()
        self.pending = self.widget.after(self.delay, self.show)

    def show(self):
        self.pending = None
        try:
            if not self.widget.winfo_viewable():
                return
            x,y = self.widget.winfo_pointerxy()
            if self.widget.winfo_containing(x,y) is not self.widget:
                return
            text = self.text() if callable(self.text) else self.text
            popup = self.popup = tk.Toplevel(self.widget)
            popup.withdraw()
            popup.overrideredirect(True)
            popup.attributes("-topmost", True)
            popup.configure(background=PALETTE["border"])
            tk.Label(popup, text=translate(text), background=PALETTE["surface"],
                     foreground=PALETTE["text"], padx=9, pady=5,
                     font=("Segoe UI", 9), borderwidth=0).pack(padx=1,pady=1)
            popup.update_idletasks()
            root = self.widget.winfo_toplevel()
            # Place below the control and keep the tip inside its application.
            right = root.winfo_rootx()+root.winfo_width()
            x = max(root.winfo_rootx()+4,min(self.widget.winfo_rootx(),right-popup.winfo_reqwidth()-4))
            y = self.widget.winfo_rooty()+self.widget.winfo_height()+5
            if y+popup.winfo_reqheight()>root.winfo_rooty()+root.winfo_height():
                y = self.widget.winfo_rooty()-popup.winfo_reqheight()-5
            popup.geometry(f"+{x}+{y}")
            popup.deiconify()
        except tk.TclError:
            self.hide()

    def hide(self, _event=None):
        if self.pending is not None:
            try:self.widget.after_cancel(self.pending)
            except tk.TclError:pass
            self.pending = None
        if self.popup is not None:
            try:self.popup.destroy()
            except tk.TclError:pass
            self.popup = None
