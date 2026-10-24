from __future__ import annotations

import logging
import shutil
from pathlib import Path

import cv2
import chess
import numpy as np
from PySide6.QtCore import QObject, QPoint, QRect, QSize, Qt, QMetaObject, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QIcon, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QGraphicsDropShadowEffect, QInputDialog, QPushButton, QSplitter, QStatusBar, QVBoxLayout, QWidget,
)

from core.analysis_manager import AnalysisManager
from core.board_detector import BoardDetector
from core.piece_recognizer import PieceRecognizer, RecognitionResult
from core.fen_builder import placement_from_pieces
from core.position_tracker import PositionTracker, TrackResult
from core.screen_capture import Region, ScreenCapture
from core.stockfish_engine import AnalysisLine, StockfishEngine
from core.window_capture import WindowInfo, find_window, get_window, list_windows
from services.config_service import ConfigService
from services.history_service import HistoryService
from ui.analysis_panel import AnalysisPanel
from ui.chess_board import ChessBoardWidget
from ui.history_dialog import GameHistoryDialog
from ui.settings_dialog import PositionMetadataDialog, SettingsDialog

logger = logging.getLogger(__name__)


class CaptureWorker(QObject):
    board_image = Signal(object)
    recognized = Signal(object)
    status = Signal(str)
    failed = Signal(str)
    region_changed = Signal(object)
    window_ratio_changed = Signal(object)
    window_resolved = Signal(object)
    orientation_detected = Signal(str)

    def __init__(self, templates_root: Path, settings: dict):
        super().__init__()
        self.settings = settings
        self.capture = ScreenCapture(int(settings["monitor"]))
        self.detector = BoardDetector()
        self.recognizer = PieceRecognizer(
            templates_root, settings["template_theme"],
            float(settings["recognition_threshold"]),
        )
        self.region = Region.from_dict(settings.get("board_region"))
        self.timer: QTimer | None = None
        self.paused = False
        saved_ratio = settings.get("window_board_ratio")
        self._window_board_ratio: tuple[float, float, float, float] | None = None
        if isinstance(saved_ratio, (list, tuple)) and len(saved_ratio) == 4:
            ratio = tuple(float(value) for value in saved_ratio)
            if ratio[2] > 0 and ratio[3] > 0:
                self._window_board_ratio = ratio
        self._window_board_misses = 0
        self._followup_scans = 0
        saved_handle = settings.get("window_handle")
        self._window_handle: int | None = int(saved_handle) if saved_handle else None
        self._window_title = str(settings.get("window_title", ""))
        self._saved_orientation: str | None = None
        if self.settings["orientation"] == "auto" and self.recognizer.calibrated_orientation:
            self.settings["orientation"] = self.recognizer.calibrated_orientation
            self._saved_orientation = self.recognizer.calibrated_orientation

    @Slot()
    def start(self) -> None:
        if self._saved_orientation:
            self.orientation_detected.emit(self._saved_orientation)
        if self.timer is None:
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.scan)
        self.timer.start(max(150, int(float(self.settings["scan_interval"]) * 1000)))
        self.scan()

    @Slot()
    def scan(self) -> None:
        if self.paused:
            return
        try:
            capture_mode = self.settings.get("capture_mode", "window")
            selected_title = self._window_title
            if capture_mode == "window" and not selected_title:
                self.status.emit("Hãy chọn cửa sổ đang hiển thị bàn cờ trong Nguồn đọc")
                return
            window_mode = capture_mode == "window"
            selected_window = get_window(self._window_handle) if window_mode and self._window_handle else None
            if window_mode and selected_window is None:
                selected_window = find_window(selected_title)
            if selected_window:
                changed_identity = (
                    self._window_handle != selected_window.handle or self._window_title != selected_window.title
                )
                self._window_handle = selected_window.handle
                self._window_title = selected_window.title
                if changed_identity:
                    self.window_resolved.emit({"handle": selected_window.handle, "title": selected_window.title})
            if window_mode and selected_window is None:
                self.status.emit("Không tìm thấy cửa sổ đã chọn — hãy chọn lại nguồn")
                return
            direct_window_board = False
            if selected_window and self._window_board_ratio:
                rx, ry, rw, rh = self._window_board_ratio
                window_region = selected_window.region
                source_region = Region(
                    window_region.left + int(window_region.width * rx),
                    window_region.top + int(window_region.height * ry),
                    max(120, int(window_region.width * rw)),
                    max(120, int(window_region.height * rh)),
                )
                direct_window_board = True
            else:
                source_region = selected_window.region if selected_window else self.region
            frame = self.capture.capture(source_region)
            changed = self.capture.has_changed(frame, float(self.settings["change_threshold"]))
            if changed:
                # Always inspect two follow-up frames. If the first scan lands
                # in the middle of a piece/castling animation, the stable final
                # board is still processed even when its pixel delta is small.
                self._followup_scans = 2
            elif self._followup_scans > 0:
                self._followup_scans -= 1
            else:
                return
            if selected_window:
                if direct_window_board:
                    side = min(frame.shape[:2])
                    board = frame[:side, :side].copy()
                else:
                    detection, scale = self._detect_fast(frame)
                    if detection is None:
                        self.status.emit("Không tìm thấy bàn cờ trong cửa sổ đã chọn")
                        return
                    board = detection.image
                    x, y, width, height = detection.bbox
                    actual_x, actual_y = int(x / scale), int(y / scale)
                    actual_width, actual_height = int(width / scale), int(height / scale)
                    window_region = selected_window.region
                    self._window_board_ratio = (
                        actual_x / window_region.width, actual_y / window_region.height,
                        actual_width / window_region.width, actual_height / window_region.height,
                    )
                    self.window_ratio_changed.emit(self._window_board_ratio)
                    board_region = Region(
                        window_region.left + actual_x, window_region.top + actual_y,
                        actual_width, actual_height,
                    )
                    self.region_changed.emit(board_region)
            elif self.region:
                side = min(frame.shape[:2])
                board = frame[:side, :side].copy()
            else:
                detection, scale = self._detect_fast(frame)
                if detection is None:
                    self.status.emit("Không tìm thấy bàn cờ — hãy hiệu chỉnh vùng")
                    return
                board = detection.image
                monitor = self.capture.monitor_geometry()
                x, y, width, height = detection.bbox
                self.region = Region(
                    monitor["left"] + int(x / scale), monitor["top"] + int(y / scale),
                    int(width / scale), int(height / scale),
                )
                self.region_changed.emit(self.region)

            board_like = self._board_score(board) >= 0.11
            if selected_window and direct_window_board and not board_like:
                # Highlights and piece animations can temporarily lower the
                # grid score. Do not throw away a good crop after one noisy
                # frame, otherwise detection alternates between the whole
                # window and the board and the UI appears to jump.
                self._window_board_misses += 1
                if self._window_board_misses >= 3:
                    self._window_board_ratio = None
                    self.window_ratio_changed.emit(None)
                    self._window_board_misses = 0
                    self.status.emit("Vùng bàn không còn khớp — đang tìm lại trong cửa sổ")
                return
            if selected_window and direct_window_board:
                self._window_board_misses = 0
            self.board_image.emit(board)
            if not self.recognizer.calibrated and self.settings.get("auto_calibrate_start", True):
                is_start, orientation, confidence = self.recognizer.infer_start_position(
                    board, self.settings.get("orientation", "auto")
                )
                if is_start:
                    self.recognizer.calibrate_from_start(board, orientation)
                    self.settings["orientation"] = orientation
                    self.orientation_detected.emit(orientation)
                    self.status.emit(f"Đã tự hiệu chỉnh thế xuất phát ({confidence * 100:.0f}%)")
            result = self.recognizer.recognize(board, self.settings["orientation"])
            if not selected_window and self.region and not board_like and self.recognizer.calibrated:
                # Reacquire only after the calibrated crop stops matching. This
                # follows a browser/window that was moved or resized without
                # continuously processing the entire monitor.
                full = self.capture.capture(None)
                detection = self.detector.detect(full)
                if detection is not None:
                    retry = self.recognizer.recognize(detection.image, self.settings["orientation"])
                    if retry.confidence > result.confidence and not retry.needs_calibration:
                        monitor = self.capture.monitor_geometry()
                        x, y, width, height = detection.bbox
                        self.region = Region(monitor["left"] + x, monitor["top"] + y, width, height)
                        self.region_changed.emit(self.region)
                        self.board_image.emit(detection.image)
                        result = retry
            self.recognized.emit(result)
        except Exception as exc:
            logger.exception("Capture pipeline failed")
            self.failed.emit(str(exc))

    def _detect_fast(self, frame: np.ndarray):
        height, width = frame.shape[:2]
        scale = min(1.0, 1400.0 / max(height, width))
        work = frame if scale == 1.0 else cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        detector = BoardDetector(min_size=max(120, int(self.detector.min_size * scale)))
        return detector.detect(work), scale

    def _board_score(self, board: np.ndarray) -> float:
        gray = cv2.cvtColor(cv2.resize(board, (320, 320)), cv2.COLOR_BGR2GRAY)
        return self.detector._grid_score(gray)

    @Slot(bool)
    def set_paused(self, paused: bool) -> None:
        self.paused = paused

    @Slot()
    def stop(self) -> None:
        if self.timer:
            self.timer.stop()


