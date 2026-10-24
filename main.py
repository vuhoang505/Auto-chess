from __future__ import annotations

import os
import sys
import ctypes
import logging
from pathlib import Path

from PySide6.QtCore import QLockFile, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from services.config_service import ConfigService
from services.logging_service import configure_logging
from ui.main_window import MainWindow


def hide_packaged_console() -> None:
    """Hide only the console created by the console bootloader on Windows."""
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return
    console = ctypes.windll.kernel32.GetConsoleWindow()
    if console:
        ctypes.windll.user32.ShowWindow(console, 0)


def enable_dpi_awareness() -> None:
    """Keep MSS pixels and Win32 window coordinates in the same DPI space."""
    if os.name != "nt":
        return
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()


def install_exception_hook(log_file: Path) -> None:
    def report(exc_type, exc_value, traceback) -> None:
        logging.getLogger("chess_vision").critical(
            "Unhandled application error", exc_info=(exc_type, exc_value, traceback)
        )
        try:
            QMessageBox.critical(
                None,
                "Chess Vision Analyzer gặp lỗi",
                f"{exc_value}\n\nChi tiết đã được lưu tại:\n{log_file}",
            )
        except Exception:
            sys.__excepthook__(exc_type, exc_value, traceback)

    sys.excepthook = report


def main() -> int:
    hide_packaged_console()
    enable_dpi_awareness()
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    storage = (
        Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ChessVisionAnalyzer"
        if getattr(sys, "frozen", False) else root
    )
    storage.mkdir(parents=True, exist_ok=True)
    log_file = storage / "logs" / "chess_vision.log"
    configure_logging(log_file.parent)
    app = QApplication(sys.argv)
    install_exception_hook(log_file)
    app.setApplicationName("Chess Vision Analyzer")
    app.setOrganizationName("ChessVision")

    instance_lock = QLockFile(str(storage / "chess_vision.lock"))
    instance_lock.setStaleLockTime(30_000)
    if not instance_lock.tryLock(100):
        QMessageBox.information(
            None, "Chess Vision Analyzer", "Ứng dụng đang chạy. Hãy mở cửa sổ hiện có thay vì chạy thêm một bản."
        )
        return 0

    config = ConfigService(storage / "config.json")
    window = MainWindow(root, config, storage)
    window.show()

    if not config.get("safety_acknowledged", False):
        def show_safety_notice() -> None:
            box = QMessageBox(window)
            box.setWindowTitle("Sử dụng có trách nhiệm")
            box.setIcon(QMessageBox.Icon.Information)
            box.setText("Chess Vision Analyzer chỉ dành cho luyện tập, phân tích và chơi với máy.")
            box.setInformativeText(
                "Không dùng ứng dụng để nhận gợi ý trong trận đấu cạnh tranh trực tuyến. "
                "Ứng dụng không điều khiển chuột hoặc bàn phím."
            )
            box.setStandardButtons(QMessageBox.StandardButton.Ok)
            box.button(QMessageBox.StandardButton.Ok).setText("Đã hiểu")
            box.exec()
            config.set("safety_acknowledged", True)

        # Show the main window first so this first-run notice can never be
        # hidden behind another window and mistaken for a failed launch.
        QTimer.singleShot(0, show_safety_notice)
    exit_code = app.exec()
    instance_lock.unlock()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

