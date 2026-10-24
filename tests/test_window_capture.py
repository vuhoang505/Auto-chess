from __future__ import annotations

from core.screen_capture import Region
from core.window_capture import WindowInfo, find_window


def test_find_window_exact_and_partial(monkeypatch) -> None:
    windows = [
        WindowInfo(1, "Analysis Board - Browser", Region(0, 0, 900, 700)),
        WindowInfo(2, "Notes", Region(10, 10, 500, 400)),
    ]
    monkeypatch.setattr("core.window_capture.list_windows", lambda: windows)
    assert find_window("Notes").handle == 2
    assert find_window("Analysis Board").handle == 1
    assert find_window("Missing") is None


def test_window_identity_is_handle_not_title() -> None:
    first = WindowInfo(42, "Old page title", Region(0, 0, 900, 700))
    renamed = WindowInfo(42, "New page title", Region(20, 10, 900, 700))
    assert first.handle == renamed.handle
