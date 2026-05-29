"""v2-mirror window: shows the live captured VN frame with translated text.

Displays the rendered frame inside a PyQt6 window, preserving aspect ratio
(letterboxed).  Hotkeys are exposed as Qt signals so the controller can wire
them to pipeline actions; fullscreen/close are handled in the window itself.

When input forwarding is enabled, mouse clicks, the wheel, and a small set of
keys (Enter/Space/Ctrl) are mapped from widget space to VN client space and
handed to an :class:`~yaku.v2_mirror.input_forward.BaseInputForwarder`.
"""
from __future__ import annotations

from typing import Optional, Union

import numpy as np
from PIL import Image
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QImage, QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import QLabel, QMainWindow, QWidget

from yaku.core.logging import get_logger
from yaku.v2_mirror.coordinate_map import (
    mirror_click_to_vn_client_coord,
    widget_point_to_frame_point,
)
from yaku.v2_mirror.input_forward import BaseInputForwarder

_log = get_logger("mirror_window")

# Status → CSS colour for the overlay badge.
_STATUS_STYLE: dict[str, str] = {
    "idle":        "#888888",
    "capturing":   "#aaaaaa",
    "ocr":         "#ffcc44",
    "translating": "#ffcc44",
    "translated":  "#44cc88",
    "cached":      "#44ccff",
    "paused":      "#ff9933",
    "error":       "#ff5555",
}

# Qt key → forwarder key name for the supported forwarded keys.
_FORWARD_KEYS: dict[int, str] = {
    Qt.Key.Key_Return: "enter",
    Qt.Key.Key_Enter: "enter",
    Qt.Key.Key_Space: "space",
    Qt.Key.Key_Control: "ctrl",
}


def pil_to_qimage(image: Image.Image) -> QImage:
    """Convert a PIL image to a 24-bit RGB :class:`QImage` (copy-owned)."""
    rgb = image.convert("RGB")
    data = rgb.tobytes("raw", "RGB")
    qimg = QImage(data, rgb.width, rgb.height, rgb.width * 3, QImage.Format.Format_RGB888)
    # tobytes() buffer is owned by Python; copy so Qt keeps its own memory.
    return qimg.copy()


