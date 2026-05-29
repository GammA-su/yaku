"""Console-based window picker with lazy pywin32 imports."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Optional


@dataclass
class WindowInfo:
    """Snapshot of a visible top-level window."""

    hwnd: int
    title: str
    rect: tuple[int, int, int, int]  # (left, top, right, bottom) — Windows RECT
    pid: int | None


# ---------------------------------------------------------------------------
# Platform-aware enumeration
# ---------------------------------------------------------------------------

def list_visible_windows() -> list[WindowInfo]:
    """Return all visible, titled, reasonably-sized top-level windows.

    On non-Windows platforms or when ``pywin32`` is not installed the list is
    empty — the caller must handle that gracefully.
    """
    try:
        import win32gui
        import win32process  # noqa: F401 (used inside callback)
    except ImportError:
        return []

    import win32process as _wp  # local alias for use in closure

    windows: list[WindowInfo] = []

    def _cb(hwnd: int, _: None) -> bool:
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return True
        try:
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        except Exception:
            return True
        if (right - left) < 100 or (bottom - top) < 50:
            return True
        try:
            _, pid = _wp.GetWindowThreadProcessId(hwnd)
        except Exception:
            pid = None
        windows.append(
            WindowInfo(hwnd=hwnd, title=title, rect=(left, top, right, bottom), pid=pid)
        )
        return True

    win32gui.EnumWindows(_cb, None)
    return windows


def get_window_info(hwnd: int) -> Optional[WindowInfo]:
    """Return a :class:`WindowInfo` for *hwnd*, or ``None`` if unavailable.

    Used for runtime diagnostics (showing the current target title/rect).
    Returns ``None`` on non-Windows platforms, when ``pywin32`` is missing, or
    when the window no longer exists.
    """
    if hwnd is None:
        return None
    try:
        import win32gui
        import win32process as _wp
    except ImportError:
        return None

    try:
        if not win32gui.IsWindow(hwnd):
            return None
        title = win32gui.GetWindowText(hwnd)
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    except Exception:
        return None

    try:
        _, pid = _wp.GetWindowThreadProcessId(hwnd)
    except Exception:
        pid = None

    return WindowInfo(hwnd=hwnd, title=title, rect=(left, top, right, bottom), pid=pid)


# ---------------------------------------------------------------------------
# Console interaction
# ---------------------------------------------------------------------------

def pick_window_cli() -> Optional[WindowInfo]:
    """Print a numbered list of visible windows and block for user input.

    Returns the selected :class:`WindowInfo` or ``None`` when the user cancels
    or when no windows are available.

    Gracefully handles:
    - ``pywin32`` not installed (prints install command).
    - Non-Windows platform (prints unsupported message).
    - Non-interactive stdin (prints instructions and returns ``None``).
    """
    windows = list_visible_windows()

    if not windows:
        print(
            "No windows found.\n"
            "  On Windows, install pywin32: uv add pywin32\n"
            "  On other platforms, window picking is not supported."
        )
        return None

    print("Visible windows:")
    print(f"  {'#':>3}  {'HWND':>10}  {'Size':>11}  Title")
    print("  " + "-" * 70)
    for i, w in enumerate(windows, 1):
        left, top, right, bottom = w.rect
        size_str = f"{right - left}×{bottom - top}"
        title_trunc = w.title[:55] + "…" if len(w.title) > 55 else w.title
        print(f"  {i:>3}  {w.hwnd:>10}  {size_str:>11}  {title_trunc}")

    print()

    if not sys.stdin.isatty():
        print("(stdin is not a terminal — interactive picking not available)")
        print("Pass the window title substring via --config or edit configs/default.yaml.")
        return None

    print("Enter number to select (0 to cancel): ", end="", flush=True)
    try:
        raw = sys.stdin.readline().strip()
        n = int(raw)
    except (ValueError, EOFError):
        print("Cancelled.")
        return None

    if n == 0:
        print("Cancelled.")
        return None
    if not (1 <= n <= len(windows)):
        print(f"Invalid selection: {n}. Expected 1–{len(windows)}.")
        return None

    return windows[n - 1]
