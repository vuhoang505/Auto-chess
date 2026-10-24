from __future__ import annotations

import chess
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QFrame, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSplitter,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from core.fen_builder import pieces_from_board
from services.history_service import GameSummary, HistoryService
from ui.chess_board import ChessBoardWidget


class GameHistoryDialog(QDialog):
    def __init__(self, history: HistoryService, orientation: str = "white", parent=None):
        super().__init__(parent)
        self.history = history
        self.orientation = orientation if orientation in ("white", "black") else "white"
        self._games: dict[int, GameSummary] = {}
        self.setWindowTitle("Quản lý lịch sử ván đấu")
        self.setMinimumSize(980, 680)
        self.resize(1120, 760)
        self._build_ui()
        self.refresh_games()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        heading = QLabel("LỊCH SỬ VÁN ĐẤU")
        heading.setObjectName("appTitle")
        root.addWidget(heading)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Tìm theo tên ván…")
        self.search.textChanged.connect(self.refresh_games)
        root.addWidget(self.search)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        left = QFrame()
        left.setObjectName("historyPane")
        left_layout = QVBoxLayout(left)
        self.games = QTableWidget(0, 4)
        self.games.setHorizontalHeaderLabels(["Tên ván", "Thời gian", "Số nước", "Kết quả"])
        self.games.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.games.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.games.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.games.verticalHeader().setVisible(False)
        self.games.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.games.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.games.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.games.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.games.itemSelectionChanged.connect(self._game_selected)
        left_layout.addWidget(self.games, 1)

        game_buttons = QHBoxLayout()
        rename = QPushButton("Đổi tên")
        delete = QPushButton("Xóa ván")
        delete.setObjectName("danger")
        clear = QPushButton("Xóa tất cả")
        clear.setObjectName("danger")
        rename.clicked.connect(self._rename_game)
        delete.clicked.connect(self._delete_game)
        clear.clicked.connect(self._clear_all)
        game_buttons.addWidget(rename)
        game_buttons.addWidget(delete)
        game_buttons.addWidget(clear)
        left_layout.addLayout(game_buttons)
        splitter.addWidget(left)

        right = QFrame()
        right.setObjectName("replayPane")
        right_layout = QVBoxLayout(right)
        self.game_title = QLabel("Chọn một ván để xem lại")
        self.game_title.setObjectName("sectionTitle")
        right_layout.addWidget(self.game_title)
        self.board = ChessBoardWidget()
        self.board.setMinimumSize(380, 380)
        self.board.set_orientation(self.orientation)
        right_layout.addWidget(self.board, 1)
        self.position_label = QLabel("—")
        self.position_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.addWidget(self.position_label)
        self.moves = QListWidget()
        self.moves.setMaximumHeight(170)
        self.moves.currentRowChanged.connect(self._position_selected)
        right_layout.addWidget(self.moves)
        replay_buttons = QHBoxLayout()
        previous = QPushButton("◀ Nước trước")
        next_move = QPushButton("Nước sau ▶")
        previous.clicked.connect(lambda: self._step(-1))
        next_move.clicked.connect(lambda: self._step(1))
        replay_buttons.addWidget(previous)
        replay_buttons.addWidget(next_move)
        right_layout.addLayout(replay_buttons)
        splitter.addWidget(right)
        splitter.setSizes([520, 560])
        root.addWidget(splitter, 1)

        close = QPushButton("Đóng")
        close.clicked.connect(self.accept)
        close_row = QHBoxLayout()
        close_row.addStretch()
        close_row.addWidget(close)
        root.addLayout(close_row)

    def refresh_games(self, *_args) -> None:
        selected = self._selected_game_id()
        query = self.search.text().strip().casefold() if hasattr(self, "search") else ""
        summaries = [game for game in self.history.list_games() if query in game.title.casefold()]
        self._games = {game.id: game for game in summaries}
        self.games.blockSignals(True)
        self.games.setRowCount(0)
        selected_row = -1
        for game in summaries:
            row = self.games.rowCount()
            self.games.insertRow(row)
            title = QTableWidgetItem(game.title)
            title.setData(Qt.ItemDataRole.UserRole, game.id)
            self.games.setItem(row, 0, title)
            self.games.setItem(row, 1, QTableWidgetItem(game.updated_at))
            self.games.setItem(row, 2, QTableWidgetItem(str(game.move_count)))
            self.games.setItem(row, 3, QTableWidgetItem(game.result or ("Đang chơi" if game.status == "active" else "Đã lưu")))
            if game.id == selected:
                selected_row = row
        self.games.blockSignals(False)
        if summaries:
            self.games.selectRow(selected_row if selected_row >= 0 else 0)
            self._game_selected()
        else:
            self._clear_preview("Không có ván đấu phù hợp")

    def _selected_game_id(self) -> int | None:
        row = self.games.currentRow() if hasattr(self, "games") else -1
        item = self.games.item(row, 0) if row >= 0 else None
        value = item.data(Qt.ItemDataRole.UserRole) if item else None
        return int(value) if value is not None else None

    def _game_selected(self) -> None:
        game_id = self._selected_game_id()
        game = self._games.get(game_id) if game_id else None
        if not game:
            self._clear_preview("Chọn một ván để xem lại")
            return
        self.game_title.setText(
            f"{game.title} · {game.move_count} nửa-nước"
            + (f" · {game.result}" if game.result else "")
        )
        self.moves.blockSignals(True)
        self.moves.clear()
        initial = QListWidgetItem("0.  Vị trí ban đầu")
        initial.setData(Qt.ItemDataRole.UserRole, game.initial_fen)
        self.moves.addItem(initial)
        for _id, _created_at, fen, _uci, san, ply in self.history.game_moves(game.id):
            number = max(1, (int(ply) + 1) // 2)
            separator = "." if int(ply) % 2 else "..."
            item = QListWidgetItem(f"{number}{separator}  {san}")
            item.setData(Qt.ItemDataRole.UserRole, fen)
            self.moves.addItem(item)
        self.moves.blockSignals(False)
        self.moves.setCurrentRow(max(0, self.moves.count() - 1))
        self._position_selected(self.moves.currentRow())

    def _position_selected(self, row: int) -> None:
        item = self.moves.item(row)
        if not item:
            return
        fen = str(item.data(Qt.ItemDataRole.UserRole) or "")
        try:
            board = chess.Board(fen)
        except ValueError:
            self.board.set_position({})
            self.position_label.setText("Dữ liệu vị trí không hợp lệ")
            return
        self.board.set_position(pieces_from_board(board))
        self.position_label.setText(item.text() + f" · Lượt {'Trắng' if board.turn else 'Đen'}")

    def _step(self, offset: int) -> None:
        if not self.moves.count():
            return
        row = min(self.moves.count() - 1, max(0, self.moves.currentRow() + offset))
        self.moves.setCurrentRow(row)

    def _rename_game(self) -> None:
        game_id = self._selected_game_id()
        game = self._games.get(game_id) if game_id else None
        if not game:
            return
        title, accepted = QInputDialog.getText(self, "Đổi tên ván", "Tên mới:", text=game.title)
        if accepted and self.history.rename_game(game.id, title):
            self.refresh_games()

    def _delete_game(self) -> None:
        game_id = self._selected_game_id()
        game = self._games.get(game_id) if game_id else None
        if not game:
            return
        answer = QMessageBox.question(
            self, "Xóa ván đấu", f"Xóa vĩnh viễn “{game.title}” và toàn bộ nước đi?"
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.history.delete_game(game.id)
            self.refresh_games()

    def _clear_all(self) -> None:
        if not self._games:
            return
        answer = QMessageBox.warning(
            self,
            "Xóa toàn bộ lịch sử",
            "Thao tác này xóa tất cả ván đấu, nước đi và kết quả phân tích. Bạn chắc chắn chứ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.history.clear_all()
            self.refresh_games()

    def _clear_preview(self, message: str) -> None:
        self.game_title.setText(message)
        self.board.set_position({})
        self.moves.clear()
        self.position_label.setText("—")
