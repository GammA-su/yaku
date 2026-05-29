"""Screen capture backends with lazy optional imports."""
from __future__ import annotations

from abc import ABC, abstractmethod

from PIL import Image

from yaku.core.config import WindowConfig
from yaku.core.errors import CaptureError, InvalidBackendError, OptionalDependencyMissing
from yaku.core.image_utils import Rect


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

class BaseCapture(ABC):
    """All capture backends implement this interface."""

    @abstractmethod
    def capture_frame(self) -> Image.Image:
        """Capture the full monitor / source window and return an RGB PIL image."""

    @abstractmethod
    def capture_region(self, rect: Rect) -> Image.Image:
        """Capture a sub-region of the source and return an RGB PIL image."""

    def close(self) -> None:
        """Release any held resources."""

    def source_origin(self) -> tuple[int, int]:
        """Top-left screen coordinate for ``capture_frame`` output."""
        return (0, 0)


# ---------------------------------------------------------------------------
# mss backend
# ---------------------------------------------------------------------------

class MSSCapture(BaseCapture):
    """Captures the primary monitor via ``mss``.

    Requires ``uv add mss``.
    """

    def __init__(self, config: WindowConfig | None = None) -> None:
        try:
            import mss as _mss  # lazy import
        except ImportError as exc:
            raise OptionalDependencyMissing(
                "mss is not installed. Install with: uv add mss"
            ) from exc
        self._mss = _mss
        self._config = config
        self._last_origin = (0, 0)

    def _target_monitor(self, sct) -> dict:
        rect = _window_rect(self._config)
        if rect is None:
            monitor = sct.monitors[1]  # primary monitor
            self._last_origin = (monitor["left"], monitor["top"])
            return monitor

        left, top, right, bottom = rect
        self._last_origin = (left, top)
        return {
            "left": left,
            "top": top,
            "width": max(1, right - left),
            "height": max(1, bottom - top),
        }

    def capture_frame(self) -> Image.Image:
        with self._mss.mss() as sct:
            monitor = self._target_monitor(sct)
            shot = sct.grab(monitor)
            return Image.frombytes("RGB", shot.size, shot.rgb)

    def capture_region(self, rect: Rect) -> Image.Image:
        with self._mss.mss() as sct:
            region = {
                "top": rect.y,
                "left": rect.x,
                "width": rect.w,
                "height": rect.h,
            }
            shot = sct.grab(region)
            return Image.frombytes("RGB", shot.size, shot.rgb)

    def source_origin(self) -> tuple[int, int]:
        return self._last_origin


# ---------------------------------------------------------------------------
# dxcam backend (Windows, high-performance)
# ---------------------------------------------------------------------------

class DXCamCapture(BaseCapture):
    """Captures via ``dxcam`` (Windows only, DXGI Desktop Duplication).

    Requires ``uv add dxcam`` (not on PyPI — install from GitHub).
    """

    def __init__(self) -> None:
        try:
            import dxcam  # lazy import
        except ImportError as exc:
            raise OptionalDependencyMissing(
                "dxcam is not installed. Install with: uv add dxcam"
            ) from exc
        self._camera = dxcam.create()

    def capture_frame(self) -> Image.Image:
        frame = self._camera.grab()
        if frame is None:
            raise CaptureError("dxcam.grab() returned None — screen may not be updating")
        # dxcam returns BGRA; take first three channels and reverse → RGB
        return Image.fromarray(frame[:, :, 2::-1])

    def capture_region(self, rect: Rect) -> Image.Image:
        region = (rect.x, rect.y, rect.x + rect.w, rect.y + rect.h)
        frame = self._camera.grab(region=region)
        if frame is None:
            raise CaptureError("dxcam.grab() returned None — screen may not be updating")
        return Image.fromarray(frame[:, :, 2::-1])

    def close(self) -> None:
        del self._camera


def _window_rect(config: WindowConfig | None) -> tuple[int, int, int, int] | None:
    """Resolve the configured target window rect, if available."""
    if config is None:
        return None
    try:
        from yaku.ui.window_picker import get_window_info, list_visible_windows

        info = get_window_info(config.hwnd) if config.hwnd is not None else None
        if info is None and config.title_contains:
            needle = config.title_contains.lower()
            for candidate in list_visible_windows():
                if needle in candidate.title.lower():
                    info = candidate
                    break
        if info is None:
            return None

        left, top, right, bottom = info.rect
        if right <= left or bottom <= top:
            return None
        return info.rect
    except Exception:
        return None


def _create_mss_capture(config: WindowConfig) -> BaseCapture:
    try:
        return MSSCapture(config)
    except TypeError:
        return MSSCapture()


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_capture(config: WindowConfig) -> BaseCapture:
    """Instantiate and return a capture backend from *config*.

    For ``backend="auto"`` mss is preferred because it is more reliable with
    static visual-novel frames; dxcam is the fallback.  Raises
    :class:`~yaku.core.errors.OptionalDependencyMissing`
    with install instructions if no backend is available.
    """
    backend = config.capture_backend

    if backend == "dxcam":
        return DXCamCapture()

    if backend == "mss":
        return _create_mss_capture(config)

    if backend == "win32":
        raise InvalidBackendError(
            "win32 capture is not yet implemented. Use dxcam or mss."
        )

    if backend == "auto":
        for create in (lambda: _create_mss_capture(config), DXCamCapture):
            try:
                return create()
            except OptionalDependencyMissing:
                continue
        raise OptionalDependencyMissing(
            "No capture backend is available. "
            "Install one of:\n"
            "  uv add dxcam  (Windows, best performance)\n"
            "  uv add mss    (cross-platform)"
        )

    raise InvalidBackendError(f"Unknown capture backend: '{backend}'")
