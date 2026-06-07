"""Dummy OCR backend — returns a fixed string without any model."""
from __future__ import annotations

from PIL import Image

from yaku.ocr.base import BaseOCR, OCRResult, OCRBox


class DummyOCR(BaseOCR):
    """Returns a configurable fixed string regardless of the input image.

    Useful for unit tests, pipeline smoke-tests, and UI layout work where a
    real OCR model is not needed.
    """

    def __init__(self, text: str = "[dummy ocr output]") -> None:
        self._text = text

    def recognize(self, image: Image.Image) -> OCRResult:
        return OCRResult(text=self._text)

    def detect_text_boxes(self, image: Image.Image) -> list[OCRBox]:
        # Return a list containing a single dummy OCRBox
        return [OCRBox(text=self._text, box=(10, 10, 100, 30), confidence=1.0)]
