"""Duplicate OCR/context suppression behavior."""
from __future__ import annotations

import numpy as np
from PIL import Image

from yaku.core.cache import YakuCache
from yaku.core.config import YakuConfig
from yaku.core.pipeline import V1Pipeline
from yaku.ocr.base import BaseOCR, OCRResult
from yaku.translate.base import BaseTranslator, TranslationResult


def _noise(seed: int) -> Image.Image:
    rng = np.random.default_rng(seed)
    return Image.fromarray(rng.integers(0, 256, (48, 48, 3), dtype=np.uint8))


class _SeqOCR(BaseOCR):
    def __init__(self, texts: list[str]) -> None:
        self._texts = texts
        self._idx = 0

    def recognize(self, image: Image.Image) -> OCRResult:
        text = self._texts[min(self._idx, len(self._texts) - 1)]
        self._idx += 1
        return OCRResult(text=text)


class _Translator(BaseTranslator):
    def __init__(self) -> None:
        self.call_count = 0

    @property
    def backend_name(self) -> str:
        return "test"

    def translate(self, text: str, context: list[str], target_lang: str) -> TranslationResult:
        self.call_count += 1
        return TranslationResult(
            source_text=text,
            translated_text=f"T:{text}",
            target_lang=target_lang,
            backend="test",
        )


def test_duplicate_context_line_suppressed_after_forced_retranslate(tmp_path):
    config = YakuConfig()
    config.v1_overlay.duplicate_suppression_window = 3
    cache = YakuCache(tmp_path / "cache.sqlite3")
    translator = _Translator()
    pipeline = V1Pipeline(_SeqOCR(["same", "same"]), translator, cache, config)

    assert pipeline.tick(_noise(1)) is not None
    pipeline.force_next(bypass_cache=True)
    assert pipeline.tick(_noise(2)) is not None

    assert len(pipeline._context) == 1  # type: ignore[attr-defined]
    cache.close()


def test_empty_then_same_keeps_current_translation(tmp_path):
    config = YakuConfig()
    cache = YakuCache(tmp_path / "cache.sqlite3")
    translator = _Translator()
    pipeline = V1Pipeline(_SeqOCR(["same", "", "same"]), translator, cache, config)

    first = pipeline.tick(_noise(1))
    empty = pipeline.tick(_noise(2))
    repeated = pipeline.tick(_noise(3))

    assert first is not None
    assert empty is None
    assert repeated is None
    assert translator.call_count == 1
    cache.close()


def test_min_chars_filters_noisy_short_text(tmp_path):
    config = YakuConfig()
    config.ocr.min_chars = 2
    cache = YakuCache(tmp_path / "cache.sqlite3")
    translator = _Translator()
    pipeline = V1Pipeline(_SeqOCR(["x"]), translator, cache, config)

    result = pipeline.tick(_noise(1))

    assert result is None
    assert translator.call_count == 0
    cache.close()
