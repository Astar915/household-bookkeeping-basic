from __future__ import annotations

import ctypes
import unittest
from unittest.mock import patch

import bookkeeping.single_instance as single_instance


class _FakeFunction:
    def __init__(self, callback):
        self.callback = callback
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self.callback(*args)


class SingleInstanceWindowRepairTests(unittest.TestCase):
    def _fake_user32(self, *, already_on_monitor: bool):
        calls = {}
        user32 = type("FakeUser32", (), {})()
        user32.GetAncestor = _FakeFunction(lambda _window, _flags: 101)
        user32.MonitorFromWindow = _FakeFunction(
            lambda _window, flags: 202 if flags == single_instance._MONITOR_DEFAULTTOPRIMARY
            or already_on_monitor else None
        )

        def get_monitor_info(_monitor, info_pointer):
            info = ctypes.cast(
                info_pointer, ctypes.POINTER(single_instance._MonitorInfo)
            ).contents
            info.rcWork.left = 0
            info.rcWork.top = 0
            info.rcWork.right = 1920
            info.rcWork.bottom = 1040
            return 1

        def get_window_rect(_window, rect_pointer):
            rect = ctypes.cast(rect_pointer, ctypes.POINTER(single_instance._Rect)).contents
            rect.left = -32000
            rect.top = -32000
            rect.right = -31164
            rect.bottom = -31401
            return 1

        def set_window_pos(*args):
            calls["set_window_pos"] = args
            return 1

        user32.GetMonitorInfoW = _FakeFunction(get_monitor_info)
        user32.GetWindowRect = _FakeFunction(get_window_rect)
        user32.SetWindowPos = _FakeFunction(set_window_pos)
        return user32, calls

    def test_fully_offscreen_window_is_centered_on_primary_work_area(self):
        user32, calls = self._fake_user32(already_on_monitor=False)
        with (
            patch.object(single_instance.os, "name", "nt"),
            patch.object(
                single_instance.ctypes, "WinDLL", return_value=user32, create=True
            ),
        ):
            repaired = single_instance.repair_window_position(99)

        self.assertTrue(repaired)
        _, insert_after, left, top, width, height, flags = calls["set_window_pos"]
        self.assertIsNone(insert_after)
        self.assertEqual((left, top, width, height), (542, 220, 836, 599))
        self.assertEqual(
            flags,
            single_instance._SWP_NOZORDER
            | single_instance._SWP_NOACTIVATE
            | single_instance._SWP_NOOWNERZORDER,
        )

    def test_window_already_on_a_monitor_is_not_moved(self):
        user32, calls = self._fake_user32(already_on_monitor=True)
        with (
            patch.object(single_instance.os, "name", "nt"),
            patch.object(
                single_instance.ctypes, "WinDLL", return_value=user32, create=True
            ),
        ):
            repaired = single_instance.repair_window_position(99)

        self.assertFalse(repaired)
        self.assertNotIn("set_window_pos", calls)

    def test_non_windows_platform_skips_native_repair(self):
        with (
            patch.object(single_instance.os, "name", "posix"),
            patch.object(single_instance.ctypes, "WinDLL", create=True) as win_dll,
        ):
            self.assertFalse(single_instance.repair_window_position(99))

        win_dll.assert_not_called()


if __name__ == "__main__":
    unittest.main()
