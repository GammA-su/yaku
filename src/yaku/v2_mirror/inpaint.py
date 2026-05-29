"""Inpaint / erase original text from a frame region.

For the MVP the mask is a padded rectangle over the text/replacement region —
no glyph-perfect masking yet.  Only the OpenCV backend is implemented;
AnyText2-style editing is reserved for ``ai-text-edit``.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from PIL import Image, ImageDraw

from yaku.core.config import InpaintConfig
from yaku.core.errors import InpaintError, InvalidBackendError, OptionalDependencyMissing
from yaku.core.image_utils import Rect, clamp_rect
from yaku.core.logging import get_logger

_log = get_logger("inpaint")


# ---------------------------------------------------------------------------
# Mask creation
# ---------------------------------------------------------------------------

def build_rect_mask(size: tuple[int, int], rect: Rect, padding: int = 0) -> Image.Image:
    """Return an ``L``-mode mask (white = inpaint) the same size as the image.

    The *rect* is expanded by *padding* on every side and then clamped to the
    image bounds, so the white region never extends outside the frame.
    """
    width, height = size
    padded = Rect(
        x=rect.x - padding,
        y=rect.y - padding,
        w=rect.w + 2 * padding,
        h=rect.h + 2 * padding,
    )
    clamped = clamp_rect(padded, width, height)

    mask = Image.new("L", (width, height), 0)
    if clamped.w > 0 and clamped.h > 0:
        draw = ImageDraw.Draw(mask)
        # Inclusive coordinates: fill exactly clamped.w × clamped.h pixels.
        draw.rectangle(
            (clamped.x, clamped.y, clamped.x + clamped.w - 1, clamped.y + clamped.h - 1),
            fill=255,
        )
    return mask


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

class BaseInpainter(ABC):
    """Removes content under a mask, reconstructing plausible background."""

    @abstractmethod
    def inpaint(self, image: Image.Image, mask: Image.Image) -> Image.Image:
        """Return a copy of *image* with the white areas of *mask* reconstructed.

        *image* and the result are ``RGB``; *mask* is single-channel (``L``)
        where non-zero pixels mark the region to inpaint.  The output is the
        same size as *image*.
        """


# ---------------------------------------------------------------------------
# OpenCV backend
# ---------------------------------------------------------------------------

class OpenCVInpainter(BaseInpainter):
    """Inpaint using ``cv2.inpaint`` (Telea or Navier-Stokes)."""

    _METHODS = ("telea", "ns")

    def __init__(self, method: str = "telea", radius: int = 3) -> None:
        if method not in self._METHODS:
            raise InvalidBackendError(
                f"Unknown inpaint method '{method}'. Valid: {', '.join(self._METHODS)}"
            )
        try:
            import cv2  # lazy import
        except ImportError as exc:
            raise OptionalDependencyMissing(
                "opencv is not installed. Install with: uv add opencv-python"
            ) from exc

        self._cv2 = cv2
        self._radius = max(1, int(radius))
        self._flag = cv2.INPAINT_TELEA if method == "telea" else cv2.INPAINT_NS
        self._method = method

    def inpaint(self, image: Image.Image, mask: Image.Image) -> Image.Image:
        import numpy as np

        rgb = np.array(image.convert("RGB"))
        bgr = rgb[:, :, ::-1].copy()  # RGB → BGR for OpenCV
        m = np.array(mask.convert("L"))

        if m.shape[:2] != bgr.shape[:2]:
            raise InpaintError(
                f"mask size {m.shape[:2]} != image size {bgr.shape[:2]}"
            )

        try:
            out_bgr = self._cv2.inpaint(bgr, m, self._radius, self._flag)
        except Exception as exc:  # noqa: BLE001 — surface as a typed error
            raise InpaintError(f"cv2.inpaint failed: {exc}") from exc

        out_rgb = out_bgr[:, :, ::-1]
        return Image.fromarray(out_rgb, mode="RGB")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_inpainter(config: InpaintConfig) -> BaseInpainter:
    """Instantiate the inpainter described by *config*.

    Raises :class:`OptionalDependencyMissing` when the backend's package is
    not installed, or :class:`InvalidBackendError` for unknown backends.
    """
    if config.backend == "opencv":
        return OpenCVInpainter(method=config.method, radius=config.radius)

    raise InvalidBackendError(
        f"Unknown inpaint backend: '{config.backend}'. Valid choices: opencv"
    )
