from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication, QInputDialog

from yaku.core.config import YakuConfig
from yaku.core.logging import get_logger
from yaku.core.pipeline import translate_with_cache
from yaku.core.context_memory import ContextMemory
from yaku.translate.base import BaseTranslator, TranslationResult
from yaku.v1_overlay.overlay_window import OverlayWindow
from yaku.audio.audio_pipeline import AudioPipeline
from yaku.audio.transcript_cleanup import TranscriptCleanup

_log = get_logger("audio_overlay_controller")


class _Signals(QObject):
    """Signal carrier created in the main thread so slots run there too."""
    result = pyqtSignal(object)   # TranslationResult
    error  = pyqtSignal(str)


class _TranslateJob(QRunnable):
    """Single translation tick submitted to QThreadPool."""

    def __init__(
        self,
        cache: Any,
        translator: BaseTranslator,
        source_text: str,
        context: list[str],
        target_lang: str,
        glossary: Any,
        signals: _Signals,
    ) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._cache = cache
        self._translator = translator
        self._source_text = source_text
        self._context = context
        self._target_lang = target_lang
        self._glossary = glossary
        self._signals = signals

    @pyqtSlot()
    def run(self) -> None:
        try:
            res = translate_with_cache(
                self._cache,
                self._translator,
                self._source_text,
                self._context,
                self._target_lang,
                bypass_cache=False,
                glossary=self._glossary,
            )
            self._signals.result.emit(res)
        except Exception as exc:
            _log.exception("Audio translation worker error")
            self._signals.error.emit(f"{type(exc).__name__}: {exc}")


class AudioOverlayController(QObject):
    """Manages the audio pipeline polling, transcript cleaning, and async translation routing."""

    def __init__(
        self,
        config: YakuConfig,
        window: OverlayWindow,
        pipeline: AudioPipeline,
        translator: BaseTranslator,
        cache: Any,
        config_path: Optional[Path] = None,
    ) -> None:
        super().__init__()
        self._config = config
        self._window = window
        self._pipeline = pipeline
        self._translator = translator
        self._cache = cache
        self._config_path = config_path

        self._cleanup = TranscriptCleanup(
            min_transcript_chars=config.audio.min_transcript_chars,
            dedupe_window=config.audio.dedupe_window,
        )

        self._context = ContextMemory(max_lines=config.translator.context_lines)
        self._signals = _Signals()
        self._signals.result.connect(self._on_result)
        self._signals.error.connect(self._on_error)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_poll)

        self._paused = False
        self._stopped = False
        self._busy = False
        self._last_result: Optional[TranslationResult] = None
        self._debug_panel: Optional[Any] = None
        self._settings_panel: Optional[Any] = None

        # connect overlay hotkeys
        window.hotkey_f7.connect(self._handle_toggle_lock)
        window.hotkey_f9.connect(self._handle_toggle_pause)
        window.hotkey_f10.connect(self._handle_debug_panel)
        window.hotkey_f11.connect(self._handle_settings_panel)
        window.hotkey_esc.connect(self._handle_esc)
        window.copy_source_requested.connect(self._copy_source_text)
        window.copy_translation_requested.connect(self._copy_translated_text)
        window.edit_translation_requested.connect(self._handle_edit_translation)

    def start(self) -> None:
        self._stopped = False
        self._window.set_status("listening")
        self._pipeline.start()
        # Poll the audio pipeline every 100ms
        self._timer.start(100)
        _log.debug("V3 Audio Overlay controller started")

    def stop(self, *, wait_ms: int = 3000) -> None:
        self._stopped = True
        self._timer.stop()
        self._pipeline.stop()
        try:
            QThreadPool.globalInstance().waitForDone(wait_ms)
        except Exception:
            pass
        self._busy = False
        self._window.set_status("idle")
        _log.debug("V3 Audio Overlay controller stopped")

    @pyqtSlot()
    def _on_poll(self) -> None:
        if self._paused or self._stopped or self._busy:
            return

        asr_res = self._pipeline.poll()
        if asr_res is None or not asr_res.text:
            return

        text = asr_res.text.strip()
        if self._cleanup.should_ignore(text):
            _log.debug(f"Transcript filtered/ignored: '{text}'")
            return

        self._cleanup.add_to_history(text)

        self._busy = True
        self._window.set_status("translating")
        if self._config.v1_overlay.pending_behavior == "show_pending":
            self._window.set_translation("...")

        context = self._context.previous_translation_lines(
            self._config.translator.context_lines
        )
        glossary = self._config.glossary.entries if self._config.glossary.enabled else None

        job = _TranslateJob(
            cache=self._cache,
            translator=self._translator,
            source_text=text,
            context=context,
            target_lang=self._config.app.target_lang,
            glossary=glossary,
            signals=self._signals,
        )
        QThreadPool.globalInstance().start(job)

    @pyqtSlot(object)
    def _on_result(self, result: TranslationResult) -> None:
        self._busy = False
        if self._stopped:
            return

        self._last_result = result
        self._window.set_translation(result.translated_text)
        self._window.set_source(result.source_text)
        status = "cached" if result.cached else "translated"
        self._window.set_status(status)

        self._context.add(
            result.source_text,
            result.translated_text,
            suppress_window=self._config.v1_overlay.duplicate_suppression_window,
        )

        if self._debug_panel is not None:
            self._debug_panel.update_result(
                ocr_clean=result.source_text,
                translation=result.translated_text,
                backend=result.backend,
                backend_model=result.backend_model,
                cached=result.cached,
                ocr_raw=result.source_text,
                ocr_ms=0.0,
                trans_ms=result.translation_ms,
                tokens_per_second=result.tokens_per_second,
            )

    @pyqtSlot(str)
    def _on_error(self, message: str) -> None:
        self._busy = False
        if self._stopped:
            return
        _log.error("Audio Overlay Translation error: %s", message)
        self._window.set_status("error")
        if self._debug_panel is not None:
            self._debug_panel.update_result(error=message)

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
    def _handle_toggle_pause(self) -> None:
        self._paused = not self._paused
        self._window.set_status("paused" if self._paused else "listening")
        _log.debug("Pause toggled → %s", self._paused)

    @pyqtSlot()
    def _handle_debug_panel(self) -> None:
        from yaku.ui.debug_panel import DebugPanel
        if self._debug_panel is None:
            self._debug_panel = DebugPanel()
        panel = self._debug_panel
        if panel.isVisible():
            panel.hide()
        else:
            panel.show()
            panel.raise_()

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
        panel.show()
        panel.raise_()

    def _apply_runtime_config(self) -> None:
        self._window.apply_config(self._config.v1_overlay)
        try:
            from yaku.translate.factory import create_translator
            self._translator = create_translator(self._config.translator)
        except Exception as exc:
            _log.error("Translator refresh failed after settings save: %s", exc)

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
        self._cache.overwrite_translation(
            self._last_result.source_text,
            self._last_result.target_lang,
            self._last_result.backend,
            self._last_result.translated_text,
            self._last_result.backend_model,
        )
        _log.info("Manual translation edit saved in Audio Overlay")

    @pyqtSlot()
    def _handle_esc(self) -> None:
        if self._debug_panel is not None and self._debug_panel.isVisible():
            self._debug_panel.hide()
            return
        self._window.close()
