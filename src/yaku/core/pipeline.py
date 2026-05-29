"""Translation pipeline: shared helper and V1 pipeline logic."""
from __future__ import annotations

import inspect
import time
import unicodedata
from pathlib import Path
from typing import Any, TYPE_CHECKING, Optional, Sequence

from PIL import Image

from yaku.core.cache import YakuCache
from yaku.core.config import YakuConfig
from yaku.core.context_memory import ContextMemory
from yaku.core.errors import CaptureError, OCRError, TranslationError
from yaku.core.hash_gate import HashGate
from yaku.core.image_utils import Rect, clamp_rect, crop_pil
from yaku.core.logging import get_logger
from yaku.core.metrics import MetricsTracker, PipelineMetrics
from yaku.core.text_cleanup import cleanup_ocr_text
from yaku.ocr.base import BaseOCR
from yaku.translate.base import BaseTranslator, TranslationResult

_log = get_logger("pipeline")

if TYPE_CHECKING:
    from yaku.core.capture import BaseCapture


def _is_meaningful_ocr_text(text: str) -> bool:
    """Return false for punctuation-only OCR artifacts such as ``...``."""
    return any(
        unicodedata.category(char)[0] in {"L", "N"}
        for char in text
    )


def _record_ocr_debug_image(image: Image.Image, raw_text: str, clean_text: str) -> None:
    """Write the latest OCR crop and text to ``out/`` for debugging."""
    if not _log.isEnabledFor(10):
        return
    try:
        out = Path("out")
        out.mkdir(parents=True, exist_ok=True)
        image.save(out / "ocr_latest.png")
        (out / "ocr_latest.txt").write_text(
            f"raw={raw_text!r}\nclean={clean_text!r}\n",
            encoding="utf-8",
        )
    except Exception as exc:  # noqa: BLE001
        _log.debug("failed to write OCR debug snapshot: %s", exc)


# ---------------------------------------------------------------------------
# Shared cache helper (used by both V1 and V2)
# ---------------------------------------------------------------------------

def translate_with_cache(
    cache: YakuCache,
    translator: BaseTranslator,
    source_text: str,
    context: list[str],
    target_lang: str,
    *,
    bypass_cache: bool = False,
    glossary: Sequence[Any] | None = None,
) -> TranslationResult:
    """Translate *source_text*, consulting the cache before calling the backend.

    On a cache hit the backend is **not** called and the returned result has
    ``cached=True``.  On a miss the backend is called and the result is stored.
    """
    started = time.perf_counter()
    cached_text = None
    if not bypass_cache:
        cached_text = cache.get_translation(
            source_text,
            target_lang,
            translator.backend_name,
            translator.backend_model,
        )
    if cached_text is not None:
        return TranslationResult(
            source_text=source_text,
            translated_text=cached_text,
            target_lang=target_lang,
            backend=translator.backend_name,
            backend_model=translator.backend_model,
            cached=True,
            translation_ms=(time.perf_counter() - started) * 1000.0,
        )

    translate_kwargs: dict[str, Any] = {}
    if glossary and "glossary" in inspect.signature(translator.translate).parameters:
        translate_kwargs["glossary"] = glossary
    result = translator.translate(source_text, context, target_lang, **translate_kwargs)
    result.translation_ms = (time.perf_counter() - started) * 1000.0
    if bypass_cache:
        cache.overwrite_translation(
            source_text,
            target_lang,
            result.backend,
            result.translated_text,
            result.backend_model,
        )
    else:
        cache.put_translation(
            source_text,
            target_lang,
            result.backend,
            result.translated_text,
            result.backend_model,
        )
    return result


# ---------------------------------------------------------------------------
# V1 pipeline — pure Python, no Qt
# ---------------------------------------------------------------------------

