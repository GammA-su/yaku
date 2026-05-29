"""Resolve font family name to a usable font path. Not implemented yet."""
from __future__ import annotations

from pathlib import Path
from typing import Optional


def find_font(family: str, size: int = 16) -> Optional[Path]:
    """Return a Path to a TTF/OTF file matching *family*, or None if not found."""
    raise NotImplementedError("not implemented yet")


def load_font(family: str, size: int = 16):
    """Load and return a PIL ImageFont for *family* at *size* pt."""
    from PIL import ImageFont

    path = find_font(family, size)
    if path is not None:
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()
