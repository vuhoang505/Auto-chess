from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class BoardDetection:
    image: np.ndarray
    bbox: tuple[int, int, int, int]
    confidence: float


class BoardDetector:
    def __init__(self, min_size: int = 240):
        self.min_size = min_size

    @staticmethod
    def _grid_score(gray: np.ndarray) -> float:
        size = gray.shape[0]
        if size < 8:
            return 0.0
        means = np.empty((8, 8), dtype=np.float32)
        for row in range(8):
            for col in range(8):
                tile = gray[row * size // 8 : (row + 1) * size // 8, col * size // 8 : (col + 1) * size // 8]
                means[row, col] = float(tile.mean())
        checker = np.fromfunction(lambda r, c: ((r + c) % 2) * 2 - 1, (8, 8), dtype=int)
        correlation = abs(float(np.sum((means - means.mean()) * checker))) / (64 * 128)
        row_edges = np.mean([np.std(gray[i * size // 8 : i * size // 8 + 2]) for i in range(1, 8)]) / 128
        col_edges = np.mean([np.std(gray[:, i * size // 8 : i * size // 8 + 2]) for i in range(1, 8)]) / 128
        return float(np.clip(correlation + 0.25 * (row_edges + col_edges), 0, 1))

    def detect(self, frame: np.ndarray) -> BoardDetection | None:
        if frame is None or frame.size == 0:
            return None
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 40, 130)
        contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        candidates: list[BoardDetection] = []
        height, width = gray.shape[:2]
        for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:80]:
            x, y, w, h = cv2.boundingRect(contour)
            if min(w, h) < self.min_size or abs(w - h) / max(w, h) > 0.08:
                continue
            if w > width * 0.99 and h > height * 0.99:
                continue
            side = min(w, h)
            crop = frame[y : y + side, x : x + side]
            score = self._grid_score(cv2.resize(gray[y : y + side, x : x + side], (320, 320)))
            if score >= 0.12:
                candidates.append(BoardDetection(crop.copy(), (x, y, side, side), score))
        if candidates:
            return max(candidates, key=lambda item: item.confidence)

        # A checkerboard often has no single continuous outer contour. Its 7x7
        # internal corners still give a stable board rectangle and perspective.
        found, corners = cv2.findChessboardCornersSB(gray, (7, 7), cv2.CALIB_CB_NORMALIZE_IMAGE)
        if found and corners is not None:
            points = corners.reshape(-1, 2)
            grid = points.reshape(7, 7, 2)
            horizontal = np.linalg.norm(np.diff(grid, axis=1), axis=2)
            vertical = np.linalg.norm(np.diff(grid, axis=0), axis=2)
            cell = float(np.median(np.concatenate((horizontal.ravel(), vertical.ravel()))))
            x1 = max(0, int(points[:, 0].min() - cell))
            y1 = max(0, int(points[:, 1].min() - cell))
            x2 = min(width, int(points[:, 0].max() + cell))
            y2 = min(height, int(points[:, 1].max() + cell))
            side = min(x2 - x1, y2 - y1)
            if side >= self.min_size:
                crop = frame[y1:y1 + side, x1:x1 + side].copy()
                score = self._grid_score(cv2.resize(gray[y1:y1 + side, x1:x1 + side], (320, 320)))
                return BoardDetection(crop, (x1, y1, side, side), score)
        return None

    @staticmethod
    def split_squares(board_image: np.ndarray, orientation: str = "white") -> dict[str, np.ndarray]:
        side = min(board_image.shape[:2])
        board = cv2.resize(board_image[:side, :side], (800, 800), interpolation=cv2.INTER_AREA)
        result: dict[str, np.ndarray] = {}
        files = "abcdefgh"
        for screen_row in range(8):
            for screen_col in range(8):
                if orientation == "black":
                    file_index, rank = 7 - screen_col, screen_row + 1
                else:
                    file_index, rank = screen_col, 8 - screen_row
                square = f"{files[file_index]}{rank}"
                result[square] = board[screen_row * 100 : (screen_row + 1) * 100, screen_col * 100 : (screen_col + 1) * 100].copy()
        return result

    @staticmethod
    def image_point_to_square(x: int, y: int, size: int, orientation: str = "white") -> str:
        col = min(7, max(0, int(x * 8 / size)))
        row = min(7, max(0, int(y * 8 / size)))
        if orientation == "black":
            return f"{'hgfedcba'[col]}{row + 1}"
        return f"{'abcdefgh'[col]}{8 - row}"