class V1Pipeline:
    """Per-tick pipeline: capture → hash-gate → OCR → cleanup → translate.

    Designed to run in a background thread; holds no Qt objects.

    Thread-safety contract: only one concurrent call to :meth:`tick` is
    supported.  The caller (``OverlayController``) ensures this via a
    ``_busy`` flag that prevents overlapping submissions.
    """

    def __init__(
        self,
        ocr: BaseOCR,
        translator: BaseTranslator,
        cache: YakuCache,
        config: YakuConfig,
        capture: "Optional[BaseCapture]" = None,
    ) -> None:
        self._ocr = ocr
        self._translator = translator
        self._cache = cache
        self._config = config
        self._capture = capture
        self._hash_gate = HashGate(threshold=config.ocr.hash_threshold)
        self._context = ContextMemory(max_lines=config.translator.context_lines)
        self._last_source: str = ""
        self._force: bool = False
        self._bypass_cache_next: bool = False
        self._metrics = MetricsTracker()

    # ------------------------------------------------------------------
    # Public control
    # ------------------------------------------------------------------

    @property
    def metrics(self) -> MetricsTracker:
        return self._metrics

    def force_next(self, *, bypass_cache: bool = False) -> None:
        """Force next tick to bypass the hash gate/text dedup, optionally cache."""
        self._force = True
        self._bypass_cache_next = bypass_cache
        self._hash_gate.reset()
        self._last_source = ""

    def update_capture(self, capture: "Optional[BaseCapture]") -> None:
        self._capture = capture

    def update_ocr(self, ocr: BaseOCR) -> None:
        old = self._ocr
        self._ocr = ocr
        if old is not ocr:
            old.close()
        self.force_next()

    def update_translator(self, translator: BaseTranslator) -> None:
        old = self._translator
        self._translator = translator
        if old is not translator:
            old.close()

    def overwrite_cached_translation(self, result: TranslationResult) -> None:
        """Persist a manually edited translation for the result's cache key."""
        self._cache.overwrite_translation(
            result.source_text,
            result.target_lang,
            result.backend,
            result.translated_text,
            result.backend_model,
        )

    # ------------------------------------------------------------------
    # Core tick
    # ------------------------------------------------------------------

    def tick(self, image: Optional[Image.Image] = None) -> Optional[TranslationResult]:
        """Run one pipeline cycle.

        Args:
            image: Pre-captured frame to process.  When ``None`` the capture
                   backend is used.  Supply a frame directly in tests to avoid
                   needing a real screen-capture backend.

        Returns:
            A :class:`~yaku.translate.base.TranslationResult` when the source
            text changed and a translation was produced, or ``None`` when the
            frame was identical to the last one or the OCR produced the same
            text.
        """
        force = self._force
        bypass_cache = self._bypass_cache_next
        self._force = False
        self._bypass_cache_next = False
        metrics = PipelineMetrics()

        # ── 1. capture ────────────────────────────────────────────────
        if image is None:
            if self._capture is None:
                return None
            region = Rect(
                x=self._config.ocr.region.x,
                y=self._config.ocr.region.y,
                w=self._config.ocr.region.w,
                h=self._config.ocr.region.h,
            )
            started = time.perf_counter()
            try:
                if region.w > 0 and region.h > 0:
                    image = self._capture.capture_region(region)
                else:
                    image = self._capture.capture_frame()
            except Exception as exc:  # noqa: BLE001 — report as a typed error
                self._metrics.record_error()
                raise CaptureError(f"capture failed: {exc}") from exc
            metrics.capture_ms = (time.perf_counter() - started) * 1000.0

        # ── 2. hash gate ───────────────────────────────────────────────
        started = time.perf_counter()
        proceed = self._hash_gate.should_process(image, force=force)
        metrics.hash_ms = (time.perf_counter() - started) * 1000.0
        if not proceed:
            return None

        # ── 3. OCR ────────────────────────────────────────────────────
        started = time.perf_counter()
        try:
            ocr_result = self._ocr.recognize(image)
        except Exception as exc:  # noqa: BLE001
            self._metrics.record_error()
            raise OCRError(f"OCR failed: {exc}") from exc
        metrics.ocr_ms = (time.perf_counter() - started) * 1000.0
        source = cleanup_ocr_text(ocr_result.text)
        _record_ocr_debug_image(image, ocr_result.text, source)
        _log.debug("ocr raw=%r clean=%r crop=%sx%s", ocr_result.text, source, image.width, image.height)

        if not source:
            return None
        if not _is_meaningful_ocr_text(source):
            _log.debug("ignoring punctuation-only OCR text: %r", source)
            return None
        if len(source.strip()) < self._config.ocr.min_chars:
            return None

        # ── 4. text dedup ──────────────────────────────────────────────
        if source == self._last_source:
            return None
        self._last_source = source

        # ── 5. translate (with cache) ─────────────────────────────────
        context = self._context.previous_translation_lines(
            self._config.translator.context_lines
        )
        try:
            result = translate_with_cache(
                self._cache,
                self._translator,
                source,
                context,
                self._config.app.target_lang,
                bypass_cache=bypass_cache,
                glossary=(
                    self._config.glossary.entries
                    if self._config.glossary.enabled
                    else None
                ),
            )
        except Exception as exc:  # noqa: BLE001
            self._metrics.record_error()
            # Allow retranslation on the next tick rather than sticking dedup'd.
            self._last_source = ""
            raise TranslationError(f"translation failed: {exc}") from exc

        result.raw_source_text = ocr_result.text
        result.ocr_ms = metrics.ocr_ms
        metrics.translate_ms = result.translation_ms or 0.0
        metrics.cache_hit = result.cached
        metrics.backend = result.backend
        metrics.source_chars = len(source)
        metrics.translated_chars = len(result.translated_text)
        result.metrics = metrics
        self._metrics.record(metrics)
        self._context.add(
            source,
            result.translated_text,
            suppress_window=self._config.v1_overlay.duplicate_suppression_window,
        )
        _log.info(
            "tick ocr_ms=%.1f translation_ms=%.1f backend=%s cache_hit=%s source_len=%d",
            result.ocr_ms or 0.0,
            result.translation_ms or 0.0,
            result.backend,
            result.cached,
            len(source),
        )
        return result


