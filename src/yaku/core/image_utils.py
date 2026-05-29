"""Image region helpers — coordinate math and PIL crop utilities."""
from __future__ import annotations

from dataclasses import dataclass

from PIL import Image


# ---------------------------------------------------------------------------
# Region types
# ---------------------------------------------------------------------------

@dataclass
class Rect:
    """Pixel-space axis-aligned bounding rectangle."""

    x: int
    y: int
    w: int
    h: int


@dataclass
class NormalizedRect:
    """Viewport-relative bounding rectangle with values in [0, 1].

    Stored as top-left origin + extent, all as fractions of the image size.
    """

    x_ratio: float
    y_ratio: float
    w_ratio: float
    h_ratio: float


# ---------------------------------------------------------------------------
# Coordinate conversions
# ---------------------------------------------------------------------------

def normalized_to_rect(norm: NormalizedRect, width: int, height: int) -> Rect:
    """Convert a :class:`NormalizedRect` to pixel coordinates.

    Uses ``round()`` instead of truncation so that round-tripping a
    :class:`Rect` through :func:`rect_to_normalized` and back gives the
    original pixel values.
    """
    return Rect(
        x=round(norm.x_ratio * width),
        y=round(norm.y_ratio * height),
        w=round(norm.w_ratio * width),
        h=round(norm.h_ratio * height),
    )


def rect_to_normalized(rect: Rect, width: int, height: int) -> NormalizedRect:
    """Convert a pixel :class:`Rect` to viewport-relative fractions."""
    return NormalizedRect(
        x_ratio=rect.x / width,
        y_ratio=rect.y / height,
        w_ratio=rect.w / width,
        h_ratio=rect.h / height,
    )


# ---------------------------------------------------------------------------
# Rect operations
# ---------------------------------------------------------------------------

def clamp_rect(rect: Rect, image_w: int, image_h: int) -> Rect:
    """Return *rect* clamped so it lies entirely within the image bounds.

    Handles negative origins and rects that extend beyond the image edge.
    The returned width/height may be 0 if the rect is fully outside the image.
    """
    x = max(0, min(rect.x, image_w))
    y = max(0, min(rect.y, image_h))
    x2 = max(0, min(rect.x + rect.w, image_w))
    y2 = max(0, min(rect.y + rect.h, image_h))
    return Rect(x=x, y=y, w=max(0, x2 - x), h=max(0, y2 - y))


# ---------------------------------------------------------------------------
# PIL helpers
# ---------------------------------------------------------------------------

def crop_pil(image: Image.Image, rect: Rect) -> Image.Image:
    """Crop *image* to the given *rect*.

    Does **not** clamp; pass a clamped rect if out-of-bounds safety is needed.

    Args:
        image: Any PIL image.
        rect:  Pixel-space region to crop.

    Returns:
        A new PIL image of size ``(rect.w, rect.h)``.
    """
    return image.crop((rect.x, rect.y, rect.x + rect.w, rect.y + rect.h))
