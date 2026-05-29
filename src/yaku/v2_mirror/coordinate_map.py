"""Map coordinates between captured-frame space and mirror-widget space.

The mirror window shows a captured VN frame inside a Qt widget.  When the
aspect ratios differ the frame is letterboxed (centered with black bars), so a
widget pixel does not map linearly onto the whole widget — it maps onto the
displayed sub-rectangle only.  These helpers convert between:

- **frame space**   — pixels of the captured image (``frame_w`` × ``frame_h``)
- **widget space**  — pixels of the Qt widget (``widget_w`` × ``widget_h``)
- **normalized space** — fractions in ``[0, 1]`` relative to the frame
- **VN client space** — pixels of the real VN window client area

All functions are pure; they hold no Qt objects so they are unit-testable.
"""
from __future__ import annotations

from typing import Optional

from yaku.core.image_utils import (
    NormalizedRect,
    Rect,
    normalized_to_rect,
    rect_to_normalized,
)


# ---------------------------------------------------------------------------
# Frame ↔ widget display rectangle
# ---------------------------------------------------------------------------

def frame_to_widget_rect(
    frame_w: int,
    frame_h: int,
    widget_w: int,
    widget_h: int,
    preserve_aspect: bool = True,
) -> Rect:
    """Return the widget-space rectangle the frame is drawn into.

    When *preserve_aspect* is ``True`` the frame is scaled to fit inside the
    widget and centered, producing letterbox/pillarbox bars.  When ``False``
    the frame is stretched to fill the whole widget.

    Returns a zero-size :class:`Rect` if either source dimension is non-positive.
    """
    if frame_w <= 0 or frame_h <= 0 or widget_w <= 0 or widget_h <= 0:
        return Rect(x=0, y=0, w=0, h=0)

    if not preserve_aspect:
        return Rect(x=0, y=0, w=widget_w, h=widget_h)

    scale = min(widget_w / frame_w, widget_h / frame_h)
    disp_w = int(round(frame_w * scale))
    disp_h = int(round(frame_h * scale))
    x = (widget_w - disp_w) // 2
    y = (widget_h - disp_h) // 2
    return Rect(x=x, y=y, w=disp_w, h=disp_h)


# ---------------------------------------------------------------------------
# Point conversions
# ---------------------------------------------------------------------------

def widget_point_to_frame_point(
    wx: int,
    wy: int,
    frame_w: int,
    frame_h: int,
    widget_w: int,
    widget_h: int,
    preserve_aspect: bool = True,
) -> Optional[tuple[int, int]]:
    """Map a widget pixel to a frame pixel.

    Returns ``None`` when the point falls outside the displayed frame
    rectangle (i.e. inside a letterbox bar).
    """
    disp = frame_to_widget_rect(frame_w, frame_h, widget_w, widget_h, preserve_aspect)
    if disp.w <= 0 or disp.h <= 0:
        return None
    if not (disp.x <= wx < disp.x + disp.w and disp.y <= wy < disp.y + disp.h):
        return None

    fx = (wx - disp.x) / disp.w * frame_w
    fy = (wy - disp.y) / disp.h * frame_h
    return (int(fx), int(fy))


def frame_point_to_widget_point(
    fx: int,
    fy: int,
    frame_w: int,
    frame_h: int,
    widget_w: int,
    widget_h: int,
    preserve_aspect: bool = True,
) -> tuple[int, int]:
    """Map a frame pixel to its widget pixel (inverse of
    :func:`widget_point_to_frame_point`)."""
    disp = frame_to_widget_rect(frame_w, frame_h, widget_w, widget_h, preserve_aspect)
    if frame_w <= 0 or frame_h <= 0:
        return (disp.x, disp.y)
    wx = disp.x + fx / frame_w * disp.w
    wy = disp.y + fy / frame_h * disp.h
    return (int(round(wx)), int(round(wy)))


# ---------------------------------------------------------------------------
# Normalized ↔ frame rectangle
# ---------------------------------------------------------------------------

def normalized_rect_to_frame_rect(
    norm: NormalizedRect,
    frame_w: int,
    frame_h: int,
) -> Rect:
    """Convert a normalized ``[0, 1]`` rect into frame pixel coordinates."""
    return normalized_to_rect(norm, frame_w, frame_h)


def frame_rect_to_normalized_rect(
    rect: Rect,
    frame_w: int,
    frame_h: int,
) -> NormalizedRect:
    """Convert a frame pixel rect into normalized ``[0, 1]`` coordinates."""
    return rect_to_normalized(rect, frame_w, frame_h)


# ---------------------------------------------------------------------------
# Mirror click → VN client coordinate
# ---------------------------------------------------------------------------

def mirror_click_to_vn_client_coord(
    wx: int,
    wy: int,
    frame_w: int,
    frame_h: int,
    widget_w: int,
    widget_h: int,
    vn_client_w: int,
    vn_client_h: int,
    preserve_aspect: bool = True,
) -> Optional[tuple[int, int]]:
    """Map a mirror-widget click to a coordinate in the VN window client area.

    Goes widget → frame → VN client, accounting for any scale difference
    between the captured frame and the live VN client size.  Returns ``None``
    when the click landed in a letterbox bar (outside the displayed frame).

    Input forwarding is not wired up yet, but this is the conversion a future
    input-forwarder will use.
    """
    fp = widget_point_to_frame_point(
        wx, wy, frame_w, frame_h, widget_w, widget_h, preserve_aspect
    )
    if fp is None:
        return None
    fx, fy = fp
    if frame_w <= 0 or frame_h <= 0:
        return None
    cx = fx / frame_w * vn_client_w
    cy = fy / frame_h * vn_client_h
    return (int(cx), int(cy))


# ---------------------------------------------------------------------------
# Legacy linear mapper (kept for backwards compatibility)
# ---------------------------------------------------------------------------

class CoordinateMap:
    """Converts (x, y) between two rectangles with simple linear scaling.

    Does not handle aspect-ratio letterboxing; prefer the module-level
    functions for mirror display mapping.
    """

    def __init__(self, source: Rect, display: Rect) -> None:
        self._source = source
        self._display = display

    def to_display(self, x: int, y: int) -> tuple[int, int]:
        sx = (x - self._source.x) / max(self._source.w, 1)
        sy = (y - self._source.y) / max(self._source.h, 1)
        return (
            int(self._display.x + sx * self._display.w),
            int(self._display.y + sy * self._display.h),
        )

    def to_source(self, x: int, y: int) -> tuple[int, int]:
        sx = (x - self._display.x) / max(self._display.w, 1)
        sy = (y - self._display.y) / max(self._display.h, 1)
        return (
            int(self._source.x + sx * self._source.w),
            int(self._source.y + sy * self._source.h),
        )
