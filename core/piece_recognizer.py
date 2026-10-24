from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from core.board_detector import BoardDetector


STARTING_PIECES = {
    **{f"{file}2": "P" for file in "abcdefgh"},
    **{f"{file}7": "p" for file in "abcdefgh"},
    "a1": "R", "b1": "N", "c1": "B", "d1": "Q", "e1": "K", "f1": "B", "g1": "N", "h1": "R",
    "a8": "r", "b8": "n", "c8": "b", "d8": "q", "e8": "k", "f8": "b", "g8": "n", "h8": "r",
}


@dataclass(frozen=True)
class RecognitionResult:
    pieces: dict[str, str]
    confidence: float
    square_confidence: dict[str, float]
    needs_calibration: bool = False
    reason: str = ""


class PieceRecognizer:
    """Theme-specific OpenCV recognizer using calibrated square templates."""

    def __init__(self, templates_root: str | Path, theme: str = "default", threshold: float = 0.72):
        self.root = Path(templates_root)
        self.theme = theme
        self.threshold = threshold
        self.templates: dict[str, list[np.ndarray]] = {}
        self.empty_templates: dict[int, list[np.ndarray]] = {0: [], 1: []}
        self.calibrated_orientation: str | None = None
        self.load()

    @staticmethod
    def _features(image: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        # Board coordinates and site badges are usually drawn in square
        # corners. Excluding the outer band also makes templates less sensitive
        # to borders and last-move highlights while retaining the piece body.
        height, width = gray.shape[:2]
        margin_y = max(1, int(height * 0.12))
        margin_x = max(1, int(width * 0.12))
        if height > margin_y * 2 and width > margin_x * 2:
            gray = gray[margin_y:height - margin_y, margin_x:width - margin_x]
        gray = cv2.resize(gray, (64, 64), interpolation=cv2.INTER_AREA)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        edges = cv2.Canny(gray, 45, 135).astype(np.float32) / 255.0
        normalized = cv2.normalize(gray.astype(np.float32), None, 0, 1, cv2.NORM_MINMAX)
        return np.dstack((normalized, edges)).astype(np.float32)

    @staticmethod
    def _similarity(a: np.ndarray, b: np.ndarray) -> float:
        mse = float(np.mean((a - b) ** 2))
        return max(0.0, 1.0 - mse * 2.5)

    @staticmethod
    def _read_image(path: Path) -> np.ndarray:
        # cv2.imread/imwrite can fail on non-ASCII Windows paths.
        data = np.frombuffer(path.read_bytes(), dtype=np.uint8)
        image = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"Không đọc được template: {path.name}")
        return image

    @staticmethod
    def _write_image(path: Path, image: np.ndarray) -> None:
        ok, encoded = cv2.imencode(path.suffix or ".png", image)
        if not ok:
            raise OSError(f"Không mã hóa được template: {path.name}")
        path.write_bytes(encoded.tobytes())

    def load(self) -> None:
        self.templates.clear()
        self.empty_templates = {0: [], 1: []}
        self.calibrated_orientation = None
        folder = self.root / self.theme
        manifest = folder / "manifest.json"
        if not manifest.exists():
            return
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            saved_orientation = data.get("orientation")
            if saved_orientation in ("white", "black"):
                self.calibrated_orientation = saved_orientation
            for name, entries in data.get("pieces", {}).items():
                self.templates[name] = [self._features(self._read_image(folder / entry)) for entry in entries]
            for parity, entries in data.get("empty", {}).items():
                self.empty_templates[int(parity)] = [self._features(self._read_image(folder / entry)) for entry in entries]
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            self.templates.clear()
            self.empty_templates = {0: [], 1: []}
            self.calibrated_orientation = None

    def calibrate_from_start(self, board_image: np.ndarray, orientation: str = "white") -> None:
        folder = self.root / self.theme
        folder.mkdir(parents=True, exist_ok=True)
        squares = BoardDetector.split_squares(board_image, orientation)
        manifest: dict = {"orientation": orientation, "pieces": {}, "empty": {"0": [], "1": []}}
        for square, symbol in STARTING_PIECES.items():
            filename = f"{symbol}_{square}.png" if symbol.isupper() else f"black_{symbol}_{square}.png"
            self._write_image(folder / filename, squares[square])
            manifest["pieces"].setdefault(symbol, []).append(filename)
        for square in ("a3", "b3", "a4", "b4"):
            file_index = ord(square[0]) - ord("a")
            rank = int(square[1])
            parity = (file_index + rank) % 2
            filename = f"empty_{square}.png"
            self._write_image(folder / filename, squares[square])
            manifest["empty"][str(parity)].append(filename)
        (folder / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        self.load()

    @property
    def calibrated(self) -> bool:
        return len(self.templates) == 12 and all(self.empty_templates.values())

    @staticmethod
    def infer_start_position(board_image: np.ndarray, fallback_orientation: str = "white") -> tuple[bool, str, float]:
        """Conservatively recognize the occupied-rank pattern of a standard start.

        This does not classify pieces. It only permits automatic template
        calibration when all four outer ranks are visibly busier than the four
        middle ranks. Piece luminance supplies an orientation hint.
        """
        side = min(board_image.shape[:2])
        board = cv2.resize(board_image[:side, :side], (800, 800), interpolation=cv2.INTER_AREA)
        densities = np.zeros((8, 8), dtype=np.float32)
        tiles: list[list[np.ndarray]] = []
        for row in range(8):
            tile_row = []
            for col in range(8):
                tile = board[row * 100:(row + 1) * 100, col * 100:(col + 1) * 100]
                inner = tile[12:88, 12:88]
                gray = cv2.cvtColor(inner, cv2.COLOR_BGR2GRAY)
                densities[row, col] = float(np.mean(cv2.Canny(gray, 45, 135)) / 255.0)
                tile_row.append(inner)
            tiles.append(tile_row)
        outer = np.concatenate((densities[:2].ravel(), densities[6:].ravel()))
        middle = densities[2:6].ravel()
        gap = float(np.quantile(outer, 0.20) - np.quantile(middle, 0.90))
        mean_gap = float(outer.mean() - middle.mean())
        confidence = float(np.clip((gap * 10 + mean_gap * 8) / 2, 0, 1))
        split = float((np.quantile(outer, 0.20) + np.quantile(middle, 0.90)) / 2)
        outer_occupied = float(np.mean(outer > split))
        middle_empty = float(np.mean(middle < split))
        if gap < 0.004 or mean_gap < 0.012 or outer_occupied < 0.98 or middle_empty < 0.98:
            return False, fallback_orientation if fallback_orientation in ("white", "black") else "white", confidence

        # Estimate foreground brightness against same-color empty squares.
        side_luminance: dict[str, list[float]] = {"top": [], "bottom": []}
        for name, rows in (("top", (0, 1)), ("bottom", (6, 7))):
            for row in rows:
                for col in range(8):
                    tile_gray = cv2.cvtColor(tiles[row][col], cv2.COLOR_BGR2GRAY).astype(np.float32)
                    refs = [
                        cv2.cvtColor(tiles[mid_row][col], cv2.COLOR_BGR2GRAY).astype(np.float32)
                        for mid_row in range(2, 6) if (mid_row + col) % 2 == (row + col) % 2
                    ]
                    background = np.median(np.stack(refs), axis=0)
                    mask = np.abs(tile_gray - background) > 22
                    if int(mask.sum()) > 80:
                        side_luminance[name].append(float(tile_gray[mask].mean()))
        if side_luminance["top"] and side_luminance["bottom"]:
            delta = float(np.median(side_luminance["bottom"]) - np.median(side_luminance["top"]))
            if abs(delta) >= 10:
                return True, "white" if delta > 0 else "black", max(confidence, min(1.0, abs(delta) / 80))
        orientation = fallback_orientation if fallback_orientation in ("white", "black") else "white"
        return True, orientation, confidence

    def recognize(self, board_image: np.ndarray, orientation: str = "white") -> RecognitionResult:
        if not self.calibrated:
            return RecognitionResult({}, 0.0, {}, True, "Chưa có template. Hãy hiệu chỉnh từ thế cờ ban đầu.")
        pieces: dict[str, str] = {}
        confidences: dict[str, float] = {}
        for square, image in BoardDetector.split_squares(board_image, orientation).items():
            feature = self._features(image)
            parity = (ord(square[0]) - ord("a") + int(square[1])) % 2
            scores: dict[str, float] = {}
            empty_refs = self.empty_templates.get(parity, [])
            scores["."] = max((self._similarity(feature, ref) for ref in empty_refs), default=0.0)
            for symbol, refs in self.templates.items():
                scores[symbol] = max(self._similarity(feature, ref) for ref in refs)
            ordered = sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
            label, score = ordered[0]
            margin = score - ordered[1][1] if len(ordered) > 1 else score
            # Absolute similarity is the primary signal; the margin is useful
            # but naturally small for related pieces rendered in one font.
            confidence = float(np.clip(0.9 * score + 0.1 * min(1.0, margin * 4), 0, 1))
            confidences[square] = confidence
            if label != ".":
                pieces[square] = label
        overall = float(np.mean(list(confidences.values()))) if confidences else 0.0
        low = sum(value < self.threshold for value in confidences.values())
        needs = overall < self.threshold or low > 6
        reason = f"{low}/64 ô có độ tin cậy thấp" if needs else ""
        return RecognitionResult(pieces, overall, confidences, needs, reason)

