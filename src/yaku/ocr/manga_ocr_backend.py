"""MangaOCR backend — lazy import, requires ``uv add manga-ocr``."""
from __future__ import annotations

from PIL import Image

from yaku.core.errors import OptionalDependencyMissing
from yaku.ocr.base import BaseOCR, OCRResult


class MangaOCRBackend(BaseOCR):
    """Uses the ``manga-ocr`` model for Japanese manga / VN dialogue OCR.

    The model is loaded the first time :class:`MangaOCRBackend` is instantiated.
    If ``manga-ocr`` is not installed the constructor raises
    :class:`~yaku.core.errors.OptionalDependencyMissing` immediately.
    """

    def __init__(self) -> None:
        try:
            from manga_ocr import MangaOcr  # lazy import
        except ImportError as exc:
            raise OptionalDependencyMissing(
                "manga-ocr is not installed. Install with: uv add manga-ocr"
            ) from exc
        self._model = MangaOcr()

    def recognize(self, image: Image.Image) -> OCRResult:
        if image.mode != "RGB":
            image = image.convert("RGB")
        text: str = self._model(image)
        return OCRResult(text=text)
