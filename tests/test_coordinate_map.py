"""Tests for v2-mirror coordinate mapping."""
from __future__ import annotations

from yaku.core.image_utils import NormalizedRect
from yaku.v2_mirror.coordinate_map import (
    frame_point_to_widget_point,
    frame_rect_to_normalized_rect,
    frame_to_widget_rect,
    mirror_click_to_vn_client_coord,
    normalized_rect_to_frame_rect,
    widget_point_to_frame_point,
)


# ---------------------------------------------------------------------------
# frame_to_widget_rect
# ---------------------------------------------------------------------------

def test_same_aspect_fills_widget():
    # 16:9 frame in a 16:9 widget → fills exactly, no letterbox.
    rect = frame_to_widget_rect(1920, 1080, 1280, 720)
    assert (rect.x, rect.y, rect.w, rect.h) == (0, 0, 1280, 720)


def test_tall_widget_letterboxes_top_and_bottom():
    # 16:9 frame in a square widget → pillar/letterbox with vertical bars.
    rect = frame_to_widget_rect(1920, 1080, 1000, 1000)
    # Scale limited by width: 1000/1920 → displayed height 562.
    assert rect.w == 1000
    assert rect.h == 562
    assert rect.x == 0
    assert rect.y == (1000 - 562) // 2  # centered vertically


def test_no_preserve_aspect_stretches():
    rect = frame_to_widget_rect(1920, 1080, 1000, 1000, preserve_aspect=False)
    assert (rect.x, rect.y, rect.w, rect.h) == (0, 0, 1000, 1000)


def test_zero_dimensions_return_empty():
    rect = frame_to_widget_rect(0, 0, 100, 100)
    assert (rect.w, rect.h) == (0, 0)


# ---------------------------------------------------------------------------
# widget_point_to_frame_point
# ---------------------------------------------------------------------------

def test_direct_mapping_center():
    # Center of widget maps to center of frame.
    pt = widget_point_to_frame_point(640, 360, 1920, 1080, 1280, 720)
    assert pt is not None
    fx, fy = pt
    assert abs(fx - 960) <= 1
    assert abs(fy - 540) <= 1


def test_point_in_letterbox_returns_none():
    # Tall widget: top region is a letterbox bar → outside displayed frame.
    pt = widget_point_to_frame_point(500, 10, 1920, 1080, 1000, 1000)
    assert pt is None


def test_point_inside_displayed_frame_maps():
    pt = widget_point_to_frame_point(500, 500, 1920, 1080, 1000, 1000)
    assert pt is not None


def test_point_far_outside_returns_none():
    assert widget_point_to_frame_point(2000, 2000, 1920, 1080, 1280, 720) is None


# ---------------------------------------------------------------------------
# frame_point_to_widget_point round trip
# ---------------------------------------------------------------------------

def test_round_trip_widget_frame_widget():
    args = (1920, 1080, 1000, 1000)
    fp = widget_point_to_frame_point(500, 500, *args)
    assert fp is not None
    wp = frame_point_to_widget_point(fp[0], fp[1], *args)
    assert abs(wp[0] - 500) <= 2
    assert abs(wp[1] - 500) <= 2


# ---------------------------------------------------------------------------
# normalized <-> frame rect
# ---------------------------------------------------------------------------

def test_normalized_rect_to_frame_rect():
    norm = NormalizedRect(0.08, 0.72, 0.84, 0.20)
    rect = normalized_rect_to_frame_rect(norm, 1000, 1000)
    assert (rect.x, rect.y, rect.w, rect.h) == (80, 720, 840, 200)


def test_normalized_round_trip():
    norm = NormalizedRect(0.1, 0.2, 0.5, 0.25)
    rect = normalized_rect_to_frame_rect(norm, 1920, 1080)
    back = frame_rect_to_normalized_rect(rect, 1920, 1080)
    assert abs(back.x_ratio - 0.1) < 1e-3
    assert abs(back.y_ratio - 0.2) < 1e-3
    assert abs(back.w_ratio - 0.5) < 1e-3
    assert abs(back.h_ratio - 0.25) < 1e-3


# ---------------------------------------------------------------------------
# mirror_click_to_vn_client_coord
# ---------------------------------------------------------------------------

def test_mirror_click_to_vn_client_scales():
    # Frame captured at 1920x1080, VN client is actually 960x540 (2x scale).
    coord = mirror_click_to_vn_client_coord(
        640, 360, 1920, 1080, 1280, 720, 960, 540
    )
    assert coord is not None
    cx, cy = coord
    assert abs(cx - 480) <= 1
    assert abs(cy - 270) <= 1


def test_mirror_click_in_letterbox_returns_none():
    coord = mirror_click_to_vn_client_coord(
        500, 10, 1920, 1080, 1000, 1000, 1920, 1080
    )
    assert coord is None
