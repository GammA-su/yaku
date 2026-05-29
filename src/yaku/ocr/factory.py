"""OCR backend factory."""
from __future__ import annotations

from yaku.core.config import OCRConfig
from yaku.core.errors import InvalidBackendError
from yaku.ocr.base import BaseOCR


def create_ocr(config: OCRConfig) -> BaseOCR:
    """Instantiate and return the OCR backend described by *config*.

    All optional-dependency backends (``manga_ocr``, ``paddleocr``) are
    imported lazily inside this function body — importing this module does
    **not** trigger those imports.

    Raises:
        :class:`~yaku.core.errors.OptionalDependencyMissing` when the
        requested backend's package is not installed.
        :class:`~yaku.core.errors.InvalidBackendError` for unknown names.
    """
    if config.backend == "dummy":
        from yaku.ocr.dummy import DummyOCR
        return DummyOCR()

    if config.backend == "manga_ocr":
        from yaku.ocr.manga_ocr_backend import MangaOCRBackend
        return MangaOCRBackend()

    if config.backend == "paddleocr":
        from yaku.ocr.paddleocr_backend import PaddleOCRBackend
        return PaddleOCRBackend()

    raise InvalidBackendError(
        f"Unknown OCR backend: '{config.backend}'. "
        "Valid choices: dummy, manga_ocr, paddleocr"
    )
