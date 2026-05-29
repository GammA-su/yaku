"""Tests for v2-mirror region mapping and V2Pipeline cache behavior."""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from yaku.core.cache import YakuCache
from yaku.core.config import YakuConfig
from yaku.core.image_utils import NormalizedRect
from yaku.core.pipeline import V2Pipeline
from yaku.ocr.dummy import DummyOCR
from yaku.translate.base import BaseTranslator, TranslationResult
from yaku.v2_mirror.coordinate_map import normalized_rect_to_frame_rect


# ---------------------------------------------------------------------------
# Region mapping
# ---------------------------------------------------------------------------

def test_replacement_region_maps_to_frame():
    cfg = YakuConfig()
    rr = cfg.v2_mirror.replacement_region
    norm = NormalizedRect(rr.x_ratio, rr.y_ratio, rr.w_ratio, rr.h_ratio)
    rect = normalized_rect_to_frame_rect(norm, 1920, 1080)
    # Default region (0.08, 0.72, 0.84, 0.20) sits in the lower-middle band.
    assert rect.x == round(0.08 * 1920)
    assert rect.y == round(0.72 * 1080)
    assert rect.w == round(0.84 * 1920)
    assert rect.h == round(0.20 * 1080)
    # Lies fully within the frame.
    assert rect.x + rect.w <= 1920
    assert rect.y + rect.h <= 1080


# ---------------------------------------------------------------------------
# Helpers for pipeline tests
# ---------------------------------------------------------------------------

def _noise(seed: int = 0, size: int = 64) -> Image.Image:
    rng = np.random.default_rng(seed)
    return Image.fromarray(rng.integers(0, 256, (size, size, 3), dtype=np.uint8))


class _CountingTranslator(BaseTranslator):
    def __init__(self, response: str = "Hello") -> None:
        self._response = response
        self.call_count = 0

    @property
    def backend_name(self) -> str:
        return "test"

    def translate(self, text, context, target_lang, glossary=None) -> TranslationResult:
        self.call_count += 1
        return TranslationResult(
            source_text=text,
            translated_text=self._response,
            target_lang=target_lang,
            backend="test",
        )


@pytest.fixture
def cache(tmp_path):
    c = YakuCache(tmp_path / "cache.sqlite3")
    yield c
    c.close()


@pytest.fixture
def config():
    return YakuConfig()


def _pipeline(ocr, translator, cache, config):
    return V2Pipeline(ocr=ocr, translator=translator, cache=cache, config=config)


# ---------------------------------------------------------------------------
# V2Pipeline cache / gating behavior
# ---------------------------------------------------------------------------

def test_none_frame_returns_none(cache, config):
    pipe = _pipeline(DummyOCR("text"), _CountingTranslator(), cache, config)
    assert pipe.tick(None) is None


def test_first_frame_translates(cache, config):
    translator = _CountingTranslator("Hello")
    pipe = _pipeline(DummyOCR("日本語"), translator, cache, config)
    result = pipe.tick(_noise(1))
    assert result is not None
    assert result.cached is False
    assert result.translated_text == "Hello"
    assert translator.call_count == 1


def test_unchanged_frame_skips_second_tick(cache, config):
    translator = _CountingTranslator()
    pipe = _pipeline(DummyOCR("日本語"), translator, cache, config)
    img = _noise(2)
    r1 = pipe.tick(img)
    r2 = pipe.tick(img)  # same frame → hash gate blocks
    assert r1 is not None
    assert r2 is None
    assert translator.call_count == 1


def test_cache_hit_avoids_translator(cache, config):
    translator = _CountingTranslator("SHOULD NOT SEE")
    pipe = _pipeline(DummyOCR("テスト"), translator, cache, config)
    cache.put_translation("テスト", config.app.target_lang, "test", "Pre-cached")
    result = pipe.tick(_noise(3))
    assert result is not None
    assert result.cached is True
    assert result.translated_text == "Pre-cached"
    assert translator.call_count == 0


def test_empty_ocr_returns_none(cache, config):
    translator = _CountingTranslator()
    pipe = _pipeline(DummyOCR(""), translator, cache, config)
    assert pipe.tick(_noise(4)) is None
    assert translator.call_count == 0


def test_same_text_dedup(cache, config):
    translator = _CountingTranslator()
    pipe = _pipeline(DummyOCR("persistent"), translator, cache, config)
    r1 = pipe.tick(_noise(5))
    r2 = pipe.tick(_noise(99))  # different frame, same OCR text
    assert r1 is not None
    assert r2 is None
    assert translator.call_count == 1


def test_force_next_bypasses_gate(cache, config):
    translator = _CountingTranslator()
    pipe = _pipeline(DummyOCR("text"), translator, cache, config)
    img = _noise(6)
    r1 = pipe.tick(img)
    pipe.force_next()
    r2 = pipe.tick(img)  # same frame but forced → cache hit
    assert r1 is not None
    assert r2 is not None
    assert r2.cached is True
    assert translator.call_count == 1


def test_ocr_region_crop_used(cache, config):
    # Set an OCR region; pipeline should crop without error and still translate.
    config.ocr.region.x = 10
    config.ocr.region.y = 10
    config.ocr.region.w = 30
    config.ocr.region.h = 30
    translator = _CountingTranslator("X")
    pipe = _pipeline(DummyOCR("内"), translator, cache, config)
    result = pipe.tick(_noise(7))
    assert result is not None
    assert result.translated_text == "X"
