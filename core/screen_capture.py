from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import cv2
import mss
import numpy as np


@dataclass(frozen=True)
class Region:
    left: int
    top: int
    width: int
    height: int

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "Region | None":
        if not value:
            return None
        try:
            region = cls(*(int(value[k]) for k in ("left", "top", "width", "height")))
            return region if region.width > 0 and region.height > 0 else None
        except (KeyError, TypeError, ValueError):
            return None

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


class ScreenCapture:
    """MSS-based capture. Frames remain in memory and are never recorded."""

    def __init__(self, monitor_index: int = 1):
        self.monitor_index = monitor_index
        self._last_signature: np.ndarray | None = None

    @staticmethod
    def monitors() -> list[dict[str, int]]:
        with mss.mss() as grabber:
            return [dict(m) for m in grabber.monitors[1:]]

    def monitor_geometry(self) -> dict[str, int]:
        with mss.mss() as grabber:
            index = min(max(0, self.monitor_index), len(grabber.monitors) - 1)
            return dict(grabber.monitors[index])

    def capture(self, region: Region | None = None) -> np.ndarray:
        with mss.mss() as grabber:
            monitors = grabber.monitors
            index = min(max(0, self.monitor_index), len(monitors) - 1)
            target = region.to_dict() if region else dict(monitors[index])
            bgra = np.asarray(grabber.grab(target))
        return cv2.cvtColor(bgra, cv2.COLOR_BGRA2BGR)

    def has_changed(self, frame: np.ndarray, threshold: float = 0.003) -> bool:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        signature = cv2.resize(gray, (64, 64), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
        if self._last_signature is None:
            self._last_signature = signature
            return True
        difference = np.abs(signature - self._last_signature)
        score = float(np.mean(difference))
        # A chess move changes only one or two of 64 squares, so a global
        # average alone can miss it. Compare 8x8 spatial blocks as well.
        block_scores = np.array([
            difference[row * 8:(row + 1) * 8, col * 8:(col + 1) * 8].mean()
            for row in range(8) for col in range(8)
        ])
        local_change = float(np.partition(block_scores, -2)[-2]) if len(block_scores) >= 2 else 0.0
        if score >= threshold or local_change >= 0.025:
            self._last_signature = signature
            return True
        return False

