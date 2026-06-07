from __future__ import annotations

import sys
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QKeySequence, QPainter, QShortcut
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

from yaku.core.config import YakuConfig
from yaku.core.logging import get_logger
from yaku.ocr.base import OCRBox
from yaku.v1_overlay_max.layout import compute_label_positions

_log = get_logger("max_overlay_window")

_STATUS_STYLE: dict[str, str] = {
    "idle":         "#888888",
    "scanning":     "#aaaaaa",
    "translating":  "#ffcc44",
    "cached":       "#44ccff",
    "paused":       "#ff9933",
    "error":        "#ff5555",
}


class MaxOverlayWindow(QWidget):
    """Frameless, always-on-top, translucent full-window/screen overlay drawing many small labels."""

    hotkey_f8 = pyqtSignal()
    hotkey_f9 = pyqtSignal()
    hotkey_f10 = pyqtSignal()
    hotkey_esc = pyqtSignal()

    def __init__(self, config: YakuConfig, parent: Optional[QWidget] = None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)

        self._config = config
        self._max_config = config.v1_overlay_max
        self._labels: list[QLabel] = []
        self._warning_label: Optional[QLabel] = None

        # Status Badge
        self._status_label = QLabel(self)
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._status_label.setFixedHeight(20)
        self._status_label.setStyleSheet("color: #888888; background: transparent; font-size: 11px; font-weight: bold;")
        self._status_label.setText("idle")

        self._install_shortcuts()
        self._set_click_through(True)

    def _set_click_through(self, enabled: bool) -> None:
        if sys.platform != "win32":
            return
        try:
            import ctypes
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_LAYERED = 0x00080000
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if enabled:
                style = style | WS_EX_TRANSPARENT | WS_EX_LAYERED
            else:
                style = style & ~WS_EX_TRANSPARENT
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception as exc:
            _log.warning(f"Click-through unavailable: {exc}")

    def _install_shortcuts(self) -> None:
        ctx = Qt.ShortcutContext.ApplicationShortcut
        bindings = [
            ("F8", self.hotkey_f8),
            ("F9", self.hotkey_f9),
            ("F10", self.hotkey_f10),
            ("Esc", self.hotkey_esc),
        ]
        for key, signal in bindings:
            QShortcut(QKeySequence(key), self, context=ctx).activated.connect(signal.emit)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._set_click_through(True)

    def set_status(self, status: str) -> None:
        color = _STATUS_STYLE.get(status, "#aaaaaa")
        self._status_label.setText(status)
        self._status_label.setStyleSheet(
            f"color: {color}; background-color: rgba(0, 0, 0, 180); "
            f"font-size: 11px; font-weight: bold; padding: 2px 6px; border-radius: 3px;"
        )
        self._status_label.adjustSize()
        self._position_status_label()

    def _position_status_label(self) -> None:
        self._status_label.move(self.width() - self._status_label.width() - 10, 10)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_status_label()
        if self._warning_label:
            self._position_warning_label()

    def show_warning(self, message: str) -> None:
        """Display a visible overlay status warning (e.g. backend doesn't support boxes)."""
        if not self._warning_label:
            self._warning_label = QLabel(self)
            self._warning_label.setWordWrap(True)
            self._warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._warning_label.setText(message)
        self._warning_label.setStyleSheet(
            "color: #ff5555; background-color: rgba(0, 0, 0, 220); "
            "font-size: 14px; font-weight: bold; border: 2px solid #ff5555; "
            "padding: 10px 20px; border-radius: 8px;"
        )
        self._warning_label.show()
        self._warning_label.adjustSize()
        self._position_warning_label()

    def _position_warning_label(self) -> None:
        if self._warning_label:
            self._warning_label.move(
                (self.width() - self._warning_label.width()) // 2,
                (self.height() - self._warning_label.height()) // 2
            )

    def hide_warning(self) -> None:
        if self._warning_label:
            self._warning_label.hide()

    def update_overlays(self, boxes: list[OCRBox], translations: list[str]) -> None:
        """Update the list of small translated labels and place them next to OCR boxes."""
        for lbl in self._labels:
            lbl.deleteLater()
        self._labels.clear()

        if not boxes:
            return

        overlay_cfg = self._max_config.overlay
        bg_color = overlay_cfg.background
        fg_color = overlay_cfg.foreground
        opacity = overlay_cfg.opacity
        bg_rgba = f"rgba({bg_color[0]}, {bg_color[1]}, {bg_color[2]}, {int(opacity * 255)})"
        fg_rgb = f"rgb({fg_color[0]}, {fg_color[1]}, {fg_color[2]})"
        font_family = overlay_cfg.font_family
        font_size = overlay_cfg.font_size
        padding = overlay_cfg.padding
        max_width = overlay_cfg.max_width
        show_source_in_debug = overlay_cfg.show_source_in_debug and self._config.app.debug

        label_sizes: list[tuple[int, int]] = []
        temp_labels: list[QLabel] = []

        for box, trans in zip(boxes, translations):
            lbl = QLabel(self)
            lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            lbl.setWordWrap(True)
            lbl.setMaximumWidth(max_width)

            text_content = f"{trans}\n({box.text})" if show_source_in_debug else trans
            lbl.setText(text_content)

            style = (
                f"background-color: {bg_rgba}; "
                f"color: {fg_rgb}; "
                f"font-family: '{font_family}'; "
                f"font-size: {font_size}px; "
                f"padding: {padding}px; "
                f"border-radius: 4px;"
            )
            lbl.setStyleSheet(style)
            lbl.adjustSize()
            
            label_sizes.append((lbl.width(), lbl.height()))
            temp_labels.append(lbl)

        positions = compute_label_positions(
            boxes=boxes,
            label_sizes=label_sizes,
            screen_width=self.width(),
            screen_height=self.height(),
            config=self._max_config,
        )

        for lbl, (lx, ly) in zip(temp_labels, positions):
            lbl.move(int(lx), int(ly))
            lbl.show()
            self._labels.append(lbl)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 1))
        painter.end()

    def closeEvent(self, event) -> None:
        super().closeEvent(event)
        app = QApplication.instance()
        if app is not None:
            app.quit()
