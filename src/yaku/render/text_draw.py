"""Draw text onto a PIL image or numpy frame."""
from __future__ import annotations

from typing import Sequence, Union

import numpy as np
from PIL import Image, ImageDraw, ImageFont

AnyFont = Union[ImageFont.ImageFont, ImageFont.FreeTypeFont]

# Four-neighbour offsets used for a cheap 1px text outline.
_OUTLINE_OFFSETS = ((-1, 0), (1, 0), (0, -1), (0, 1))


def draw_text_pil(
    image: Image.Image,
    text: str,
    x: int,
    y: int,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int, int] = (255, 255, 255, 255),
    outline: bool = False,
    outline_fill: tuple[int, int, int, int] = (0, 0, 0, 200),
) -> Image.Image:
    draw = ImageDraw.Draw(image)
    if outline:
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            draw.text((x + dx, y + dy), text, font=font, fill=outline_fill)
    draw.text((x, y), text, font=font, fill=fill)
    return image


def draw_text_block(
    draw: ImageDraw.ImageDraw,
    lines: Sequence[str],
    x: int,
    y: int,
    font: AnyFont,
    line_height: int,
    fill: tuple[int, int, int, int] = (255, 255, 255, 255),
    outline: bool = True,
    outline_fill: tuple[int, int, int, int] = (0, 0, 0, 220),
) -> None:
    """Draw a block of pre-wrapped *lines* top-down, one per *line_height*.

    Renders directly through an existing :class:`PIL.ImageDraw.ImageDraw` so
    callers can compose onto an RGBA overlay.  Each line gets an optional cheap
    1px outline for legibility over arbitrary backgrounds.
    """
    cy = y
    for line in lines:
        if outline:
            for dx, dy in _OUTLINE_OFFSETS:
                draw.text((x + dx, cy + dy), line, font=font, fill=outline_fill)
        draw.text((x, cy), line, font=font, fill=fill)
        cy += line_height


def draw_text_on_frame(
    frame: np.ndarray,
    text: str,
    x: int,
    y: int,
    font: ImageFont.FreeTypeFont,
) -> np.ndarray:
    img = Image.fromarray(frame)
    img = draw_text_pil(img, text, x, y, font)
    return np.array(img)


def draw_text_box(
    image: Image.Image,
    text: str,
    rect: "Rect",
    style: object,
) -> Image.Image:
    """Draw *text* inside *rect* on *image* styled according to *style* config/dict.

    Supports stroke_width, stroke_fill, fill, line_spacing, and left/center alignment.
    Does not modify input text.
    """
    from PIL import ImageDraw, ImageFont
    from yaku.core.image_utils import Rect
    from yaku.render.font_match import find_font
    from yaku.render.text_fit import fit_font_to_box, wrap_text_to_box

    def get_attr(name: str, fallback):
        if isinstance(style, dict):
            return style.get(name, fallback)
        return getattr(style, name, fallback)

    # Extract fill color
    fill = get_attr("fill", None)
    if fill is None:
        fill = get_attr("fill_rgb", (255, 255, 255))
    if isinstance(fill, list):
        fill = tuple(fill)
    if isinstance(fill, tuple) and len(fill) == 3:
        fill = (fill[0], fill[1], fill[2], 255)

    # Extract stroke color
    stroke_fill = get_attr("stroke_fill", None)
    if stroke_fill is None:
        stroke_fill = get_attr("stroke_rgb", (0, 0, 0))
    if isinstance(stroke_fill, list):
        stroke_fill = tuple(stroke_fill)
    if isinstance(stroke_fill, tuple) and len(stroke_fill) == 3:
        stroke_fill = (stroke_fill[0], stroke_fill[1], stroke_fill[2], 255)

    stroke_width = get_attr("stroke_width", 2)
    line_spacing = get_attr("line_spacing", 1.15)
    alignment = get_attr("alignment", "left")

    font_path = get_attr("font_path", None)
    font_family = get_attr("font_family", "Noto Sans")
    font_size = get_attr("font_size", None)
    auto_fit = get_attr("auto_fit", True)
    min_font_size = get_attr("min_font_size", 14)
    max_font_size = get_attr("max_font_size", 42)

    font_spec = font_path or font_family

    box_w = max(1, rect.w)
    box_h = max(1, rect.h)

    _FONT_CANDIDATES = (
        "arial.ttf",
        "DejaVuSans.ttf",
        "Arial.ttf",
        "segoeui.ttf",
    )

    def _load_font(size: int):
        if font_spec:
            path = find_font(font_spec, size)
            if path is not None:
                try:
                    return ImageFont.truetype(str(path), size)
                except Exception:
                    pass
        for name in _FONT_CANDIDATES:
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                continue
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            return ImageFont.load_default()

    def _line_height(font, line_spacing: float) -> int:
        try:
            ascent, descent = font.getmetrics()
        except AttributeError:
            bbox = font.getbbox("Ag")
            ascent, descent = bbox[3] - bbox[1], 0
        return max(1, int(round((ascent + descent) * line_spacing)))

    if font_size is not None and not auto_fit:
        font = _load_font(font_size)
        lines = wrap_text_to_box(text, font, box_w)
        line_height = _line_height(font, line_spacing)
    else:
        fitted = fit_font_to_box(
            text,
            font_spec,
            box_w,
            box_h,
            min_size=min_font_size,
            max_size=max_font_size,
            line_spacing=line_spacing,
        )
        font = fitted.font
        lines = fitted.lines
        line_height = fitted.line_height

    rgba = image.convert("RGBA")
    overlay = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    total_h = len(lines) * line_height
    ty = rect.y + max(0, (box_h - total_h) // 2)

    cy = ty
    for line in lines:
        if not line:
            cy += line_height
            continue
        try:
            line_w = font.getlength(line)
        except AttributeError:
            bbox = font.getbbox(line)
            line_w = bbox[2] - bbox[0]

        if alignment == "center":
            tx = rect.x + max(0, (box_w - line_w) // 2)
        else:
            tx = rect.x

        if stroke_width > 0:
            try:
                draw.text(
                    (tx, cy),
                    line,
                    font=font,
                    fill=fill,
                    stroke_width=stroke_width,
                    stroke_fill=stroke_fill,
                )
            except TypeError:
                for dx in range(-stroke_width, stroke_width + 1):
                    for dy in range(-stroke_width, stroke_width + 1):
                        if dx == 0 and dy == 0:
                            continue
                        draw.text((tx + dx, cy + dy), line, font=font, fill=stroke_fill)
                draw.text((tx, cy), line, font=font, fill=fill)
        else:
            draw.text((tx, cy), line, font=font, fill=fill)
        cy += line_height

    composed = Image.alpha_composite(rgba, overlay)
    return composed.convert("RGB")

