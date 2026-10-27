from __future__ import annotations

import tkinter as tk
from tkinter import ttk
import unittest

from bookkeeping.desktop_frame import DesktopPanedWindow


def inherited_cursor(widget):
    """Follow Tk's cursor inheritance, stopping at the owning toplevel."""
    while widget is not None:
        value = str(widget.cget("cursor"))
        if value:
            return value
        if isinstance(widget, (tk.Tk, tk.Toplevel)):
            break
        widget = widget.master
    return "arrow"


class DesktopCursorTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        self.addCleanup(self.root.destroy)
        self.root.geometry("900x600")
        self.errors = []
        self.root.report_callback_exception = lambda *error: self.errors.append(error)
        self.panes = DesktopPanedWindow(
            self.root, orient="horizontal", sashwidth=8,
            sashcursor="sb_h_double_arrow", opaqueresize=False,
            showhandle=True, handlesize=6,
        )
        self.panes.pack(fill="both", expand=True)
        self.navigation = ttk.Frame(self.panes)
        self.content = ttk.Frame(self.panes)
        self.panes.add(self.navigation, width=220, minsize=180)
        self.panes.add(self.content, minsize=300)
        self.root.update()

    def test_pending_sash_cursor_does_not_reach_existing_or_new_content(self):
        label = ttk.Label(self.content, text="Ordinary content")
        label.pack()
        # Reproduce the interval between the sash changing its cursor and its
        # deferred Leave/drag cleanup. The parent remains a sizing cursor.
        self.panes.configure(cursor="sb_h_double_arrow")
        self.assertEqual(inherited_cursor(self.navigation), "arrow")
        self.assertEqual(inherited_cursor(label), "arrow")
        late_frame = ttk.Frame(self.content)
        late_label = ttk.Label(late_frame, text="New page content")
        self.assertEqual(inherited_cursor(late_label), "arrow")

    def test_input_and_link_cursors_survive_the_sash_cursor(self):
        entry = ttk.Entry(self.content, cursor="xterm")
        link = ttk.Label(self.navigation, text="Link", cursor="hand2")
        self.panes.configure(cursor="sb_h_double_arrow")
        self.assertEqual(inherited_cursor(entry), "xterm")
        self.assertEqual(inherited_cursor(link), "hand2")
        explicit_pane = ttk.Frame(self.panes, cursor="crosshair")
        self.panes.add(str(explicit_pane))
        self.assertEqual(str(explicit_pane.cget("cursor")), "crosshair")

    def test_native_sash_bindings_still_drag_and_apply_width_on_release(self):
        start, _ = self.panes.sash_coord(0)
        self.panes.event_generate("<Motion>", x=start + 2, y=100)
        self.root.update()
        self.assertEqual(str(self.panes.cget("cursor")), "sb_h_double_arrow")
        self.panes.event_generate("<ButtonPress-1>", x=start + 2, y=100)
        self.panes.event_generate("<B1-Motion>", x=start + 82, y=100)
        self.root.update()
        self.assertEqual(self.panes.sash_coord(0)[0], start)
        self.assertGreater(self.panes.proxy_coord()[0], start)
        self.assertEqual(inherited_cursor(self.content), "arrow")
        self.panes.event_generate("<ButtonRelease-1>", x=start + 82, y=100)
        self.root.update()
        self.assertGreater(self.panes.sash_coord(0)[0], start)
        self.panes.event_generate("<Leave>")
        self.root.update()
        self.assertEqual(str(self.panes.cget("cursor")), "arrow")
        self.assertEqual(inherited_cursor(self.content), "arrow")
        self.assertEqual(self.errors, [])


if __name__ == "__main__":
    unittest.main()
