"""v1-overlay floating translation window."""
from __future__ import annotations

import sys
from typing import Optional

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QKeySequence, QPainter, QShortcut
from PyQt6.QtWidgets import QApplication, QLabel, QMenu, QVBoxLayout, QWidget

from yaku.core.config import V1OverlayConfig
from yaku.core.logging import get_logger

_log = get_logger("overlay_window")

# Status → (text, CSS colour)
_STATUS_STYLE: dict[str, str] = {
    "idle":         "#888888",
    "capturing":    "#aaaaaa",
    "processing":   "#ffcc44",
    "translated":   "#44cc88",
    "cached":       "#44ccff",
    "paused":       "#ff9933",
    "error":        "#ff5555",
}


class OverlayWindow(QWidget):
    """Frameless, always-on-top, translucent overlay showing translated text.

    **Hotkeys** (application-wide):
    - F6  emit :attr:`hotkey_f6`  (select OCR region)
    - F7  emit :attr:`hotkey_f7`  (toggle lock / click-through)
    - F8  emit :attr:`hotkey_f8`  (force OCR + translate)
    - F9  emit :attr:`hotkey_f9`  (pause / resume)
    - F10 emit :attr:`hotkey_f10` (toggle debug panel)
    - Esc emit :attr:`hotkey_esc`

    **Drag to move** when unlocked (left-button drag on the overlay).
    """

    hotkey_f6  = pyqtSignal()
    hotkey_f7  = pyqtSignal()
    hotkey_f8  = pyqtSignal()
    hotkey_shift_f8 = pyqtSignal()
    hotkey_f9  = pyqtSignal()
    hotkey_f10 = pyqtSignal()
    hotkey_f11 = pyqtSignal()
    hotkey_esc = pyqtSignal()
    copy_source_requested = pyqtSignal()
    copy_translation_requested = pyqtSignal()
    edit_translation_requested = pyqtSignal()

    def __init__(self, config: V1OverlayConfig, parent: Optional[QWidget] = None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._config = config
        self._locked: bool = config.locked
        self._bg_alpha: int = int(config.background_opacity * 255)
        self._drag_start: Optional[QPoint] = None
        self._window_start: Optional[QPoint] = None

        # ----- layout -----
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        self._status_label = QLabel("")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._status_label.setFixedHeight(16)
        self._status_label.setVisible(config.show_status_badge)
        layout.addWidget(self._status_label)

        self._source_label = QLabel("")
        self._source_label.setWordWrap(True)
        self._source_label.setVisible(False)
        layout.addWidget(self._source_label)

        self._trans_label = QLabel("")
        self._trans_label.setWordWrap(True)
        self._trans_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        layout.addWidget(self._trans_label, stretch=1)

        self._apply_styles()
        self._install_shortcuts()
        self.setGeometry(config.x, config.y, config.w, config.h)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def apply_config(self, config: V1OverlayConfig) -> None:
        """Apply a new V1OverlayConfig (geometry, fonts, opacity)."""
        self._config = config
        self._bg_alpha = int(config.background_opacity * 255)
        self.setGeometry(config.x, config.y, config.w, config.h)
        self.setWindowOpacity(config.opacity)
        self._apply_styles()
        self._status_label.setVisible(config.show_status_badge)
        self.set_locked(config.locked)

    def set_translation(self, text: str) -> None:
        self._trans_label.setText(text)

    def set_source(self, text: str) -> None:
        self._source_label.setText(text)

    def source_text(self) -> str:
        return self._source_label.text()

    def translated_text(self) -> str:
        return self._trans_label.text()

    def set_status(self, status: str) -> None:
        if not self._config.show_status_badge:
            self._status_label.setText("")
            return
        color = _STATUS_STYLE.get(status, "#aaaaaa")
        self._status_label.setText(status)
        self._status_label.setStyleSheet(f"color: {color}; background: transparent; font-size: 11px;")

    def set_debug_visible(self, visible: bool) -> None:
        self._source_label.setVisible(visible)

    def set_locked(self, locked: bool) -> None:
        self._locked = locked
        if locked and self._config.click_through:
            self._set_click_through(True)
        else:
            self._set_click_through(False)

    def current_geometry(self) -> tuple[int, int, int, int]:
        """Return (x, y, w, h) of the current window position."""
        g = self.geometry()
        return g.x(), g.y(), g.width(), g.height()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_styles(self) -> None:
        c = self._config
        outline = (
            "text-shadow: -1px -1px 0 #000, 1px -1px 0 #000, "
            "-1px 1px 0 #000, 1px 1px 0 #000;"
            if c.text_outline else ""
        )
        base = (
            f"color: white; background: transparent; "
            f"font-family: {c.font_family!r}; font-size: {c.font_size}px; "
            f"{outline}"
        )
        self._trans_label.setStyleSheet(base)
        self._source_label.setStyleSheet(
            f"color: #cccccc; background: transparent; font-size: 11px; "
            f"font-style: italic;"
        )
        self._status_label.setStyleSheet(
            "color: #888888; background: transparent; font-size: 11px;"
        )

    def _install_shortcuts(self) -> None:
        ctx = Qt.ShortcutContext.ApplicationShortcut
        bindings = [
            ("F6",  self.hotkey_f6),
            ("F7",  self.hotkey_f7),
            ("F8",  self.hotkey_f8),
            ("Shift+F8", self.hotkey_shift_f8),
            ("F9",  self.hotkey_f9),
            ("F10", self.hotkey_f10),
            ("F11", self.hotkey_f11),
            ("Esc", self.hotkey_esc),
        ]
        for key, signal in bindings:
            QShortcut(QKeySequence(key), self, context=ctx).activated.connect(signal.emit)

    def _set_click_through(self, enabled: bool) -> None:
        """Apply / remove WS_EX_TRANSPARENT on Windows."""
        if sys.platform != "win32":
            if enabled:
                _log.warning("Click-through is only supported on Windows.")
            return
        try:
            import ctypes
            hwnd = int(self.winId())
            GWL_EXSTYLE   = -20
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_LAYERED     = 0x00080000
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if enabled:
                style = style | WS_EX_TRANSPARENT | WS_EX_LAYERED
            else:
                style = style & ~WS_EX_TRANSPARENT
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception as exc:
            _log.warning(f"Click-through unavailable: {exc}")

    # ------------------------------------------------------------------
    # Qt event overrides
    # ------------------------------------------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.setWindowOpacity(self._config.opacity)
        # Apply click-through after the window handle is valid
        if self._locked and self._config.click_through:
            self._set_click_through(True)

    def paintEvent(self, event) -> None:  # noqa: ARG002
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, self._bg_alpha))
        painter.end()

    def mousePressEvent(self, event) -> None:
        if not self._locked and event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.globalPosition().toPoint()
            self._window_start = self.pos()

    def mouseMoveEvent(self, event) -> None:
        if (
            not self._locked
            and self._drag_start is not None
            and self._window_start is not None
        ):
            delta = event.globalPosition().toPoint() - self._drag_start
            self.move(self._window_start + delta)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = None
            self._window_start = None

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)

        force_ocr = QAction("Force re-OCR", self)
        force_ocr.triggered.connect(self.hotkey_f8.emit)
        menu.addAction(force_ocr)

        force_retranslate = QAction("Force retranslate", self)
        force_retranslate.triggered.connect(self.hotkey_shift_f8.emit)
        menu.addAction(force_retranslate)

        edit_translation = QAction("Edit translation", self)
        edit_translation.triggered.connect(self.edit_translation_requested.emit)
        menu.addAction(edit_translation)

        menu.addSeparator()

        copy_source = QAction("Copy source text", self)
        copy_source.triggered.connect(self.copy_source_requested.emit)
        menu.addAction(copy_source)

        copy_translation = QAction("Copy translated text", self)
        copy_translation.triggered.connect(self.copy_translation_requested.emit)
        menu.addAction(copy_translation)

        menu.addSeparator()

        settings = QAction("Settings", self)
        settings.triggered.connect(self.hotkey_f11.emit)
        menu.addAction(settings)

        menu.addSeparator()

        close_overlay = QAction("Close overlay", self)
        close_overlay.triggered.connect(self.close)
        menu.addAction(close_overlay)

        menu.exec(event.globalPos())

    def closeEvent(self, event) -> None:
        super().closeEvent(event)
        app = QApplication.instance()
        if app is not None:
            app.quit()
