from __future__ import annotations

import cv2
import numpy as np

from core.board_detector import BoardDetector


def synthetic_board(side: int = 480) -> np.ndarray:
    board = np.zeros((side, side, 3), dtype=np.uint8)
    cell = side // 8
    for row in range(8):
        for col in range(8):
            value = 220 if (row + col) % 2 == 0 else 55
            board[row * cell:(row + 1) * cell, col * cell:(col + 1) * cell] = value
    cv2.rectangle(board, (1, 1), (side - 2, side - 2), (10, 10, 10), 4)
    return board


def test_detect_synthetic_board() -> None:
    canvas = np.full((640, 800, 3), 25, np.uint8)
    canvas[80:560, 160:640] = synthetic_board()
    found = BoardDetector(min_size=200).detect(canvas)
    assert found is not None
    assert found.image.shape[0] == found.image.shape[1]
    assert found.confidence >= 0.12


def test_coordinate_conversion_both_orientations() -> None:
    assert BoardDetector.image_point_to_square(5, 5, 800, "white") == "a8"
    assert BoardDetector.image_point_to_square(795, 795, 800, "white") == "h1"
    assert BoardDetector.image_point_to_square(5, 5, 800, "black") == "h1"
    assert BoardDetector.image_point_to_square(795, 795, 800, "black") == "a8"


def test_split_squares_rotated() -> None:
    image = synthetic_board(800)
    white = BoardDetector.split_squares(image, "white")
    black = BoardDetector.split_squares(image, "black")
    assert np.array_equal(white["a8"], black["h1"])
    assert np.array_equal(white["h1"], black["a8"])

