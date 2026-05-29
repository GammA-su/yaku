"""Benchmark the translation pipeline with fully fake components.

Runs the real :class:`V1Pipeline` against a fake capture, a dummy OCR, and a
fake translator so it needs no GPU, network, or screen.  It reports average
per-stage timings and verifies that unchanged frames do not trigger duplicate
translation calls.

    uv run python scripts/bench_fake_pipeline.py
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image

# Allow running directly from a source checkout without installation.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from yaku.core.cache import YakuCache  # noqa: E402
from yaku.core.capture import BaseCapture  # noqa: E402
from yaku.core.config import YakuConfig  # noqa: E402
from yaku.core.image_utils import Rect  # noqa: E402
from yaku.core.pipeline import V1Pipeline  # noqa: E402
from yaku.ocr.base import BaseOCR, OCRResult  # noqa: E402
from yaku.ocr.dummy import DummyOCR  # noqa: E402
from yaku.translate.base import BaseTranslator, TranslationResult  # noqa: E402

TICKS = 100


class ChangingCapture(BaseCapture):
    """Emits a fresh noise frame each call."""

    def __init__(self) -> None:
        self.n = 0

    def capture_frame(self) -> Image.Image:
        self.n += 1
        rng = np.random.default_rng(self.n)
        return Image.fromarray(rng.integers(0, 256, (180, 320, 3), dtype=np.uint8))

    def capture_region(self, rect: Rect) -> Image.Image:
        return self.capture_frame()


class ConstantCapture(BaseCapture):
    """Always emits the same frame (to exercise the no-duplicate guard)."""

    def __init__(self) -> None:
        rng = np.random.default_rng(1234)
        self._frame = Image.fromarray(
            rng.integers(0, 256, (180, 320, 3), dtype=np.uint8)
        )

    def capture_frame(self) -> Image.Image:
        return self._frame.copy()

    def capture_region(self, rect: Rect) -> Image.Image:
        return self._frame.copy()


class CountingOCR(BaseOCR):
    """Returns a different Japanese line on every call."""

    def __init__(self) -> None:
        self.i = 0

    def recognize(self, image: Image.Image) -> OCRResult:
        self.i += 1
        return OCRResult(text=f"これはテスト文の{self.i}番です")


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
            translated_text=f"[en] {text}",
            target_lang=target_lang,
            backend="fake",
        )


def _new_cache() -> YakuCache:
    return YakuCache(Path(tempfile.mkdtemp()) / "bench_cache.sqlite3")


def bench_changing() -> tuple[dict, int, float]:
    """Run TICKS with changing frames + changing text; return averages."""
    cache = _new_cache()
    translator = FakeTranslator()
    pipeline = V1Pipeline(
        CountingOCR(), translator, cache, YakuConfig(), capture=ChangingCapture()
    )
    started = time.perf_counter()
    for _ in range(TICKS):
        pipeline.tick()
    wall_ms = (time.perf_counter() - started) * 1000.0
    averages = pipeline.metrics.averages()
    cache.close()
    return averages, translator.calls, wall_ms


def bench_unchanged() -> int:
    """Run TICKS with an unchanged frame; return the translator call count."""
    cache = _new_cache()
    translator = FakeTranslator()
    pipeline = V1Pipeline(
        DummyOCR("変わらない文"), translator, cache, YakuConfig(),
        capture=ConstantCapture(),
    )
    for _ in range(TICKS):
        pipeline.tick()
    cache.close()
    return translator.calls


def main() -> int:
    print("Yaku fake-pipeline benchmark")
    print("=" * 60)

    averages, calls, wall_ms = bench_changing()
    print(f"Ran {TICKS} ticks (changing frames) in {wall_ms:.1f} ms "
          f"({wall_ms / TICKS:.2f} ms/tick wall)")
    print("Average stage timings (ms):")
    for stage in ("capture_ms", "hash_ms", "ocr_ms", "translate_ms", "total_ms"):
        print(f"  {stage:<14} {averages.get(stage, 0.0):7.3f}")
    print(f"  cache_hit_rate {averages.get('cache_hit_rate', 0.0) * 100:6.1f}%")
    print(f"  samples        {averages.get('samples', 0):7d}")
    print(f"  translator calls (changing): {calls}")

    print("-" * 60)
    dup_calls = bench_unchanged()
    ok = dup_calls == 1
    print(f"Unchanged-frame run: translator called {dup_calls} time(s) "
          f"over {TICKS} ticks")
    print(f"No-duplicate-translation check: {'PASS' if ok else 'FAIL'}")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
