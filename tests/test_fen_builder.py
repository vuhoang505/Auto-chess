from __future__ import annotations

import chess
import pytest

from core.fen_builder import FenError, build_fen, pieces_from_board, placement_from_pieces


def test_start_position_to_fen() -> None:
    board = chess.Board()
    pieces = pieces_from_board(board)
    assert placement_from_pieces(pieces) == board.board_fen()
    assert build_fen(pieces, "w", "KQkq") == chess.STARTING_FEN


def test_rejects_missing_king() -> None:
    with pytest.raises(FenError):
        build_fen({"e1": "K"}, "w")

