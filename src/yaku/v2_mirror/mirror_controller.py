"""Controller wiring capture → V2Pipeline → renderer → mirror window.

Two independent cadences keep the UI responsive:

- a **display loop** (QTimer) captures the live frame, renders the last known
  translation into it, and shows it — this never blocks on OCR/translation;
- **pipeline jobs** run on a ``QThreadPool`` worker; when a translation is
  ready it updates the rendered text, leaving the previous one visible until
  then.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Optional

from PIL import Image
from PyQt6.QtCore import QObject, QRunnable, QThreadPool, QTimer, pyqtSignal, pyqtSlot

from yaku.core.config import YakuConfig
from yaku.core.logging import get_logger
from yaku.core.pipeline import V2Pipeline
from yaku.translate.base import TranslationResult
from yaku.v2_mirror.frame_renderer import FrameRenderer
from yaku.v2_mirror.input_forward import BaseInputForwarder
from yaku.v2_mirror.mirror_window import MirrorWindow

_log = get_logger("mirror_controller")


# ---------------------------------------------------------------------------
# Thread-pool worker
# ---------------------------------------------------------------------------

class _Signals(QObject):
    result = pyqtSignal(object)   # TranslationResult | None
    error = pyqtSignal(str)


class _PipelineJob(QRunnable):
    """Single V2 pipeline tick over a captured frame."""

    def __init__(self, pipeline: V2Pipeline, frame: Image.Image, signals: _Signals) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._pipeline = pipeline
        self._frame = frame
        self._signals = signals

    @pyqtSlot()
    def run(self) -> None:
        # Error boundary: never let a worker exception escape the thread pool.
        try:
            result = self._pipeline.tick(self._frame)
            self._signals.result.emit(result)
        except Exception as exc:  # noqa: BLE001
            _log.exception("Mirror pipeline worker error")
            self._signals.error.emit(f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------

class MirrorController(QObject):
    """Drives the mirror display loop and dispatches OCR/translation jobs."""

    def __init__(
        self,
        config: YakuConfig,
        window: MirrorWindow,
        pipeline: V2Pipeline,
        renderer: FrameRenderer,
        capture,
        forwarder: Optional[BaseInputForwarder] = None,
        config_path: Optional[Path] = None,
        *,
        executor: Optional[Callable[[QRunnable], None]] = None,
    ) -> None:
        super().__init__()
        self._config = config
        self._window = window
        self._pipeline = pipeline
        self._renderer = renderer
        self._capture = capture
        self._forwarder = forwarder
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
        self._errors = 0
        self._last_render_ms = 0.0
        self._current_frame: Optional[Image.Image] = None
        self._last_translation: str = ""
        self._last_result: Optional[TranslationResult] = None
        self._debug_panel: Optional[object] = None
        # Most recent forwarded-input diagnostic: (description, mapped, success).
        self._last_input: tuple[str, object, Optional[bool]] = ("none", None, None)

        window.set_input_forwarder(forwarder, config.v2_mirror.forward_input)
        window.hotkey_f8.connect(self._handle_force_ocr)
        window.hotkey_f9.connect(self._handle_toggle_pause)
        window.hotkey_f10.connect(self._handle_debug_panel)
        window.input_forwarded.connect(self._on_input_forwarded)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._stopped = False
        self._window.set_status("idle")
        self._timer.start(self._config.app.tick_ms)
        _log.debug("V2 mirror controller started (tick=%dms)", self._config.app.tick_ms)

    def stop(self, *, wait_ms: int = 3000) -> None:
        """Stop the display loop and drain in-flight workers (no hanging threads)."""
        self._stopped = True
        self._timer.stop()
        try:
            QThreadPool.globalInstance().waitForDone(wait_ms)
        except Exception:  # noqa: BLE001 — shutdown must never raise
            pass
        self._busy = False
        _log.debug("V2 mirror controller stopped")

    # ------------------------------------------------------------------
    # Display loop
    # ------------------------------------------------------------------

    @pyqtSlot()
    def _on_tick(self) -> None:
        if self._stopped:
            return
        frame = self._capture_frame()
        if frame is None:
            return
        self._current_frame = frame
        self._render_and_show(frame)

        # No-duplicate-jobs guard: only one OCR/translate job in flight at a time.
        if not self._paused and not self._busy:
            self._busy = True
            self._executor(_PipelineJob(self._pipeline, frame.copy(), self._signals))

    def _capture_frame(self) -> Optional[Image.Image]:
        # Capture error boundary: a failure here must not kill the display loop.
        if self._capture is None:
            self._window.set_status("error")
            return None
        try:
            return self._capture.capture_frame()
        except Exception as exc:  # noqa: BLE001
            self._errors += 1
            _log.error("Capture failed: %s", exc)
            self._window.set_status("error")
            return None

    def _render_and_show(self, frame: Image.Image) -> None:
        # Render error boundary: fall back to the raw frame so the mirror keeps
        # showing live video even if compositing fails.
        source_text = self._last_result.source_text if self._last_result else ""
        started = time.perf_counter()
        try:
            rendered = self._renderer.render(
                frame, self._last_translation, source_text=source_text
            )
        except Exception as exc:  # noqa: BLE001
            self._errors += 1
            _log.error("Render failed: %s", exc)
            rendered = frame
        self._last_render_ms = (time.perf_counter() - started) * 1000.0
        self._window.display_frame(rendered)

    # ------------------------------------------------------------------
    # Pipeline result handlers (main thread via Qt signals)
    # ------------------------------------------------------------------

    @pyqtSlot(object)
    def _on_result(self, result: Optional[TranslationResult]) -> None:
        self._busy = False
        if self._stopped:
            return
        # Empty/unchanged OCR returns None — keep the last translation visible.
        if result is None:
            return

        self._last_result = result
        self._last_translation = result.translated_text
        self._window.set_status("cached" if result.cached else "translated")

        # Re-render the current frame immediately so new text appears promptly.
        if self._current_frame is not None:
            self._render_and_show(self._current_frame)

        if result.metrics is not None:
            result.metrics.render_ms = self._last_render_ms  # type: ignore[attr-defined]

        if self._debug_panel is not None:
            self._debug_panel.update_result(  # type: ignore[attr-defined]
                ocr_clean=result.source_text,
                translation=result.translated_text,
                backend=result.backend,
                backend_model=result.backend_model,
                cached=result.cached,
                ocr_raw=result.raw_source_text,
                ocr_ms=result.ocr_ms,
                trans_ms=result.translation_ms,
            )
            self._push_metrics()

    @pyqtSlot(str)
    def _on_error(self, message: str) -> None:
        self._busy = False
        self._errors += 1
        if self._stopped:
            return
        _log.error("Pipeline error: %s", message)
        # Keep the previous translation rendered; only show the error badge.
        self._window.set_status("error")
        if self._debug_panel is not None:
            self._debug_panel.update_result(error=message)  # type: ignore[attr-defined]
            self._push_metrics()

    def _push_metrics(self) -> None:
        panel = self._debug_panel
        if panel is None or not hasattr(panel, "update_metrics"):
            return
        avg = self._pipeline.metrics.averages()
        avg["render_ms"] = self._last_render_ms
        panel.update_metrics(avg, self._errors)  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Hotkey handlers
    # ------------------------------------------------------------------

    @pyqtSlot()
    def _handle_force_ocr(self) -> None:
        _log.debug("Force OCR requested")
        self._pipeline.force_next()
        if (
            not self._busy
            and not self._stopped
            and self._current_frame is not None
            and not self._paused
        ):
            self._busy = True
            self._executor(
                _PipelineJob(self._pipeline, self._current_frame.copy(), self._signals)
            )

    @pyqtSlot()
    def _handle_toggle_pause(self) -> None:
        self._paused = not self._paused
        self._window.set_status("paused" if self._paused else "idle")
        _log.debug("Pause toggled → %s", self._paused)

    @pyqtSlot(str, object, bool)
    def _on_input_forwarded(self, description: str, mapped: object, success: bool) -> None:
        self._last_input = (description, mapped, success)
        if self._debug_panel is not None:
            hwnd, title = self._target_info()
            self._debug_panel.update_input(  # type: ignore[attr-defined]
                last_input=description,
                mapped=mapped,
                success=success,
                hwnd=hwnd,
                title=title,
            )

    def _target_info(self) -> tuple[Optional[int], str]:
        if self._forwarder is not None:
            hwnd, title = self._forwarder.target_info()
            if hwnd is not None:
                return (hwnd, title)
        hwnd = self._config.window.hwnd
        title = self._config.window.title_contains
        if hwnd is not None:
            from yaku.ui.window_picker import get_window_info
            info = get_window_info(hwnd)
            if info is not None:
                return (info.hwnd, info.title)
        return (hwnd, title)

    @pyqtSlot()
    def _handle_debug_panel(self) -> None:
        from yaku.ui.debug_panel import DebugPanel

        if self._debug_panel is None:
            self._debug_panel = DebugPanel()
        panel = self._debug_panel
        if panel.isVisible():  # type: ignore[attr-defined]
            panel.hide()  # type: ignore[attr-defined]
        else:
            # Push current target + last input so the panel is populated on open.
            hwnd, title = self._target_info()
            panel.set_target(hwnd, title)  # type: ignore[attr-defined]
            desc, mapped, success = self._last_input
            panel.update_input(  # type: ignore[attr-defined]
                last_input=desc, mapped=mapped, success=success, hwnd=hwnd, title=title
            )
            panel.show()  # type: ignore[attr-defined]
            panel.raise_()  # type: ignore[attr-defined]
