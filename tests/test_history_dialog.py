from __future__ import annotations

import chess
from PySide6.QtWidgets import QApplication

from services.history_service import HistoryService
from ui.history_dialog import GameHistoryDialog


def test_selects_game_and_replays_each_position(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    history = HistoryService(tmp_path / "history.db")
    game_id = history.create_game(chess.STARTING_FEN, "Ván để xem lại")
    board = chess.Board()
    board.push_uci("e2e4")
    history.add_move(board.fen(), "e2e4", "e4", 1, game_id)
    board.push_uci("e7e5")
    history.add_move(board.fen(), "e7e5", "e5", 2, game_id)

    dialog = GameHistoryDialog(history)
    try:
        assert dialog.games.rowCount() == 1
        assert dialog.moves.count() == 3
        dialog.moves.setCurrentRow(0)
        app.processEvents()
        assert len(dialog.board._pieces) == 32
        assert dialog.board._pieces.get("e2") == "P"
        dialog.moves.setCurrentRow(2)
        app.processEvents()
        assert dialog.board._pieces.get("e4") == "P"
        assert dialog.board._pieces.get("e5") == "p"
    finally:
        dialog.close()
