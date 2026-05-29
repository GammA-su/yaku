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


# ---------------------------------------------------------------------------
# GUI Dialog implementation
# ---------------------------------------------------------------------------

class WindowPickerDialog:
    """Helper to dynamically create the dialog subclass with PyQt6 imports."""

    def __new__(cls, parent=None):
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import (
            QDialog,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QListWidget,
            QListWidgetItem,
            QMessageBox,
            QPushButton,
            QVBoxLayout,
        )

        class Dialog(QDialog):
            def __init__(self, parent_widget=None) -> None:
                super().__init__(parent_widget)
                self.setWindowTitle("Select VN Window")
                self.resize(580, 420)
                self.selected_window: Optional[WindowInfo] = None

                layout = QVBoxLayout(self)
                layout.setSpacing(12)
                layout.setContentsMargins(16, 16, 16, 16)

                # Search Header
                search_layout = QHBoxLayout()
                search_layout.setSpacing(8)
                search_label = QLabel("Search:")
                search_label.setStyleSheet("font-weight: bold;")
                self.search_input = QLineEdit()
                self.search_input.setPlaceholderText("Type to filter windows by title...")
                self.search_input.textChanged.connect(self._filter_windows)
                search_layout.addWidget(search_label)
                search_layout.addWidget(self.search_input)
                layout.addLayout(search_layout)

                # List View
                self.list_widget = QListWidget()
                self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
                layout.addWidget(self.list_widget)

                # Info status
                self.info_label = QLabel("Select the target game window to capture.")
                self.info_label.setStyleSheet("color: #94a3b8; font-size: 11px;")
                layout.addWidget(self.info_label)

                # Action row
                btn_layout = QHBoxLayout()
                btn_layout.setSpacing(8)
                self.btn_refresh = QPushButton("Refresh")
                self.btn_refresh.clicked.connect(self._refresh_list)
                
                self.btn_cancel = QPushButton("Cancel")
                self.btn_cancel.clicked.connect(self.reject)

                self.btn_select = QPushButton("Select Window")
                self.btn_select.setObjectName("btn_primary")
                self.btn_select.clicked.connect(self._on_select)

                btn_layout.addWidget(self.btn_refresh)
                btn_layout.addStretch()
                btn_layout.addWidget(self.btn_cancel)
                btn_layout.addWidget(self.btn_select)
                layout.addLayout(btn_layout)

                self.windows_list: list[WindowInfo] = []
                self._refresh_list()

            def _refresh_list(self) -> None:
                self.list_widget.clear()
                self.windows_list = list_visible_windows()
                
                if not self.windows_list:
                    item = QListWidgetItem("No visible windows found. Is the game running?")
                    item.setFlags(Qt.ItemFlag.NoItemFlags)
                    self.list_widget.addItem(item)
                    self.btn_select.setEnabled(False)
                    return

                self.btn_select.setEnabled(True)
                for w in self.windows_list:
                    left, top, right, bottom = w.rect
                    w_width = right - left
                    w_height = bottom - top
                    size_str = f"{w_width}×{w_height}"
                    
                    # Nice formatted text line for each item
                    item_text = f"{w.title}   [{size_str} | HWND: {w.hwnd}]"
                    item = QListWidgetItem(item_text)
                    item.setData(Qt.ItemDataRole.UserRole, w)
                    self.list_widget.addItem(item)
                
                # Apply filter in case text was typed before refresh
                self._filter_windows(self.search_input.text())

            def _filter_windows(self, text: str) -> None:
                text = text.lower().strip()
                for i in range(self.list_widget.count()):
                    item = self.list_widget.item(i)
                    # Don't filter out the 'no windows' message item
                    if item.flags() == Qt.ItemFlag.NoItemFlags:
                        continue
                    item.setHidden(text not in item.text().lower())

            def _on_select(self) -> None:
                current_item = self.list_widget.currentItem()
                if current_item is not None and current_item.flags() != Qt.ItemFlag.NoItemFlags:
                    self.selected_window = current_item.data(Qt.ItemDataRole.UserRole)
                    self.accept()
                else:
                    QMessageBox.warning(self, "Selection Required", "Please select a window from the list.")

            def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
                if item.flags() != Qt.ItemFlag.NoItemFlags:
                    self.selected_window = item.data(Qt.ItemDataRole.UserRole)
                    self.accept()

        return Dialog(parent)


def pick_window_gui(parent=None) -> Optional[WindowInfo]:
    """Show the graphical window picker dialog. Returns the selected WindowInfo or None."""
    from PyQt6.QtWidgets import QApplication
    if QApplication.instance() is None:
        return None
    dialog = WindowPickerDialog(parent)
    if dialog.exec():
        return dialog.selected_window
    return None

