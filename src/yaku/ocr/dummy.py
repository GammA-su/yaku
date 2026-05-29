"""Dummy OCR backend — returns a fixed string without any model."""
from __future__ import annotations

from PIL import Image

from yaku.ocr.base import BaseOCR, OCRResult


class DummyOCR(BaseOCR):
    """Returns a configurable fixed string regardless of the input image.

    Useful for unit tests, pipeline smoke-tests, and UI layout work where a
    real OCR model is not needed.
    """

    def __init__(self, text: str = "[dummy ocr output]") -> None:
        self._text = text

    def recognize(self, image: Image.Image) -> OCRResult:
        return OCRResult(text=self._text)
