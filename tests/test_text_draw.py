"""Tests for text wrapping, font fitting, and box drawing utilities."""
from __future__ import annotations

import pytest
from PIL import Image, ImageFont
from yaku.core.image_utils import Rect
from yaku.render.text_fit import wrap_text_to_box, fit_font_to_box
from yaku.render.text_draw import draw_text_box


@pytest.fixture(scope="module")
def font():
    return ImageFont.load_default()


def test_wrap_text_to_box(font):
    text = "This is a relatively long sentence that needs to be wrapped inside the box."
    lines = wrap_text_to_box(text, font, box_w=60)
    assert len(lines) > 1
    assert "".join(lines).replace(" ", "") == text.replace(" ", "")


def test_fit_font_to_box():
    text = "Test auto fit"
    fitted = fit_font_to_box(text, None, box_w=200, box_h=50, min_size=10, max_size=40)
    assert fitted.font is not None
    assert fitted.font_size >= 10
    assert fitted.font_size <= 40


def test_draw_text_box_does_not_modify_content():
    img = Image.new("RGB", (300, 100), (0, 0, 0))
    rect = Rect(10, 10, 280, 80)
    text = "Exact text content match"
    
    style = {
        "font_family": "Arial",
        "font_size": 18,
        "auto_fit": True,
        "stroke_width": 1,
        "fill_rgb": (255, 255, 255),
        "stroke_rgb": (0, 0, 0),
        "alignment": "center",
    }
    
    out = draw_text_box(img, text, rect, style)
    assert out.size == img.size
    import numpy as np
    assert np.array(out).sum() > 0
