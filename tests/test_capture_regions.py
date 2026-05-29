"""Tests for image-region utilities in yaku.core.image_utils."""
from __future__ import annotations

import pytest
from PIL import Image

from yaku.core.image_utils import (
    NormalizedRect,
    Rect,
    clamp_rect,
    crop_pil,
    normalized_to_rect,
    rect_to_normalized,
)


# ---------------------------------------------------------------------------
# crop_pil
# ---------------------------------------------------------------------------

def test_crop_pil_returns_expected_size():
    img = Image.new("RGB", (200, 200))
    rect = Rect(x=10, y=20, w=50, h=30)
    cropped = crop_pil(img, rect)
    assert cropped.size == (50, 30)


def test_crop_pil_correct_pixel_at_origin():
    img = Image.new("RGB", (100, 100), color=(255, 0, 0))  # all red
    img.putpixel((50, 50), (0, 255, 0))                    # one green pixel
    rect = Rect(x=50, y=50, w=10, h=10)
    cropped = crop_pil(img, rect)
    assert cropped.getpixel((0, 0)) == (0, 255, 0)


def test_crop_pil_full_image():
    img = Image.new("RGB", (80, 60))
    cropped = crop_pil(img, Rect(x=0, y=0, w=80, h=60))
    assert cropped.size == (80, 60)


def test_crop_pil_1x1():
    img = Image.new("RGB", (50, 50), color=(7, 8, 9))
    cropped = crop_pil(img, Rect(x=25, y=25, w=1, h=1))
    assert cropped.size == (1, 1)
    assert cropped.getpixel((0, 0)) == (7, 8, 9)


def test_crop_pil_preserves_mode():
    for mode in ("RGB", "RGBA", "L"):
        img = Image.new(mode, (100, 100))
        cropped = crop_pil(img, Rect(x=0, y=0, w=10, h=10))
        assert cropped.mode == mode


# ---------------------------------------------------------------------------
# normalized_to_rect
# ---------------------------------------------------------------------------

def test_normalized_to_rect_basic():
    norm = NormalizedRect(x_ratio=0.1, y_ratio=0.2, w_ratio=0.5, h_ratio=0.4)
    rect = normalized_to_rect(norm, 1000, 800)
    assert rect.x == 100
    assert rect.y == 160
    assert rect.w == 500
    assert rect.h == 320


def test_normalized_to_rect_full_frame():
    norm = NormalizedRect(x_ratio=0.0, y_ratio=0.0, w_ratio=1.0, h_ratio=1.0)
    rect = normalized_to_rect(norm, 1920, 1080)
    assert rect == Rect(x=0, y=0, w=1920, h=1080)


def test_normalized_to_rect_zero_size():
    norm = NormalizedRect(x_ratio=0.5, y_ratio=0.5, w_ratio=0.0, h_ratio=0.0)
    rect = normalized_to_rect(norm, 200, 200)
    assert rect.w == 0
    assert rect.h == 0


# ---------------------------------------------------------------------------
# rect_to_normalized
# ---------------------------------------------------------------------------

def test_rect_to_normalized_basic():
    rect = Rect(x=100, y=200, w=400, h=300)
    norm = rect_to_normalized(rect, 1000, 1000)
    assert abs(norm.x_ratio - 0.1) < 1e-9
    assert abs(norm.y_ratio - 0.2) < 1e-9
    assert abs(norm.w_ratio - 0.4) < 1e-9
    assert abs(norm.h_ratio - 0.3) < 1e-9


def test_rect_to_normalized_origin():
    rect = Rect(x=0, y=0, w=1920, h=1080)
    norm = rect_to_normalized(rect, 1920, 1080)
    assert norm.x_ratio == 0.0
    assert norm.y_ratio == 0.0
    assert abs(norm.w_ratio - 1.0) < 1e-9
    assert abs(norm.h_ratio - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------

def test_normalized_roundtrip_exact():
    rect = Rect(x=100, y=200, w=300, h=400)
    back = normalized_to_rect(rect_to_normalized(rect, 1000, 1000), 1000, 1000)
    assert back == rect


def test_normalized_roundtrip_small_values():
    rect = Rect(x=1, y=2, w=3, h=4)
    back = normalized_to_rect(rect_to_normalized(rect, 100, 100), 100, 100)
    assert back == rect


def test_normalized_roundtrip_asymmetric_canvas():
    rect = Rect(x=100, y=50, w=200, h=100)
    back = normalized_to_rect(rect_to_normalized(rect, 400, 200), 400, 200)
    assert back == rect


# ---------------------------------------------------------------------------
# clamp_rect
# ---------------------------------------------------------------------------

def test_clamp_rect_inside_bounds_unchanged():
    rect = Rect(x=10, y=10, w=50, h=50)
    assert clamp_rect(rect, 200, 200) == rect


def test_clamp_rect_right_edge_overflow():
    rect = Rect(x=150, y=0, w=100, h=50)
    clamped = clamp_rect(rect, 200, 200)
    assert clamped.x == 150
    assert clamped.w == 50   # 150 + 100 clamped to 200 → w = 50


def test_clamp_rect_bottom_edge_overflow():
    rect = Rect(x=0, y=150, w=50, h=100)
    clamped = clamp_rect(rect, 200, 200)
    assert clamped.y == 150
    assert clamped.h == 50


def test_clamp_rect_both_edges_overflow():
    rect = Rect(x=150, y=150, w=100, h=100)
    clamped = clamp_rect(rect, 200, 200)
    assert clamped == Rect(x=150, y=150, w=50, h=50)


def test_clamp_rect_fully_outside_right():
    rect = Rect(x=300, y=0, w=100, h=50)
    clamped = clamp_rect(rect, 200, 200)
    assert clamped.w == 0


def test_clamp_rect_fully_outside_below():
    rect = Rect(x=0, y=300, w=50, h=100)
    clamped = clamp_rect(rect, 200, 200)
    assert clamped.h == 0


def test_clamp_rect_fully_outside_both():
    rect = Rect(x=300, y=300, w=100, h=100)
    clamped = clamp_rect(rect, 200, 200)
    assert clamped.w == 0
    assert clamped.h == 0


def test_clamp_rect_negative_origin_x():
    rect = Rect(x=-20, y=0, w=100, h=50)
    clamped = clamp_rect(rect, 200, 200)
    assert clamped.x == 0
    assert clamped.w == 80   # right edge was at -20+100=80


def test_clamp_rect_negative_origin_y():
    rect = Rect(x=0, y=-30, w=50, h=100)
    clamped = clamp_rect(rect, 200, 200)
    assert clamped.y == 0
    assert clamped.h == 70   # bottom edge was at -30+100=70


def test_clamp_rect_negative_origin_both():
    rect = Rect(x=-10, y=-20, w=100, h=80)
    clamped = clamp_rect(rect, 200, 200)
    assert clamped.x == 0
    assert clamped.y == 0
    assert clamped.w == 90   # right edge at -10+100=90
    assert clamped.h == 60   # bottom edge at -20+80=60


def test_clamp_rect_zero_dimensions():
    rect = Rect(x=10, y=10, w=0, h=0)
    clamped = clamp_rect(rect, 200, 200)
    assert clamped == rect
