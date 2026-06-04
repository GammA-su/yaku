"""Style extraction from original captured frames."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple, Optional
from PIL import Image
import numpy as np


@dataclass
class TextStyle:
    fill_rgb: Tuple[int, int, int]
    stroke_rgb: Tuple[int, int, int]
    estimated_font_size: Optional[int] = None
    shadow_offset: Optional[Tuple[int, int]] = None


def estimate_text_style(crop: Image.Image) -> TextStyle:
    """Estimate fill, stroke colors and font size from a PIL Image containing dialogue text.

    Uses a simple pixel analysis heuristic:
    - Bright pixels likely indicate the text fill.
    - Dark pixels surrounding bright clusters likely indicate the stroke/shadow.
    - Glyph height is estimated from vertical projection of non-background pixels.

    Falls back to a white fill and black stroke on uniform/blank images.
    """
    img = crop.convert("RGB")
    w, h = img.size

    # Fallback default style
    fallback = TextStyle(fill_rgb=(255, 255, 255), stroke_rgb=(0, 0, 0), estimated_font_size=None)

    if w <= 2 or h <= 2:
        return fallback

    arr = np.array(img)
    # Calculate luminance: Y = 0.299R + 0.587G + 0.114B
    gray = (0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]).astype(np.uint8)

    # Use a fixed threshold for finding bright text fill
    bright_mask = gray > 200
    if not np.any(bright_mask):
        # Fallback to a lower threshold if text isn't pure white/bright
        bright_mask = gray > 160

    if not np.any(bright_mask):
        return fallback

    # Compute average color of bright pixels as fill color
    fill_pixels = arr[bright_mask]
    fill_rgb = tuple(map(int, np.mean(fill_pixels, axis=0)))

    # Compute boundary pixels for stroke color estimation
    # Dilate bright mask by rolling/offset shifting
    border_mask = np.zeros_like(bright_mask)
    for dy in [-2, -1, 0, 1, 2]:
        for dx in [-2, -1, 0, 1, 2]:
            if dy == 0 and dx == 0:
                continue
            shifted = np.roll(np.roll(bright_mask, dy, axis=0), dx, axis=1)
            border_mask |= shifted

    # Stroke is represented by relatively dark pixels near bright pixels
    border_mask &= (~bright_mask) & (gray < 120)

    if np.any(border_mask):
        stroke_pixels = arr[border_mask]
        stroke_rgb = tuple(map(int, np.mean(stroke_pixels, axis=0)))
    else:
        stroke_rgb = (0, 0, 0)

    # Estimate font size (glyph height) from vertical projection
    row_counts = np.sum(bright_mask, axis=1)
    # Filter out row noise
    active_rows = np.where(row_counts > max(1, w * 0.005))[0]

    estimated_font_size = None
    if len(active_rows) > 0:
        # Group contiguous active rows
        diffs = np.diff(active_rows)
        breaks = np.where(diffs > 5)[0]  # gaps greater than 5px suggest different lines

        line_heights = []
        start = active_rows[0]
        for b in breaks:
            end = active_rows[b]
            line_heights.append(end - start + 1)
            start = active_rows[b + 1]
        line_heights.append(active_rows[-1] - start + 1)

        if line_heights:
            estimated_font_size = int(np.mean(line_heights))

    # Clamp font size estimate to reasonable bounds
    if estimated_font_size is not None:
        if estimated_font_size < 8:
            estimated_font_size = 8
        elif estimated_font_size > 100:
            estimated_font_size = 100

    # Ensure output color types are pure 3-tuples of ints
    return TextStyle(
        fill_rgb=(int(fill_rgb[0]), int(fill_rgb[1]), int(fill_rgb[2])),
        stroke_rgb=(int(stroke_rgb[0]), int(stroke_rgb[1]), int(stroke_rgb[2])),
        estimated_font_size=estimated_font_size,
        shadow_offset=None
    )
