from __future__ import annotations

import chess
import chess.engine
import pytest

from core.stockfish_engine import StockfishEngine, StockfishNotFound


class FakeEngine:
    options = {"Threads": object(), "Hash": object()}

    def __init__(self):
        self.configured = {}
        self.quit_called = False

    def configure(self, values):
        self.configured.update(values)

    def analyse(self, board, _limit, multipv=1):
        moves = list(board.legal_moves)[:multipv]
        return [
            {"pv": [move], "score": chess.engine.PovScore(chess.engine.Cp(42 - rank), board.turn), "depth": 18}
            for rank, move in enumerate(moves)
        ]

    def quit(self):
        self.quit_called = True

    def close(self):
        self.quit_called = True


class FailingEngine(FakeEngine):
    def analyse(self, *_args, **_kwargs):
        raise chess.engine.EngineTerminatedError("engine stopped")


def test_missing_stockfish(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("core.stockfish_engine.shutil.which", lambda _name: None)
    with pytest.raises(StockfishNotFound):
        StockfishEngine(str(tmp_path / "missing.exe")).start()


def test_start_analyse_and_stop(monkeypatch, tmp_path) -> None:
    executable = tmp_path / "stockfish.exe"
    executable.write_bytes(b"placeholder")
    fake = FakeEngine()
    monkeypatch.setattr(chess.engine.SimpleEngine, "popen_uci", lambda *_args, **_kwargs: fake)
    engine = StockfishEngine(str(executable), threads=3, hash_mb=128)
    engine.start()
    lines = engine.analyse(chess.STARTING_FEN, 0.1, 3)
    assert len(lines) == 3
    assert lines[0].evaluation == "+0.42"
    assert fake.configured == {"Threads": 3, "Hash": 128}
    engine.stop()
    assert fake.quit_called


def test_real_stockfish_integration_when_available() -> None:
    path = StockfishEngine.discover()
    if not path:
        pytest.skip("Stockfish executable is not installed")
    engine = StockfishEngine(path, threads=1, hash_mb=32)
    try:
        lines = engine.analyse(chess.STARTING_FEN, 0.1, 3)
        assert len(lines) == 3
        assert all(line.move_uci in {move.uci() for move in chess.Board().legal_moves} for line in lines)
        assert all(line.depth > 0 for line in lines)
        board = chess.Board()
        board.push_uci("e2e4")
        replies = engine.analyse(board.fen(), 0.1, 3)
        assert len(replies) == 3
        assert all(line.move_uci in {move.uci() for move in board.legal_moves} for line in replies)
    finally:
        engine.stop()


def test_engine_can_restart_after_process_failure(monkeypatch, tmp_path) -> None:
    executable = tmp_path / "stockfish.exe"
    executable.write_bytes(b"placeholder")
    failing = FailingEngine()
    healthy = FakeEngine()
    engines = iter((failing, healthy))
    monkeypatch.setattr(chess.engine.SimpleEngine, "popen_uci", lambda *_args, **_kwargs: next(engines))
    engine = StockfishEngine(str(executable), threads=1, hash_mb=32)
    with pytest.raises(chess.engine.EngineTerminatedError):
        engine.analyse(chess.STARTING_FEN, 0.1, 1)
    assert engine.engine is None
    assert engine.analyse(chess.STARTING_FEN, 0.1, 1)
    engine.stop()