# ---------------------------------------------------------------------------
# V2 pipeline — full-frame in, crops the OCR region itself
# ---------------------------------------------------------------------------

class V2Pipeline:
    """Per-tick pipeline for v2-mirror mode.

    Unlike :class:`V1Pipeline`, :meth:`tick` is always handed a *full* captured
    frame; the pipeline crops the configured OCR region from it before
    hash-gating and OCR.  This lets the mirror display the whole live frame
    while OCR only looks at the dialogue box.

    Holds no Qt objects so it can run in a background thread.  Only one
    concurrent call to :meth:`tick` is supported (the controller serialises
    submissions with a ``_busy`` flag).
    """

    def __init__(
        self,
        ocr: BaseOCR,
        translator: BaseTranslator,
        cache: YakuCache,
        config: YakuConfig,
    ) -> None:
        self._ocr = ocr
        self._translator = translator
        self._cache = cache
        self._config = config
        self._hash_gate = HashGate(threshold=config.ocr.hash_threshold)
        self._context = ContextMemory(max_lines=config.translator.context_lines)
        self._last_source: str = ""
        self._force: bool = False
        self._bypass_cache_next: bool = False
        self._metrics = MetricsTracker()

    # ------------------------------------------------------------------
    # Public control
    # ------------------------------------------------------------------

    @property
    def metrics(self) -> MetricsTracker:
        return self._metrics

    def force_next(self, *, bypass_cache: bool = False) -> None:
        """Force the next tick to bypass the hash gate and text dedup."""
        self._force = True
        self._bypass_cache_next = bypass_cache
        self._hash_gate.reset()
        self._last_source = ""

    def update_translator(self, translator: BaseTranslator) -> None:
        old = self._translator
        self._translator = translator
        if old is not translator:
            old.close()

    def update_ocr(self, ocr: BaseOCR) -> None:
        old = self._ocr
        self._ocr = ocr
        if old is not ocr:
            old.close()
        self.force_next()

    # ------------------------------------------------------------------
    # Core tick
    # ------------------------------------------------------------------

    def _ocr_crop(self, frame: Image.Image) -> Image.Image:
        region = Rect(
            x=self._config.ocr.region.x,
            y=self._config.ocr.region.y,
            w=self._config.ocr.region.w,
            h=self._config.ocr.region.h,
        )
        if region.w <= 0 or region.h <= 0:
            return frame
        clamped = clamp_rect(region, frame.width, frame.height)
        if clamped.w <= 0 or clamped.h <= 0:
            return frame
        return crop_pil(frame, clamped)

    def tick(self, frame: Optional[Image.Image]) -> Optional[TranslationResult]:
        """Run one OCR → translate cycle over the OCR region of *frame*.

        Returns a :class:`TranslationResult` when the region changed and a
        translation was produced, otherwise ``None`` (unchanged frame, empty
        OCR, or duplicate text).
        """
        if frame is None:
            return None

        force = self._force
        bypass_cache = self._bypass_cache_next
        self._force = False
        self._bypass_cache_next = False
        metrics = PipelineMetrics()

        # ── 1. crop OCR region ────────────────────────────────────────
        crop = self._ocr_crop(frame)

        # ── 2. hash gate ──────────────────────────────────────────────
        started = time.perf_counter()
        proceed = self._hash_gate.should_process(crop, force=force)
        metrics.hash_ms = (time.perf_counter() - started) * 1000.0
        if not proceed:
            return None

        # ── 3. OCR ────────────────────────────────────────────────────
        started = time.perf_counter()
        try:
            ocr_result = self._ocr.recognize(crop)
        except Exception as exc:  # noqa: BLE001
            self._metrics.record_error()
            raise OCRError(f"OCR failed: {exc}") from exc
        metrics.ocr_ms = (time.perf_counter() - started) * 1000.0
        source = cleanup_ocr_text(ocr_result.text)
        _record_ocr_debug_image(crop, ocr_result.text, source)
        _log.debug("v2 ocr raw=%r clean=%r crop=%sx%s", ocr_result.text, source, crop.width, crop.height)

        if not source:
            return None
        if not _is_meaningful_ocr_text(source):
            _log.debug("ignoring punctuation-only OCR text: %r", source)
            return None
        if len(source.strip()) < self._config.ocr.min_chars:
            return None

        # ── 4. text dedup ─────────────────────────────────────────────
        if source == self._last_source:
            return None
        self._last_source = source

        # ── 5. translate (with cache) ─────────────────────────────────
        context = self._context.previous_translation_lines(
            self._config.translator.context_lines
        )
        try:
            result = translate_with_cache(
                self._cache,
                self._translator,
                source,
                context,
                self._config.app.target_lang,
                bypass_cache=bypass_cache,
                glossary=(
                    self._config.glossary.entries
                    if self._config.glossary.enabled
                    else None
                ),
            )
        except Exception as exc:  # noqa: BLE001
            self._metrics.record_error()
            self._last_source = ""
            raise TranslationError(f"translation failed: {exc}") from exc

        result.raw_source_text = ocr_result.text
        result.ocr_ms = metrics.ocr_ms
        metrics.translate_ms = result.translation_ms or 0.0
        metrics.cache_hit = result.cached
        metrics.backend = result.backend
        metrics.source_chars = len(source)
        metrics.translated_chars = len(result.translated_text)
        result.metrics = metrics
        self._metrics.record(metrics)
        self._context.add(
            source,
            result.translated_text,
            suppress_window=self._config.v1_overlay.duplicate_suppression_window,
        )
        _log.info(
            "v2 tick ocr_ms=%.1f translation_ms=%.1f backend=%s cache_hit=%s source_len=%d",
            result.ocr_ms or 0.0,
            result.translation_ms or 0.0,
            result.backend,
            result.cached,
            len(source),
        )
        return result
