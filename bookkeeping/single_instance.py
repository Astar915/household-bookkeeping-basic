from __future__ import annotations

import ctypes
import hashlib
import os
from pathlib import Path


_ERROR_ALREADY_EXISTS = 183
_INFINITE = 0xFFFFFFFF
_WAIT_OBJECT_0 = 0x00000000
_WAIT_ABANDONED = 0x00000080
_SW_RESTORE = 9
_SW_SHOW = 5
_GA_ROOT = 2
_MONITOR_DEFAULTTONULL = 0
_MONITOR_DEFAULTTOPRIMARY = 1
_SWP_NOZORDER = 0x0004
_SWP_NOACTIVATE = 0x0010
_SWP_NOOWNERZORDER = 0x0200
_FLASHW_TRAY = 0x00000002
_FLASHW_TIMERNOFG = 0x0000000C


class _Rect(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _MonitorInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("rcMonitor", _Rect),
        ("rcWork", _Rect),
        ("dwFlags", ctypes.c_uint),
    ]


class _FlashWindowInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("hwnd", ctypes.c_void_p),
        ("dwFlags", ctypes.c_uint),
        ("uCount", ctypes.c_uint),
        ("dwTimeout", ctypes.c_uint),
    ]


class SingleInstance:
    """Keep one desktop window per local ledger and activate it on relaunch."""

    def __init__(self, database_path: str | Path, window_title: str) -> None:
        self.database_path = Path(database_path).resolve()
        self.window_title = window_title
        self._handle: int | None = None
        self._owned = False

    def acquire(self, *, wait_for_existing: bool = False) -> bool:
        if os.name != "nt":
            return True

        digest = hashlib.sha256(
            os.path.normcase(str(self.database_path)).encode("utf-8")
        ).hexdigest()[:24]
        mutex_name = f"Local\\HouseholdBookkeeping-{digest}"
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        kernel32.WaitForSingleObject.restype = ctypes.c_uint
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int

        ctypes.set_last_error(0)
        handle = kernel32.CreateMutexW(None, 1, mutex_name)
        if not handle:
            return False

        if ctypes.get_last_error() == _ERROR_ALREADY_EXISTS:
            if not wait_for_existing:
                kernel32.CloseHandle(handle)
                _activate_window(self.window_title)
                return False
            result = kernel32.WaitForSingleObject(handle, _INFINITE)
            if result not in (_WAIT_OBJECT_0, _WAIT_ABANDONED):
                kernel32.CloseHandle(handle)
                return False

        self._handle = handle
        self._owned = True
        return True

    def release(self) -> None:
        if not self._handle:
            return

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.ReleaseMutex.argtypes = [ctypes.c_void_p]
        kernel32.ReleaseMutex.restype = ctypes.c_int
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int
        if self._owned:
            kernel32.ReleaseMutex(self._handle)
        kernel32.CloseHandle(self._handle)
        self._handle = None
        self._owned = False


def _activate_window(window_title: str) -> None:
    if os.name != "nt":
        return

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    user32.FindWindowW.restype = ctypes.c_void_p
    user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.ShowWindow.restype = ctypes.c_int
    user32.BringWindowToTop.argtypes = [ctypes.c_void_p]
    user32.BringWindowToTop.restype = ctypes.c_int
    user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
    user32.SetForegroundWindow.restype = ctypes.c_int
    user32.FlashWindowEx.argtypes = [ctypes.POINTER(_FlashWindowInfo)]
    user32.FlashWindowEx.restype = ctypes.c_int

    window = user32.FindWindowW(None, window_title)
    if not window:
        return

    user32.ShowWindow(window, _SW_RESTORE)
    repair_window_position(window)
    user32.ShowWindow(window, _SW_SHOW)
    user32.BringWindowToTop(window)
    if not user32.SetForegroundWindow(window):
        info = _FlashWindowInfo(
            ctypes.sizeof(_FlashWindowInfo),
            window,
            _FLASHW_TRAY | _FLASHW_TIMERNOFG,
            3,
            0,
        )
        user32.FlashWindowEx(ctypes.byref(info))


def repair_window_position(window_handle: int | ctypes.c_void_p) -> bool:
    """Move a window back to the primary work area if it is fully off-screen."""
    if os.name != "nt":
        return False

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    user32.GetAncestor.restype = ctypes.c_void_p
    user32.MonitorFromWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    user32.MonitorFromWindow.restype = ctypes.c_void_p
    user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_MonitorInfo)]
    user32.GetMonitorInfoW.restype = ctypes.c_int
    user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Rect)]
    user32.GetWindowRect.restype = ctypes.c_int
    user32.SetWindowPos.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    user32.SetWindowPos.restype = ctypes.c_int

    handle = (
        window_handle
        if isinstance(window_handle, ctypes.c_void_p)
        else ctypes.c_void_p(int(window_handle))
    )
    root_window = user32.GetAncestor(handle, _GA_ROOT) or handle
    if user32.MonitorFromWindow(root_window, _MONITOR_DEFAULTTONULL):
        return False

    monitor = user32.MonitorFromWindow(root_window, _MONITOR_DEFAULTTOPRIMARY)
    if not monitor:
        return False
    monitor_info = _MonitorInfo()
    monitor_info.cbSize = ctypes.sizeof(_MonitorInfo)
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(monitor_info)):
        return False

    rect = _Rect()
    if not user32.GetWindowRect(root_window, ctypes.byref(rect)):
        return False
    work = monitor_info.rcWork
    work_width = work.right - work.left
    work_height = work.bottom - work.top
    if work_width <= 0 or work_height <= 0:
        return False

    width = min(max(rect.right - rect.left, 1), work_width)
    height = min(max(rect.bottom - rect.top, 1), work_height)
    left = work.left + (work_width - width) // 2
    top = work.top + (work_height - height) // 2
    flags = _SWP_NOZORDER | _SWP_NOACTIVATE | _SWP_NOOWNERZORDER
    return bool(user32.SetWindowPos(root_window, None, left, top, width, height, flags))
