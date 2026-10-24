from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QListWidget, QVBoxLayout, QWidget,
)

from core.stockfish_engine import AnalysisLine


class AnalysisPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(9)
        header = QHBoxLayout()
        title = QLabel("NƯỚC ĐI TỐT NHẤT")
        title.setObjectName("eyebrow")
        engine_badge = QLabel("STOCKFISH  •  LIVE")
        engine_badge.setObjectName("liveBadge")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(engine_badge)
        layout.addLayout(header)
        self.best = QLabel("—")
        self.best.setObjectName("bestMove")
        self.best.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.best.setMinimumHeight(92)
        glow = QGraphicsDropShadowEffect(self.best)
        glow.setBlurRadius(34)
        glow.setOffset(0, 7)
        glow.setColor(QColor(41, 209, 226, 105))
        self.best.setGraphicsEffect(glow)
        layout.addWidget(self.best)

        metrics = QHBoxLayout()
        self.origin = self._metric(metrics, "TỪ", "—")
        self.target = self._metric(metrics, "ĐẾN", "—")
        self.evaluation = self._metric(metrics, "ĐÁNH GIÁ", "—")
        self.depth = self._metric(metrics, "ĐỘ SÂU", "—")
        layout.addLayout(metrics)

        alternatives_title = QLabel("TOP 3 PHƯƠNG ÁN")
        alternatives_title.setObjectName("sectionTitle")
        layout.addWidget(alternatives_title)
        self.lines = QListWidget()
        self.lines.setObjectName("analysisLines")
        self.lines.setAlternatingRowColors(True)
        self.lines.setMinimumHeight(155)
        layout.addWidget(self.lines, 1)
        history_title = QLabel("LỊCH SỬ NƯỚC ĐI")
        history_title.setObjectName("sectionTitle")
        layout.addWidget(history_title)
        self.history = QListWidget()
        self.history.setObjectName("moveHistory")
        self.history.setAlternatingRowColors(True)
        self.history.setMinimumHeight(90)
        self.history.setMaximumHeight(135)
        layout.addWidget(self.history)

    @staticmethod
    def _metric(parent: QHBoxLayout, caption: str, initial: str) -> QLabel:
        frame = QFrame()
        frame.setObjectName("metric")
        box = QVBoxLayout(frame)
        label = QLabel(caption)
        label.setObjectName("metricLabel")
        value = QLabel(initial)
        value.setObjectName("metricValue")
        value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.addWidget(label)
        box.addWidget(value)
        parent.addWidget(frame)
        return value

    def set_results(self, results: list[AnalysisLine]) -> None:
        self.lines.clear()
        if not results:
            self.clear_result()
            return
        first = results[0]
        self.best.setText(first.move_san)
        self.origin.setText(first.from_square)
        self.target.setText(first.to_square)
        self.evaluation.setText(first.evaluation)
        self.depth.setText(str(first.depth))
        for line in results:
            self.lines.addItem(f"#{line.rank}  {line.move_san:<8}  {line.evaluation:>7}  d{line.depth}\n     {line.pv_san}")

    def clear_result(self) -> None:
        self.best.setText("—")
        for label in (self.origin, self.target, self.evaluation, self.depth):
            label.setText("—")
        self.lines.clear()

    def set_busy(self) -> None:
        self.clear_result()
        self.best.setText("ĐANG PHÂN TÍCH…")

    def set_error(self, message: str) -> None:
        self.clear_result()
        self.best.setText("CHƯA PHÂN TÍCH")
        self.lines.addItem(message)

    def add_move(self, move_number: int, san: str) -> None:
        self.history.addItem(self._move_label(move_number, san))
        self.history.scrollToBottom()

    def start_new_game(self) -> None:
        if self.history.count():
            self.history.addItem("────────  Ván mới  ────────")
            self.history.scrollToBottom()

    def load_moves(self, moves: list[tuple]) -> None:
        self.history.clear()
        for _created_at, _fen, _uci, san, ply in moves:
            self.history.addItem(self._move_label(int(ply), san))
        self.history.scrollToBottom()

    @staticmethod
    def _move_label(ply: int, san: str) -> str:
        move_number = max(1, (ply + 1) // 2)
        separator = "." if ply % 2 else "..."
        return f"{move_number}{separator}  {san}"

