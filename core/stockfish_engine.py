from __future__ import annotations

import os
import shutil
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

import chess
import chess.engine


class StockfishNotFound(FileNotFoundError):
    pass


@dataclass(frozen=True)
class AnalysisLine:
    rank: int
    move_uci: str
    move_san: str
    from_square: str
    to_square: str
    evaluation: str
    depth: int
    pv_san: str


class StockfishEngine:
    def __init__(self, path: str = "", threads: int = 2, hash_mb: int = 256):
        self.requested_path = path
        self.threads = threads
        self.hash_mb = hash_mb
        self.engine: chess.engine.SimpleEngine | None = None
        self.path: str | None = None
        self._state_lock = threading.RLock()

    @staticmethod
    def discover(configured: str = "") -> str | None:
        candidates = [configured, os.environ.get("STOCKFISH_EXECUTABLE", ""), shutil.which("stockfish") or ""]
        executable_root = Path(sys.executable).resolve().parent
        roots = [
            Path.cwd() / "stockfish", Path.cwd() / "engine", Path.cwd(),
            executable_root / "stockfish", executable_root / "engine", executable_root,
            Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Stockfish",
            Path.home() / "Downloads",
        ]
        for root in roots:
            if root.exists():
                candidates.extend(str(path) for path in root.glob("stockfish*.exe"))
                candidates.extend(str(path) for path in root.glob("stockfish*/stockfish*.exe"))
        for candidate in candidates:
            if candidate and Path(candidate).is_file():
                return str(Path(candidate).resolve())
        return None

    def start(self) -> None:
        with self._state_lock:
            if self.engine:
                return
            self.path = self.discover(self.requested_path)
            if not self.path:
                raise StockfishNotFound("Không tìm thấy Stockfish. Chọn file stockfish.exe trong Cài đặt.")
            created: chess.engine.SimpleEngine | None = None
            try:
                created = chess.engine.SimpleEngine.popen_uci(self.path, timeout=10)
                options = created.options
                settings = {}
                if "Threads" in options:
                    settings["Threads"] = max(1, self.threads)
                if "Hash" in options:
                    settings["Hash"] = max(16, self.hash_mb)
                if settings:
                    created.configure(settings)
                self.engine = created
            except Exception:
                if created:
                    try:
                        created.close()
                    except Exception:
                        pass
                self.engine = None
                raise

    @staticmethod
    def _score_text(score: chess.engine.PovScore, turn: chess.Color) -> str:
        relative = score.pov(turn)
        mate = relative.mate()
        if mate is not None:
            return f"M{mate:+d}"
        cp = relative.score(mate_score=100000) or 0
        return f"{cp / 100:+.2f}"

    def analyse(self, fen: str, time_limit: float = 1.0, multipv: int = 3) -> list[AnalysisLine]:
        self.start()
        with self._state_lock:
            engine = self.engine
        assert engine is not None
        board = chess.Board(fen)
        try:
            infos = engine.analyse(board, chess.engine.Limit(time=max(0.05, time_limit)), multipv=max(1, multipv))
        except Exception:
            # A terminated UCI process must not poison every later request.
            with self._state_lock:
                if self.engine is engine:
                    self.engine = None
            try:
                engine.close()
            except Exception:
                pass
            raise
        if isinstance(infos, dict):
            infos = [infos]
        lines: list[AnalysisLine] = []
        for rank, info in enumerate(infos, 1):
            pv = info.get("pv", [])
            if not pv:
                continue
            first = pv[0]
            san = board.san(first)
            temp = board.copy(stack=False)
            pv_san: list[str] = []
            for move in pv[:8]:
                if move not in temp.legal_moves:
                    break
                pv_san.append(temp.san(move))
                temp.push(move)
            score = info.get("score", chess.engine.PovScore(chess.engine.Cp(0), board.turn))
            lines.append(
                AnalysisLine(rank, first.uci(), san, chess.square_name(first.from_square),
                             chess.square_name(first.to_square), self._score_text(score, board.turn),
                             int(info.get("depth", 0)), " ".join(pv_san))
            )
        return lines

    def stop(self) -> None:
        with self._state_lock:
            engine, self.engine = self.engine, None
        if engine:
            try:
                engine.quit()
            except Exception:
                try:
                    engine.close()
                except Exception:
                    pass

    def cancel(self) -> None:
        """Force the current UCI operation to end; the next call restarts it."""
        with self._state_lock:
            engine, self.engine = self.engine, None
        if engine:
            try:
                engine.close()
            except Exception:
                pass

    def __enter__(self) -> "StockfishEngine":
        self.start()
        return self

    def __exit__(self, *_args) -> None:
        self.stop()

