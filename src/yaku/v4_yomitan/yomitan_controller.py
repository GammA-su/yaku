from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, QTimer, Qt, pyqtSlot
from PyQt6.QtGui import QCursor

from yaku.core.config import YakuConfig
from yaku.core.image_utils import Rect
from yaku.core.logging import get_logger
from yaku.v4_yomitan.dictionary_lookup import DictionaryLookup
from yaku.v4_yomitan.dictionary_popup import DictionaryPopup
from yaku.v4_yomitan.tokenize import (
    approximate_token_boxes,
    longest_match_lookup,
    tokenize_japanese,
)

_log = get_logger("yomitan_controller")


class YomitanController(QObject):
    """Drives the Yomitan scanning loop and cursor-tracking dictionary lookup overlay."""

    def __init__(self, config: YakuConfig, config_path: Optional[Path] = None) -> None:
        super().__init__()
        self._config = config
        self._config_path = config_path

        from yaku.core.capture import create_capture
        from yaku.ocr.factory import create_ocr

        self._capture = create_capture(self._config.window)
        self._ocr = create_ocr(self._config.ocr)

        db_path = Path(self._config.v4_yomitan.dictionaries.index_path)
        self._lookup = DictionaryLookup(db_path)
        self._popup = DictionaryPopup()
        
        # Make popup transparent for mouse clicks so interaction with the game is uninterrupted
        self._popup.setWindowFlags(self._popup.windowFlags() | Qt.WindowType.WindowTransparentForInput)

        self._active_boxes: list[dict] = []
        self._last_hovered: Optional[tuple[str, int]] = None
        self._running = False

        self._scan_timer = QTimer(self)
        self._scan_timer.timeout.connect(self._scan_tick)

        self._hover_timer = QTimer(self)
        self._hover_timer.timeout.connect(self._hover_tick)

    def start(self) -> None:
        """Start scanning and mouse tracking timers."""
        self._running = True

        if self._config.app.mode == "v1-yomitan":
            region = self._config.ocr.region
            is_set = region.w > 0 and region.h > 0
        else:
            region = self._config.v4_yomitan.region
            is_set = region.is_set and region.w > 0 and region.h > 0

        if not is_set:
            _log.warning("Yomitan scan region is not set!")

        self._scan_timer.start(self._config.v4_yomitan.scan_interval_ms)
        self._hover_timer.start(50)  # smooth 50ms polling
        _log.info("YomitanController started (scan_interval=%dms)", self._config.v4_yomitan.scan_interval_ms)

    def stop(self) -> None:
        """Stop timers and hide display."""
        self._running = False
        self._scan_timer.stop()
        self._hover_timer.stop()
        self._popup.hide_popup()
        self._last_hovered = None
        _log.info("YomitanController stopped")

    @pyqtSlot()
    def _scan_tick(self) -> None:
        if not self._running:
            return

        if self._config.app.mode == "v1-yomitan":
            region = self._config.ocr.region
            is_set = region.w > 0 and region.h > 0
        else:
            region = self._config.v4_yomitan.region
            is_set = region.is_set and region.w > 0 and region.h > 0

        if not is_set:
            return

        try:
            rect = Rect(x=region.x, y=region.y, w=region.w, h=region.h)
            image = self._capture.capture_region(rect)
            ocr_boxes = self._ocr.detect_text_boxes(image)

            from PyQt6.QtWidgets import QApplication
            screen = QApplication.primaryScreen()
            dpr = screen.devicePixelRatio() if screen else 1.0

            new_active_boxes = []
            for ob in ocr_boxes:
                tokens = tokenize_japanese(ob.text)
                token_boxes = approximate_token_boxes(ob.text, ob.box, tokens)
                
                for tb in token_boxes:
                    gx = (rect.x + tb.box[0]) / dpr
                    gy = (rect.y + tb.box[1]) / dpr
                    gw = tb.box[2] / dpr
                    gh = tb.box[3] / dpr
                    
                    new_active_boxes.append({
                        "text": ob.text,
                        "char_index": tb.token.index,
                        "global_box": (gx, gy, gw, gh)
                    })
            
            self._active_boxes = new_active_boxes
        except Exception as exc:
            _log.error("Yomitan scanner OCR tick failed: %s", exc)

    @pyqtSlot()
    def _hover_tick(self) -> None:
        if not self._running:
            return

        mouse_pos = QCursor.pos()
        mx, my = mouse_pos.x(), mouse_pos.y()

        hovered_box = None
        for item in self._active_boxes:
            gx, gy, gw, gh = item["global_box"]
            if gx <= mx < gx + gw and gy <= my < gy + gh:
                hovered_box = item
                break

        if hovered_box:
            text = hovered_box["text"]
            char_index = hovered_box["char_index"]
            current_hover = (text, char_index)

            if self._last_hovered != current_hover:
                self._last_hovered = current_hover
                _, entries = longest_match_lookup(
                    text, char_index, self._lookup, max_len=12
                )
                if entries:
                    self._popup.set_entries(entries)
                    self._popup.show_at(mouse_pos)
                else:
                    self._popup.hide_popup()
            else:
                # keep popup positioned near moving cursor if already visible
                if not self._popup.isHidden():
                    self._popup.show_at(mouse_pos)
        else:
            self._last_hovered = None
            self._popup.hide_popup()
