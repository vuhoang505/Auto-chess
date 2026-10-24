from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLineEdit, QPushButton, QSpinBox, QVBoxLayout,
)

from services.config_service import ConfigService


class SettingsDialog(QDialog):
    def __init__(self, config: ConfigService, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Cài đặt")
        self.setMinimumWidth(480)
        root = QVBoxLayout(self)
        form = QFormLayout()

        self.monitor = QSpinBox()
        self.monitor.setRange(0, 16)
        self.monitor.setSpecialValueText("Tự động (tất cả)")
        self.monitor.setValue(int(config.get("monitor", 0)))
        form.addRow("Màn hình (0 = tự động):", self.monitor)

        self.interval = QDoubleSpinBox()
        self.interval.setRange(0.15, 3.0)
        self.interval.setSingleStep(0.05)
        self.interval.setSuffix(" giây")
        self.interval.setValue(float(config.get("scan_interval", 1.0)))
        form.addRow("Chu kỳ quét:", self.interval)

        self.orientation = QComboBox()
        self.orientation.addItem("Tự nhận biết", "auto")
        self.orientation.addItem("Trắng ở dưới", "white")
        self.orientation.addItem("Đen ở dưới", "black")
        orientation = config.get("orientation", "auto")
        self.orientation.setCurrentIndex(max(0, self.orientation.findData(orientation)))
        form.addRow("Hướng bàn:", self.orientation)

        path_row = QHBoxLayout()
        self.engine_path = QLineEdit(str(config.get("stockfish_path", "")))
        browse = QPushButton("Chọn…")
        browse.clicked.connect(self._browse)
        path_row.addWidget(self.engine_path, 1)
        path_row.addWidget(browse)
        form.addRow("Stockfish EXE:", path_row)

        self.analysis_time = QDoubleSpinBox()
        self.analysis_time.setRange(0.1, 30.0)
        self.analysis_time.setSingleStep(0.25)
        self.analysis_time.setSuffix(" giây")
        self.analysis_time.setValue(float(config.get("analysis_time", 1.0)))
        form.addRow("Thời gian phân tích:", self.analysis_time)

        self.threads = QSpinBox()
        self.threads.setRange(1, 64)
        self.threads.setValue(int(config.get("threads", 2)))
        form.addRow("Luồng CPU:", self.threads)

        self.hash_mb = QSpinBox()
        self.hash_mb.setRange(16, 32768)
        self.hash_mb.setSuffix(" MB")
        self.hash_mb.setValue(int(config.get("hash_mb", 256)))
        form.addRow("Hash:", self.hash_mb)
        root.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Chọn Stockfish", str(Path.cwd()), "Executable (*.exe);;All files (*)")
        if path:
            self.engine_path.setText(path)

    def values(self) -> dict:
        return {
            "monitor": self.monitor.value(),
            "scan_interval": self.interval.value(),
            "orientation": self.orientation.currentData(),
            "stockfish_path": self.engine_path.text().strip(),
            "analysis_time": self.analysis_time.value(),
            "threads": self.threads.value(),
            "hash_mb": self.hash_mb.value(),
        }


class PositionMetadataDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Xác nhận trạng thái ván")
        layout = QFormLayout(self)
        self.turn = QComboBox()
        self.turn.addItem("Trắng", "w")
        self.turn.addItem("Đen", "b")
        self.castling = QLineEdit("-")
        self.castling.setPlaceholderText("KQkq hoặc -")
        self.en_passant = QLineEdit("-")
        self.en_passant.setPlaceholderText("Ví dụ e3 hoặc -")
        layout.addRow("Bên đến lượt:", self.turn)
        layout.addRow("Quyền nhập thành:", self.castling)
        layout.addRow("Ô bắt tốt qua đường:", self.en_passant)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

