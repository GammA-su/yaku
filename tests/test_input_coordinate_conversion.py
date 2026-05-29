"""Tests for mirror-click → VN-client coordinate conversion (input forwarding).

These are pure-math tests that mirror exactly what ``MirrorWindow`` does when a
click arrives, so they hold on every platform without Qt or pywin32.
"""
from __future__ import annotations

from yaku.v2_mirror.coordinate_map import mirror_click_to_vn_client_coord
from yaku.v2_mirror.input_forward import (
    NullInputForwarder,
    WindowsInputForwarder,
    create_input_forwarder,
)


# ---------------------------------------------------------------------------
# Click inside the displayed frame → correct VN client coordinate
# ---------------------------------------------------------------------------

def test_click_center_maps_to_client_center():
    # 1:1 frame/client, widget same size → click maps straight through.
    coord = mirror_click_to_vn_client_coord(
        640, 360, 1280, 720, 1280, 720, 1280, 720
    )
    assert coord == (640, 360)


def test_click_top_left_corner_maps_to_origin():
    coord = mirror_click_to_vn_client_coord(
        0, 0, 1280, 720, 1280, 720, 1280, 720
    )
    assert coord == (0, 0)


def test_client_differs_from_frame_resolution():
    # Frame captured at 1920x1080 but the live VN client is 960x540 (½ scale).
    coord = mirror_click_to_vn_client_coord(
        640, 360, 1920, 1080, 1280, 720, 960, 540
    )
    assert coord is not None
    cx, cy = coord
    assert abs(cx - 480) <= 1
    assert abs(cy - 270) <= 1


# ---------------------------------------------------------------------------
# Letterbox clicks are ignored
# ---------------------------------------------------------------------------

def test_click_in_top_letterbox_returns_none():
    # 16:9 frame in a square widget → horizontal bars top/bottom.
    coord = mirror_click_to_vn_client_coord(
        500, 10, 1920, 1080, 1000, 1000, 1920, 1080
    )
    assert coord is None


def test_click_in_side_pillarbox_returns_none():
    # 16:9 frame in an ultrawide widget → vertical bars left/right.
    coord = mirror_click_to_vn_client_coord(
        5, 540, 1920, 1080, 2560, 1080, 1920, 1080
    )
    assert coord is None


def test_click_just_inside_displayed_area_maps():
    coord = mirror_click_to_vn_client_coord(
        500, 250, 1920, 1080, 1000, 1000, 1920, 1080
    )
    assert coord is not None


# ---------------------------------------------------------------------------
# Scaling — widget smaller than frame
# ---------------------------------------------------------------------------

def test_scaling_widget_smaller_than_frame():
    # Frame & client 1920x1080, widget shrunk to 640x360 (⅓). Center stays center.
    coord = mirror_click_to_vn_client_coord(
        320, 180, 1920, 1080, 640, 360, 1920, 1080
    )
    assert coord is not None
    cx, cy = coord
    assert abs(cx - 960) <= 3
    assert abs(cy - 540) <= 3


def test_scaling_quarter_point():
    coord = mirror_click_to_vn_client_coord(
        160, 90, 1920, 1080, 640, 360, 1920, 1080
    )
    assert coord is not None
    cx, cy = coord
    assert abs(cx - 480) <= 3
    assert abs(cy - 270) <= 3


# ---------------------------------------------------------------------------
# Fullscreen scaling — widget larger than frame, with letterboxing
# ---------------------------------------------------------------------------

def test_fullscreen_same_aspect_maps_center():
    # 1920x1080 frame shown fullscreen on a 2560x1440 screen (same 16:9).
    coord = mirror_click_to_vn_client_coord(
        1280, 720, 1920, 1080, 2560, 1440, 1920, 1080
    )
    assert coord is not None
    cx, cy = coord
    assert abs(cx - 960) <= 2
    assert abs(cy - 540) <= 2


def test_fullscreen_ultrawide_letterbox_ignored():
    # 16:9 frame fullscreen on a 21:9 (2560x1080) screen → side pillarbars.
    # A click in the left bar is ignored...
    assert mirror_click_to_vn_client_coord(
        10, 540, 1920, 1080, 2560, 1080, 1920, 1080
    ) is None
    # ...but a click at the true center still maps to the client center.
    coord = mirror_click_to_vn_client_coord(
        1280, 540, 1920, 1080, 2560, 1080, 1920, 1080
    )
    assert coord is not None
    cx, cy = coord
    assert abs(cx - 960) <= 2
    assert abs(cy - 540) <= 2


# ---------------------------------------------------------------------------
# Forwarder factory — graceful fallback
# ---------------------------------------------------------------------------

def test_factory_disabled_returns_null():
    fwd = create_input_forwarder("disabled", 1234, forward_input=True)
    assert isinstance(fwd, NullInputForwarder)


def test_factory_forward_input_false_returns_null():
    fwd = create_input_forwarder("send_input_only", 1234, forward_input=False)
    assert isinstance(fwd, NullInputForwarder)


def test_null_forwarder_methods_return_false():
    fwd = NullInputForwarder("test")
    assert fwd.forward_mouse_click(1, 2) is False
    assert fwd.forward_key("enter") is False
    assert fwd.forward_mouse_wheel(120) is False
    assert fwd.client_size() is None
    assert fwd.target_info() == (None, "")


def test_factory_on_non_windows_returns_null():
    import sys

    if sys.platform == "win32":
        # On Windows with pywin32 present this yields a real forwarder; the
        # graceful-fallback path is covered by the platform check itself.
        return
    fwd = create_input_forwarder("send_input_only", 1234, forward_input=True)
    assert isinstance(fwd, NullInputForwarder)


def test_windows_forwarder_unsupported_platform_raises():
    import sys

    from yaku.core.errors import OptionalDependencyMissing

    if sys.platform == "win32":
        return
    try:
        WindowsInputForwarder(1234)
    except OptionalDependencyMissing:
        return
    raise AssertionError("expected OptionalDependencyMissing on non-Windows")
