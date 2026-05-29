"""Tests for pipeline latency metrics."""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from yaku.core.cache import YakuCache
from yaku.core.config import YakuConfig
from yaku.core.metrics import MetricsTracker, PipelineMetrics
from yaku.core.pipeline import V1Pipeline
from yaku.ocr.dummy import DummyOCR
from yaku.translate.base import BaseTranslator, TranslationResult


def _noise(seed: int) -> Image.Image:
    rng = np.random.default_rng(seed)
    return Image.fromarray(rng.integers(0, 256, (64, 64, 3), dtype=np.uint8))


class _Translator(BaseTranslator):
    @property
    def backend_name(self) -> str:
        return "fake"

    def translate(self, text, context, target_lang, glossary=None) -> TranslationResult:
        return TranslationResult(
            source_text=text, translated_text="X" * 7, target_lang=target_lang,
            backend="fake",
        )


@pytest.fixture
def cache(tmp_path):
    c = YakuCache(tmp_path / "c.sqlite3")
    yield c
    c.close()


# ---------------------------------------------------------------------------
# PipelineMetrics dataclass
# ---------------------------------------------------------------------------

def test_pipeline_metrics_defaults_and_total():
    m = PipelineMetrics(capture_ms=1.0, hash_ms=2.0, ocr_ms=3.0, translate_ms=4.0,
                        render_ms=5.0)
    assert m.total_ms == 15.0
    assert m.cache_hit is False
    assert "capture_ms" in m.as_dict()


# ---------------------------------------------------------------------------
# MetricsTracker rolling averages
# ---------------------------------------------------------------------------

def test_tracker_empty_averages():
    t = MetricsTracker()
    a = t.averages()
    assert a["samples"] == 0
    assert a["total_ms"] == 0.0
    assert a["errors_count"] == 0


def test_tracker_averages_and_rate():
    t = MetricsTracker()
    t.record(PipelineMetrics(ocr_ms=10.0, translate_ms=20.0, cache_hit=True))
    t.record(PipelineMetrics(ocr_ms=20.0, translate_ms=40.0, cache_hit=False))
    a = t.averages()
    assert a["ocr_ms"] == 15.0
    assert a["translate_ms"] == 30.0
    assert a["cache_hit_rate"] == 0.5
    assert a["samples"] == 2


def test_tracker_rolling_window():
    t = MetricsTracker(window=3)
    for i in range(5):
        t.record(PipelineMetrics(ocr_ms=float(i)))
    a = t.averages()
    assert a["samples"] == 3            # only last 3 kept
    assert a["ocr_ms"] == (2 + 3 + 4) / 3
    assert t.ticks_count == 5           # cumulative count preserved


def test_tracker_error_count():
    t = MetricsTracker()
    t.record_error()
    t.record_error()
    assert t.errors_count == 2
    assert t.averages()["errors_count"] == 2


def test_tracker_format_summary():
    t = MetricsTracker()
    t.record(PipelineMetrics(ocr_ms=5.0))
    assert "ocr=" in t.format_summary()


# ---------------------------------------------------------------------------
# Pipeline populates metrics
# ---------------------------------------------------------------------------

def test_pipeline_attaches_metrics_to_result(cache):
    pipeline = V1Pipeline(DummyOCR("日本語"), _Translator(), cache, YakuConfig())
    result = pipeline.tick(_noise(1))
    assert result is not None
    assert isinstance(result.metrics, PipelineMetrics)
    assert result.metrics.backend == "fake"
    assert result.metrics.source_chars == 3
    assert result.metrics.translated_chars == 7
    assert result.metrics.ocr_ms >= 0.0


def test_pipeline_tracker_records_samples(cache):
    pipeline = V1Pipeline(DummyOCR("text"), _Translator(), cache, YakuConfig())
    pipeline.tick(_noise(1))
    pipeline.force_next()
    pipeline.tick(_noise(2))
    assert pipeline.metrics.sample_count == 2
    assert pipeline.metrics.averages()["samples"] == 2
