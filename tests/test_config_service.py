from __future__ import annotations

import json

from services.config_service import ConfigService


def test_invalid_values_are_normalized(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "scan_interval": -5,
        "threads": "invalid",
        "orientation": "sideways",
        "capture_mode": "unknown",
        "window_board_ratio": [0, 0, -1, 0],
    }), encoding="utf-8")
    config = ConfigService(path)
    assert config.get("scan_interval") == 0.15
    assert config.get("threads") == 4
    assert config.get("orientation") == "auto"
    assert config.get("capture_mode") == "window"
    assert config.get("window_board_ratio") is None


def test_legacy_default_scan_rate_is_upgraded(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"scan_interval": 0.5}), encoding="utf-8")
    config = ConfigService(path)
    assert config.get("scan_interval") == 0.25
    assert config.get("hash_mb") == 64
    assert config.get("performance_profile_version") == 3
