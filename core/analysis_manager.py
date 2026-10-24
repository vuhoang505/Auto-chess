from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event, Lock

from PySide6.QtCore import QObject, Signal

from core.stockfish_engine import AnalysisLine, StockfishEngine


class AnalysisManager(QObject):
    preview = Signal(str, object)
    completed = Signal(str, object)
    failed = Signal(str, str)
    busy_changed = Signal(bool)

    def __init__(self, engine: StockfishEngine):
        super().__init__()
        self.engine = engine
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="stockfish")
        self._generation = 0
        self._lock = Lock()
        self._closed = False
        self._active: Future[list[AnalysisLine]] | None = None
        self._cancel_event: Event | None = None

    def submit(self, fen: str, seconds: float, multipv: int = 3) -> None:
        with self._lock:
            if self._closed:
                return
            self._generation += 1
            generation = self._generation
            active = self._active
            previous_event = self._cancel_event
            cancel_event = Event()
            self._cancel_event = cancel_event
        if previous_event:
            previous_event.set()
        if active and not active.done():
            # SimpleEngine.close() is thread-safe and releases a blocking UCI
            # analysis quickly. The stale callback is ignored by generation.
            self.engine.cancel()
        self.busy_changed.emit(True)
        future = self._executor.submit(
            self._analyse_progressively, fen, seconds, multipv, generation, cancel_event
        )
        with self._lock:
            self._active = future
        future.add_done_callback(lambda item: self._finish(item, generation, fen))

    def _analyse_progressively(
        self, fen: str, seconds: float, multipv: int, generation: int, cancel_event: Event
    ) -> list[AnalysisLine]:
        # Return a useful move almost immediately, then refine it for the full
        # configured time. Short analyses already complete quickly and run once.
        if seconds < 0.18:
            return self.engine.analyse(fen, seconds, multipv)
        preview = self.engine.analyse(fen, 0.07, 1)
        with self._lock:
            current = generation == self._generation and not self._closed
        if cancel_event.is_set() or not current:
            return preview
        self.preview.emit(fen, preview)
        if cancel_event.is_set():
            return preview
        return self.engine.analyse(fen, seconds, multipv)

    def _finish(self, future: Future[list[AnalysisLine]], generation: int, fen: str) -> None:
        with self._lock:
            current = generation == self._generation and not self._closed
        if not current:
            return
        try:
            self.completed.emit(fen, future.result())
        except Exception as exc:
            self.failed.emit(fen, str(exc))
        finally:
            self.busy_changed.emit(False)

    def cancel_pending(self) -> None:
        with self._lock:
            self._generation += 1
            active = self._active
            cancel_event = self._cancel_event
        if cancel_event:
            cancel_event.set()
        if active and not active.done():
            self.engine.cancel()
        # A stale future deliberately emits nothing from _finish(). Clear the
        # busy state here so Stop/source changes cannot leave the UI spinning.
        self.busy_changed.emit(False)

    def shutdown(self) -> None:
        with self._lock:
            self._closed = True
            self._generation += 1
            cancel_event = self._cancel_event
        if cancel_event:
            cancel_event.set()
        self.engine.stop()
        self._executor.shutdown(wait=False, cancel_futures=True)

