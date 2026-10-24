from __future__ import annotations

import numpy as np

from core.screen_capture import ScreenCapture


def test_detects_change_limited_to_two_chess_squares() -> None:
    capture = ScreenCapture()
    first = np.full((800, 800, 3), 120, dtype=np.uint8)
    second = first.copy()
    second[100:200, 400:500] = 220
    second[300:400, 400:500] = 40
    assert capture.has_changed(first, 0.018)
    assert capture.has_changed(second, 0.018)


def test_ignores_identical_frame() -> None:
    capture = ScreenCapture()
    frame = np.full((400, 400, 3), 80, dtype=np.uint8)
    assert capture.has_changed(frame)
    assert not capture.has_changed(frame.copy())
