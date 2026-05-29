"""QApplication singleton and GUI launcher helpers."""
from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QApplication

_app: "QApplication | None" = None


class GuiDependencyError(RuntimeError):
    """Raised when the GUI dependency stack is unavailable."""


def _load_qapplication():
    try:
        from PyQt6.QtWidgets import QApplication
    except ModuleNotFoundError as exc:
        if exc.name == "PyQt6" or (exc.name and exc.name.startswith("PyQt6.")):
            raise GuiDependencyError(
                "PyQt6 is required for the Yaku GUI."
            ) from exc
        raise
    return QApplication


def _print_pyqt6_error() -> None:
    print("PyQt6 is required for the Yaku GUI.", file=sys.stderr)
    print("Install it with:", file=sys.stderr)
    print("  uv add PyQt6", file=sys.stderr)


def ensure_qapplication() -> "QApplication":
    """Return the shared QApplication, creating it on first call."""
    global _app
    QApplication = _load_qapplication()
    existing = QApplication.instance()
    if existing is not None:
        _app = existing  # type: ignore[assignment]
    if _app is None:
        _app = QApplication(sys.argv)
    return _app


def get_app() -> "QApplication":
    """Backward-compatible alias for older UI code."""
    return ensure_qapplication()


def launch_main_gui(profile: str | None = None, config_path: str | None = None) -> int:
    try:
        app = ensure_qapplication()
    except GuiDependencyError:
        _print_pyqt6_error()
        return 1

    from yaku.ui.main_window import MainWindow

    win = MainWindow(profile=profile, config_path=config_path)
    win.show()
    return app.exec()


def launch_setup_wizard_gui(profile: str | None = None, config_path: str | None = None) -> int:
    try:
        app = ensure_qapplication()
    except GuiDependencyError:
        _print_pyqt6_error()
        return 1

    from yaku.ui.setup_wizard import SetupWizard

    wizard = SetupWizard(profile=profile, config_path=config_path)
    wizard.show()
    return app.exec()
