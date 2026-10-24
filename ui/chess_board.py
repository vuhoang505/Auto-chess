from __future__ import annotations

import chess
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget


UNICODE_PIECES = {
    "K": "♔", "Q": "♕", "R": "♖", "B": "♗", "N": "♘", "P": "♙",
    "k": "♚", "q": "♛", "r": "♜", "b": "♝", "n": "♞", "p": "♟",
}


class ChessBoardWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("visionBoard")
        self.setMinimumSize(360, 360)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._pieces: dict[str, str] = {}
        self._orientation = "white"
        self._arrow: tuple[str, str] | None = None
        self._confidence: dict[str, float] = {}

    def set_position(self, pieces: dict[str, str], confidence: dict[str, float] | None = None) -> None:
        self._pieces = dict(pieces)
        self._confidence = confidence or {}
        self.update()

    def set_orientation(self, orientation: str) -> None:
        self._orientation = orientation
        self.update()

    def set_arrow(self, start: str | None, end: str | None) -> None:
        self._arrow = (start, end) if start and end else None
        self.update()

    def _screen_cell(self, square: str) -> tuple[int, int]:
        file_index = ord(square[0]) - ord("a")
        rank_index = int(square[1]) - 1
        if self._orientation == "black":
            return 7 - file_index, rank_index
        return file_index, 7 - rank_index

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        side = max(80, min(self.width(), self.height()) - 38)
        x0, y0 = (self.width() - side) / 2, (self.height() - side) / 2
        cell = side / 8

        # Layered frame and drop shadow give the board depth without bitmap
        # assets, so it remains sharp at every DPI and window size.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 80))
        painter.drawRoundedRect(QRectF(x0 - 12, y0 - 7, side + 24, side + 25), 16, 16)
        frame = QLinearGradient(x0 - 11, y0 - 11, x0 + side + 11, y0 + side + 11)
        frame.setColorAt(0, QColor("#7596c8"))
        frame.setColorAt(0.24, QColor("#263b62"))
        frame.setColorAt(0.72, QColor("#0a1428"))
        frame.setColorAt(1, QColor("#5d7fae"))
        painter.setBrush(frame)
        painter.drawRoundedRect(QRectF(x0 - 11, y0 - 11, side + 22, side + 22), 15, 15)
        painter.setBrush(QColor("#070d1b"))
        painter.drawRoundedRect(QRectF(x0 - 6, y0 - 6, side + 12, side + 12), 10, 10)

        for row in range(8):
            for col in range(8):
                rect = QRectF(x0 + col * cell, y0 + row * cell, cell, cell)
                light_square = (row + col) % 2 == 0
                tile = QLinearGradient(rect.topLeft(), rect.bottomRight())
                if light_square:
                    tile.setColorAt(0, QColor("#d8e5f7"))
                    tile.setColorAt(0.56, QColor("#afc4e3"))
                    tile.setColorAt(1, QColor("#8ea8cf"))
                else:
                    tile.setColorAt(0, QColor("#526d9c"))
                    tile.setColorAt(0.55, QColor("#344f7e"))
                    tile.setColorAt(1, QColor("#203760"))
                painter.fillRect(rect, tile)
                # Fine bevels make each square read as a physical tile.
                painter.setPen(QPen(QColor(255, 255, 255, 22), max(1, int(cell * .012))))
                painter.drawLine(rect.topLeft(), rect.topRight())
                painter.drawLine(rect.topLeft(), rect.bottomLeft())
                painter.setPen(QPen(QColor(0, 0, 0, 26), max(1, int(cell * .012))))
                painter.drawLine(rect.bottomLeft(), rect.bottomRight())
                painter.drawLine(rect.topRight(), rect.bottomRight())

        # Subtle glass reflection across the top half of the board.
        glass = QLinearGradient(0, y0, 0, y0 + side)
        glass.setColorAt(0, QColor(255, 255, 255, 20))
        glass.setColorAt(0.48, QColor(255, 255, 255, 0))
        glass.setColorAt(1, QColor(0, 0, 0, 14))
        painter.fillRect(QRectF(x0, y0, side, side), glass)

        piece_font = QFont("Segoe UI Symbol", max(18, int(cell * 0.70)))
        piece_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(piece_font)
        for square, symbol in self._pieces.items():
            col, row = self._screen_cell(square)
            rect = QRectF(x0 + col * cell, y0 + row * cell, cell, cell)
            if self._confidence.get(square, 1.0) < 0.72:
                warning = QLinearGradient(rect.topLeft(), rect.bottomRight())
                warning.setColorAt(0, QColor(255, 78, 116, 105))
                warning.setColorAt(1, QColor(255, 153, 70, 70))
                painter.fillRect(rect, warning)
            glyph = UNICODE_PIECES.get(symbol, "?")
            shadow_rect = rect.translated(cell * .035, cell * .055)
            painter.setPen(QColor(0, 4, 14, 150))
            painter.drawText(shadow_rect, Qt.AlignmentFlag.AlignCenter, glyph)
            if symbol.islower():
                # A pale one-pixel halo keeps dark pieces legible on dark tiles.
                painter.setPen(QColor(216, 230, 250, 150))
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    painter.drawText(rect.translated(dx, dy), Qt.AlignmentFlag.AlignCenter, glyph)
                painter.setPen(QColor("#10182a"))
            else:
                painter.setPen(QColor("#fbfdff"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, UNICODE_PIECES.get(symbol, "?"))

        # Coordinates are intentionally quiet and stay inside the board.
        coordinate_font = QFont("Segoe UI", max(7, int(cell * .13)))
        coordinate_font.setWeight(QFont.Weight.Bold)
        painter.setFont(coordinate_font)
        for index in range(8):
            file_char = "hgfedcba"[index] if self._orientation == "black" else "abcdefgh"[index]
            rank_char = str(index + 1) if self._orientation == "black" else str(8 - index)
            painter.setPen(QColor(255, 255, 255, 125) if index % 2 else QColor(24, 42, 72, 145))
            painter.drawText(
                QRectF(x0 + index * cell + 3, y0 + side - cell * .20, cell - 6, cell * .18),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                file_char,
            )
            painter.drawText(
                QRectF(x0 + 3, y0 + index * cell + 2, cell * .20, cell * .20),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                rank_char,
            )
        if self._arrow:
            start_col, start_row = self._screen_cell(self._arrow[0])
            end_col, end_row = self._screen_cell(self._arrow[1])
            start = QPointF(x0 + (start_col + .5) * cell, y0 + (start_row + .5) * cell)
            end = QPointF(x0 + (end_col + .5) * cell, y0 + (end_row + .5) * cell)
            painter.setPen(QPen(QColor(19, 235, 224, 75), max(10, int(cell * .20)), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(start, end)
            pen = QPen(QColor(55, 248, 230, 225), max(5, int(cell * .10)), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(start, end)
            direction = end - start
            length = max(1.0, (direction.x() ** 2 + direction.y() ** 2) ** .5)
            ux, uy = direction.x() / length, direction.y() / length
            normal = QPointF(-uy, ux)
            tip = end
            base = end - QPointF(ux, uy) * cell * .34
            polygon = QPolygonF([tip, base + normal * cell * .17, base - normal * cell * .17])
            painter.setBrush(QColor(25, 224, 214, 230))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPolygon(polygon)

