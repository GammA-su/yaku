"""Latency metrics for the translation pipeline.

A :class:`PipelineMetrics` holds the per-tick stage timings and counters; a
:class:`MetricsTracker` keeps a rolling window of them and exposes averages for
the debug panel and the benchmark script.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, fields
from typing import Deque, Optional

_MS_FIELDS = ("capture_ms", "hash_ms", "ocr_ms", "translate_ms", "render_ms")


@dataclass
class PipelineMetrics:
    """Timings (milliseconds) and counters for a single pipeline tick."""

    capture_ms: float = 0.0
    hash_ms: float = 0.0
    ocr_ms: float = 0.0
    translate_ms: float = 0.0
    render_ms: float = 0.0
    cache_hit: bool = False
    backend: str = ""
    source_chars: int = 0
    translated_chars: int = 0
    errors_count: int = 0

    @property
    def total_ms(self) -> float:
        return sum(getattr(self, name) for name in _MS_FIELDS)

    def as_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}


class MetricsTracker:
    """Rolling-window aggregator over :class:`PipelineMetrics` samples.

    Thread-safety: ``record``/``record_error`` may be called from a worker
    thread while the UI thread reads ``averages``/``last``.  Operations are
    cheap and the GIL makes the individual deque/int updates atomic enough for
    diagnostics; no lock is taken to keep the hot path free.
    """

    def __init__(self, window: int = 50) -> None:
        self._samples: Deque[PipelineMetrics] = deque(maxlen=window)
        self._errors_total = 0
        self._ticks_total = 0

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(self, metrics: PipelineMetrics) -> None:
        self._samples.append(metrics)
        self._ticks_total += 1
        self._errors_total += metrics.errors_count

    def record_error(self) -> None:
        self._errors_total += 1

    def reset(self) -> None:
        self._samples.clear()
        self._errors_total = 0
        self._ticks_total = 0

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    @property
    def errors_count(self) -> int:
        return self._errors_total

    @property
    def ticks_count(self) -> int:
        return self._ticks_total

    @property
    def sample_count(self) -> int:
        return len(self._samples)

    def last(self) -> Optional[PipelineMetrics]:
        return self._samples[-1] if self._samples else None

    def averages(self) -> dict:
        """Return rolling averages of the timing fields plus derived rates."""
        n = len(self._samples)
        if n == 0:
            avg = {name: 0.0 for name in _MS_FIELDS}
            avg.update(cache_hit_rate=0.0, total_ms=0.0, samples=0,
                       errors_count=self._errors_total)
            return avg

        avg = {
            name: sum(getattr(s, name) for s in self._samples) / n
            for name in _MS_FIELDS
        }
        avg["total_ms"] = sum(avg[name] for name in _MS_FIELDS)
        avg["cache_hit_rate"] = sum(1 for s in self._samples if s.cache_hit) / n
        avg["samples"] = n
        avg["errors_count"] = self._errors_total
        return avg

    def format_summary(self) -> str:
        a = self.averages()
        return (
            f"capture={a['capture_ms']:.1f}ms hash={a['hash_ms']:.1f}ms "
            f"ocr={a['ocr_ms']:.1f}ms translate={a['translate_ms']:.1f}ms "
            f"render={a['render_ms']:.1f}ms total={a['total_ms']:.1f}ms "
            f"cache_hit={a['cache_hit_rate'] * 100:.0f}% "
            f"errors={a['errors_count']} n={a['samples']}"
        )
