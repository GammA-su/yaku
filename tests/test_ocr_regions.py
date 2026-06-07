from __future__ import annotations

from yaku.ocr.base import OCRBox
from yaku.v1_overlay_max.ocr_regions import (
    sort_ocr_boxes_reading_order,
    merge_nearby_ocr_boxes,
    filter_ocr_boxes,
)
from yaku.v1_overlay_max.layout import compute_label_positions


class DummyConfig:
    def __init__(self, japanese_only=True, min_text_chars=1, max_regions=30):
        self.japanese_only = japanese_only
        self.min_text_chars = min_text_chars
        self.max_regions = max_regions


def test_filter_ocr_boxes():
    boxes = [
        OCRBox(text="日本語", box=(0, 0, 10, 10)),
        OCRBox(text="English", box=(0, 0, 10, 10)),
        OCRBox(text="日", box=(0, 0, 10, 10)),
        OCRBox(text="", box=(0, 0, 10, 10)),
    ]

    cfg = DummyConfig(japanese_only=True, min_text_chars=1)
    filtered = filter_ocr_boxes(boxes, cfg)
    assert len(filtered) == 2
    assert filtered[0].text == "日本語"
    assert filtered[1].text == "日"

    cfg_short = DummyConfig(japanese_only=True, min_text_chars=2)
    filtered_short = filter_ocr_boxes(boxes, cfg_short)
    assert len(filtered_short) == 1
    assert filtered_short[0].text == "日本語"

    cfg_cap = DummyConfig(japanese_only=False, min_text_chars=1, max_regions=1)
    filtered_cap = filter_ocr_boxes(boxes, cfg_cap)
    assert len(filtered_cap) == 1
    assert filtered_cap[0].text == "日本語"


def test_merge_nearby_ocr_boxes():
    boxes = [
        OCRBox(text="日本", box=(10, 10, 40, 20)),
        OCRBox(text="語", box=(55, 10, 20, 20)),
    ]
    merged = merge_nearby_ocr_boxes(boxes, distance_px=16)
    assert len(merged) == 1
    assert merged[0].text == "日本語"
    assert merged[0].box == (10, 10, 65, 20)


def test_label_layout_avoids_offscreen():
    boxes = [
        OCRBox(text="A", box=(5, 5, 20, 20)),
        OCRBox(text="B", box=(980, 5, 20, 20)),
    ]
    label_sizes = [(100, 30), (100, 30)]

    class DummyOverlayConfig:
        anchor = "right"
        padding = 6
        avoid_offscreen = True

    class DummyMaxConfig:
        overlay = DummyOverlayConfig()

    positions = compute_label_positions(
        boxes=boxes,
        label_sizes=label_sizes,
        screen_width=1000,
        screen_height=1000,
        config=DummyMaxConfig(),
    )

    assert positions[0] == (31, 0)
    assert positions[1] == (900, 0)
