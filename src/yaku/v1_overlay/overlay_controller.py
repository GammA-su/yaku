"""Controller that wires the V1Pipeline to the overlay window and timer."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication, QInputDialog

from yaku.core.config import YakuConfig
from yaku.core.logging import get_logger
from yaku.core.pipeline import V1Pipeline
from yaku.translate.base import TranslationResult
from yaku.v1_overlay.overlay_window import OverlayWindow

_log = get_logger("overlay_controller")


# ---------------------------------------------------------------------------
# Thread-pool worker
# ---------------------------------------------------------------------------

class _Signals(QObject):
    """Signal carrier created in the main thread so slots run there too."""
    result = pyqtSignal(object)   # TranslationResult | None
    error  = pyqtSignal(str)


class _PipelineJob(QRunnable):
    """Single pipeline tick submitted to QThreadPool."""

    def __init__(self, pipeline: V1Pipeline, signals: _Signals) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._pipeline = pipeline
        self._signals  = signals

    @pyqtSlot()
    def run(self) -> None:
        # Error boundary: a worker exception must never propagate out of the
        # thread-pool (that would be swallowed silently and could abort the
        # pool thread).  Report it on the error signal instead.
        try:
            result = self._pipeline.tick()
            self._signals.result.emit(result)
        except Exception as exc:  # noqa: BLE001
            _log.exception("Pipeline worker error")
            self._signals.error.emit(f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------

class OverlayController(QObject):
    """Manages the periodic pipeline tick and routes results to the overlay.

    Design:
    - A ``QTimer`` fires every ``config.app.tick_ms`` milliseconds.
    - Each tick submits a ``_PipelineJob`` to ``QThreadPool`` (max 1 in flight).
    - Results are delivered back to the main thread via Qt signals.
    - The overlay window emits hotkey signals that the controller handles.
    """

    def __init__(
        self,
        config: YakuConfig,
        window: OverlayWindow,
        pipeline: V1Pipeline,
        config_path: Optional[Path] = None,
        *,
        executor: Optional[Callable[[QRunnable], None]] = None,
    ) -> None:
        super().__init__()
        self._config      = config
        self._window      = window
        self._pipeline    = pipeline
        self._config_path = config_path
        # Injectable job runner (tests pass a synchronous one).
        self._executor = executor or QThreadPool.globalInstance().start

        self._signals = _Signals()
        self._signals.result.connect(self._on_result)
        self._signals.error.connect(self._on_error)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)

        self._paused  = False
        self._busy    = False
        self._stopped = False
        self._errors  = 0
        self._last_ocr: str = ""
        self._last_clean: str = ""
        self._debug_panel: Optional[object] = None
        self._settings_panel: Optional[object] = None
        self._last_result: Optional[TranslationResult] = None

        # connect overlay hotkeys
        window.hotkey_f6.connect(self._handle_select_ocr_region)
        window.hotkey_f7.connect(self._handle_toggle_lock)
        window.hotkey_f8.connect(self._handle_force_ocr)
        window.hotkey_shift_f8.connect(self._handle_force_retranslate)
        window.hotkey_f9.connect(self._handle_toggle_pause)
        window.hotkey_f10.connect(self._handle_debug_panel)
        window.hotkey_f11.connect(self._handle_settings_panel)
        window.hotkey_esc.connect(self._handle_esc)
        window.copy_source_requested.connect(self._copy_source_text)
        window.copy_translation_requested.connect(self._copy_translated_text)
        window.edit_translation_requested.connect(self._handle_edit_translation)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._stopped = False
        self._window.set_status("idle")
        self._timer.start(self._config.app.tick_ms)
        _log.debug("V1 controller started (tick=%dms)", self._config.app.tick_ms)

    def stop(self, *, wait_ms: int = 3000) -> None:
        """Stop ticking and drain in-flight workers so no threads hang."""
        self._stopped = True
        self._timer.stop()
        # Drain the thread pool so a late tick can't touch a torn-down window.
        try:
            QThreadPool.globalInstance().waitForDone(wait_ms)
        except Exception:  # noqa: BLE001 — shutdown must never raise
            pass
        self._busy = False
        _log.debug("V1 controller stopped")

    # ------------------------------------------------------------------
    # Timer → thread-pool dispatch
    # ------------------------------------------------------------------

    @pyqtSlot()
    def _on_tick(self) -> None:
        # No-duplicate-jobs guard: skip while paused, stopped, or a job is in
        # flight, so the same work is never dispatched twice concurrently.
        if self._paused or self._busy or self._stopped:
            return
        self._busy = True
        if self._config.v1_overlay.pending_behavior == "show_pending":
            self._window.set_translation("...")
        self._window.set_status("capturing")
        self._executor(_PipelineJob(self._pipeline, self._signals))

    # ------------------------------------------------------------------
    # Result / error handlers (run in main thread via Qt signal dispatch)
    # ------------------------------------------------------------------

    @pyqtSlot(object)
    def _on_result(self, result: Optional[TranslationResult]) -> None:
        self._busy = False
        if self._stopped:
            return
        # Empty/unchanged OCR returns None — keep the previous translation
        # visible rather than clearing it.
        if result is None:
            self._window.set_status("idle")
            return

        self._last_result = result
        self._window.set_translation(result.translated_text)
        self._window.set_source(result.source_text)
        status = "cached" if result.cached else "translated"
        self._window.set_status(status)

        if self._debug_panel is not None:
            self._debug_panel.update_result(  # type: ignore[attr-defined]
                ocr_clean=result.source_text,
                translation=result.translated_text,
                backend=result.backend,
                backend_model=result.backend_model,
                cached=result.cached,
                ocr_raw=(
                    result.raw_source_text
                    if self._config.v1_overlay.show_source_in_debug
                    else ""
                ),
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
        # Keep the previous translation; only flip the badge to error.
        self._window.set_status("error")
        if self._debug_panel is not None:
            self._debug_panel.update_result(error=message)  # type: ignore[attr-defined]
            self._push_metrics()

    def _push_metrics(self) -> None:
        panel = self._debug_panel
        if panel is None or not hasattr(panel, "update_metrics"):
            return
        panel.update_metrics(  # type: ignore[attr-defined]
            self._pipeline.metrics.averages(), self._errors
        )

    # ------------------------------------------------------------------
    # Hotkey handlers
    # ------------------------------------------------------------------

    @pyqtSlot()
    def _handle_select_ocr_region(self) -> None:
        from yaku.ui.region_selector import RegionSelector
        rect = RegionSelector().run_blocking()
        if rect is None:
            return
        from yaku.core.config import save_config, update_ocr_region
        update_ocr_region(self._config, rect)
        if self._config_path:
            save_config(self._config, self._config_path)
        _log.info("OCR region updated: %s", rect)

    @pyqtSlot()
    def _handle_toggle_lock(self) -> None:
        locked = not self._config.v1_overlay.locked
        self._config.v1_overlay.locked = locked
        self._window.set_locked(locked)
        _log.debug("Lock toggled → %s", locked)
        if self._config_path:
            from yaku.core.config import save_config
            save_config(self._config, self._config_path)

    @pyqtSlot()
    def _handle_force_ocr(self) -> None:
        _log.debug("Force OCR requested")
        self._pipeline.force_next()
        if not self._busy:
            self._on_tick()

    @pyqtSlot()
    def _handle_force_retranslate(self) -> None:
        _log.debug("Force retranslate requested")
        self._pipeline.force_next(bypass_cache=True)
        if not self._busy:
            self._on_tick()

    @pyqtSlot()
    def _handle_toggle_pause(self) -> None:
        self._paused = not self._paused
        self._window.set_status("paused" if self._paused else "idle")
        _log.debug("Pause toggled → %s", self._paused)

    @pyqtSlot()
    def _handle_debug_panel(self) -> None:
        from yaku.ui.debug_panel import DebugPanel
        if self._debug_panel is None:
            self._debug_panel = DebugPanel()
        panel = self._debug_panel
        if panel.isVisible():  # type: ignore[attr-defined]
            panel.hide()  # type: ignore[attr-defined]
        else:
            panel.show()  # type: ignore[attr-defined]
            panel.raise_()  # type: ignore[attr-defined]

    @pyqtSlot()
    def _handle_settings_panel(self) -> None:
        from yaku.ui.settings_panel import SettingsPanel

        if self._settings_panel is None:
            self._settings_panel = SettingsPanel(
                self._config,
                self._config_path,
                self._window,
                on_saved=self._apply_runtime_config,
            )
        panel = self._settings_panel
        panel.show()  # type: ignore[attr-defined]
        panel.raise_()  # type: ignore[attr-defined]

    def _apply_runtime_config(self) -> None:
        self._window.apply_config(self._config.v1_overlay)
        self._timer.setInterval(self._config.app.tick_ms)
        try:
            from yaku.translate.factory import create_translator
            self._pipeline.update_translator(create_translator(self._config.translator))
        except Exception as exc:  # noqa: BLE001
            _log.error("Translator refresh failed after settings save: %s", exc)
        try:
            from yaku.ocr.factory import create_ocr
            self._pipeline.update_ocr(create_ocr(self._config.ocr))
        except Exception as exc:  # noqa: BLE001
            _log.error("OCR refresh failed after settings save: %s", exc)
        _log.info(
            "Settings saved translator=%s ocr=%s target_lang=%s tick_ms=%d",
            self._config.translator.backend,
            self._config.ocr.backend,
            self._config.app.target_lang,
            self._config.app.tick_ms,
        )

    @pyqtSlot()
    def _copy_source_text(self) -> None:
        text = self._last_result.source_text if self._last_result else self._window.source_text()
        QApplication.clipboard().setText(text)

    @pyqtSlot()
    def _copy_translated_text(self) -> None:
        text = (
            self._last_result.translated_text
            if self._last_result
            else self._window.translated_text()
        )
        QApplication.clipboard().setText(text)

    @pyqtSlot()
    def _handle_edit_translation(self) -> None:
        if self._last_result is None:
            return
        edited, ok = QInputDialog.getMultiLineText(
            self._window,
            "Edit translation",
            "Translation",
            self._last_result.translated_text,
        )
        if not ok:
            return
        edited = edited.strip()
        if not edited:
            return
        self._last_result.translated_text = edited
        self._last_result.cached = False
        self._window.set_translation(edited)
        self._pipeline.overwrite_cached_translation(self._last_result)
        _log.info("Manual translation edit saved backend=%s", self._last_result.backend)

    @pyqtSlot()
    def _handle_esc(self) -> None:
        if self._debug_panel is not None and self._debug_panel.isVisible():  # type: ignore[attr-defined]
            self._debug_panel.hide()  # type: ignore[attr-defined]
            return
        self._window.close()