class RegionOverlay(QWidget):
    selected = Signal(object)
    cancelled = Signal()

    def __init__(self, geometry: QRect, physical_monitor: dict[str, int]):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(geometry)
        self.physical_monitor = physical_monitor
        self.origin: QPoint | None = None
        self.current: QPoint | None = None

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.origin = event.position().toPoint()
            self.current = self.origin
            self.update()

    def mouseMoveEvent(self, event) -> None:
        if self.origin:
            self.current = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self.origin and self.current:
            rect = QRect(self.origin, event.position().toPoint()).normalized()
            if rect.width() >= 120 and rect.height() >= 120:
                side = min(rect.width(), rect.height())
                scale_x = self.physical_monitor["width"] / max(1, self.width())
                scale_y = self.physical_monitor["height"] / max(1, self.height())
                physical_side = int(min(side * scale_x, side * scale_y))
                left = self.physical_monitor["left"] + int(rect.left() * scale_x)
                top = self.physical_monitor["top"] + int(rect.top() * scale_y)
                self.selected.emit(Region(left, top, physical_side, physical_side))
                self.close()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            self.close()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(4, 8, 18, 145))
        if self.origin and self.current:
            rect = QRect(self.origin, self.current).normalized()
            side = min(rect.width(), rect.height())
            rect.setSize(QRect(0, 0, side, side).size())
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(rect, Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setPen(QPen(QColor("#35e6ed"), 3))
            painter.drawRect(rect)


class MainWindow(QMainWindow):
    pause_requested = Signal(bool)
    stop_requested = Signal()

    def __init__(self, root: Path, config: ConfigService, storage_root: Path | None = None):
        super().__init__()
        self.root = root
        self.storage_root = storage_root or root
        self.templates_root = self.storage_root / "assets" / "piece_templates"
        self._ensure_packaged_templates()
        self.config = config
        self.history_service = HistoryService(self.storage_root / "data" / "history.db")
        self.tracker = PositionTracker()
        self.current_board_image: np.ndarray | None = None
        self._metadata_open = False
        self._overlay: RegionOverlay | None = None
        self._thread: QThread | None = None
        self._worker: CaptureWorker | None = None
        self._running = False
        self._paused = False
        self._last_submitted_fen: str | None = None
        self.current_game_id: int | None = None
        self._source_windows: dict[int, WindowInfo] = {}
        self._build_ui()
        self.analysis.load_moves(self.history_service.recent_moves())
        self._load_style()
        self._create_analysis_manager()
        self.setMinimumSize(1150, 680)
        self.resize(1280, 760)
        self.setWindowTitle("Chess Vision Analyzer")
        self.setWindowIcon(QIcon(str(self.root / "assets" / "icons" / "target.svg")))
        QTimer.singleShot(600, self.start_capture)

    def _ensure_packaged_templates(self) -> None:
        bundled = self.root / "assets" / "piece_templates"
        if bundled.resolve() == self.templates_root.resolve() or not bundled.exists():
            return
        theme = "default"
        target_manifest = self.templates_root / theme / "manifest.json"
        source_theme = bundled / theme
        if target_manifest.exists() or not source_theme.exists():
            return
        try:
            shutil.copytree(source_theme, self.templates_root / theme, dirs_exist_ok=True)
        except OSError:
            logger.exception("Could not initialize packaged piece templates")

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("appShell")
        outer = QVBoxLayout(central)
        outer.setContentsMargins(22, 18, 22, 18)
        outer.setSpacing(14)

        hero = QFrame()
        hero.setObjectName("heroCard")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(20, 12, 20, 12)
        brand_orb = QLabel("♞")
        brand_orb.setObjectName("brandOrb")
        brand_orb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_orb.setFixedSize(58, 58)
        title_box = QVBoxLayout()
        title = QLabel("CHESS VISION ANALYZER")
        title.setObjectName("appTitle")
        subtitle = QLabel("REAL-TIME VISION  /  STOCKFISH INTELLIGENCE  /  100% LOCAL")
        subtitle.setObjectName("subtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        mode_badge = QLabel("●  OFFLINE ENGINE")
        mode_badge.setObjectName("modeBadge")
        mode_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(brand_orb)
        hero_layout.addSpacing(14)
        hero_layout.addLayout(title_box)
        hero_layout.addStretch()
        hero_layout.addWidget(mode_badge)
        self._add_shadow(hero, 36, 8, QColor(0, 0, 0, 145))
        outer.addWidget(hero)

        source_card = QFrame()
        source_card.setObjectName("sourceCard")
        source_bar = QHBoxLayout(source_card)
        source_bar.setContentsMargins(14, 10, 14, 10)
        source_bar.setSpacing(9)
        source_label = QLabel("NGUỒN NHẬN DIỆN")
        source_label.setObjectName("toolbarLabel")
        source_bar.addWidget(source_label)
        self.capture_state = QLabel("● Đã dừng")
        self.capture_state.setObjectName("captureStatus")
        self.vision_state = QLabel("Nhận dạng: chờ")
        self.vision_state.setObjectName("visionStatus")
        self.engine_state = QLabel("Stockfish: đang kiểm tra")
        self.engine_state.setObjectName("engineStatus")
        # Status text changes often. Fixed slots prevent the source selector
        # and the rest of the header from shifting on every scan.
        self.capture_state.setFixedWidth(126)
        self.vision_state.setFixedWidth(225)
        self.engine_state.setFixedWidth(176)
        self.source_combo = QComboBox()
        self.source_combo.setObjectName("sourceSelector")
        self.source_combo.setMinimumWidth(280)
        self.source_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.source_combo.setMinimumContentsLength(28)
        self.source_combo.setToolTip("Chọn cửa sổ trình duyệt đang hiển thị tab bàn cờ")
        self.source_combo.currentIndexChanged.connect(self._source_selected)
        refresh_source = QPushButton()
        refresh_source.setObjectName("iconButton")
        refresh_source.setIcon(QIcon(str(self.root / "assets" / "icons" / "refresh.svg")))
        refresh_source.setIconSize(QSize(18, 18))
        refresh_source.setToolTip("Làm mới danh sách cửa sổ")
        refresh_source.setFixedSize(40, 40)
        refresh_source.clicked.connect(self._refresh_sources)
        source_bar.addWidget(self.source_combo, 1)
        source_bar.addWidget(refresh_source)
        source_bar.addStretch()
        source_bar.addWidget(self.capture_state)
        source_bar.addWidget(self.vision_state)
        source_bar.addWidget(self.engine_state)
        self._add_shadow(source_card, 28, 7, QColor(0, 0, 0, 125))
        outer.addWidget(source_card)

        content = QSplitter(Qt.Orientation.Horizontal)
        content.setObjectName("mainSplitter")
        left = QFrame()
        left.setObjectName("boardPanel")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(16, 14, 16, 14)
        left_layout.setSpacing(9)
        board_header = QHBoxLayout()
        board_title = QLabel("LIVE VISION BOARD")
        board_title.setObjectName("panelTitle")
        live_badge = QLabel("●  LIVE")
        live_badge.setObjectName("liveBadge")
        board_header.addWidget(board_title)
        board_header.addStretch()
        board_header.addWidget(live_badge)
        left_layout.addLayout(board_header)
        self.board = ChessBoardWidget()
        self.board.set_orientation(self.config.get("orientation", "white"))
        left_layout.addWidget(self.board, 1)
        board_info = QHBoxLayout()
        self.confidence = QLabel("Độ tin cậy: —")
        self.confidence.setObjectName("infoPill")
        self.confidence.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.game_state = QLabel("Ván cờ: chờ đồng bộ")
        self.game_state.setObjectName("infoPill")
        self.game_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        board_info.addWidget(self.confidence)
        board_info.addWidget(self.game_state, 1)
        left_layout.addLayout(board_info)
        content.addWidget(left)

        right = QFrame()
        right.setObjectName("analysisPanel")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(14, 14, 14, 14)
        self.analysis = AnalysisPanel()
        right_layout.addWidget(self.analysis)
        content.addWidget(right)
        self._add_shadow(left, 36, 10, QColor(0, 0, 0, 155))
        self._add_shadow(right, 36, 10, QColor(0, 0, 0, 155))
        content.setStretchFactor(0, 6)
        content.setStretchFactor(1, 5)
        content.setChildrenCollapsible(False)
        content.setSizes([620, 500])
        outer.addWidget(content, 1)

        control_dock = QFrame()
        control_dock.setObjectName("controlDock")
        controls = QHBoxLayout(control_dock)
        controls.setContentsMargins(13, 10, 13, 10)
        controls.setSpacing(8)
        self.start_button = QPushButton("Bắt đầu")
        self.start_button.setObjectName("primary")
        self.pause_button = QPushButton("Tạm dừng")
        self.stop_button = QPushButton("Dừng")
        self.calibrate_button = QPushButton("Hiệu chỉnh")
        self.settings_button = QPushButton("Cài đặt")
        self.save_game_button = QPushButton("Lưu ván")
        self.history_button = QPushButton("Lịch sử ván")
        for button, icon in (
            (self.start_button, "play.svg"), (self.pause_button, "pause.svg"),
            (self.stop_button, "stop.svg"), (self.calibrate_button, "target.svg"),
            (self.settings_button, "settings.svg"), (self.save_game_button, "save.svg"),
            (self.history_button, "history.svg"),
        ):
            button.setIcon(QIcon(str(self.root / "assets" / "icons" / icon)))
            button.setIconSize(QSize(18, 18))
        for button in (
            self.start_button, self.pause_button, self.stop_button, self.calibrate_button,
            self.settings_button, self.save_game_button, self.history_button,
        ):
            button.setMinimumHeight(42)
        self.start_button.clicked.connect(self.start_capture)
        self.pause_button.clicked.connect(self.toggle_pause)
        self.stop_button.clicked.connect(self.stop_capture)
        self.calibrate_button.clicked.connect(self.recalibrate)
        self.settings_button.clicked.connect(self.open_settings)
        self.save_game_button.clicked.connect(self.save_current_game)
        self.history_button.clicked.connect(self.open_game_history)
        for button in (
            self.start_button, self.pause_button, self.stop_button, self.calibrate_button,
            self.settings_button,
        ):
            controls.addWidget(button)
        divider = QFrame()
        divider.setObjectName("dockDivider")
        divider.setFrameShape(QFrame.Shape.VLine)
        controls.addWidget(divider)
        controls.addWidget(self.save_game_button)
        controls.addWidget(self.history_button)
        controls.addStretch()
        self._add_shadow(control_dock, 30, 8, QColor(0, 0, 0, 145))
        outer.addWidget(control_dock)
        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Sẵn sàng. Chọn vùng bàn cờ hoặc nhấn Start để tự phát hiện.")
        self._refresh_sources()
        self._update_capture_controls()

    @staticmethod
    def _add_shadow(widget: QWidget, blur: int, y_offset: int, color: QColor) -> None:
        shadow = QGraphicsDropShadowEffect(widget)
        shadow.setBlurRadius(blur)
        shadow.setOffset(0, y_offset)
        shadow.setColor(color)
        widget.setGraphicsEffect(shadow)

    def _load_style(self) -> None:
        try:
            self.setStyleSheet((self.root / "ui" / "styles.qss").read_text(encoding="utf-8"))
        except OSError:
            pass

    def _create_analysis_manager(self) -> None:
        if hasattr(self, "analysis_manager"):
            self.analysis_manager.shutdown()
        configured_path = self.config.get("stockfish_path", "")
        engine = StockfishEngine(configured_path, self.config.get("threads", 2), self.config.get("hash_mb", 256))
        discovered = engine.discover(configured_path)
        self.engine_state.setText("Stockfish: sẵn sàng" if discovered else "Stockfish: chưa cài")
        self.analysis_manager = AnalysisManager(engine)
        self.analysis_manager.preview.connect(self._analysis_preview)
        self.analysis_manager.completed.connect(self._analysis_done)
        self.analysis_manager.failed.connect(self._analysis_failed)
        self.analysis_manager.busy_changed.connect(self._analysis_busy_changed)

    @Slot()
    def start_capture(self) -> None:
        if self.config.get("capture_mode", "window") == "window" and not self.config.get("window_title", ""):
            self._running = False
            self.capture_state.setText("● Chờ nguồn")
            self.statusBar().showMessage("Hãy chọn cửa sổ Chrome/Edge đang hiển thị bàn cờ")
            self._update_capture_controls()
            return
        if self._thread and self._thread.isRunning():
            self._paused = False
            self.pause_requested.emit(False)
            self.capture_state.setText("● Đang quét")
            self._update_capture_controls()
            return
        self._thread = QThread(self)
        self._worker = CaptureWorker(self.templates_root, self.config.as_dict())
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.start)
        self.pause_requested.connect(self._worker.set_paused, Qt.ConnectionType.QueuedConnection)
        self.stop_requested.connect(self._worker.stop, Qt.ConnectionType.QueuedConnection)
        self._worker.board_image.connect(self._set_board_image)
        self._worker.recognized.connect(self._recognition_ready)
        self._worker.status.connect(self.statusBar().showMessage)
        self._worker.failed.connect(self._capture_failed)
        self._worker.region_changed.connect(self._tracked_region_changed)
        self._worker.window_ratio_changed.connect(self._window_ratio_changed)
        self._worker.window_resolved.connect(self._window_resolved)
        self._worker.orientation_detected.connect(self._orientation_detected)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.start()
        self._running = True
        self.capture_state.setText("● Đang quét")
        self._update_capture_controls()

    @Slot()
    def toggle_pause(self) -> None:
        if not self._running:
            return
        self._paused = not self._paused
        self.pause_requested.emit(self._paused)
        self.pause_button.setText("Resume" if self._paused else "Pause")
        self.pause_button.setIcon(QIcon(str(self.root / "assets" / "icons" / ("play.svg" if self._paused else "pause.svg"))))
        self.capture_state.setText("● Tạm dừng" if self._paused else "● Đang quét")
        self.statusBar().showMessage("Đã tạm dừng nhận dạng" if self._paused else "Đã tiếp tục nhận dạng")
        self._update_capture_controls()

    @Slot()
    def stop_capture(self) -> None:
        if self._running:
            self.capture_state.setText("● Đang dừng…")
            self.stop_button.setText("Đang dừng…")
            self.stop_button.setEnabled(False)
            self.capture_state.repaint()
            self.stop_button.repaint()
        self.analysis_manager.cancel_pending()
        if self.engine_state.text() == "Stockfish: đang nghĩ":
            self.engine_state.setText("Stockfish: sẵn sàng")
        if self._thread and self._thread.isRunning():
            if self._worker:
                # Wait until an in-progress OpenCV scan returns, then stop its
                # timer inside the worker thread before quitting that thread.
                QMetaObject.invokeMethod(
                    self._worker, "stop", Qt.ConnectionType.BlockingQueuedConnection
                )
            self._thread.quit()
            self._thread.wait(5000)
        if self._thread:
            self._thread.deleteLater()
        self._thread = None
        self._worker = None
        self._running = False
        self._paused = False
        self.capture_state.setText("● Đã dừng")
        self.statusBar().showMessage("Đã dừng nhận dạng và hủy lượt phân tích đang chờ")
        self._update_capture_controls()

    def _update_capture_controls(self) -> None:
        if not hasattr(self, "start_button"):
            return
        has_source = (
            self.config.get("capture_mode", "window") == "desktop"
            or bool(self.config.get("window_title", ""))
        )
        self.start_button.setEnabled(not self._running and has_source)
        self.start_button.setText("Đang chạy ✓" if self._running else ("Bắt đầu" if has_source else "Chọn nguồn"))
        self.pause_button.setEnabled(self._running)
        self.pause_button.setText("Tiếp tục ▶" if self._paused else "Tạm dừng")
        self.stop_button.setEnabled(self._running)
        self.stop_button.setText("Dừng")
        self.save_game_button.setEnabled(self.tracker.board is not None)
        capture_mode = "paused" if self._paused else ("running" if self._running else "idle")
        self.capture_state.setProperty("state", capture_mode)
        self.capture_state.style().unpolish(self.capture_state)
        self.capture_state.style().polish(self.capture_state)
        for button, active in (
            (self.start_button, self._running and not self._paused),
            (self.pause_button, self._paused),
            (self.stop_button, False),
        ):
            button.setProperty("active", active)
            button.style().unpolish(button)
            button.style().polish(button)

    @Slot(object)
    def _set_board_image(self, image: np.ndarray) -> None:
        self.current_board_image = image.copy()

    @Slot(object)
    def _recognition_ready(self, result: RecognitionResult) -> None:
        self.confidence.setText(f"Độ tin cậy: {result.confidence * 100:.1f}%")
        placement = placement_from_pieces(result.pieces)

        # A low global confidence is common while chess sites draw last-move
        # highlights. Once a game is synchronized, legality is the stronger
        # filter: only one legal move may produce the observed piece map.
        if self.tracker.board is None:
            is_standard_start = placement == chess.Board().board_fen()
            saved_state = None if is_standard_start else self.history_service.find_latest_state(placement)
            if saved_state:
                saved_fen, saved_game_id = saved_state
                restored = self.tracker.restore(saved_fen)
                if restored.accepted:
                    self.current_game_id = saved_game_id
                    self.statusBar().showMessage("Đã đồng bộ trạng thái từ lịch sử gần nhất")
            if self.tracker.board is None and result.needs_calibration and not is_standard_start:
                self.vision_state.setText("Nhận dạng: cần khung ổn định")
                self.statusBar().showMessage(result.reason)
                return

        if self.tracker.board is not None and self.current_game_id is None:
            self.current_game_id = self.history_service.create_game(self.tracker.board.fen())

        tracked = self.tracker.update(result.pieces)
        if tracked.needs_metadata:
            self._ask_metadata(result)
            return
        if not tracked.accepted:
            self.vision_state.setText("Nhận dạng: chờ ổn định" if result.needs_calibration else "Nhận dạng: vị trí không hợp lệ")
            self.statusBar().showMessage(
                f"{tracked.reason}; đang chờ animation kết thúc" if result.needs_calibration else tracked.reason
            )
            return
        self._apply_accepted_position(tracked, result)

    def _apply_accepted_position(self, tracked: TrackResult, result: RecognitionResult) -> None:
        # Render only a position accepted by the chess rules. Raw recognition
        # frames can be incomplete during animation and must never replace the
        # last stable board shown to the user.
        self.board.set_position(self.tracker.pieces)
        self._update_capture_controls()
        self.vision_state.setText("Nhận dạng: hợp lệ" + (" · confidence thấp" if result.needs_calibration else ""))
        if tracked.new_game:
            if self.current_game_id:
                self.history_service.finish_game(self.current_game_id, self.tracker.outcome_text)
            self.current_game_id = self.history_service.create_game(tracked.fen or chess.STARTING_FEN)
            self.analysis.start_new_game()
        elif self.current_game_id is None and tracked.fen:
            self.current_game_id = self.history_service.create_game(tracked.fen)
        for detected in tracked.detected_moves:
            self.analysis.add_move(detected.ply, detected.san)
            self.history_service.add_move(
                detected.fen, detected.uci, detected.san, detected.ply, self.current_game_id
            )
            logger.info(
                "Accepted move %s (%s), recognition confidence %.3f",
                detected.san, detected.uci, result.confidence,
            )
        if self.tracker.board:
            turn = "Trắng" if self.tracker.board.turn == chess.WHITE else "Đen"
            outcome = self.tracker.outcome_text
            self.game_state.setText(f"{outcome} · Lượt: {turn}" if outcome else f"Lượt đi: {turn}")
            if self.tracker.board.is_game_over(claim_draw=True):
                self.history_service.finish_game(self.current_game_id, outcome or self.tracker.board.result(claim_draw=True))
                self.analysis.clear_result()
                self.board.set_arrow(None, None)
                self._last_submitted_fen = tracked.fen
                self.statusBar().showMessage(outcome or "Ván cờ đã kết thúc")
                return
        if tracked.fen and tracked.fen != self._last_submitted_fen:
            self._last_submitted_fen = tracked.fen
            self.board.set_arrow(None, None)
            self.analysis.set_busy()
            self.engine_state.setText("Stockfish: đang nghĩ")
            self.analysis_manager.submit(
                tracked.fen, float(self.config.get("analysis_time", 1.0)), int(self.config.get("multipv", 3))
            )

    def _ask_metadata(self, result: RecognitionResult) -> None:
        if self._metadata_open:
            return
        self._metadata_open = True
        dialog = PositionMetadataDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            tracked = self.tracker.initialize(
                result.pieces,
                dialog.turn.currentData(),
                dialog.castling.text().strip() or "-",
                dialog.en_passant.text().strip() or "-",
            )
            if tracked.accepted and tracked.fen:
                self._apply_accepted_position(tracked, result)
            else:
                QMessageBox.warning(self, "Vị trí không hợp lệ", tracked.reason)
        self._metadata_open = False

    @Slot(str, object)
    def _analysis_preview(self, fen: str, results: list[AnalysisLine]) -> None:
        if fen != self._last_submitted_fen:
            return
        self.analysis.set_results(results)
        if results:
            first = results[0]
            self.board.set_arrow(first.from_square, first.to_square)
            self.engine_state.setText("Stockfish: đang tinh chỉnh")
            self.statusBar().showMessage(f"Gợi ý nhanh: {first.move_san} · {first.evaluation}")

    @Slot(bool)
    def _analysis_busy_changed(self, busy: bool) -> None:
        if busy:
            self.statusBar().showMessage("Stockfish đang phân tích…")

    @Slot(str, object)
    def _analysis_done(self, fen: str, results: list[AnalysisLine]) -> None:
        if fen != self._last_submitted_fen:
            return
        self.engine_state.setText("Stockfish: sẵn sàng")
        self.analysis.set_results(results)
        if results:
            first = results[0]
            self.board.set_arrow(first.from_square, first.to_square)
            self.history_service.add(
                fen, first.move_san, first.evaluation, first.depth, self.current_game_id
            )
            logger.info("Stockfish result for %s: %s %s depth %s", fen, first.move_san, first.evaluation, first.depth)
            self.statusBar().showMessage(f"Stockfish: {first.move_san} · {first.evaluation} · depth {first.depth}")

    @Slot(str, str)
    def _analysis_failed(self, fen: str, message: str) -> None:
        if fen != self._last_submitted_fen:
            return
        self._last_submitted_fen = None
        self.engine_state.setText("Stockfish: lỗi")
        self.statusBar().showMessage(message)
        self.analysis.set_error(message)

    @Slot(str)
    def _capture_failed(self, message: str) -> None:
        self.capture_state.setText("● Lỗi chụp màn hình")
        self.statusBar().showMessage(message)

    @Slot()
    def recalibrate(self) -> None:
        choice = QMessageBox(self)
        choice.setWindowTitle("Hiệu chỉnh")
        choice.setText("Chọn loại hiệu chỉnh")
        region_button = choice.addButton("Chọn vùng bàn cờ", QMessageBox.ButtonRole.AcceptRole)
        template_button = choice.addButton("Tạo template từ thế xuất phát", QMessageBox.ButtonRole.ActionRole)
        choice.addButton(QMessageBox.StandardButton.Cancel)
        choice.exec()
        if choice.clickedButton() is template_button:
            self._calibrate_templates()
        elif choice.clickedButton() is region_button:
            self._select_region()

    def _select_region(self) -> None:
        was_running = self._running
        self.stop_capture()
        screens = QApplication.screens()
        index = min(max(0, int(self.config.get("monitor", 1)) - 1), len(screens) - 1)
        physical_monitors = ScreenCapture.monitors()
        physical = physical_monitors[min(index, len(physical_monitors) - 1)]
        self._overlay = RegionOverlay(screens[index].geometry(), physical)
        self._overlay.selected.connect(self._region_selected)
        if was_running:
            self._overlay.cancelled.connect(self.start_capture)
        self._overlay.show()
        self._overlay.activateWindow()

    @Slot(object)
    def _region_selected(self, region: Region) -> None:
        values: dict = {"board_region": region.to_dict()}
        if self.config.get("capture_mode") == "window":
            handle = self.config.get("window_handle")
            window = get_window(handle) if handle else None
            if window is None:
                window = find_window(self.config.get("window_title", ""))
            inside_window = window and (
                region.left >= window.region.left
                and region.top >= window.region.top
                and region.left + region.width <= window.region.left + window.region.width
                and region.top + region.height <= window.region.top + window.region.height
            )
            if inside_window and window:
                values["window_board_ratio"] = [
                    (region.left - window.region.left) / max(1, window.region.width),
                    (region.top - window.region.top) / max(1, window.region.height),
                    region.width / max(1, window.region.width),
                    region.height / max(1, window.region.height),
                ]
            else:
                values.update({
                    "capture_mode": "desktop", "window_title": "", "window_handle": None,
                    "window_board_ratio": None,
                })
        self.config.update(values)
        self._refresh_sources()
        self.statusBar().showMessage("Đã lưu vùng bàn cờ. Có thể hiệu chỉnh template từ thế xuất phát.")
        self.start_capture()

    @Slot(object)
    def _tracked_region_changed(self, region: Region) -> None:
        if self.config.get("board_region") != region.to_dict():
            self.config.set("board_region", region.to_dict())
            self.statusBar().showMessage("Đã tự cập nhật vùng khi cửa sổ bàn cờ di chuyển/đổi kích thước.")

    @Slot(object)
    def _window_ratio_changed(self, ratio) -> None:
        value = list(ratio) if ratio is not None else None
        if self.config.get("window_board_ratio") != value:
            self.config.set("window_board_ratio", value)

    @Slot(object)
    def _window_resolved(self, identity: dict) -> None:
        handle = identity.get("handle")
        title = identity.get("title", "")
        if self.config.get("window_handle") != handle or self.config.get("window_title") != title:
            self.config.update({"window_handle": handle, "window_title": title})

    @Slot(str)
    def _orientation_detected(self, orientation: str) -> None:
        self.config.set("orientation", orientation)
        self.board.set_orientation(orientation)
        self.statusBar().showMessage(
            "Đã tự nhận hướng: " + ("Trắng ở dưới" if orientation == "white" else "Đen ở dưới")
        )

    @Slot()
    def _refresh_sources(self) -> None:
        current_title = self.config.get("window_title", "")
        current_handle = self.config.get("window_handle")
        current_mode = self.config.get("capture_mode", "window")
        self.source_combo.blockSignals(True)
        self.source_combo.clear()
        self._source_windows.clear()
        self.source_combo.addItem("— Chọn cửa sổ bàn cờ —", "select")
        self.source_combo.addItem("Tự động — toàn màn hình", "desktop")
        windows = list_windows()
        duplicate_titles = {window.title for window in windows if sum(item.title == window.title for item in windows) > 1}
        for window in windows:
            if window.title == self.windowTitle():
                continue
            self._source_windows[window.handle] = window
            label = f"{window.title} [{window.handle:X}]" if window.title in duplicate_titles else window.title
            self.source_combo.addItem(label, f"window:{window.handle}")
        handle_data = f"window:{int(current_handle)}" if current_handle else ""
        if current_mode == "window" and handle_data and self.source_combo.findData(handle_data) >= 0:
            index = self.source_combo.findData(handle_data)
        elif current_mode == "window" and current_title:
            index = next(
                (item for item in range(self.source_combo.count())
                 if (self._source_windows.get(self._handle_from_source_data(self.source_combo.itemData(item)))
                     and self._source_windows[self._handle_from_source_data(self.source_combo.itemData(item))].title == current_title)),
                -1,
            )
            if index < 0:
                self.source_combo.addItem(current_title + " (không còn mở)", "select")
                index = self.source_combo.count() - 1
        elif current_mode == "desktop":
            index = self.source_combo.findData("desktop")
        else:
            index = 0
        self.source_combo.setCurrentIndex(max(0, index))
        self.source_combo.blockSignals(False)

    @Slot(int)
    def _source_selected(self, index: int) -> None:
        if index < 0:
            return
        source_data = str(self.source_combo.itemData(index) or "select")
        self.stop_capture()
        if source_data == "select":
            self.config.update({
                "capture_mode": "window",
                "window_title": "",
                "window_handle": None,
                "board_region": None,
                "window_board_ratio": None,
            })
            self.tracker.reset()
            self.current_game_id = None
            self._last_submitted_fen = None
            self.analysis.clear_result()
            self.board.set_position({})
            self.board.set_arrow(None, None)
            self.game_state.setText("Ván cờ: chờ đồng bộ")
            self.current_board_image = None
            self.capture_state.setText("● Chờ nguồn")
            self.statusBar().showMessage("Hãy chọn cửa sổ Chrome/Edge đang hiển thị bàn cờ")
            self._update_capture_controls()
            return
        handle = self._handle_from_source_data(source_data)
        window = self._source_windows.get(handle) if handle else None
        title = window.title if window else ""
        desktop = source_data == "desktop"
        if not desktop and not window:
            self.capture_state.setText("● Chờ nguồn")
            self.statusBar().showMessage("Cửa sổ đã đóng — hãy làm mới và chọn lại")
            return
        self.config.update({
            "capture_mode": "desktop" if desktop else "window",
            "window_title": title,
            "window_handle": handle,
            "board_region": None,
            "window_board_ratio": None,
        })
        self.tracker.reset()
        self.current_game_id = None
        self._last_submitted_fen = None
        self.analysis.clear_result()
        self.board.set_position({})
        self.board.set_arrow(None, None)
        self.game_state.setText("Ván cờ: chờ đồng bộ")
        self.current_board_image = None
        self.start_capture()
        self.statusBar().showMessage(
            f"Đang chỉ đọc cửa sổ: {title}" if title else "Đang tự tìm trên toàn màn hình"
        )

    @staticmethod
    def _handle_from_source_data(value) -> int | None:
        text = str(value or "")
        if not text.startswith("window:"):
            return None
        try:
            return int(text.split(":", 1)[1])
        except ValueError:
            return None

    def _calibrate_templates(self) -> None:
        if self.current_board_image is None:
            QMessageBox.warning(self, "Chưa có ảnh", "Hãy Start hoặc chọn vùng bàn cờ trước.")
            return
        answer = QMessageBox.question(
            self, "Xác nhận thế xuất phát",
            "Bàn cờ đang hiển thị phải là thế xuất phát chuẩn, không thiếu quân. Tiếp tục?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        recognizer = PieceRecognizer(
            self.templates_root, self.config.get("template_theme", "default")
        )
        recognizer.calibrate_from_start(self.current_board_image, self.config.get("orientation", "white"))
        self.tracker.reset()
        self._last_submitted_fen = None
        self.stop_capture()
        self.start_capture()
        self.statusBar().showMessage("Đã tạo template cục bộ cho giao diện bàn cờ hiện tại.")

    @Slot()
    def save_current_game(self) -> None:
        if self.tracker.board is None:
            QMessageBox.information(self, "Chưa có ván", "Hãy nhận dạng một bàn cờ hợp lệ trước khi lưu.")
            return
        if not self.history_service.game_exists(self.current_game_id):
            self.current_game_id = self.history_service.create_game(self.tracker.board.fen())
        game = self.history_service.get_game(int(self.current_game_id))
        current_title = game.title if game else ""
        title, accepted = QInputDialog.getText(
            self, "Lưu ván hiện tại", "Tên ván:", text=current_title
        )
        if accepted:
            if not title.strip():
                QMessageBox.warning(self, "Thiếu tên", "Tên ván không được để trống.")
                return
            self.history_service.rename_game(int(self.current_game_id), title)
            self.statusBar().showMessage(f"Đã lưu ván “{title.strip()}”. Các nước tiếp theo vẫn được tự động cập nhật.")

    @Slot()
    def open_game_history(self) -> None:
        resume_after = self._running and not self._paused
        if resume_after:
            self.toggle_pause()
        dialog = GameHistoryDialog(
            self.history_service, self.config.get("orientation", "white"), self
        )
        dialog.exec()
        if self.current_game_id and not self.history_service.game_exists(self.current_game_id):
            self.current_game_id = None
        self.analysis.load_moves(self.history_service.recent_moves())
        if resume_after and self._running:
            self.toggle_pause()

    @Slot()
    def open_settings(self) -> None:
        dialog = SettingsDialog(self.config, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            was_running = self._running
            self.stop_capture()
            self.config.update(dialog.values())
            self.board.set_orientation(self.config.get("orientation", "white"))
            self._last_submitted_fen = None
            self._create_analysis_manager()
            if was_running:
                self.start_capture()

    def closeEvent(self, event) -> None:
        self.stop_capture()
        self.analysis_manager.shutdown()
        event.accept()

