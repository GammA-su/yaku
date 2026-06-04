"""Latency metrics for the translation pipeline.

A :class:`PipelineMetrics` holds the per-tick stage timings and counters; a
:class:`MetricsTracker` keeps a rolling window of them and exposes averages for
the debug panel and the benchmark script.
"""
from __future__ import annotations

import json
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field, fields, asdict
from datetime import datetime, timezone
from pathlib import Path
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


# ---------------------------------------------------------------------------
# Telemetry event components
# ---------------------------------------------------------------------------

class StageTimer:
    """Context manager for measuring execution time in milliseconds."""

    def __init__(self) -> None:
        self.elapsed_ms: Optional[float] = None
        self._start: Optional[float] = None

    def __enter__(self) -> StageTimer:
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._start is not None:
            self.elapsed_ms = (time.perf_counter() - self._start) * 1000.0


@dataclass
class LatencyEvent:
    """Telemetry payload for a single pipeline step/OCR/translation attempt."""

    ts: str
    mode: str
    ocr_backend: str | None
    translator: str | None
    model: str | None
    base_url: str | None
    render_mode: str | None
    capture_ms: float | None
    hash_ms: float | None
    ocr_ms: float | None
    translate_ms: float | None
    render_ms: float | None
    total_ms: float | None
    cache_hit: bool
    source_chars: int
    translated_chars: int
    source_preview: str | None
    translation_preview: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    tokens_per_second: float | None
    error: str | None


class MetricsLogger:
    """Thread-safe JSONL logger for latency events."""

    def __init__(self, path: str | Path, enabled: bool = True) -> None:
        self.path = Path(path)
        self.enabled = enabled
        self._lock = threading.Lock()

    def log_event(self, event: LatencyEvent) -> None:
        if not self.enabled:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            event_dict = asdict(event)

            # Sanitize potential inline credentials in base_url
            if event_dict.get("base_url"):
                event_dict["base_url"] = re.sub(r"(key|token|auth)=[^&]+", r"\1=[REDACTED]", event_dict["base_url"])

            line = json.dumps(event_dict, ensure_ascii=False) + "\n"
            with self._lock:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(line)
        except Exception as exc:
            import sys
            print(f"Warning: failed to write to metrics log: {exc}", file=sys.stderr)
