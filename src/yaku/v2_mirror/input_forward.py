"""Forward mouse/keyboard input from the mirror window to the real VN window.

Windows-first.  On non-Windows platforms or when ``pywin32`` is missing a
:class:`NullInputForwarder` is returned so the mirror keeps displaying — input
simply isn't forwarded.

Coordinate contract: ``forward_mouse_click``/``forward_mouse_wheel`` receive
**VN client coordinates** (the same space the captured frame represents).  The
Windows backend converts those to screen coordinates via ``ClientToScreen`` and
injects them with ``SendInput`` using absolute virtual-desktop coordinates.
"""
from __future__ import annotations

import ctypes
import sys
from abc import ABC, abstractmethod
from ctypes import wintypes
from typing import Optional

from yaku.core.errors import OptionalDependencyMissing
from yaku.core.logging import get_logger

_log = get_logger("input_forward")

# Focus modes (mirror values of V2MirrorConfig.input_focus_mode).
FOCUS_SEND_ONLY = "send_input_only"
FOCUS_THEN_SEND = "focus_then_send"
FOCUS_DISABLED = "disabled"

# Virtual-key codes for the supported keys (case-insensitive aliases).
_VK_MAP: dict[str, int] = {
    "enter": 0x0D,
    "return": 0x0D,
    "space": 0x20,
    "ctrl": 0x11,
    "control": 0x11,
    "escape": 0x1B,
    "esc": 0x1B,
}


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

class BaseInputForwarder(ABC):
    """Forwards synthesized input to a target window.

    All ``forward_*`` methods return ``True`` on success and ``False`` on any
    failure (no target, window gone, unsupported platform) — they never raise.
    """

    @abstractmethod
    def forward_mouse_click(self, x: int, y: int, button: str = "left") -> bool:
        """Click at VN *client* coordinate ``(x, y)``."""

    @abstractmethod
    def forward_key(self, key: str, pressed: bool = True) -> bool:
        """Send a key down (``pressed=True``) or up (``pressed=False``)."""

    @abstractmethod
    def forward_mouse_wheel(self, delta: int) -> bool:
        """Scroll the wheel by *delta* (positive = up, like Qt angleDelta)."""

    def client_size(self) -> Optional[tuple[int, int]]:
        """Return ``(w, h)`` of the target's client area, or ``None``."""
        return None

    def target_info(self) -> tuple[Optional[int], str]:
        """Return ``(hwnd, title)`` of the target window for diagnostics."""
        return (None, "")

    def close(self) -> None:
        """Release any held resources."""


# ---------------------------------------------------------------------------
# Null forwarder (unsupported / disabled)
# ---------------------------------------------------------------------------

class NullInputForwarder(BaseInputForwarder):
    """No-op forwarder used when forwarding is disabled or unsupported."""

    def __init__(self, reason: str = "") -> None:
        self.reason = reason

    def forward_mouse_click(self, x: int, y: int, button: str = "left") -> bool:
        return False

    def forward_key(self, key: str, pressed: bool = True) -> bool:
        return False

    def forward_mouse_wheel(self, delta: int) -> bool:
        return False


# ---------------------------------------------------------------------------
# ctypes SendInput structures (safe to define on any platform)
# ---------------------------------------------------------------------------

_ULONG_PTR = wintypes.WPARAM

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000

KEYEVENTF_KEYUP = 0x0002
WHEEL_DELTA = 120

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", _ULONG_PTR),
    ]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", _ULONG_PTR),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", _INPUTUNION)]


# ---------------------------------------------------------------------------
# Windows forwarder
# ---------------------------------------------------------------------------

