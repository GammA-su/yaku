from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from PIL import Image
from PyQt6.QtCore import QObject, QRunnable, QThreadPool, QTimer, pyqtSignal, pyqtSlot

from yaku.core.config import YakuConfig
from yaku.core.logging import get_logger
from yaku.core.metrics import LatencyEvent, MetricsLogger, PipelineMetrics, StageTimer
from yaku.ocr.base import BaseOCR, OCRBox
from yaku.ocr.japanese_filter import contains_japanese, clean_ocr_text
from yaku.v1_overlay_max.ocr_regions import filter_ocr_boxes, merge_nearby_ocr_boxes
from yaku.v1_overlay_max.max_overlay_window import MaxOverlayWindow
from yaku.translate.base import BaseTranslator, TranslationResult
from yaku.core.pipeline import translate_with_cache

_log = get_logger("max_overlay_controller")


class _Signals(QObject):
    result = pyqtSignal(dict)  # passes dict of results back to main thread
    error = pyqtSignal(str)


class _MaxPipelineJob(QRunnable):
    """Worker job that runs the full-window UI translation pipeline in a background thread."""

    def __init__(
        self,
        config: YakuConfig,
        ocr: BaseOCR,
        translator: BaseTranslator,
        cache: Any,
        capture: Any,
        signals: _Signals,
    ) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._config = config
        self._ocr = ocr
        self._translator = translator
        self._cache = cache
        self._capture = capture
        self._signals = signals

    @pyqtSlot()
    def run(self) -> None:
        try:
            res_dict = self._run_pipeline()
            self._signals.result.emit(res_dict)
        except NotImplementedError as exc:
            self._signals.error.emit(f"unsupported_backend: {exc}")
        except Exception as exc:
            _log.exception("MaxPipelineJob background thread error")
            self._signals.error.emit(f"error: {exc}")

    def _run_pipeline(self) -> dict:
        overall_start = time.perf_counter()
        max_cfg = self._config.v1_overlay_max

        # 1. Capture
        capture_timer = StageTimer()
        if self._capture is None:
            raise RuntimeError("Capture backend is not initialized.")

        with capture_timer:
            frame = self._capture.capture_frame()

        capture_ms = capture_timer.elapsed_ms or 0.0
        origin = self._capture.source_origin()
        frame_w, frame_h = frame.width, frame.height

        # 2. OCR Bounding Box Detection
        ocr_timer = StageTimer()
        with ocr_timer:
            try:
                raw_boxes = self._ocr.detect_text_boxes(frame)
            except NotImplementedError as e:
                raise NotImplementedError("v1-overlay-max requires an OCR backend with bounding boxes. Use PaddleOCR.") from e
            except AttributeError as e:
                raise NotImplementedError("v1-overlay-max requires an OCR backend with bounding boxes. Use PaddleOCR.") from e

        ocr_ms = ocr_timer.elapsed_ms or 0.0
        box_count_raw = len(raw_boxes)

        # 3. Filtering and Merging
        filtered_boxes = filter_ocr_boxes(raw_boxes, max_cfg)
        box_count_filtered = len(filtered_boxes)

        if max_cfg.merge_nearby_boxes:
            merged_boxes = merge_nearby_ocr_boxes(filtered_boxes, max_cfg.merge_distance_px)
        else:
            merged_boxes = filtered_boxes

        # Cap to max_regions
        final_boxes = merged_boxes[: max_cfg.max_regions]

        # 4. Translation Behavior
        translations: list[str] = []
        cache_hit_count = 0
        translated_box_count = 0
        translate_timer = StageTimer()

        with translate_timer:
            for box in final_boxes:
                try:
                    result = translate_with_cache(
                        cache=self._cache,
                        translator=self._translator,
                        source_text=box.text,
                        context=[],
                        target_lang=self._config.app.target_lang,
                        bypass_cache=False,
                        glossary=(
                            self._config.glossary.entries
                            if self._config.glossary.enabled
                            else None
                        ),
                    )
                    translations.append(result.translated_text)
                    if result.cached:
                        cache_hit_count += 1
                    else:
                        translated_box_count += 1
                except Exception as exc:
                    _log.error(f"Failed to translate region '{box.text}': {exc}")
                    translations.append("[Translation Error]")

        translate_ms = translate_timer.elapsed_ms or 0.0
        total_scan_ms = (time.perf_counter() - overall_start) * 1000.0

        return {
            "boxes": final_boxes,
            "translations": translations,
            "origin": origin,
            "size": (frame_w, frame_h),
            "metrics": {
                "capture_ms": capture_ms,
                "ocr_ms": ocr_ms,
                "translate_ms": translate_ms,
                "total_scan_ms": total_scan_ms,
                "box_count_raw": box_count_raw,
                "box_count_filtered": box_count_filtered,
                "translated_box_count": translated_box_count,
                "cache_hit_count": cache_hit_count,
            },
        }


