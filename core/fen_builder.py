from __future__ import annotations

import chess


class FenError(ValueError):
    pass


def placement_from_pieces(pieces: dict[str, str]) -> str:
    invalid = set(pieces.values()) - set("PNBRQKpnbrqk")
    if invalid:
        raise FenError(f"Ký hiệu quân không hợp lệ: {sorted(invalid)}")
    ranks: list[str] = []
    for rank in range(8, 0, -1):
        empty = 0
        fields: list[str] = []
        for file in "abcdefgh":
            piece = pieces.get(f"{file}{rank}")
            if piece is None:
                empty += 1
            else:
                if empty:
                    fields.append(str(empty))
                    empty = 0
                fields.append(piece)
        if empty:
            fields.append(str(empty))
        ranks.append("".join(fields))
    return "/".join(ranks)


def build_fen(
    pieces: dict[str, str],
    turn: str,
    castling: str = "-",
    en_passant: str = "-",
    halfmove: int = 0,
    fullmove: int = 1,
) -> str:
    if turn not in ("w", "b"):
        raise FenError("Lượt đi phải là 'w' hoặc 'b'.")
    castling = castling or "-"
    fen = f"{placement_from_pieces(pieces)} {turn} {castling} {en_passant} {halfmove} {fullmove}"
    try:
        board = chess.Board(fen)
    except ValueError as exc:
        raise FenError(str(exc)) from exc
    status = board.status()
    if status != chess.STATUS_VALID:
        raise FenError(f"Vị trí không hợp lệ (python-chess status={int(status)}).")
    return fen


def pieces_from_board(board: chess.Board) -> dict[str, str]:
    return {chess.square_name(square): piece.symbol() for square, piece in board.piece_map().items()}

