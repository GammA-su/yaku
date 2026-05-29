"""Text layout utilities for PIL-based rendering."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Union

from PIL import ImageFont

AnyFont = Union[ImageFont.ImageFont, ImageFont.FreeTypeFont]


def _measure_width(
    font: Union[ImageFont.ImageFont, ImageFont.FreeTypeFont],
    text: str,
) -> float:
    """Return the rendered pixel width of *text* using *font*.

    Uses ``getlength`` (most accurate for advance width) and falls back to
    the bounding-box width for older PIL font objects.
    """
    try:
        return font.getlength(text)
    except AttributeError:
        bbox = font.getbbox(text)
        return float(bbox[2] - bbox[0])


def wrap_text_to_width(
    text: str,
    font: Union[ImageFont.ImageFont, ImageFont.FreeTypeFont],
    max_width: int,
) -> list[str]:
    """Split *text* into lines each no wider than *max_width* pixels.

    Existing newlines in *text* are treated as hard paragraph breaks.
    Each paragraph is word-wrapped independently.  A word that is wider
    than *max_width* on its own is placed alone on its line rather than
    being split mid-character.

    Args:
        text:      Input text (may contain ``\\n`` characters).
        font:      Loaded PIL font used to measure glyph widths.
        max_width: Maximum line width in pixels.

    Returns:
        List of wrapped lines.  Never empty — an empty *text* returns
        ``[""]``.
    """
    if not text:
        return [""]

    output: list[str] = []

    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            output.append("")
            continue

        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if _measure_width(font, candidate) <= max_width:
                current = candidate
            else:
                output.append(current)
                current = word
        output.append(current)

    return output


def fit_font_size(
    text: str,
    font_path: str,
    box_w: int,
    box_h: int,
    min_size: int = 8,
    max_size: int = 72,
) -> int:
    """Binary-search for the largest font size where *text* fits in (*box_w*, *box_h*).

    Only the first line of *text* is measured (use :func:`wrap_text_to_width`
    for multi-line text before calling this).
    """
    lo, hi = min_size, max_size
    best = min_size
    while lo <= hi:
        mid = (lo + hi) // 2
        font = ImageFont.truetype(font_path, mid)
        bbox = font.getbbox(text)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        if tw <= box_w and th <= box_h:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best


@dataclass
class FittedText:
    """Result of fitting wrapped text into a box."""

    font: AnyFont
    lines: list[str]
    font_size: int
    line_height: int


def _line_height(font: AnyFont, line_spacing: float) -> int:
    """Return the per-line advance height for *font* including *line_spacing*."""
    ascent, descent = 0, 0
    try:
        ascent, descent = font.getmetrics()
    except AttributeError:
        bbox = font.getbbox("Ag")
        ascent, descent = bbox[3] - bbox[1], 0
    return max(1, int(round((ascent + descent) * line_spacing)))


def fit_wrapped_text(
    text: str,
    box_w: int,
    box_h: int,
    load_font: Callable[[int], AnyFont],
    *,
    min_size: int = 8,
    max_size: int = 96,
    line_spacing: float = 1.15,
) -> FittedText:
    """Find the largest font size whose word-wrapped *text* fits in the box.

    *load_font* is a callable returning a font object for a given pixel size
    (this keeps the fitter independent of how fonts are resolved).  The text is
    wrapped to *box_w* at each candidate size and rejected if the wrapped block
    is taller than *box_h* or any line is wider than *box_w*.

    Always returns a usable :class:`FittedText`; if even *min_size* overflows,
    the result at *min_size* is returned (the caller may clip).
    """
    lo, hi = min_size, max_size
    best_size = min_size

    def _fits(size: int) -> bool:
        font = load_font(size)
        lines = wrap_text_to_width(text, font, box_w)
        widest = max((_measure_width(font, line) for line in lines), default=0.0)
        total_h = len(lines) * _line_height(font, line_spacing)
        return widest <= box_w and total_h <= box_h

    while lo <= hi:
        mid = (lo + hi) // 2
        if _fits(mid):
            best_size = mid
            lo = mid + 1
        else:
            hi = mid - 1

    font = load_font(best_size)
    lines = wrap_text_to_width(text, font, box_w)
    return FittedText(
        font=font,
        lines=lines,
        font_size=best_size,
        line_height=_line_height(font, line_spacing),
    )
