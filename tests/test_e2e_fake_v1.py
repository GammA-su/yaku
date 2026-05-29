"""End-to-end v1-overlay test with fake components (headless)."""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from yaku.core.cache import YakuCache
from yaku.core.capture import BaseCapture
from yaku.core.config import YakuConfig
from yaku.core.image_utils import Rect
from yaku.core.pipeline import V1Pipeline
from yaku.ocr.dummy import DummyOCR
from yaku.translate.base import BaseTranslator, TranslationResult

JP_LINE = "これはテストの文です"
EN_LINE = "This is a test sentence."


class FakeCapture(BaseCapture):
    """Emits a different noise frame on every call."""

    def __init__(self) -> None:
        self.n = 0

    def capture_frame(self) -> Image.Image:
        self.n += 1
        rng = np.random.default_rng(self.n)
        return Image.fromarray(rng.integers(0, 256, (180, 320, 3), dtype=np.uint8))

    def capture_region(self, rect: Rect) -> Image.Image:
        return self.capture_frame().crop(
            (rect.x, rect.y, rect.x + rect.w, rect.y + rect.h)
        )


class FakeTranslator(BaseTranslator):
    def __init__(self) -> None:
        self.calls = 0

    @property
    def backend_name(self) -> str:
        return "fake"

    def translate(self, text, context, target_lang, glossary=None) -> TranslationResult:
        self.calls += 1
        return TranslationResult(
            source_text=text,
            translated_text=EN_LINE,
            target_lang=target_lang,
            backend="fake",
        )


@pytest.fixture
def cache(tmp_path):
    c = YakuCache(tmp_path / "cache.sqlite3")
    yield c
    c.close()


# ---------------------------------------------------------------------------
# Pipeline e2e (no GUI)
# ---------------------------------------------------------------------------

def test_v1_pipeline_capture_ocr_translate(cache):
    config = YakuConfig()
    pipeline = V1Pipeline(
        DummyOCR(JP_LINE), FakeTranslator(), cache, config, capture=FakeCapture()
    )
    result = pipeline.tick()  # captures via FakeCapture
    assert result is not None
    assert result.source_text == JP_LINE
    assert result.translated_text == EN_LINE


def test_v1_pipeline_second_translation_is_cached(cache):
    config = YakuConfig()
    translator = FakeTranslator()
    pipeline = V1Pipeline(
        DummyOCR(JP_LINE), translator, cache, config, capture=FakeCapture()
    )
    r1 = pipeline.tick()
    pipeline.force_next()  # bypass hash/text dedup
    r2 = pipeline.tick()
    assert r1 is not None and not r1.cached
    assert r2 is not None and r2.cached      # came from cache
    assert translator.calls == 1             # backend hit only once


# ---------------------------------------------------------------------------
# Controller updates the overlay model (offscreen, no event loop needed)
# ---------------------------------------------------------------------------

def test_v1_controller_updates_overlay_model(cache):
    from yaku.ui.app import get_app
    from yaku.v1_overlay.overlay_controller import OverlayController
    from yaku.v1_overlay.overlay_window import OverlayWindow

    get_app()
    config = YakuConfig()
    pipeline = V1Pipeline(
        DummyOCR(JP_LINE), FakeTranslator(), cache, config, capture=FakeCapture()
    )
    window = OverlayWindow(config.v1_overlay)
    controller = OverlayController(config, window, pipeline)

    result = pipeline.tick()
    controller._on_result(result)  # simulate the worker delivering a result

    assert window.translated_text() == EN_LINE
    assert window.source_text() == JP_LINE
