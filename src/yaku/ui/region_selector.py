"""PyQt6 translucent fullscreen overlay for dragging a pixel region."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QEventLoop, QPoint, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QWidget

from yaku.core.image_utils import Rect


def logical_rect_to_physical(
    rect: Rect,
    *,
    screen_x: int = 0,
    screen_y: int = 0,
    device_pixel_ratio: float = 1.0,
) -> Rect:
    """Convert a Qt logical screen rect to physical capture pixels."""
    return Rect(
        x=round((screen_x + rect.x) * device_pixel_ratio),
        y=round((screen_y + rect.y) * device_pixel_ratio),
        w=round(rect.w * device_pixel_ratio),
        h=round(rect.h * device_pixel_ratio),
    )


class RegionSelector(QWidget):
    """Transparent fullscreen overlay — drag to define a rectangular region.

    Usage::

        from yaku.ui.app import get_app
        get_app()                       # ensure QApplication exists
        sel = RegionSelector()
        rect = sel.run_blocking()       # blocks until Enter / Esc
        if rect:
            print(rect)                 # Rect(x=…, y=…, w=…, h=…)

    Controls:
    - **Left-drag**: draw selection rectangle.
    - **Enter / Return**: confirm and return the rectangle.
    - **Esc**: cancel and return ``None``.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)

        self._start: Optional[QPoint] = None
        self._current: Optional[QPoint] = None
        self._region: Optional[Rect] = None
        self._loop: Optional[QEventLoop] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_blocking(self) -> Optional[Rect]:
        """Show the overlay and block until the user confirms or cancels.

        Returns:
            A :class:`~yaku.core.image_utils.Rect` in screen coordinates,
            or ``None`` if the user pressed Esc or closed the window without
            making a selection.
        """
        app = QApplication.instance()
        if app is None:
            raise RuntimeError(
                "QApplication must exist before calling run_blocking(). "
                "Call yaku.ui.app.get_app() first."
            )

        screen = app.primaryScreen()
        self.setGeometry(screen.geometry())

        self._loop = QEventLoop()
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        QApplication.setOverrideCursor(Qt.CursorShape.CrossCursor)
        self._loop.exec()
        QApplication.restoreOverrideCursor()

        return self._region

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _commit(self) -> None:
        """Compute the final Rect from current drag points and close."""
        if self._start and self._current:
            x1 = min(self._start.x(), self._current.x())
            y1 = min(self._start.y(), self._current.y())
            x2 = max(self._start.x(), self._current.x())
            y2 = max(self._start.y(), self._current.y())
            if x2 > x1 and y2 > y1:
                logical = Rect(x=x1, y=y1, w=x2 - x1, h=y2 - y1)
                screen = self.screen() or QApplication.primaryScreen()
                if screen is not None:
                    geom = screen.geometry()
                    self._region = logical_rect_to_physical(
                        logical,
                        screen_x=geom.x(),
                        screen_y=geom.y(),
                        device_pixel_ratio=screen.devicePixelRatio(),
                    )
                else:
                    self._region = logical
        self._finish()

    def _cancel(self) -> None:
        self._region = None
        self._finish()

    def _finish(self) -> None:
        if self._loop is not None:
            self._loop.quit()
            self._loop = None
        self.close()

    # ------------------------------------------------------------------
    # Qt event handlers
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = event.pos()
            self._current = event.pos()

    def mouseMoveEvent(self, event) -> None:
        self._current = event.pos()
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._current = event.pos()
            self.update()

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._commit()
        elif key == Qt.Key.Key_Escape:
            self._cancel()

    def closeEvent(self, event) -> None:
        if self._loop is not None:
            self._loop.quit()
            self._loop = None
        super().closeEvent(event)

    def paintEvent(self, event) -> None:  # noqa: ARG002
        painter = QPainter(self)

        # --- full-screen semi-transparent dark tint ---
        painter.fillRect(self.rect(), QColor(0, 0, 0, 110))

        if self._start and self._current:
            x1 = min(self._start.x(), self._current.x())
            y1 = min(self._start.y(), self._current.y())
            w = abs(self._current.x() - self._start.x())
            h = abs(self._current.y() - self._start.y())

            if w > 0 and h > 0:
                # Clear the tint inside the selection so the user sees the real screen
                painter.setCompositionMode(
                    QPainter.CompositionMode.CompositionMode_Clear
                )
                painter.fillRect(x1, y1, w, h, QColor(0, 0, 0, 255))
                painter.setCompositionMode(
                    QPainter.CompositionMode.CompositionMode_SourceOver
                )

                # Selection border
                pen = QPen(QColor(0, 200, 255), 2, Qt.PenStyle.SolidLine)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(x1, y1, w, h)

                # Dimension label
                label = f"{w} × {h} px"
                label_y = y1 - 6 if y1 > 22 else y1 + h + 18
                painter.setPen(QColor(255, 255, 255))
                painter.setFont(QFont("monospace", 11))
                painter.drawText(x1 + 4, label_y, label)

        # Instructions bar at the bottom
        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_SourceOver
        )
        painter.setPen(QColor(255, 255, 255, 210))
        painter.setFont(QFont("monospace", 12))
        painter.drawText(
            10,
            self.height() - 12,
            "Drag to select region  •  Enter = confirm  •  Esc = cancel",
        )

        painter.end()
