from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass
from ctypes import wintypes

from core.screen_capture import Region


@dataclass(frozen=True)
class WindowInfo:
    handle: int
    title: str
    region: Region


def _user32():
    return ctypes.windll.user32 if os.name == "nt" else None


def get_window(handle: int, min_width: int = 300, min_height: int = 220) -> WindowInfo | None:
    """Resolve a window by HWND so title changes do not break capture."""
    user32 = _user32()
    if user32 is None or not handle:
        return None
    hwnd = wintypes.HWND(handle)
    if not user32.IsWindow(hwnd):
        return None
    if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
        return None
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return None
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    width, height = rect.right - rect.left, rect.bottom - rect.top
    title = buffer.value.strip()
    if not title or width < min_width or height < min_height:
        return None
    return WindowInfo(int(handle), title, Region(rect.left, rect.top, width, height))


def list_windows(min_width: int = 300, min_height: int = 220) -> list[WindowInfo]:
    """Return visible, titled top-level Windows in stable title order."""
    user32 = _user32()
    if user32 is None:
        return []
    results: list[WindowInfo] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def visit(hwnd, _lparam):
        window = get_window(int(hwnd), min_width, min_height)
        if window:
            results.append(window)
        return True

    user32.EnumWindows(callback_type(visit), 0)
    return sorted(results, key=lambda item: item.title.casefold())


def find_window(title: str) -> WindowInfo | None:
    if not title:
        return None
    windows = list_windows()
    exact = next((item for item in windows if item.title == title), None)
    if exact:
        return exact
    needle = title.casefold()
    return next((item for item in windows if needle in item.title.casefold() or item.title.casefold() in needle), None)

