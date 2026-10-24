from __future__ import annotations

from dataclasses import dataclass

import chess

from core.fen_builder import FenError, build_fen, pieces_from_board, placement_from_pieces


@dataclass(frozen=True)
class DetectedMove:
    uci: str
    san: str
    fen: str
    ply: int


@dataclass(frozen=True)
class TrackResult:
    accepted: bool
    fen: str | None
    move_uci: str | None = None
    move_san: str | None = None
    new_game: bool = False
    needs_metadata: bool = False
    reason: str = ""
    detected_moves: tuple[DetectedMove, ...] = ()


class PositionTracker:
    def __init__(self):
        self.board: chess.Board | None = None
        self.moves: list[str] = []

    def reset(self) -> None:
        self.board = None
        self.moves.clear()

    def restore(self, fen: str) -> TrackResult:
        try:
            board = chess.Board(fen)
            if not board.is_valid():
                return TrackResult(False, None, reason="FEN lịch sử không hợp lệ.")
            self.board = board
            self.moves.clear()
            return TrackResult(True, board.fen())
        except ValueError as exc:
            return TrackResult(False, None, reason=str(exc))

    def initialize(
        self,
        pieces: dict[str, str],
        turn: str | None = None,
        castling: str | None = None,
        en_passant: str = "-",
    ) -> TrackResult:
        placement = placement_from_pieces(pieces)
        starting = chess.Board()
        if placement == starting.board_fen():
            self.board = starting
            self.moves.clear()
            return TrackResult(True, self.board.fen(), new_game=True)
        if turn is None or castling is None:
            return TrackResult(False, None, needs_metadata=True, reason="Cần xác nhận lượt đi và quyền nhập thành.")
        try:
            self.board = chess.Board(build_fen(pieces, turn, castling, en_passant))
        except (FenError, ValueError) as exc:
            return TrackResult(False, None, reason=str(exc))
        self.moves.clear()
        return TrackResult(True, self.board.fen())

    def update(self, pieces: dict[str, str]) -> TrackResult:
        if self.board is None:
            return self.initialize(pieces)
        placement = placement_from_pieces(pieces)
        if placement == self.board.board_fen():
            return TrackResult(True, self.board.fen())
        if placement == chess.Board().board_fen():
            return self.initialize(pieces)

        matches: list[tuple[chess.Move, ...]] = []
        for move in self.board.legal_moves:
            candidate = self.board.copy(stack=False)
            candidate.push(move)
            if candidate.board_fen() == placement:
                matches.append((move,))
        # If one visual update was lost during a browser animation, the old
        # implementation stayed desynchronised forever. Search one extra ply
        # so a missed player/opponent move can be reconstructed legally.
        if not matches:
            for first in self.board.legal_moves:
                after_first = self.board.copy(stack=False)
                after_first.push(first)
                for second in after_first.legal_moves:
                    candidate = after_first.copy(stack=False)
                    candidate.push(second)
                    if candidate.board_fen() == placement:
                        matches.append((first, second))
                        if len(matches) > 1:
                            break
                if len(matches) > 1:
                    break
        if len(matches) != 1:
            reason = "Không khớp nước đi hợp lệ" if not matches else "Vị trí mơ hồ"
            return TrackResult(False, self.board.fen(), reason=reason)
        detected: list[DetectedMove] = []
        for move in matches[0]:
            san = self.board.san(move)
            uci = move.uci()
            self.board.push(move)
            self.moves.append(san)
            detected.append(DetectedMove(uci, san, self.board.fen(), self.board.ply()))
        last = detected[-1]
        return TrackResult(
            True, self.board.fen(), last.uci, last.san,
            detected_moves=tuple(detected),
        )

    @property
    def outcome_text(self) -> str:
        if self.board is None:
            return ""
        if self.board.is_checkmate():
            return "Chiếu hết"
        if self.board.is_check():
            return "Chiếu"
        outcome = self.board.outcome(claim_draw=True)
        if not outcome:
            return ""
        draw_reasons = {
            chess.Termination.STALEMATE: "Hòa do hết nước đi",
            chess.Termination.INSUFFICIENT_MATERIAL: "Hòa do thiếu quân chiếu hết",
            chess.Termination.SEVENTYFIVE_MOVES: "Hòa theo luật 75 nước",
            chess.Termination.FIVEFOLD_REPETITION: "Hòa do lặp lại năm lần",
            chess.Termination.FIFTY_MOVES: "Hòa theo luật 50 nước",
            chess.Termination.THREEFOLD_REPETITION: "Hòa do lặp lại ba lần",
        }
        return draw_reasons.get(outcome.termination, f"Kết thúc: {outcome.result()}")

    @property
    def pieces(self) -> dict[str, str]:
        return pieces_from_board(self.board) if self.board else {}

