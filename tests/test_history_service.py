from __future__ import annotations

import chess
import sqlite3

from services.history_service import HistoryService


def test_persists_moves_and_restores_matching_fen(tmp_path) -> None:
    history = HistoryService(tmp_path / "history.db")
    board = chess.Board()
    board.push_uci("e2e4")
    history.add_move(board.fen(), "e2e4", "e4", 1)
    moves = history.recent_moves()
    assert len(moves) == 1
    assert moves[0][2:] == ("e2e4", "e4", 1)
    assert history.find_latest_fen(board.board_fen()) == board.fen()


def test_manages_games_and_deletes_one_game_with_its_history(tmp_path) -> None:
    history = HistoryService(tmp_path / "history.db")
    game_id = history.create_game(chess.STARTING_FEN, "Ván thử nghiệm")
    board = chess.Board()
    board.push_uci("e2e4")
    history.add_move(board.fen(), "e2e4", "e4", 1, game_id)
    history.add(board.fen(), "e5", "+0.20", 12, game_id)
    board.push_uci("e7e5")
    history.add_move(board.fen(), "e7e5", "e5", 2, game_id)

    games = history.list_games()
    assert len(games) == 1
    assert games[0].title == "Ván thử nghiệm"
    assert games[0].move_count == 2
    assert games[0].final_fen == board.fen()
    assert len(history.game_moves(game_id)) == 2
    assert history.find_latest_state(board.board_fen()) == (board.fen(), game_id)

    assert history.rename_game(game_id, "Chiến thắng đầu tiên")
    history.finish_game(game_id, "Chiếu hết")
    game = history.get_game(game_id)
    assert game and game.title == "Chiến thắng đầu tiên"
    assert game.result == "Chiếu hết" and game.status == "finished"
    assert history.delete_game(game_id)
    assert history.list_games() == []
    assert history.recent_moves() == []
    assert history.recent() == []


def test_migrates_legacy_move_rows_into_a_game(tmp_path) -> None:
    path = tmp_path / "legacy.db"
    board = chess.Board()
    board.push_uci("e2e4")
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE moves (id INTEGER PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP, "
            "fen TEXT NOT NULL, move_uci TEXT NOT NULL, move_san TEXT NOT NULL, ply INTEGER NOT NULL)"
        )
        db.execute(
            "CREATE TABLE analyses (id INTEGER PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP, "
            "fen TEXT NOT NULL, best_move TEXT, evaluation TEXT, depth INTEGER)"
        )
        db.execute(
            "INSERT INTO moves(fen,move_uci,move_san,ply) VALUES(?,?,?,?)",
            (board.fen(), "e2e4", "e4", 1),
        )

    history = HistoryService(path)
    assert (tmp_path / "legacy-backup-before-game-management.db").exists()
    games = history.list_games()
    assert len(games) == 1
    assert games[0].title == "Ván cũ 1"
    assert games[0].initial_fen == chess.STARTING_FEN
    assert games[0].move_count == 1
