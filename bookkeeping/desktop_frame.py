"""Windows client-drawn frame, retaining native taskbar and window state behavior.

Uses WM_NCCALCSIZE instead of override-redirect so minimize/restore stays native.
See https://learn.microsoft.com/en-us/windows/win32/dwm/customframe
"""
from __future__ import annotations
import os
import tkinter as tk
from tkinter import ttk


def center_window(window, relative_to=None):
    """Center once in the monitor work area, or over the owning window."""
    window.update_idletasks()
    if os.name == "nt":
        import ctypes as c
        from ctypes import wintypes as w
        class RECT(c.Structure):
            _fields_ = [(name,c.c_long) for name in ("left","top","right","bottom")]
        class MONITORINFO(c.Structure):
            _fields_ = [("cbSize",w.DWORD),("rcMonitor",RECT),("rcWork",RECT),("dwFlags",w.DWORD)]
        try:
            user=c.WinDLL("user32",use_last_error=True)
            user.GetAncestor.argtypes=[w.HWND,w.UINT];user.GetAncestor.restype=w.HWND
            user.GetWindowRect.argtypes=[w.HWND,c.POINTER(RECT)]
            user.MonitorFromWindow.argtypes=[w.HWND,w.DWORD];user.MonitorFromWindow.restype=w.HMONITOR
            user.GetMonitorInfoW.argtypes=[w.HMONITOR,c.POINTER(MONITORINFO)]
            user.SetWindowPos.argtypes=[w.HWND,w.HWND,c.c_int,c.c_int,c.c_int,c.c_int,w.UINT]
            hwnd=user.GetAncestor(window.winfo_id(),2)
            owner=user.GetAncestor(relative_to.winfo_id(),2) if relative_to is not None else hwnd
            info=MONITORINFO();info.cbSize=c.sizeof(info)
            rect=RECT()
            if not user.GetWindowRect(hwnd,c.byref(rect)) or not user.GetMonitorInfoW(
                    user.MonitorFromWindow(owner,2),c.byref(info)):
                raise OSError("Window bounds unavailable")
            width,height=rect.right-rect.left,rect.bottom-rect.top
            work=info.rcWork
            target=work
            if relative_to is not None:
                parent=RECT()
                if user.GetWindowRect(owner,c.byref(parent)):
                    target=parent
            x=max(work.left,min(target.left+(target.right-target.left-width)//2,work.right-width))
            y=max(work.top,min(target.top+(target.bottom-target.top-height)//2,work.bottom-height))
            if user.SetWindowPos(hwnd,None,x,y,0,0,0x0015):
                return
        except (AttributeError,OSError,tk.TclError):
            pass
    width,height=window.winfo_width(),window.winfo_height()
    if relative_to is None:
        x=(window.winfo_screenwidth()-width)//2
        y=(window.winfo_screenheight()-height)//2
    else:
        x=relative_to.winfo_rootx()+(relative_to.winfo_width()-width)//2
        y=relative_to.winfo_rooty()+(relative_to.winfo_height()-height)//2
    window.geometry(f"+{max(0,x)}+{max(0,y)}")


class DesktopPanedWindow(tk.PanedWindow):
    """Keep the sash cursor from propagating into ordinary pane contents.

    Tk's Panedwindow class changes the container's cursor during sash motion.
    Its Leave callback can restore that option after the pointer has entered a
    child, without updating the Windows cursor already inherited by that child.
    Give each pane its own cursor so entering it never inherits the sash state.
    Native sash bindings, proxy dragging and explicit child cursors are retained.
    """

    def __init__(self, master, **kwargs):
        kwargs.setdefault("cursor", "arrow")
        super().__init__(master, **kwargs)

    def add(self, child, **kwargs):
        pane = self.nametowidget(str(child))
        if not str(pane.cget("cursor")):
            pane.configure(cursor="arrow")
        return super().add(child, **kwargs)


class DesktopFrame:
    def __init__(self, root):
        self.root = root
        self.installed = False
        self.callback = None
        self._resize_listeners = []
        self._drag_state = None
        self._drag_after = None
        self._drag_position = None
        self._size_state = None
        self._size_after = None
        self._size_position = None
        self._size_refresh_after = None
        self._resize_grips = {}
        if os.name == "nt":
            root.after(80, self.install)

    def add_resize_listener(self, callback):
        """Register for the start and end of Windows' interactive size loop."""
        if callback not in self._resize_listeners:
            self._resize_listeners.append(callback)

    def _notify_resize_listeners(self, active):
        for callback in tuple(self._resize_listeners):
            try:
                callback(active)
            except Exception:
                pass

    def install(self):
        if self.installed or not self.root.winfo_exists():
            return
        if not self.root.winfo_ismapped():
            self.root.after(80, self.install)
            return
        import ctypes as c
        from ctypes import wintypes as w
        self.user = u = c.WinDLL("user32", use_last_error=True)
        class RECT(c.Structure):
            _fields_ = [(name,c.c_long) for name in ("left","top","right","bottom")]
        class MONITORINFO(c.Structure):
            _fields_ = [("cbSize",w.DWORD),("rcMonitor",RECT),("rcWork",RECT),("dwFlags",w.DWORD)]
        self.RECT = RECT
        class MINMAXINFO(c.Structure):
            _fields_ = [(name, w.POINT) for name in (
                "ptReserved", "ptMaxSize", "ptMaxPosition", "ptMinTrackSize", "ptMaxTrackSize")]
        self._minimum_size = self.root.minsize()
        u.GetAncestor.argtypes=[w.HWND,w.UINT];u.GetAncestor.restype=w.HWND
        self.hwnd=u.GetAncestor(self.root.winfo_id(),2)
        if not self.hwnd:
            return
        setter=u.SetWindowLongPtrW if c.sizeof(c.c_void_p)==8 else u.SetWindowLongW
        setter.argtypes=[w.HWND,c.c_int,c.c_void_p];setter.restype=c.c_void_p
        u.CallWindowProcW.argtypes=[c.c_void_p,w.HWND,w.UINT,w.WPARAM,w.LPARAM]
        u.CallWindowProcW.restype=c.c_ssize_t
        u.GetWindowRect.argtypes=[w.HWND,c.POINTER(RECT)]
        u.IsZoomed.argtypes=[w.HWND]
        u.MonitorFromWindow.argtypes=[w.HWND,w.DWORD];u.MonitorFromWindow.restype=w.HMONITOR
        u.GetMonitorInfoW.argtypes=[w.HMONITOR,c.POINTER(MONITORINFO)]
        u.SendMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM];u.SendMessageW.restype=c.c_ssize_t
        u.SetWindowPos.argtypes=[w.HWND,w.HWND,c.c_int,c.c_int,c.c_int,c.c_int,w.UINT]
        proto=c.WINFUNCTYPE(c.c_ssize_t,w.HWND,w.UINT,w.WPARAM,w.LPARAM)
        def procedure(hwnd,msg,wp,lp):
            try:
                if msg == 0x0231:  # WM_ENTERSIZEMOVE
                    self._notify_resize_listeners(True)
                if msg==0x0083 and wp:  # WM_NCCALCSIZE: use the entire frame as client.
                    if u.IsZoomed(hwnd):
                        info=MONITORINFO();info.cbSize=c.sizeof(info)
                        if u.GetMonitorInfoW(u.MonitorFromWindow(hwnd,2),c.byref(info)):
                            rect=c.cast(lp,c.POINTER(RECT)).contents
                            rect.left,rect.top=info.rcWork.left,info.rcWork.top
                            rect.right,rect.bottom=info.rcWork.right,info.rcWork.bottom
                    return 0
                if msg==0x0084:  # WM_NCHITTEST
                    # Tk child HWNDs cover the custom frame, including its
                    # edges. Dedicated Tk grips own resizing and cursors;
                    # reporting native sizing hits here leaks cursors into
                    # child controls without reliably starting a size loop.
                    return 1
                if msg==0x0082:  # Restore Tk's original procedure before destruction.
                    setter(hwnd,-4,self.previous)
                    self.installed=False
            except Exception:
                pass
            result = u.CallWindowProcW(self.previous,hwnd,msg,wp,lp)
            if msg == 0x0024:  # WM_GETMINMAXINFO: the whole custom frame is client area.
                info = c.cast(lp, c.POINTER(MINMAXINFO)).contents
                info.ptMinTrackSize.x, info.ptMinTrackSize.y = self._minimum_size
            if msg == 0x0232:  # WM_EXITSIZEMOVE: flush after the final native size is applied.
                try:
                    self.root.after_idle(lambda: self._notify_resize_listeners(False))
                except tk.TclError:
                    pass
            return result
        self.callback=proto(procedure)
        c.set_last_error(0)
        self.previous=setter(self.hwnd,-4,c.cast(self.callback,c.c_void_p))
        if not self.previous:
            self.callback=None
            return
        self.installed=True
        try:
            # Let DWM retain its shadow and round only restored windows.
            corner = c.c_int(2)  # DWMWCP_ROUND, DWMWA_WINDOW_CORNER_PREFERENCE
            c.windll.dwmapi.DwmSetWindowAttribute(c.c_void_p(self.hwnd), 33,
                                                c.byref(corner), c.sizeof(corner))
        except (AttributeError, OSError):
            pass
        u.SetWindowPos(self.hwnd,None,0,0,self.root.winfo_width(),self.root.winfo_height(),0x0026)
        center_window(self.root)
        self._install_resize_grips()

    def _install_resize_grips(self):
        # The resize cursors belong only to the small perimeter hit targets.
        # Give the client area an explicit normal cursor so it cannot inherit
        # a sizing cursor from the custom frame or a previous resize grab.
        self.root.configure(cursor="arrow")
        cursors = {
            "n": "size_ns", "s": "size_ns", "w": "size_we", "e": "size_we",
            "nw": "size_nw_se", "se": "size_nw_se",
            "ne": "size_ne_sw", "sw": "size_ne_sw",
        }
        for edge, cursor in cursors.items():
            grip = ttk.Frame(self.root, style="Surface.TFrame", cursor=cursor, takefocus=False)
            grip.bind("<ButtonPress-1>", lambda event, side=edge: self._start_resize(event, side))
            grip.bind("<B1-Motion>", self._resize_motion)
            grip.bind("<ButtonRelease-1>", self._end_resize)
            self._resize_grips[edge] = grip
        self.root.bind("<Configure>", self._layout_resize_grips, add="+")
        self.root.bind("<Map>", self._layout_resize_grips, add="+")
        self.root.bind("<Unmap>", self._cancel_resize_on_unmap, add="+")
        self._layout_resize_grips()

    def _layout_resize_grips(self, event=None):
        if event is not None and event.widget is not self.root:
            return
        if self.root.state() != "normal":
            for grip in self._resize_grips.values():
                grip.place_forget()
            return
        width = max(1, self.root.winfo_width())
        height = max(1, self.root.winfo_height())
        edge, corner = 5, 8
        horizontal = max(1, width - 2 * corner)
        vertical = max(1, height - 2 * corner)
        positions = {
            "n": dict(x=corner, y=0, width=horizontal, height=edge),
            "s": dict(x=corner, y=height-edge, width=horizontal, height=edge),
            "w": dict(x=0, y=corner, width=edge, height=vertical),
            "e": dict(x=width-edge, y=corner, width=edge, height=vertical),
            "nw": dict(x=0, y=0, width=corner, height=corner),
            "ne": dict(x=width-corner, y=0, width=corner, height=corner),
            "sw": dict(x=0, y=height-corner, width=corner, height=corner),
            "se": dict(x=width-corner, y=height-corner, width=corner, height=corner),
        }
        for side, grip in self._resize_grips.items():
            grip.place(**positions[side])
            grip.lift()

    def _start_resize(self, event, edge):
        import ctypes as c

        self._cancel_drag()
        if self.root.state() != "normal":
            return "break"
        if self._size_refresh_after is not None:
            self.root.after_cancel(self._size_refresh_after)
            self._size_refresh_after = None
        self._minimum_size = self.root.minsize()
        rect = self.RECT()
        if not self.user.GetWindowRect(self.hwnd, c.byref(rect)):
            return "break"
        self._size_state = {
            "edge": edge, "pointer": (event.x_root, event.y_root),
            "bounds": (rect.left, rect.top, rect.right-rect.left, rect.bottom-rect.top),
            "minimum": self._minimum_size, "grip": event.widget,
        }
        event.widget.grab_set()
        self._notify_resize_listeners(True)
        return "break"

    def _resize_motion(self, event):
        state = self._size_state
        if state is None:
            return "break"
        x, y, width, height = state["bounds"]
        dx, dy = event.x_root-state["pointer"][0], event.y_root-state["pointer"][1]
        minimum_width, minimum_height = state["minimum"]
        if "w" in state["edge"]:
            new_width = max(minimum_width, width-dx)
            x += width-new_width
            width = new_width
        elif "e" in state["edge"]:
            width = max(minimum_width, width+dx)
        if "n" in state["edge"]:
            new_height = max(minimum_height, height-dy)
            y += height-new_height
            height = new_height
        elif "s" in state["edge"]:
            height = max(minimum_height, height+dy)
        self._size_position = (x, y, width, height)
        if self._size_after is None:
            self._size_after = self.root.after(16, self._apply_resize_position)
        return "break"

    def _apply_resize_position(self):
        self._size_after = None
        position, self._size_position = self._size_position, None
        if position is not None and self._size_state is not None:
            self.user.SetWindowPos(self.hwnd, None, *position, 0x0014)

    def _end_resize(self, _event=None):
        # Windows can coalesce motion events during a fast drag. Always use
        # the release position as well, so the last movement is not lost.
        if _event is not None and self._size_state is not None:
            self._resize_motion(_event)
        if self._size_after is not None:
            self.root.after_cancel(self._size_after)
            self._size_after = None
        self._apply_resize_position()
        state, self._size_state = self._size_state, None
        if state is not None:
            if self.root.grab_current() is state["grip"]:
                state["grip"].grab_release()
            # Let the final geometry settle before redrawing charts and
            # responsive content. A new drag cancels this pending refresh.
            self._size_refresh_after = self.root.after(150, self._finish_resize_refresh)
        return "break"

    def _finish_resize_refresh(self):
        self._size_refresh_after = None
        self._notify_resize_listeners(False)

    def _cancel_resize_on_unmap(self, event):
        if event.widget is self.root:
            self._end_resize()

    def drag(self, event):
        """Start a Tk-driven move instead of entering Windows' modal move loop.

        Sending WM_NCLBUTTONDOWN/HTCAPTION synchronously from a Tk binding
        keeps the Tk callback on the stack until the native move loop ends.
        Tracking motion in Tk keeps the normal event loop alive while moving.
        """
        self._cancel_drag()
        try:
            self._drag_state = {
                "start_x": event.x_root,
                "start_y": event.y_root,
                "offset_x": event.x_root - self.root.winfo_rootx(),
                "offset_y": event.y_root - self.root.winfo_rooty(),
                "moved": False,
                "was_zoomed": self.root.state() == "zoomed",
            }
        except tk.TclError:
            self._drag_state = None
        if self._drag_state is not None:
            self._notify_resize_listeners(True)
        return "break"

    def drag_motion(self, event):
        state = self._drag_state
        if state is None:
            return "break"
        if not state["moved"]:
            if (abs(event.x_root - state["start_x"]) < 3
                    and abs(event.y_root - state["start_y"]) < 3):
                return "break"
            if state["was_zoomed"]:
                try:
                    self.root.state("normal")
                    self.root.update_idletasks()
                    # Keep the pointer over the title area as the maximized
                    # window restores to its saved size.
                    state["offset_x"] = self.root.winfo_width() // 2
                    state["offset_y"] = min(28, max(12, self.root.winfo_height() // 8))
                    state["was_zoomed"] = False
                except tk.TclError:
                    self._cancel_drag()
                    return "break"
            state["moved"] = True

        self._drag_position = (
            event.x_root - state["offset_x"],
            event.y_root - state["offset_y"],
        )
        if self._drag_after is None:
            try:
                self._drag_after = self.root.after(16, self._apply_drag_position)
            except tk.TclError:
                self._cancel_drag()
        return "break"

    def _apply_drag_position(self):
        self._drag_after = None
        position, self._drag_position = self._drag_position, None
        if position is None or self._drag_state is None or not self._drag_state["moved"]:
            return
        x, y = position
        try:
            if os.name == "nt" and self.installed:
                # SetWindowPos uses the same DPI-virtualized coordinate space
                # as Tk and the mouse events for this window.
                self.user.SetWindowPos(self.hwnd, None, x, y, 0, 0, 0x0015)
            else:
                self.root.geometry(f"+{x}+{y}")
        except (AttributeError, OSError, tk.TclError):
            self._cancel_drag()

    def end_drag(self, _event=None):
        was_dragging = self._drag_state is not None
        if self._drag_after is not None:
            try:
                self.root.after_cancel(self._drag_after)
            except tk.TclError:
                pass
            self._drag_after = None
            self._apply_drag_position()
        self._drag_state = None
        if was_dragging:
            self._notify_resize_listeners(False)
        return "break"

    def _cancel_drag(self):
        was_dragging = self._drag_state is not None
        if self._drag_after is not None:
            try:
                self.root.after_cancel(self._drag_after)
            except tk.TclError:
                pass
        self._drag_after = None
        self._drag_state = None
        self._drag_position = None
        if was_dragging:
            self._notify_resize_listeners(False)

    def maximize(self):
        self._end_resize()
        self._cancel_drag()
        self.root.state("normal" if self.root.state()=="zoomed" else "zoomed")

    def bind_drag(self,widget):
        widget.bind("<ButtonPress-1>",self.drag)
        widget.bind("<B1-Motion>", self.drag_motion)
        widget.bind("<ButtonRelease-1>", self.end_drag)
        widget.bind("<Double-Button-1>",lambda _event:self.maximize())


class ResizeRenderCoordinator:
    """Coalesce expensive responsive redraws until interactive resizing ends."""

    def __init__(self, root):
        self.root = root
        self.active_sources = set()
        self.pending = {}

    @property
    def active(self):
        return bool(self.active_sources)

    def defer(self, key, callback):
        if not self.active:
            return False
        self.pending[key] = callback
        return True

    def set_active(self, active):
        self.set_source_active("main-window-native-size-move", active)

    def set_source_active(self, source, active):
        if active:
            self.active_sources.add(source)
            return
        self.active_sources.discard(source)
        if self.active:
            return
        callbacks = tuple(self.pending.values())
        self.pending.clear()
        try:
            if self.root.winfo_exists():
                for callback in callbacks:
                    self.root.after_idle(callback)
        except tk.TclError:
            pass


def defer_during_interactive_resize(widget, key, callback):
    """Return True after registering work to run once the user releases resize."""
    try:
        root = widget._root()
        coordinator = getattr(root, "_bk_resize_coordinator", None)
        return coordinator.defer(key, callback) if coordinator is not None else False
    except tk.TclError:
        return False


class WindowResizeMessageHook:
    """Expose native interactive sizing boundaries for a mapped Tk toplevel."""

    def __init__(self, window, coordinator):
        self.window = window
        self.coordinator = coordinator
        self.source = ("native-toplevel-size-move", id(window))
        self.hwnd = None
        self.user = None
        self.setter = None
        self.previous = None
        self.callback = None
        self.installed = False

    def install(self):
        if os.name != "nt" or self.installed:
            return False
        try:
            if not self.window.winfo_exists() or not self.window.winfo_ismapped():
                return False
            import ctypes as c
            from ctypes import wintypes as w

            user = c.WinDLL("user32", use_last_error=True)
            user.GetAncestor.argtypes = [w.HWND, w.UINT]
            user.GetAncestor.restype = w.HWND
            user.CallWindowProcW.argtypes = [c.c_void_p, w.HWND, w.UINT, w.WPARAM, w.LPARAM]
            user.CallWindowProcW.restype = c.c_ssize_t
            setter = user.SetWindowLongPtrW if c.sizeof(c.c_void_p) == 8 else user.SetWindowLongW
            setter.argtypes = [w.HWND, c.c_int, c.c_void_p]
            setter.restype = c.c_void_p
            hwnd = user.GetAncestor(self.window.winfo_id(), 2)  # GA_ROOT
            if not hwnd:
                return False

            proto = c.WINFUNCTYPE(c.c_ssize_t, w.HWND, w.UINT, w.WPARAM, w.LPARAM)

            def procedure(handle, message, wparam, lparam):
                try:
                    if message == 0x0231:  # WM_ENTERSIZEMOVE
                        self.coordinator.set_source_active(self.source, True)
                except Exception:
                    pass
                if message == 0x0082:  # WM_NCDESTROY
                    try:
                        setter(handle, -4, self.previous)
                        self.installed = False
                    except (OSError, ValueError):
                        pass
                result = user.CallWindowProcW(self.previous, handle, message, wparam, lparam)
                if message == 0x0232:  # WM_EXITSIZEMOVE
                    try:
                        self.coordinator.set_source_active(self.source, False)
                    except Exception:
                        pass
                return result

            callback = proto(procedure)
            c.set_last_error(0)
            previous = setter(hwnd, -4, c.cast(callback, c.c_void_p))  # GWLP_WNDPROC
            if not previous:
                return False
            self.user, self.setter, self.hwnd = user, setter, hwnd
            self.previous, self.callback = previous, callback
            self.installed = True
            return True
        except (AttributeError, OSError, TypeError, ValueError, tk.TclError):
            return False

    def detach(self):
        self.coordinator.set_source_active(self.source, False)
        if self.installed and self.setter is not None and self.hwnd:
            try:
                self.setter(self.hwnd, -4, self.previous)
            except (OSError, TypeError, ValueError):
                pass
        self.installed = False
        self.callback = None
