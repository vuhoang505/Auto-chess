from __future__ import annotations

from PySide6.QtWidgets import QApplication

from core.screen_capture import Region
from core.window_capture import WindowInfo
from services.config_service import ConfigService
from ui.main_window import MainWindow


def test_source_selector_distinguishes_duplicate_window_titles(monkeypatch, tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    windows = [
        WindowInfo(101, "Chess Board - Browser", Region(0, 0, 1000, 800)),
        WindowInfo(202, "Chess Board - Browser", Region(20, 20, 1000, 800)),
    ]
    monkeypatch.setattr("ui.main_window.list_windows", lambda: windows)
    config = ConfigService(tmp_path / "config.json")
    window = MainWindow(tmp_path, config, tmp_path)
    try:
        assert not window.start_button.isEnabled()
        assert window.start_button.text() == "Chọn nguồn"
        values = [window.source_combo.itemData(index) for index in range(window.source_combo.count())]
        assert "window:101" in values
        assert "window:202" in values
        labels = [window.source_combo.itemText(index) for index in range(window.source_combo.count())]
        assert any("[65]" in label for label in labels)
        assert any("[CA]" in label for label in labels)
        config.update({"capture_mode": "desktop"})
        window._update_capture_controls()
        assert window.start_button.isEnabled()
        window._running = True
        window._update_capture_controls()
        assert not window.start_button.isEnabled()
        assert window.start_button.text() == "Đang chạy ✓"
        assert window.pause_button.isEnabled()
        assert window.stop_button.isEnabled()
    finally:
        window.close()
        app.processEvents()
