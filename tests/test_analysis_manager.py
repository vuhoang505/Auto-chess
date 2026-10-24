from __future__ import annotations

import time
import threading

import chess
from PySide6.QtWidgets import QApplication

from core.analysis_manager import AnalysisManager
from core.stockfish_engine import AnalysisLine


class FakeEngine:
    def analyse(self, _fen, _seconds, _multipv):
        return [AnalysisLine(1, "e2e4", "e4", "e2", "e4", "+0.20", 12, "e4 e5")]

    def stop(self):
        pass

    def cancel(self):
        pass


def test_async_analysis_does_not_block() -> None:
    app = QApplication.instance() or QApplication([])
    manager = AnalysisManager(FakeEngine())
    received = []
    manager.completed.connect(lambda _fen, lines: received.extend(lines))
    manager.submit(chess.STARTING_FEN, 0.1, 1)
    deadline = time.monotonic() + 2
    while not received and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    manager.shutdown()
    assert received and received[0].move_uci == "e2e4"


class BlockingEngine:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()

    def analyse(self, _fen, _seconds, _multipv):
        self.started.set()
        self.release.wait(2)
        return []

    def cancel(self):
        self.release.set()

    def stop(self):
        self.release.set()


def test_cancel_clears_busy_state() -> None:
    app = QApplication.instance() or QApplication([])
    engine = BlockingEngine()
    manager = AnalysisManager(engine)
    states = []
    manager.busy_changed.connect(states.append)
    manager.submit(chess.STARTING_FEN, 1, 1)
    assert engine.started.wait(1)
    manager.cancel_pending()
    app.processEvents()
    manager.shutdown()
    assert states == [True, False]


class RecordingEngine(FakeEngine):
    def __init__(self):
        self.times = []

    def analyse(self, fen, seconds, multipv):
        self.times.append(seconds)
        return super().analyse(fen, seconds, multipv)


def test_long_analysis_emits_fast_preview_then_refines() -> None:
    app = QApplication.instance() or QApplication([])
    engine = RecordingEngine()
    manager = AnalysisManager(engine)
    previews = []
    completed = []
    manager.preview.connect(lambda _fen, lines: previews.extend(lines))
    manager.completed.connect(lambda _fen, lines: completed.extend(lines))
    manager.submit(chess.STARTING_FEN, 0.3, 1)
    deadline = time.monotonic() + 2
    while not completed and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    manager.shutdown()
    assert previews and completed
    assert engine.times == [0.07, 0.3]

