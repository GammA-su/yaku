"""Tests for DummyOCR — the test-only OCR backend."""
from __future__ import annotations

import pytest
from PIL import Image

from yaku.ocr.base import OCRResult
from yaku.ocr.dummy import DummyOCR


def _img(mode: str = "RGB", size: tuple[int, int] = (100, 100)) -> Image.Image:
    return Image.new(mode, size)


# ---------------------------------------------------------------------------
# Default text
# ---------------------------------------------------------------------------

def test_default_text_is_placeholder():
    ocr = DummyOCR()
    result = ocr.recognize(_img())
    assert isinstance(result, OCRResult)
    assert result.text  # non-empty
    assert "[dummy" in result.text


# ---------------------------------------------------------------------------
# Configurable text
# ---------------------------------------------------------------------------

def test_configured_text_returned_exactly():
    ocr = DummyOCR("こんにちは世界")
    result = ocr.recognize(_img())
    assert result.text == "こんにちは世界"


def test_empty_string_configurable():
    ocr = DummyOCR("")
    assert ocr.recognize(_img()).text == ""


def test_multiline_text_preserved():
    text = "line one\nline two\nline three"
    ocr = DummyOCR(text)
    assert ocr.recognize(_img()).text == text


# ---------------------------------------------------------------------------
# Image-independent behaviour
# ---------------------------------------------------------------------------

def test_ignores_image_content():
    ocr = DummyOCR("fixed")
    black = Image.new("RGB", (100, 100), color=0)
    white = Image.new("RGB", (100, 100), color=255)
    assert ocr.recognize(black).text == ocr.recognize(white).text


def test_works_with_rgb_image():
    ocr = DummyOCR("rgb")
    assert ocr.recognize(_img("RGB")).text == "rgb"


def test_works_with_rgba_image():
    ocr = DummyOCR("rgba")
    assert ocr.recognize(_img("RGBA")).text == "rgba"


def test_works_with_grayscale_image():
    ocr = DummyOCR("gray")
    assert ocr.recognize(_img("L")).text == "gray"


def test_works_with_small_image():
    ocr = DummyOCR("tiny")
    assert ocr.recognize(_img(size=(1, 1))).text == "tiny"


# ---------------------------------------------------------------------------
# OCRResult fields
# ---------------------------------------------------------------------------

def test_confidence_is_none():
    result = DummyOCR().recognize(_img())
    assert result.confidence is None


def test_raw_is_none():
    result = DummyOCR().recognize(_img())
    assert result.raw is None


# ---------------------------------------------------------------------------
# Reusability
# ---------------------------------------------------------------------------

def test_recognize_called_multiple_times():
    ocr = DummyOCR("stable")
    for _ in range(5):
        assert ocr.recognize(_img()).text == "stable"
