"""Tests for the OCR factory — laziness, routing, and error messages."""
from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from yaku.core.config import OCRConfig
from yaku.core.errors import InvalidBackendError, OptionalDependencyMissing
from yaku.ocr.dummy import DummyOCR
from yaku.ocr.factory import create_ocr


# ---------------------------------------------------------------------------
# Module-load laziness
# ---------------------------------------------------------------------------

def test_factory_module_importable():
    """Importing the factory must never raise — the test reaching here proves it."""
    from yaku.ocr import factory as _  # noqa: F401


# ---------------------------------------------------------------------------
# dummy backend
# ---------------------------------------------------------------------------

def test_factory_creates_dummy():
    config = OCRConfig(backend="dummy")
    ocr = create_ocr(config)
    assert isinstance(ocr, DummyOCR)


def test_factory_dummy_functional():
    from PIL import Image
    config = OCRConfig(backend="dummy")
    ocr = create_ocr(config)
    result = ocr.recognize(Image.new("RGB", (10, 10)))
    assert isinstance(result.text, str)


# ---------------------------------------------------------------------------
# Optional-dependency backends raise clear errors when not installed.
# We simulate absence by setting the entry in sys.modules to None, which
# causes `import manga_ocr` to raise ImportError regardless of whether the
# package is actually present on this machine.
# ---------------------------------------------------------------------------

def test_factory_manga_ocr_raises_optional_dep_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "manga_ocr", None)
    config = OCRConfig(backend="manga_ocr")
    with pytest.raises(OptionalDependencyMissing) as exc_info:
        create_ocr(config)
    msg = str(exc_info.value)
    assert "manga-ocr" in msg
    assert "uv add" in msg


def test_factory_manga_ocr_error_is_also_import_error(monkeypatch):
    """OptionalDependencyMissing is a subclass of ImportError for catch compatibility."""
    monkeypatch.setitem(sys.modules, "manga_ocr", None)
    config = OCRConfig(backend="manga_ocr")
    with pytest.raises(ImportError):
        create_ocr(config)


def test_factory_paddleocr_raises_optional_dep_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "paddleocr", None)
    config = OCRConfig(backend="paddleocr")
    with pytest.raises(OptionalDependencyMissing) as exc_info:
        create_ocr(config)
    msg = str(exc_info.value)
    assert "paddleocr" in msg
    assert "uv add" in msg


def test_factory_manga_ocr_error_message_has_install_command(monkeypatch):
    monkeypatch.setitem(sys.modules, "manga_ocr", None)
    config = OCRConfig(backend="manga_ocr")
    with pytest.raises(OptionalDependencyMissing) as exc_info:
        create_ocr(config)
    assert "uv add manga-ocr" in str(exc_info.value)


def test_factory_paddleocr_error_message_has_install_command(monkeypatch):
    monkeypatch.setitem(sys.modules, "paddleocr", None)
    config = OCRConfig(backend="paddleocr")
    with pytest.raises(OptionalDependencyMissing) as exc_info:
        create_ocr(config)
    assert "uv add paddleocr" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Unknown backend
# ---------------------------------------------------------------------------

def test_factory_unknown_backend_raises_invalid_backend_error():
    fake = SimpleNamespace(backend="nonexistent_backend")
    with pytest.raises(InvalidBackendError) as exc_info:
        create_ocr(fake)  # type: ignore[arg-type]
    assert "nonexistent_backend" in str(exc_info.value)


def test_factory_unknown_backend_message_lists_valid_options():
    fake = SimpleNamespace(backend="bad")
    with pytest.raises(InvalidBackendError) as exc_info:
        create_ocr(fake)  # type: ignore[arg-type]
    msg = str(exc_info.value)
    assert "dummy" in msg
    assert "manga_ocr" in msg
    assert "paddleocr" in msg
