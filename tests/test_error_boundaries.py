"""Tests for pipeline/controller error boundaries — failures stay non-fatal."""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from yaku.core.cache import YakuCache
from yaku.core.capture import BaseCapture
from yaku.core.config import YakuConfig
from yaku.core.errors import CaptureError, OCRError, TranslationError
from yaku.core.image_utils import Rect
from yaku.core.pipeline import V1Pipeline, V2Pipeline
from yaku.ocr.base import BaseOCR, OCRResult
from yaku.ocr.dummy import DummyOCR
from yaku.translate.base import BaseTranslator, TranslationResult


def _noise(seed: int) -> Image.Image:
    rng = np.random.default_rng(seed)
    return Image.fromarray(rng.integers(0, 256, (64, 64, 3), dtype=np.uint8))


class _OkTranslator(BaseTranslator):
    @property
    def backend_name(self) -> str:
        return "fake"

    def translate(self, text, context, target_lang, glossary=None) -> TranslationResult:
        return TranslationResult(
            source_text=text, translated_text="EN", target_lang=target_lang,
            backend="fake",
        )


class _BoomOCR(BaseOCR):
    def recognize(self, image) -> OCRResult:
        raise RuntimeError("ocr exploded")


class _BoomTranslator(BaseTranslator):
    @property
    def backend_name(self) -> str:
        return "boom"

    def translate(self, text, context, target_lang, glossary=None) -> TranslationResult:
        raise RuntimeError("translate exploded")


class _BoomCapture(BaseCapture):
    def capture_frame(self) -> Image.Image:
        raise RuntimeError("capture exploded")

    def capture_region(self, rect: Rect) -> Image.Image:
        raise RuntimeError("capture exploded")


@pytest.fixture
def cache(tmp_path):
    c = YakuCache(tmp_path / "c.sqlite3")
    yield c
    c.close()


# ---------------------------------------------------------------------------
# Pipeline raises typed errors and counts them
# ---------------------------------------------------------------------------

def test_capture_failure_raises_capture_error(cache):
    pipeline = V1Pipeline(DummyOCR("x"), _OkTranslator(), cache, YakuConfig(),
                          capture=_BoomCapture())
    with pytest.raises(CaptureError):
        pipeline.tick()  # no image → uses capture
    assert pipeline.metrics.errors_count == 1


def test_ocr_failure_raises_ocr_error(cache):
    pipeline = V1Pipeline(_BoomOCR(), _OkTranslator(), cache, YakuConfig())
    with pytest.raises(OCRError):
        pipeline.tick(_noise(1))
    assert pipeline.metrics.errors_count == 1


def test_translation_failure_raises_and_allows_retry(cache):
    pipeline = V1Pipeline(DummyOCR("日本語"), _BoomTranslator(), cache, YakuConfig())
    with pytest.raises(TranslationError):
        pipeline.tick(_noise(1))
    assert pipeline.metrics.errors_count == 1
    # After failure the dedup is cleared so the same text can be retried.
    pipeline.force_next()
    with pytest.raises(TranslationError):
        pipeline.tick(_noise(2))
    assert pipeline.metrics.errors_count == 2


def test_v2_ocr_failure_raises_ocr_error(cache):
    pipeline = V2Pipeline(_BoomOCR(), _OkTranslator(), cache, YakuConfig())
    with pytest.raises(OCRError):
        pipeline.tick(_noise(1))


# ---------------------------------------------------------------------------
# Worker never propagates — it reports on the error signal
# ---------------------------------------------------------------------------

def test_v1_worker_emits_error_signal_and_does_not_raise(cache):
    from yaku.v1_overlay.overlay_controller import _PipelineJob, _Signals

    pipeline = V1Pipeline(_BoomOCR(), _OkTranslator(), cache, YakuConfig(),
                          capture=None)
    # Feed a frame by monkeypatching tick to use an image is overkill; instead
    # use a pipeline whose OCR raises and a capture that yields a frame.
    pipeline._capture = _FrameCapture()

    signals = _Signals()
    errors: list[str] = []
    results: list = []
    signals.error.connect(errors.append)
    signals.result.connect(results.append)

    job = _PipelineJob(pipeline, signals)
    job.run()  # must not raise

    assert errors and "OCRError" in errors[0]
    assert results == []


class _FrameCapture(BaseCapture):
    def capture_frame(self) -> Image.Image:
        return _noise(5)

    def capture_region(self, rect: Rect) -> Image.Image:
        return _noise(5)


# ---------------------------------------------------------------------------
# Controller error handling keeps the previous translation + error badge
# ---------------------------------------------------------------------------

def test_controller_error_keeps_previous_translation(cache):
    from yaku.ui.app import get_app
    from yaku.v1_overlay.overlay_controller import OverlayController
    from yaku.v1_overlay.overlay_window import OverlayWindow

    get_app()
    config = YakuConfig()
    pipeline = V1Pipeline(DummyOCR("x"), _OkTranslator(), cache, config)
    window = OverlayWindow(config.v1_overlay)
    controller = OverlayController(config, window, pipeline)

    window.set_translation("PREVIOUS")
    controller._on_error("TranslationError: boom")

    assert window.translated_text() == "PREVIOUS"   # not cleared
    assert controller._errors == 1


def test_controller_empty_result_keeps_previous_translation(cache):
    from yaku.ui.app import get_app
    from yaku.v1_overlay.overlay_controller import OverlayController
    from yaku.v1_overlay.overlay_window import OverlayWindow

    get_app()
    config = YakuConfig()
    pipeline = V1Pipeline(DummyOCR("x"), _OkTranslator(), cache, config)
    window = OverlayWindow(config.v1_overlay)
    controller = OverlayController(config, window, pipeline)

    window.set_translation("PREVIOUS")
    controller._on_result(None)  # empty/unchanged OCR

    assert window.translated_text() == "PREVIOUS"
