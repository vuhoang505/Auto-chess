from __future__ import annotations

import json
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any


DEFAULTS: dict[str, Any] = {
    "monitor": 0,
    "capture_mode": "window",
    "window_title": "",
    "window_handle": None,
    "scan_interval": 0.25,
    "change_threshold": 0.003,
    "board_region": None,
    "window_board_ratio": None,
    "orientation": "auto",
    "template_theme": "default",
    "recognition_threshold": 0.72,
    "auto_calibrate_start": True,
    "stockfish_path": "",
    "analysis_time": 0.3,
    "threads": 4,
    "hash_mb": 64,
    "multipv": 3,
    "performance_profile_version": 3,
    "safety_acknowledged": False,
}


class ConfigService:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._data = deepcopy(DEFAULTS)
        self.load()

    def load(self) -> dict[str, Any]:
        with self._lock:
            incoming: dict[str, Any] = {}
            if self.path.exists():
                try:
                    loaded = json.loads(self.path.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        incoming = loaded
                        self._data.update(loaded)
                except (json.JSONDecodeError, OSError):
                    pass
            # Upgrade the former default scan rate once. Explicitly slower
            # custom values remain untouched.
            if incoming:
                try:
                    profile_version = int(incoming.get("performance_profile_version", 1))
                except (TypeError, ValueError):
                    profile_version = 1
                if profile_version < 2:
                    try:
                        if abs(float(incoming.get("scan_interval", 0)) - 0.5) < 0.0001:
                            self._data["scan_interval"] = DEFAULTS["scan_interval"]
                    except (TypeError, ValueError):
                        pass
                if profile_version < 3:
                    try:
                        if int(incoming.get("hash_mb", 256)) == 256:
                            self._data["hash_mb"] = DEFAULTS["hash_mb"]
                    except (TypeError, ValueError):
                        pass
                self._data["performance_profile_version"] = DEFAULTS["performance_profile_version"]
            self._normalize()
            return deepcopy(self._data)

    def _normalize(self) -> None:
        def number(key: str, minimum: float, maximum: float, integer: bool = False) -> None:
            try:
                value = float(self._data[key])
            except (KeyError, TypeError, ValueError):
                value = float(DEFAULTS[key])
            value = min(maximum, max(minimum, value))
            self._data[key] = int(value) if integer else value

        number("monitor", 0, 16, True)
        number("scan_interval", 0.15, 3.0)
        number("change_threshold", 0.0001, 0.2)
        number("recognition_threshold", 0.3, 0.99)
        number("analysis_time", 0.05, 30.0)
        number("threads", 1, 64, True)
        number("hash_mb", 16, 32768, True)
        number("multipv", 1, 5, True)
        number("performance_profile_version", 1, 3, True)
        if self._data.get("capture_mode") not in ("window", "desktop"):
            self._data["capture_mode"] = DEFAULTS["capture_mode"]
        if self._data.get("orientation") not in ("auto", "white", "black"):
            self._data["orientation"] = DEFAULTS["orientation"]
        for key in ("window_title", "template_theme", "stockfish_path"):
            if not isinstance(self._data.get(key), str):
                self._data[key] = DEFAULTS[key]
        theme = self._data["template_theme"]
        if not theme or Path(theme).name != theme:
            self._data["template_theme"] = DEFAULTS["template_theme"]
        for key in ("auto_calibrate_start", "safety_acknowledged"):
            if not isinstance(self._data.get(key), bool):
                self._data[key] = DEFAULTS[key]
        try:
            self._data["window_handle"] = int(self._data["window_handle"]) if self._data.get("window_handle") else None
        except (TypeError, ValueError):
            self._data["window_handle"] = None
        ratio = self._data.get("window_board_ratio")
        if not isinstance(ratio, (list, tuple)) or len(ratio) != 4:
            self._data["window_board_ratio"] = None
        else:
            try:
                values = [float(value) for value in ratio]
                self._data["window_board_ratio"] = values if values[2] > 0 and values[3] > 0 else None
            except (TypeError, ValueError):
                self._data["window_board_ratio"] = None

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix(".tmp")
            temp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(self.path)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return deepcopy(self._data.get(key, default))

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value
            self._normalize()
            self.save()

    def update(self, values: dict[str, Any]) -> None:
        with self._lock:
            self._data.update(values)
            self._normalize()
            self.save()

    def as_dict(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._data)

