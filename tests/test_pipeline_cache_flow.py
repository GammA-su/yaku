"""Tests for V1Pipeline logic — no Qt, no display required."""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from yaku.core.cache import YakuCache
from yaku.core.config import YakuConfig
from yaku.core.pipeline import V1Pipeline
from yaku.ocr.base import OCRResult
from yaku.ocr.dummy import DummyOCR
from yaku.translate.base import BaseTranslator, NullTranslator, TranslationResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _solid(value: int = 0, size: int = 64) -> Image.Image:
    return Image.fromarray(np.full((size, size, 3), value, dtype=np.uint8))


def _noise(seed: int = 0, size: int = 64) -> Image.Image:
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 256, (size, size, 3), dtype=np.uint8)
    return Image.fromarray(arr)


class _CountingTranslator(BaseTranslator):
    """Translator that counts calls and returns a configurable response."""

    def __init__(self, response: str = "Hello") -> None:
        self._response = response
        self.call_count = 0

    @property
    def backend_name(self) -> str:
        return "test"

    def translate(self, text: str, context: list[str], target_lang: str) -> TranslationResult:
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


def make_pipeline(ocr, translator, cache, config):
    return V1Pipeline(ocr=ocr, translator=translator, cache=cache, config=config)


# ---------------------------------------------------------------------------
# Hash gate: unchanged image must not trigger second translation
# ---------------------------------------------------------------------------

def test_unchanged_image_skips_second_tick(cache, config):
    translator = _CountingTranslator()
    pipeline = make_pipeline(DummyOCR("日本語"), translator, cache, config)

    img = _solid(128)
    r1 = pipeline.tick(img)
    r2 = pipeline.tick(img)  # same image → hash gate blocks

    assert r1 is not None
    assert r2 is None
    assert translator.call_count == 1


def test_unchanged_image_skips_many_times(cache, config):
    translator = _CountingTranslator()
    pipeline = make_pipeline(DummyOCR("text"), translator, cache, config)

    img = _noise(42)
    pipeline.tick(img)
    for _ in range(5):
        assert pipeline.tick(img) is None

    assert translator.call_count == 1


# ---------------------------------------------------------------------------
# Cache hit must avoid calling the translator backend
# ---------------------------------------------------------------------------

def test_cache_hit_avoids_translator_call(cache, config):
    translator = _CountingTranslator("SHOULD NOT SEE")
    pipeline = make_pipeline(DummyOCR("日本語テスト"), translator, cache, config)

    # Pre-populate cache
    cache.put_translation("日本語テスト", config.app.target_lang, "test", "Pre-cached")

    result = pipeline.tick(_noise(7))

    assert result is not None
    assert result.cached is True
    assert result.translated_text == "Pre-cached"
    assert translator.call_count == 0


def test_second_call_hits_cache(cache, config):
    translator = _CountingTranslator("First translation")
    pipeline = make_pipeline(DummyOCR("hello"), translator, cache, config)

    r1 = pipeline.tick(_noise(1))
    # Force next so hash gate doesn't block
    pipeline.force_next()
    r2 = pipeline.tick(_noise(2))

    assert r1 is not None and not r1.cached
    # r2: same OCR text "hello" but force_next reset _last_source, so it will
    # try to translate again — should get cache hit this time
    assert r2 is not None
    assert r2.cached is True
    assert translator.call_count == 1  # only the first call went to backend


# ---------------------------------------------------------------------------
# Different images must produce new translations
# ---------------------------------------------------------------------------

def test_different_images_trigger_new_results(cache, config):
    texts = ["first text", "second text"]
    call_n = [0]

    class SeqOCR(DummyOCR):
        def recognize(self, image: Image.Image) -> OCRResult:
            return OCRResult(text=texts[min(call_n[0], 1)])

    class SeqTranslator(_CountingTranslator):
        def translate(self, text, context, target_lang):
            self.call_count += 1
            return TranslationResult(
                source_text=text, translated_text=f"T:{text}",
                target_lang=target_lang, backend="test",
            )

    translator = SeqTranslator()
    pipeline = make_pipeline(SeqOCR(), translator, cache, config)

    r1 = pipeline.tick(_noise(0))   # "first text"
    call_n[0] = 1                   # switch OCR output
    r2 = pipeline.tick(_noise(99))  # "second text" — different phash

    assert r1 is not None
    assert r2 is not None
    assert translator.call_count == 2


# ---------------------------------------------------------------------------
# Same OCR text with different image must be deduplicated
# ---------------------------------------------------------------------------

def test_same_ocr_text_skips_retranslation(cache, config):
    translator = _CountingTranslator()
    pipeline = make_pipeline(DummyOCR("persistent text"), translator, cache, config)

    r1 = pipeline.tick(_noise(0))
    # Different image (different hash) but OCR still returns same text
    r2 = pipeline.tick(_noise(99))

    assert r1 is not None
    assert r2 is None  # text dedup blocks second call
    assert translator.call_count == 1


# ---------------------------------------------------------------------------
# force_next bypasses both hash gate and text dedup
# ---------------------------------------------------------------------------

def test_force_next_bypasses_hash_gate(cache, config):
    translator = _CountingTranslator()
    pipeline = make_pipeline(DummyOCR("text"), translator, cache, config)

    img = _noise(5)
    r1 = pipeline.tick(img)
    pipeline.force_next()
    r2 = pipeline.tick(img)  # same image, but force → cache hit

    assert r1 is not None
    assert r2 is not None  # force bypassed hash gate
    assert r2.cached is True   # but translator itself was cached from r1
    assert translator.call_count == 1


def test_force_next_resets_text_dedup(cache, config):
    translator = _CountingTranslator()
    pipeline = make_pipeline(DummyOCR("same text"), translator, cache, config)

    r1 = pipeline.tick(_noise(1))
    pipeline.force_next()
    r2 = pipeline.tick(_noise(99))  # same OCR text, but force reset _last_source

    assert r1 is not None
    assert r2 is not None  # text dedup was bypassed
    assert r2.cached is True


# ---------------------------------------------------------------------------
# Empty OCR result must not produce a translation
# ---------------------------------------------------------------------------

def test_empty_ocr_text_returns_none(cache, config):
    translator = _CountingTranslator()
    pipeline = make_pipeline(DummyOCR(""), translator, cache, config)

    result = pipeline.tick(_noise(3))

    assert result is None
    assert translator.call_count == 0


# ---------------------------------------------------------------------------
# No capture backend and no image → None
# ---------------------------------------------------------------------------

def test_no_capture_no_image_returns_none(cache, config):
    pipeline = V1Pipeline(
        ocr=DummyOCR("text"),
        translator=NullTranslator(),
        cache=cache,
        config=config,
        capture=None,
    )
    assert pipeline.tick() is None


# ---------------------------------------------------------------------------
# First result is not cached; result fields are correct
# ---------------------------------------------------------------------------

def test_first_result_not_cached(cache, config):
    pipeline = make_pipeline(DummyOCR("テキスト"), _CountingTranslator("Hello"), cache, config)
    result = pipeline.tick(_noise(10))
    assert result is not None
    assert result.cached is False
    assert result.source_text == "テキスト"
    assert result.translated_text == "Hello"
    assert result.target_lang == config.app.target_lang
