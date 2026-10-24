from __future__ import annotations

import chess

from core.fen_builder import pieces_from_board
from core.position_tracker import PositionTracker


def test_tracks_normal_move_and_new_game() -> None:
    tracker = PositionTracker()
    first = tracker.initialize(pieces_from_board(chess.Board()))
    assert first.accepted and first.new_game
    board = chess.Board()
    board.push_uci("e2e4")
    result = tracker.update(pieces_from_board(board))
    assert result.accepted
    assert result.move_uci == "e2e4"
    assert result.move_san == "e4"


def test_tracks_castling() -> None:
    board = chess.Board("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    tracker = PositionTracker()
    assert tracker.initialize(pieces_from_board(board), "w", "KQkq").accepted
    board.push_uci("e1g1")
    result = tracker.update(pieces_from_board(board))
    assert result.accepted and result.move_san == "O-O"


def test_tracks_promotion() -> None:
    board = chess.Board("7k/P7/8/8/8/8/8/7K w - - 0 1")
    tracker = PositionTracker()
    assert tracker.initialize(pieces_from_board(board), "w", "-").accepted
    board.push_uci("a7a8q")
    result = tracker.update(pieces_from_board(board))
    assert result.accepted and result.move_uci == "a7a8q"


def test_unknown_static_position_requires_metadata() -> None:
    board = chess.Board("7k/8/8/8/8/8/8/K7 b - - 0 1")
    result = PositionTracker().initialize(pieces_from_board(board))
    assert result.needs_metadata


def test_tracks_en_passant_when_metadata_supplies_target() -> None:
    board = chess.Board()
    for move in ("e2e4", "d7d5", "e4e5", "f7f5"):
        board.push_uci(move)
    tracker = PositionTracker()
    initialized = tracker.initialize(pieces_from_board(board), "w", "KQkq", "f6")
    assert initialized.accepted
    board.push_uci("e5f6")
    result = tracker.update(pieces_from_board(board))
    assert result.accepted
    assert result.move_uci == "e5f6"
    assert result.move_san == "exf6"


def test_recovers_missed_frame_including_opponent_king_move() -> None:
    board = chess.Board("4k3/8/8/8/8/8/8/4K3 w - - 0 1")
    tracker = PositionTracker()
    assert tracker.initialize(pieces_from_board(board), "w", "-").accepted
    board.push_uci("e1e2")
    board.push_uci("e8e7")

    result = tracker.update(pieces_from_board(board))

    assert result.accepted
    assert [move.uci for move in result.detected_moves] == ["e1e2", "e8e7"]
    assert [move.san for move in result.detected_moves] == ["Ke2", "Ke7"]
    assert tracker.board and tracker.board.fen() == board.fen()


def test_reports_checkmate() -> None:
    board = chess.Board()
    for move in ("f2f3", "e7e5", "g2g4", "d8h4"):
        board.push_uci(move)
    tracker = PositionTracker()
    assert tracker.restore(board.fen()).accepted
    assert tracker.outcome_text == "Chiếu hết"


def test_reports_draw_reason() -> None:
    tracker = PositionTracker()
    assert tracker.restore("8/8/8/8/8/8/7k/K7 w - - 0 1").accepted
    assert tracker.outcome_text == "Hòa do thiếu quân chiếu hết"

