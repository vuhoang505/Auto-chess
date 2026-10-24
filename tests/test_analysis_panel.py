from __future__ import annotations

from ui.analysis_panel import AnalysisPanel


def test_history_labels_group_white_and_black_moves() -> None:
    assert AnalysisPanel._move_label(1, "e4") == "1.  e4"
    assert AnalysisPanel._move_label(2, "e5") == "1...  e5"
    assert AnalysisPanel._move_label(3, "Nf3") == "2.  Nf3"
