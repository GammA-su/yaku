"""Tests for region selector coordinate conversion."""
from __future__ import annotations

from yaku.core.image_utils import Rect
from yaku.ui.region_selector import logical_rect_to_physical


def test_logical_rect_to_physical_applies_device_pixel_ratio():
    rect = logical_rect_to_physical(
        Rect(x=100, y=200, w=300, h=80),
        device_pixel_ratio=1.25,
    )

    assert rect == Rect(x=125, y=250, w=375, h=100)


def test_logical_rect_to_physical_applies_screen_origin():
    rect = logical_rect_to_physical(
        Rect(x=10, y=20, w=30, h=40),
        screen_x=1920,
        screen_y=100,
        device_pixel_ratio=1.0,
    )

    assert rect == Rect(x=1930, y=120, w=30, h=40)