class MaxOverlayController(QObject):
    """Controller linking window capture, PaddleOCR detect, translator cache and MaxOverlayWindow."""

    def __init__(
        self,
        config: YakuConfig,
        window: MaxOverlayWindow,
        ocr: BaseOCR,
        translator: BaseTranslator,
        cache: Any,
        capture: Any,
        config_path: Optional[Path] = None,
        *,
        executor: Optional[Callable[[QRunnable], None]] = None,
    ) -> None:
        super().__init__()
        self._config = config
        self._window = window
        self._ocr = ocr
        self._translator = translator
        self._cache = cache
        self._capture = capture
        self._config_path = config_path
        self._executor = executor or QThreadPool.globalInstance().start

        self._signals = _Signals()
        self._signals.result.connect(self._on_result)
        self._signals.error.connect(self._on_error)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)

        self._paused = False
        self._busy = False
        self._stopped = False

        self._metrics_logger = MetricsLogger(
            path=config.metrics.log_path,
            enabled=config.metrics.enabled and config.metrics.log_jsonl,
        )

        window.hotkey_f8.connect(self._handle_force_scan)
        window.hotkey_f9.connect(self._handle_toggle_pause)
        window.hotkey_f10.connect(self._handle_toggle_debug)
        window.hotkey_esc.connect(self._handle_esc)

    def start(self) -> None:
        self._stopped = False
        self._window.set_status("idle")
        interval = self._config.v1_overlay_max.scan_interval_ms
        self._timer.start(interval)
        _log.info(f"MaxOverlayController started (interval={interval}ms)")

    def stop(self, *, wait_ms: int = 3000) -> None:
        self._stopped = True
        self._timer.stop()
        try:
            QThreadPool.globalInstance().waitForDone(wait_ms)
        except Exception:
            pass
        self._busy = False
        _log.info("MaxOverlayController stopped")

    @pyqtSlot()
    def _on_tick(self) -> None:
        if self._paused or self._busy or self._stopped:
            return
        self._busy = True
        self._window.set_status("scanning")
        self._executor(
            _MaxPipelineJob(
                config=self._config,
                ocr=self._ocr,
                translator=self._translator,
                cache=self._cache,
                capture=self._capture,
                signals=self._signals,
            )
        )

    @pyqtSlot(dict)
    def _on_result(self, result: dict) -> None:
        self._busy = False
        if self._stopped:
            return

        self._window.hide_warning()

        dpr = self._window.devicePixelRatioF()
        if dpr <= 0:
            dpr = 1.0

        ox, oy = result["origin"]
        ow, oh = result["size"]

        # Scale physical capture bounds to logical window coordinates
        logical_x = int(ox / dpr)
        logical_y = int(oy / dpr)
        logical_w = int(ow / dpr)
        logical_h = int(oh / dpr)
        self._window.setGeometry(logical_x, logical_y, logical_w, logical_h)

        # Scale physical OCR bounding boxes to logical coordinates
        boxes = result["boxes"]
        logical_boxes = []
        for box in boxes:
            lx = int(box.box[0] / dpr)
            ly = int(box.box[1] / dpr)
            lw = int(box.box[2] / dpr)
            lh = int(box.box[3] / dpr)
            logical_boxes.append(
                OCRBox(
                    text=box.text,
                    box=(lx, ly, lw, lh),
                    confidence=box.confidence
                )
            )

        translations = result["translations"]
        self._window.update_overlays(logical_boxes, translations)

        status = "cached" if result["metrics"]["translated_box_count"] == 0 else "translated"
        self._window.set_status(status)

        self._log_metrics(result["metrics"])

    @pyqtSlot(str)
    def _on_error(self, err_msg: str) -> None:
        self._busy = False
        if self._stopped:
            return

        _log.error(f"MaxOverlay scan failed: {err_msg}")
        self._window.set_status("error")

        if err_msg.startswith("unsupported_backend:"):
            self._window.show_warning("v1-overlay-max requires an OCR backend with bounding boxes. Use PaddleOCR.")
        else:
            self._window.show_warning(f"Error: {err_msg}")

    def _log_metrics(self, m: dict) -> None:
        if not self._config.metrics.enabled:
            return

        ts = datetime.now().astimezone().isoformat()
        event = LatencyEvent(
            ts=ts,
            mode="v1-overlay-max",
            ocr_backend=self._config.ocr.backend,
            translator=self._config.translator.backend,
            model=self._translator.backend_model,
            base_url=getattr(self._translator, "_base_url", None),
            render_mode=None,
            capture_ms=m["capture_ms"],
            hash_ms=0.0,
            ocr_ms=m["ocr_ms"],
            translate_ms=m["translate_ms"],
            render_ms=0.0,
            total_ms=m["total_scan_ms"],
            cache_hit=(m["translated_box_count"] == 0),
            source_chars=0,
            translated_chars=0,
            source_preview=None,
            translation_preview=None,
            prompt_tokens=None,
            completion_tokens=None,
            tokens_per_second=None,
            error=None,
            full_capture_ms=m["capture_ms"],
            full_ocr_ms=m["ocr_ms"],
            box_count_raw=m["box_count_raw"],
            box_count_filtered=m["box_count_filtered"],
            translated_box_count=m["translated_box_count"],
            cache_hit_count=m["cache_hit_count"],
            total_scan_ms=m["total_scan_ms"],
        )
        self._metrics_logger.log_event(event)

    @pyqtSlot()
    def _handle_force_scan(self) -> None:
        _log.debug("Force scan hotkey pressed")
        if not self._busy:
            self._on_tick()

    @pyqtSlot()
    def _handle_toggle_pause(self) -> None:
        self._paused = not self._paused
        self._window.set_status("paused" if self._paused else "idle")
        _log.info(f"Scan pause state toggled to {self._paused}")

    @pyqtSlot()
    def _handle_toggle_debug(self) -> None:
        self._config.app.debug = not self._config.app.debug
        _log.info(f"Debug mode toggled to {self._config.app.debug}")
        if not self._busy:
            self._on_tick()

    @pyqtSlot()
    def _handle_esc(self) -> None:
        self._window.close()
