from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(log_dir: str | Path) -> None:
    path = Path(log_dir)
    path.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(path / "chess_vision.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    target = str((path / "chess_vision.log").resolve()).casefold()
    already_configured = any(
        isinstance(existing, RotatingFileHandler)
        and str(Path(existing.baseFilename).resolve()).casefold() == target
        for existing in root.handlers
    )
    if not already_configured:
        root.addHandler(handler)
    else:
        handler.close()

