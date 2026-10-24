from __future__ import annotations

import cv2
import numpy as np
from pathlib import Path

from core.board_detector import BoardDetector
from core.piece_recognizer import PieceRecognizer, STARTING_PIECES


def rendered_start_board() -> np.ndarray:
    side, cell = 800, 100
    image = np.zeros((side, side, 3), np.uint8)
    for row in range(8):
        for col in range(8):
            color = (205, 215, 230) if (row + col) % 2 == 0 else (65, 85, 120)
            image[row * cell:(row + 1) * cell, col * cell:(col + 1) * cell] = color
    for square, symbol in STARTING_PIECES.items():
        col = ord(square[0]) - 97
        row = 8 - int(square[1])
        ink = (245, 245, 245) if symbol.isupper() else (15, 15, 15)
        cv2.putText(image, symbol.upper(), (col * cell + 24, row * cell + 72), cv2.FONT_HERSHEY_SIMPLEX, 1.8, ink, 5)
        if symbol.islower():
            cv2.circle(image, (col * cell + 50, row * cell + 50), 37, (120, 120, 120), 2)
    return image


def test_requires_calibration(tmp_path) -> None:
    recognizer = PieceRecognizer(tmp_path)
    result = recognizer.recognize(rendered_start_board())
    assert result.needs_calibration
    assert result.pieces == {}


def test_automatically_detects_start_layout_and_orientation() -> None:
    is_start, orientation, confidence = PieceRecognizer.infer_start_position(rendered_start_board(), "auto")
    assert is_start
    assert orientation == "white"
    assert confidence > 0.8


def test_does_not_auto_calibrate_empty_board() -> None:
    empty = np.full((800, 800, 3), 128, dtype=np.uint8)
    is_start, _orientation, _confidence = PieceRecognizer.infer_start_position(empty, "auto")
    assert not is_start


def test_does_not_auto_calibrate_after_first_move() -> None:
    image = rendered_start_board()
    image[600:700, 400:500] = (205, 215, 230)
    image[400:500, 400:500] = (205, 215, 230)
    cv2.putText(image, "P", (424, 472), cv2.FONT_HERSHEY_SIMPLEX, 1.8, (245, 245, 245), 5)
    is_start, _orientation, _confidence = PieceRecognizer.infer_start_position(image, "auto")
    assert not is_start


def test_calibrate_and_recognize_start_position(tmp_path) -> None:
    image = rendered_start_board()
    recognizer = PieceRecognizer(tmp_path)
    recognizer.calibrate_from_start(image)
    assert recognizer.calibrated
    result = recognizer.recognize(image)
    assert result.pieces == STARTING_PIECES
    assert result.confidence > 0.9


def test_recognizes_move_across_highlighted_square(tmp_path) -> None:
    image = rendered_start_board()
    recognizer = PieceRecognizer(tmp_path)
    recognizer.calibrate_from_start(image)

    moved = image.copy()
    # A highlighted source/destination changes the square color completely.
    highlight = (150, 85, 210)
    moved[600:700, 400:500] = highlight  # e2 becomes empty.
    moved[500:600, 400:500] = highlight  # e3 receives the pawn.
    cv2.putText(moved, "P", (424, 572), cv2.FONT_HERSHEY_SIMPLEX, 1.8, (245, 245, 245), 5)

    result = recognizer.recognize(moved)
    assert "e2" not in result.pieces
    assert result.pieces.get("e3") == "P"


def test_real_calibrated_chesscom_templates_recognize_move() -> None:
    templates_root = Path(__file__).resolve().parents[1] / "assets" / "piece_templates"
    recognizer = PieceRecognizer(templates_root)
    assert recognizer.calibrated
    folder = templates_root / "default"
    board = np.zeros((800, 800, 3), dtype=np.uint8)

    for row in range(8):
        for col in range(8):
            square = f"{'abcdefgh'[col]}{8 - row}"
            symbol = STARTING_PIECES.get(square)
            if symbol:
                candidates = list(folder.glob(f"*_{square}.png"))
                assert candidates
                tile = recognizer._read_image(candidates[0])
            else:
                parity = (col + int(square[1])) % 2
                tile = recognizer._read_image(folder / ("empty_a4.png" if parity == 0 else "empty_a3.png"))
            board[row * 100:(row + 1) * 100, col * 100:(col + 1) * 100] = tile

    is_start, orientation, _confidence = PieceRecognizer.infer_start_position(board, "auto")
    assert is_start and orientation == "white"
    start = recognizer.recognize(board)
    assert start.pieces == STARTING_PIECES
    black_view = np.zeros_like(board)
    for square, tile in BoardDetector.split_squares(board, "white").items():
        col = 7 - (ord(square[0]) - ord("a"))
        row = int(square[1]) - 1
        black_view[row * 100:(row + 1) * 100, col * 100:(col + 1) * 100] = tile
    is_start_black, orientation_black, _confidence = PieceRecognizer.infer_start_position(black_view, "auto")
    assert is_start_black and orientation_black == "black"
    assert recognizer.recognize(black_view, "black").pieces == STARTING_PIECES

    moved = board.copy()
    moved[600:700, 400:500] = recognizer._read_image(folder / "empty_a4.png")
    moved[400:500, 400:500] = recognizer._read_image(folder / "P_e2.png")
    result = recognizer.recognize(moved)
    assert "e2" not in result.pieces
    assert result.pieces.get("e4") == "P"

    # A king has only one starting template. Verify it still classifies when
    # the opponent moves it onto the opposite square colour.
    source = recognizer._read_image(folder / "black_k_e8.png")
    source_background = recognizer._read_image(folder / "empty_a4.png")
    destination = recognizer._read_image(folder / "empty_a3.png").copy()
    difference = np.max(
        np.abs(source.astype(np.int16) - source_background.astype(np.int16)), axis=2
    )
    mask = cv2.dilate((difference > 18).astype(np.uint8), np.ones((3, 3), np.uint8))
    destination[mask > 0] = source[mask > 0]
    king_moved = board.copy()
    king_moved[0:100, 400:500] = source_background
    king_moved[100:200, 400:500] = destination
    king_result = recognizer.recognize(king_moved)
    assert "e8" not in king_result.pieces
    assert king_result.pieces.get("e7") == "k"
    assert king_result.square_confidence["e7"] > recognizer.threshold

