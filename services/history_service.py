from __future__ import annotations

import sqlite3
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import chess


@dataclass(frozen=True)
class GameSummary:
    id: int
    title: str
    created_at: str
    updated_at: str
    initial_fen: str
    result: str
    status: str
    move_count: int
    final_fen: str


class HistoryService:
    def __init__(self, db_path: str | Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._backup_legacy_database()
        with self._connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS games ("
                "id INTEGER PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP, "
                "updated_at TEXT DEFAULT CURRENT_TIMESTAMP, title TEXT NOT NULL, "
                "initial_fen TEXT NOT NULL, result TEXT DEFAULT '', status TEXT DEFAULT 'active')"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS analyses ("
                "id INTEGER PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP, "
                "fen TEXT NOT NULL, best_move TEXT, evaluation TEXT, depth INTEGER, game_id INTEGER)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS moves ("
                "id INTEGER PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP, "
                "fen TEXT NOT NULL, move_uci TEXT NOT NULL, move_san TEXT NOT NULL, "
                "ply INTEGER NOT NULL, game_id INTEGER)"
            )
            self._ensure_column(db, "analyses", "game_id", "INTEGER")
            self._ensure_column(db, "moves", "game_id", "INTEGER")
            db.execute("CREATE INDEX IF NOT EXISTS idx_moves_game ON moves(game_id,id)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_analyses_game ON analyses(game_id,id)")
            self._migrate_legacy_rows(db)

    def _backup_legacy_database(self) -> None:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return
        try:
            with sqlite3.connect(self.path, timeout=5) as db:
                tables = {
                    str(row[0]) for row in db.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                moves_columns = (
                    {str(row[1]) for row in db.execute("PRAGMA table_info(moves)")}
                    if "moves" in tables else set()
                )
                needs_upgrade = "games" not in tables or (
                    "moves" in tables and "game_id" not in moves_columns
                )
            if needs_upgrade:
                backup = self.path.with_name(self.path.stem + "-backup-before-game-management" + self.path.suffix)
                if not backup.exists():
                    shutil.copy2(self.path, backup)
        except (OSError, sqlite3.DatabaseError):
            # Initialization below still reports an unusable database through
            # the normal SQLite error path; backup failure must not hide it.
            pass

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=5)
        db.execute("PRAGMA foreign_keys = ON")
        return db

    @staticmethod
    def _ensure_column(db: sqlite3.Connection, table: str, column: str, declaration: str) -> None:
        columns = {str(row[1]) for row in db.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")

    @staticmethod
    def _default_title(prefix: str = "Ván") -> str:
        return f"{prefix} {datetime.now().strftime('%d/%m/%Y %H:%M')}"

    def _migrate_legacy_rows(self, db: sqlite3.Connection) -> None:
        rows = db.execute(
            "SELECT id,created_at,fen,ply FROM moves WHERE game_id IS NULL ORDER BY id"
        ).fetchall()
        groups: list[list[tuple]] = []
        for row in rows:
            if not groups or int(row[3]) <= int(groups[-1][-1][3]):
                groups.append([])
            groups[-1].append(row)
        for index, group in enumerate(groups, 1):
            first_id, created_at, first_fen, first_ply = group[0]
            initial_fen = chess.STARTING_FEN if int(first_ply) == 1 else str(first_fen)
            cursor = db.execute(
                "INSERT INTO games(created_at,updated_at,title,initial_fen,status) VALUES(?,?,?,?,?)",
                (created_at, group[-1][1], f"Ván cũ {index}", initial_fen, "saved"),
            )
            game_id = int(cursor.lastrowid)
            ids = [int(row[0]) for row in group]
            placeholders = ",".join("?" for _ in ids)
            db.execute(f"UPDATE moves SET game_id=? WHERE id IN ({placeholders})", (game_id, *ids))
            db.execute(
                "UPDATE analyses SET game_id=? WHERE game_id IS NULL AND fen IN "
                f"(SELECT fen FROM moves WHERE id IN ({placeholders}))",
                (game_id, *ids),
            )

    def create_game(self, initial_fen: str, title: str = "") -> int:
        chess.Board(initial_fen)
        clean_title = title.strip() or self._default_title()
        with self._lock, self._connect() as db:
            cursor = db.execute(
                "INSERT INTO games(title,initial_fen) VALUES(?,?)", (clean_title, initial_fen)
            )
            return int(cursor.lastrowid)

    def game_exists(self, game_id: int | None) -> bool:
        if not game_id:
            return False
        with self._lock, self._connect() as db:
            return db.execute("SELECT 1 FROM games WHERE id=?", (game_id,)).fetchone() is not None

    def rename_game(self, game_id: int, title: str) -> bool:
        clean_title = title.strip()
        if not clean_title:
            return False
        with self._lock, self._connect() as db:
            cursor = db.execute(
                "UPDATE games SET title=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (clean_title, game_id),
            )
            return cursor.rowcount > 0

    def finish_game(self, game_id: int | None, result: str = "") -> None:
        if not game_id:
            return
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE games SET result=?,status='finished',updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (result, game_id),
            )

    def add(
        self, fen: str, best_move: str, evaluation: str, depth: int, game_id: int | None = None
    ) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO analyses(fen,best_move,evaluation,depth,game_id) VALUES(?,?,?,?,?)",
                (fen, best_move, evaluation, depth, game_id),
            )
            if game_id:
                db.execute("UPDATE games SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (game_id,))

    def recent(self, limit: int = 50) -> list[tuple]:
        with self._lock, self._connect() as db:
            return db.execute(
                "SELECT created_at,fen,best_move,evaluation,depth FROM analyses ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()

    def add_move(
        self, fen: str, move_uci: str, move_san: str, ply: int, game_id: int | None = None
    ) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO moves(fen,move_uci,move_san,ply,game_id) VALUES(?,?,?,?,?)",
                (fen, move_uci, move_san, ply, game_id),
            )
            if game_id:
                db.execute("UPDATE games SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (game_id,))

    def recent_moves(self, limit: int = 100, game_id: int | None = None) -> list[tuple]:
        with self._lock, self._connect() as db:
            if game_id:
                rows = db.execute(
                    "SELECT created_at,fen,move_uci,move_san,ply FROM moves "
                    "WHERE game_id=? ORDER BY id DESC LIMIT ?",
                    (game_id, limit),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT created_at,fen,move_uci,move_san,ply FROM moves ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return rows[::-1]

    def game_moves(self, game_id: int) -> list[tuple]:
        with self._lock, self._connect() as db:
            return db.execute(
                "SELECT id,created_at,fen,move_uci,move_san,ply FROM moves "
                "WHERE game_id=? ORDER BY id",
                (game_id,),
            ).fetchall()

    def list_games(self, limit: int = 500) -> list[GameSummary]:
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT g.id,g.title,g.created_at,g.updated_at,g.initial_fen,g.result,g.status,"
                "COUNT(m.id),COALESCE((SELECT m2.fen FROM moves m2 WHERE m2.game_id=g.id "
                "ORDER BY m2.id DESC LIMIT 1),g.initial_fen) "
                "FROM games g LEFT JOIN moves m ON m.game_id=g.id "
                "GROUP BY g.id ORDER BY g.updated_at DESC,g.id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [GameSummary(*row) for row in rows]

    def get_game(self, game_id: int) -> GameSummary | None:
        return next((game for game in self.list_games() if game.id == game_id), None)

    def delete_game(self, game_id: int) -> bool:
        with self._lock, self._connect() as db:
            db.execute("DELETE FROM analyses WHERE game_id=?", (game_id,))
            db.execute("DELETE FROM moves WHERE game_id=?", (game_id,))
            cursor = db.execute("DELETE FROM games WHERE id=?", (game_id,))
            return cursor.rowcount > 0

    def clear_all(self) -> None:
        with self._lock, self._connect() as db:
            db.execute("DELETE FROM analyses")
            db.execute("DELETE FROM moves")
            db.execute("DELETE FROM games")

    def find_latest_state(self, board_fen: str) -> tuple[str, int | None] | None:
        pattern = board_fen + " %"
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT fen,game_id FROM ("
                "SELECT created_at,id,0 AS source,fen,game_id FROM analyses WHERE fen LIKE ? "
                "UNION ALL SELECT created_at,id,1 AS source,fen,game_id FROM moves WHERE fen LIKE ?"
                ") ORDER BY created_at DESC,source DESC,id DESC LIMIT 1",
                (pattern, pattern),
            ).fetchone()
        return (str(row[0]), int(row[1]) if row[1] is not None else None) if row else None

    def find_latest_fen(self, board_fen: str) -> str | None:
        state = self.find_latest_state(board_fen)
        return state[0] if state else None
