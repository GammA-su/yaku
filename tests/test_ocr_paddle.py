"""Tests for PaddleOCR result parsing."""
from __future__ import annotations

from yaku.ocr.paddleocr_backend import _parse_v2_result, _parse_v3_result


class _V3Page:
    json = {
        "res": {
            "rec_texts": ["エルフの国は太平洋に、", "獣人の国は東シナ海に……"],
            "rec_scores": [0.95, 0.85],
        }
    }


def test_parse_v3_result_lines_and_confidence():
    result = _parse_v3_result([_V3Page()])

    assert result.text == "エルフの国は太平洋に、\n獣人の国は東シナ海に……"
    assert result.confidence is not None
    assert abs(result.confidence - 0.9) < 1e-9


def test_parse_v2_result_lines_and_confidence():
    raw = [
        [
            [[[0, 0], [1, 0], [1, 1], [0, 1]], ("一行目", 0.8)],
            [[[0, 2], [1, 2], [1, 3], [0, 3]], ("二行目", 1.0)],
        ]
    ]

    result = _parse_v2_result(raw)

    assert result.text == "一行目\n二行目"
    assert result.confidence is not None
    assert abs(result.confidence - 0.9) < 1e-9
