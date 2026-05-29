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