class WindowsInputForwarder(BaseInputForwarder):
    """Forwards input to a window identified by *hwnd* using ``SendInput``."""

    def __init__(self, hwnd: Optional[int], focus_mode: str = FOCUS_SEND_ONLY) -> None:
        if sys.platform != "win32":
            raise OptionalDependencyMissing(
                "Input forwarding is only supported on Windows."
            )
        try:
            import win32gui
        except ImportError as exc:
            raise OptionalDependencyMissing(
                "pywin32 is not installed. Install with: uv add pywin32"
            ) from exc

        self._win32gui = win32gui
        self._user32 = ctypes.windll.user32
        self._hwnd = hwnd
        self._focus_mode = focus_mode

    # ------------------------------------------------------------------
    # Public forwarding API
    # ------------------------------------------------------------------

    def forward_mouse_click(self, x: int, y: int, button: str = "left") -> bool:
        if not self._ensure_target():
            return False
        try:
            sx, sy = self._win32gui.ClientToScreen(self._hwnd, (int(x), int(y)))
            ax, ay = self._to_absolute(sx, sy)
            base = MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
            if button == "right":
                down, up = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
            else:
                down, up = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP

            restore = self._maybe_focus()
            self._send_mouse(ax, ay, MOUSEEVENTF_MOVE | base)
            self._send_mouse(ax, ay, down | base)
            self._send_mouse(ax, ay, up | base)
            self._restore_focus(restore)
            return True
        except Exception as exc:  # noqa: BLE001
            _log.error("forward_mouse_click failed: %s", exc)
            return False

    def forward_key(self, key: str, pressed: bool = True) -> bool:
        vk = _VK_MAP.get(key.strip().lower())
        if vk is None:
            _log.warning("Unsupported key for forwarding: %r", key)
            return False
        if not self._ensure_target():
            return False
        try:
            restore = self._maybe_focus()
            self._send_key(vk, keyup=not pressed)
            self._restore_focus(restore)
            return True
        except Exception as exc:  # noqa: BLE001
            _log.error("forward_key failed: %s", exc)
            return False

    def forward_mouse_wheel(self, delta: int) -> bool:
        if not self._ensure_target():
            return False
        try:
            restore = self._maybe_focus()
            self._send_mouse(0, 0, MOUSEEVENTF_WHEEL, mouse_data=int(delta))
            self._restore_focus(restore)
            return True
        except Exception as exc:  # noqa: BLE001
            _log.error("forward_mouse_wheel failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def client_size(self) -> Optional[tuple[int, int]]:
        if self._hwnd is None:
            return None
        try:
            left, top, right, bottom = self._win32gui.GetClientRect(self._hwnd)
            w, h = right - left, bottom - top
            if w <= 0 or h <= 0:
                return None
            return (w, h)
        except Exception:  # noqa: BLE001
            return None

    def target_info(self) -> tuple[Optional[int], str]:
        if self._hwnd is None:
            return (None, "")
        try:
            return (self._hwnd, self._win32gui.GetWindowText(self._hwnd))
        except Exception:  # noqa: BLE001
            return (self._hwnd, "")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_target(self) -> bool:
        if self._hwnd is None:
            _log.error("No target hwnd configured for input forwarding.")
            return False
        try:
            if not self._win32gui.IsWindow(self._hwnd):
                _log.error("Target window %s no longer exists.", self._hwnd)
                return False
        except Exception as exc:  # noqa: BLE001
            _log.error("Target window check failed: %s", exc)
            return False
        return True

    def _maybe_focus(self) -> Optional[int]:
        """Bring the target to foreground; return the prior foreground hwnd."""
        if self._focus_mode != FOCUS_THEN_SEND:
            return None
        try:
            prior = self._win32gui.GetForegroundWindow()
            self._win32gui.SetForegroundWindow(self._hwnd)
            return prior
        except Exception as exc:  # noqa: BLE001
            _log.debug("Focus target failed: %s", exc)
            return None

    def _restore_focus(self, prior: Optional[int]) -> None:
        if prior is None or self._focus_mode != FOCUS_THEN_SEND:
            return
        try:
            self._win32gui.SetForegroundWindow(prior)
        except Exception as exc:  # noqa: BLE001
            _log.debug("Restore focus failed: %s", exc)

    def _to_absolute(self, sx: int, sy: int) -> tuple[int, int]:
        """Normalize a screen point to 0..65535 over the virtual desktop."""
        gsm = self._user32.GetSystemMetrics
        vx = gsm(SM_XVIRTUALSCREEN)
        vy = gsm(SM_YVIRTUALSCREEN)
        vw = gsm(SM_CXVIRTUALSCREEN)
        vh = gsm(SM_CYVIRTUALSCREEN)
        ax = int((sx - vx) * 65535 / max(vw - 1, 1))
        ay = int((sy - vy) * 65535 / max(vh - 1, 1))
        return ax, ay

    def _send_mouse(self, dx: int, dy: int, flags: int, mouse_data: int = 0) -> None:
        inp = _INPUT(type=INPUT_MOUSE)
        inp.union.mi = _MOUSEINPUT(
            dx=dx, dy=dy, mouseData=mouse_data & 0xFFFFFFFF,
            dwFlags=flags, time=0, dwExtraInfo=0,
        )
        self._send(inp)

    def _send_key(self, vk: int, keyup: bool) -> None:
        flags = KEYEVENTF_KEYUP if keyup else 0
        inp = _INPUT(type=INPUT_KEYBOARD)
        inp.union.ki = _KEYBDINPUT(
            wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=0
        )
        self._send(inp)

    def _send(self, inp: _INPUT) -> None:
        n = self._user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))
        if n != 1:
            err = ctypes.get_last_error()
            raise OSError(f"SendInput rejected (returned {n}, last_error={err})")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_input_forwarder(
    focus_mode: str,
    hwnd: Optional[int],
    *,
    forward_input: bool = True,
) -> BaseInputForwarder:
    """Return a forwarder appropriate for the platform and configuration.

    Falls back to :class:`NullInputForwarder` (keeping the mirror usable) when
    forwarding is disabled, the platform is unsupported, or ``pywin32`` is
    missing — in the last case an install hint is printed.
    """
    if not forward_input or focus_mode == FOCUS_DISABLED:
        return NullInputForwarder("disabled")

    if sys.platform != "win32":
        _log.warning(
            "Input forwarding is unsupported on %s; mirror display only.",
            sys.platform,
        )
        return NullInputForwarder("unsupported platform")

    try:
        return WindowsInputForwarder(hwnd, focus_mode)
    except OptionalDependencyMissing as exc:
        print(f"[yaku] {exc}")
        _log.warning("Input forwarding disabled: %s", exc)
        return NullInputForwarder(str(exc))
