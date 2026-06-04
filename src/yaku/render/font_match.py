"""Resolve font family name to a usable font path."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

_COMMON_WINDOWS_FONTS = {
    "arial": "arial.ttf",
    "times new roman": "times.ttf",
    "courier new": "cour.ttf",
    "segoe ui": "segoeui.ttf",
    "calibri": "calibri.ttf",
    "tahoma": "tahoma.ttf",
    "verdana": "verdana.ttf",
    "noto sans": "NotoSans-Regular.ttf",
}


def find_font(family: str, size: int = 16) -> Optional[Path]:
    """Return a Path to a TTF/OTF file matching *family*, or None if not found."""
    if not family:
        return None
    # If family is already a path to a font, check if it exists and return it
    p = Path(family)
    if p.exists() and p.is_file():
        return p

    family_lower = family.lower()

    # Determine search paths based on OS
    paths = []
    if sys.platform == "win32":
        windir = os.environ.get("SystemRoot", "C:\\Windows")
        paths.append(Path(windir) / "Fonts")
    elif sys.platform == "darwin":
        paths.extend([
            Path("/Library/Fonts"),
            Path("/System/Library/Fonts"),
            Path("~/Library/Fonts").expanduser(),
        ])
    else:
        paths.extend([
            Path("/usr/share/fonts"),
            Path("/usr/local/share/fonts"),
            Path("~/.fonts").expanduser(),
        ])

    # First check common mappings
    common_name = _COMMON_WINDOWS_FONTS.get(family_lower)
    if common_name:
        for base_path in paths:
            font_path = base_path / common_name
            if font_path.exists():
                return font_path
            # Recursive check if not found directly
            try:
                for r_path in base_path.rglob(common_name):
                    if r_path.exists():
                        return r_path
            except Exception:
                pass

    # Do a case-insensitive search for family name in the fonts directory
    for base_path in paths:
        if not base_path.exists():
            continue
        try:
            for item in base_path.rglob("*"):
                if item.is_file() and item.suffix.lower() in {".ttf", ".otf"}:
                    if family_lower in item.name.lower():
                        return item
        except Exception:
            pass

    return None


def load_font(family: str, size: int = 16):
    """Load and return a PIL ImageFont for *family* at *size* pt."""
    from PIL import ImageFont

    path = find_font(family, size)
    if path is not None:
        try:
            return ImageFont.truetype(str(path), size)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()