class MirrorWindow(QMainWindow):
    """Window that renders captured frames scaled to fit, aspect preserved.

    **Hotkeys:**
    - F8  → :attr:`hotkey_f8`  (force OCR / translate)
    - F9  → :attr:`hotkey_f9`  (pause / resume)
    - F10 → :attr:`hotkey_f10` (toggle debug panel)
    - F11 → toggle fullscreen
    - Esc → exit fullscreen, or close the window

    **Forwarded input** (when enabled): left/right click, wheel, Enter/Space/Ctrl.
    Each forwarded event emits :attr:`input_forwarded` for diagnostics.
    """

    hotkey_f8 = pyqtSignal()
    hotkey_f9 = pyqtSignal()
    hotkey_f10 = pyqtSignal()
    # (description, mapped VN-client coord or None, success)
    input_forwarded = pyqtSignal(str, object, bool)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Yaku Mirror")
        self.resize(960, 540)

        # Central frame display.
        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("background-color: black;")
        self.setCentralWidget(self._label)
        self.setStyleSheet("background-color: black;")

        # Status overlay (child of the label so it floats over the frame).
        self._status_label = QLabel(self._label)
        self._status_label.setStyleSheet(
            "color: #aaaaaa; background: rgba(0, 0, 0, 140); "
            "padding: 2px 8px; font-size: 12px;"
        )
        self._status_label.move(8, 8)
        self._status_label.setVisible(False)

        self._current_pixmap: Optional[QPixmap] = None
        self._frame_w: int = 0
        self._frame_h: int = 0

        self._forwarder: Optional[BaseInputForwarder] = None
        self._forward_input: bool = False

        self._install_shortcuts()

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def set_input_forwarder(
        self, forwarder: Optional[BaseInputForwarder], forward_input: bool
    ) -> None:
        """Attach the forwarder and enable/disable input forwarding."""
        self._forwarder = forwarder
        self._forward_input = forward_input

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def display_frame(self, frame: Union[Image.Image, QImage, np.ndarray]) -> None:
        """Show *frame* scaled to fit the window with aspect ratio preserved."""
        if isinstance(frame, QImage):
            qimg = frame
        elif isinstance(frame, np.ndarray):
            qimg = pil_to_qimage(Image.fromarray(frame))
        else:
            qimg = pil_to_qimage(frame)

        self._frame_w = qimg.width()
        self._frame_h = qimg.height()
        self._current_pixmap = QPixmap.fromImage(qimg)
        self._rescale_pixmap()

    def _rescale_pixmap(self) -> None:
        if self._current_pixmap is None:
            return
        scaled = self._current_pixmap.scaled(
            self._label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._label.setPixmap(scaled)

    def set_status(self, status: str, *, visible: bool = True) -> None:
        """Update the floating status badge (e.g. ``ocr``, ``translating``)."""
        if not visible or not status:
            self._status_label.setVisible(False)
            return
        color = _STATUS_STYLE.get(status, "#aaaaaa")
        self._status_label.setText(status)
        self._status_label.setStyleSheet(
            f"color: {color}; background: rgba(0, 0, 0, 140); "
            "padding: 2px 8px; font-size: 12px;"
        )
        self._status_label.adjustSize()
        self._status_label.setVisible(True)
        self._status_label.raise_()

    # ------------------------------------------------------------------
    # Input forwarding
    # ------------------------------------------------------------------

    def _vn_client_size(self) -> tuple[int, int]:
        """Return the VN client size, falling back to the frame size."""
        if self._forwarder is not None:
            size = self._forwarder.client_size()
            if size is not None:
                return size
        return (self._frame_w, self._frame_h)

    def _widget_click_to_client(self, lx: int, ly: int) -> Optional[tuple[int, int]]:
        """Map a label-space point to a VN client coordinate (None if letterbox)."""
        if self._frame_w <= 0 or self._frame_h <= 0:
            return None
        vn_w, vn_h = self._vn_client_size()
        return mirror_click_to_vn_client_coord(
            lx, ly,
            self._frame_w, self._frame_h,
            self._label.width(), self._label.height(),
            vn_w, vn_h,
        )

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if not self._forward_input or self._forwarder is None:
            super().mousePressEvent(event)
            return

        btn = event.button()
        if btn == Qt.MouseButton.LeftButton:
            button = "left"
        elif btn == Qt.MouseButton.RightButton:
            button = "right"
        else:
            super().mousePressEvent(event)
            return

        gp = event.globalPosition().toPoint()
        lp = self._label.mapFromGlobal(gp)
        client = self._widget_click_to_client(lp.x(), lp.y())
        if client is None:
            self.input_forwarded.emit(f"{button} click (outside frame)", None, False)
            return

        success = self._forwarder.forward_mouse_click(client[0], client[1], button)
        self.input_forwarded.emit(f"{button} click", client, success)

    def wheelEvent(self, event) -> None:  # noqa: N802
        if not self._forward_input or self._forwarder is None:
            super().wheelEvent(event)
            return
        delta = event.angleDelta().y()
        success = self._forwarder.forward_mouse_wheel(delta)
        self.input_forwarded.emit(f"wheel {delta:+d}", None, success)

    # ------------------------------------------------------------------
    # Qt events
    # ------------------------------------------------------------------

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._rescale_pixmap()
        self._status_label.move(8, 8)
        self._status_label.raise_()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key == Qt.Key.Key_F11:
            self._toggle_fullscreen()
            return
        if key == Qt.Key.Key_Escape:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.close()
            return

        if (
            self._forward_input
            and self._forwarder is not None
            and not event.isAutoRepeat()
            and key in _FORWARD_KEYS
        ):
            name = _FORWARD_KEYS[key]
            down = self._forwarder.forward_key(name, pressed=True)
            up = self._forwarder.forward_key(name, pressed=False)
            self.input_forwarded.emit(f"key {name}", None, down and up)
            return

        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _install_shortcuts(self) -> None:
        ctx = Qt.ShortcutContext.ApplicationShortcut
        bindings = [
            ("F8", self.hotkey_f8),
            ("F9", self.hotkey_f9),
            ("F10", self.hotkey_f10),
        ]
        for key, signal in bindings:
            QShortcut(QKeySequence(key), self, context=ctx).activated.connect(signal.emit)
