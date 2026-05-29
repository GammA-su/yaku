"""Interactive first-run setup wizard.

A console-driven flow that builds a per-game profile: choose a name, pick the
VN window, draw the OCR region, choose mode/translator, optionally draw the V2
replacement region, save, and print the exact run command.

The interactive bits reuse the existing Qt window picker / region selector.
The flow is dependency-injectable (``input_fn``/``print_fn``) so the prompting
logic stays testable without a real terminal.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from yaku.core.config import (
    save_config,
    update_ocr_region,
    update_replacement_region,
    update_window_selection,
)
from yaku.core.logging import get_logger
from yaku.core.profiles import profile_path, resolve_profile, sanitize_profile_name

_log = get_logger("setup_wizard")


def _prompt_choice(
    prompt: str,
    choices: list[str],
    default: str,
    input_fn: Callable[[str], str],
    print_fn: Callable[[str], None],
) -> str:
    choice_str = "/".join(c + " (default)" if c == default else c for c in choices)
    while True:
        raw = input_fn(f"{prompt} [{choice_str}]: ").strip().lower()
        if not raw:
            return default
        if raw in choices:
            return raw
        print_fn(f"  Please enter one of: {', '.join(choices)}")


def run_setup_wizard(
    *,
    profiles_dir: Path | str = "profiles",
    profile: str | None = None,
    config_path: str | None = None,
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[[str], None] = print,
    pick_window: bool = True,
    select_regions: bool = True,
) -> Optional[Path]:
    """Run the wizard and return the saved profile path (or ``None`` on abort).

    *pick_window* / *select_regions* can be disabled (used by tests) to skip the
    Qt-driven interactive steps.
    """
    print_fn("=" * 60)
    print_fn("Yaku setup wizard")
    print_fn("=" * 60)

    # 1. profile name -------------------------------------------------------
    raw_name = profile or input_fn("1) Profile name (e.g. my-vn): ").strip()
    if not raw_name:
        print_fn("No profile name given. Aborting.")
        return None
    try:
        name = sanitize_profile_name(raw_name)
    except ValueError:
        print_fn(f"Invalid profile name: {raw_name!r}. Aborting.")
        return None
    if name != raw_name:
        print_fn(f"   Using sanitized name: {name}")

    resolve_kwargs = {"profiles_dir": profiles_dir}
    if config_path is not None:
        resolve_kwargs["base_config_path"] = config_path
    config, path = resolve_profile(name, **resolve_kwargs)

    # Qt is only needed for the interactive picking/region steps.
    app = None
    if pick_window or select_regions:
        try:
            from yaku.ui.app import get_app
            app = get_app()
        except Exception as exc:  # noqa: BLE001
            print_fn(f"   (GUI unavailable: {exc}; skipping interactive steps)")
            pick_window = False
            select_regions = False

    # 2. pick VN window -----------------------------------------------------
    if pick_window:
        print_fn("\n2) Pick the VN window:")
        try:
            from yaku.ui.window_picker import pick_window_cli
            win = pick_window_cli()
            if win is not None:
                update_window_selection(config, win.hwnd, win.title)
                print_fn(f"   Window: {win.title!r} (hwnd={win.hwnd})")
            else:
                print_fn("   No window selected (you can set it later with --pick-window).")
        except Exception as exc:  # noqa: BLE001
            print_fn(f"   Window picking failed: {exc}")
    else:
        print_fn("\n2) Skipping window pick.")

    # 3. OCR region ---------------------------------------------------------
    if select_regions:
        print_fn("\n3) Draw the OCR capture region (drag, Enter to confirm)...")
        rect = _select_region(print_fn)
        if rect is not None:
            update_ocr_region(config, rect)
            print_fn(f"   OCR region: x={rect.x} y={rect.y} w={rect.w} h={rect.h}")
    else:
        print_fn("\n3) Skipping OCR region.")

    # 4. mode ---------------------------------------------------------------
    mode = _prompt_choice(
        "\n4) Mode", ["v1-overlay", "v2-mirror"], "v1-overlay", input_fn, print_fn
    )
    config.app.mode = mode  # type: ignore[assignment]

    # 5. translator ---------------------------------------------------------
    translator = _prompt_choice(
        "5) Translator", ["deepl", "llama-cpp"], "llama-cpp", input_fn, print_fn
    )
    config.translator.backend = "llama_cpp" if translator == "llama-cpp" else "deepl"

    # 6. replacement region (v2 only) --------------------------------------
    if mode == "v2-mirror" and select_regions:
        print_fn("\n6) Draw the V2 text replacement region (drag, Enter to confirm)...")
        rect = _select_region(print_fn)
        if rect is not None and app is not None:
            geom = app.primaryScreen().geometry()
            from yaku.core.image_utils import rect_to_normalized
            norm = rect_to_normalized(rect, geom.width(), geom.height())
            update_replacement_region(config, norm)
            print_fn(
                f"   Replacement region: "
                f"x={norm.x_ratio:.3f} y={norm.y_ratio:.3f} "
                f"w={norm.w_ratio:.3f} h={norm.h_ratio:.3f}"
            )

    # 7. save ---------------------------------------------------------------
    save_config(config, path)
    print_fn(f"\n7) Profile saved: {path}")

    # 8. run command --------------------------------------------------------
    cmd = f"uv run yaku --profile {name} --mode {mode} --translator {translator}"
    if mode == "v2-mirror":
        cmd += f" --render-mode {config.v2_mirror.render_mode}"
    cmd += " --run"
    print_fn("\n8) Start Yaku with:")
    print_fn(f"   {cmd}")
    return path


def _select_region(print_fn: Callable[[str], None]):
    try:
        from yaku.ui.region_selector import RegionSelector
        return RegionSelector().run_blocking()
    except Exception as exc:  # noqa: BLE001
        print_fn(f"   Region selection failed: {exc}")
        return None


class SetupWizard:
    """Lazy PyQt6 setup wizard factory.

    The module also contains the terminal setup flow, so PyQt6 imports stay
    inside construction to keep ``--setup --cli`` usable without GUI imports.
    """

    def __new__(cls, profile: str | None = None, config_path: str | None = None):
        return _create_setup_wizard(profile=profile, config_path=config_path)


def _create_setup_wizard(profile: str | None = None, config_path: str | None = None):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import (
        QComboBox,
        QFormLayout,
        QLabel,
        QLineEdit,
        QMessageBox,
        QVBoxLayout,
        QWizard,
        QWizardPage,
    )

    from yaku.core.config import YakuConfig, load_config, save_config

    class GuiSetupWizard(QWizard):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("Yaku Setup Wizard")
            self.resize(620, 430)
            self._apply_theme()

            self.profile_input = QLineEdit(profile or "")
            self.profile_input.setPlaceholderText("default")
            self.mode_combo = QComboBox()
            self.mode_combo.addItems(["v1-overlay", "v2-mirror"])
            self.translator_combo = QComboBox()
            self.translator_combo.addItems(["llama-cpp", "deepl"])
            self.target_lang_input = QLineEdit("en")

            self.addPage(self._welcome_page())
            self.addPage(self._mode_page())
            self.addPage(self._translator_page())
            self.addPage(self._instructions_page())
            self.addPage(self._finish_page())

        def _apply_theme(self) -> None:
            self.setStyleSheet(
                """
                QWizard {
                    background: #f8fafc;
                    color: #111827;
                }
                QWizardPage {
                    background: #f8fafc;
                    color: #111827;
                }
                QLabel {
                    color: #111827;
                    font-size: 13px;
                }
                QWizardPage QLabel#qt_wizard_title_label {
                    color: #0f172a;
                    font-size: 20px;
                    font-weight: 600;
                }
                QLineEdit,
                QComboBox {
                    min-height: 32px;
                    padding: 4px 10px;
                    border: 1px solid #94a3b8;
                    border-radius: 4px;
                    background: #ffffff;
                    color: #111827;
                    selection-background-color: #2563eb;
                    selection-color: #ffffff;
                }
                QLineEdit:focus,
                QComboBox:focus {
                    border-color: #2563eb;
                }
                QComboBox::drop-down {
                    width: 28px;
                    border-left: 1px solid #cbd5e1;
                    background: #f1f5f9;
                }
                QComboBox QAbstractItemView {
                    background: #ffffff;
                    color: #111827;
                    selection-background-color: #2563eb;
                    selection-color: #ffffff;
                    border: 1px solid #94a3b8;
                }
                QPushButton {
                    min-width: 84px;
                    min-height: 28px;
                    padding: 4px 14px;
                    border: 1px solid #94a3b8;
                    border-radius: 4px;
                    background: #ffffff;
                    color: #111827;
                }
                QPushButton:hover {
                    background: #f1f5f9;
                    border-color: #64748b;
                }
                QPushButton:default {
                    background: #2563eb;
                    border-color: #1d4ed8;
                    color: #ffffff;
                }
                QPushButton:disabled {
                    background: #e5e7eb;
                    border-color: #cbd5e1;
                    color: #64748b;
                }
                """
            )

        def _welcome_page(self):
            page = QWizardPage()
            page.setTitle("Welcome")
            layout = QFormLayout(page)
            intro = QLabel("Create or update a Yaku profile.")
            intro.setWordWrap(True)
            layout.addRow(intro)
            layout.addRow("Profile", self.profile_input)
            return page

        def _mode_page(self):
            page = QWizardPage()
            page.setTitle("Mode")
            layout = QFormLayout(page)
            layout.addRow("Mode", self.mode_combo)
            return page

        def _translator_page(self):
            page = QWizardPage()
            page.setTitle("Translator")
            layout = QFormLayout(page)
            layout.addRow("Translator", self.translator_combo)
            layout.addRow("Target language", self.target_lang_input)
            return page

        def _instructions_page(self):
            page = QWizardPage()
            page.setTitle("Window and OCR")
            layout = QVBoxLayout(page)
            text = QLabel(
                "After setup, use Pick Window and Draw OCR Rectangle from the "
                "launcher to bind the visual novel window and capture area."
            )
            text.setWordWrap(True)
            text.setAlignment(Qt.AlignmentFlag.AlignTop)
            layout.addWidget(text)
            return page

        def _finish_page(self):
            page = QWizardPage()
            page.setTitle("Finish")
            layout = QVBoxLayout(page)
            text = QLabel("Click Finish to save the selected profile settings.")
            text.setWordWrap(True)
            layout.addWidget(text)
            return page

        def accept(self) -> None:
            try:
                saved_path = self._save_profile()
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, "Yaku setup", f"Could not save profile:\n{exc}")
                return
            QMessageBox.information(self, "Yaku setup", f"Profile saved:\n{saved_path}")
            super().accept()

        def _save_profile(self) -> Path:
            raw_profile = self.profile_input.text().strip() or profile

            if raw_profile:
                config, path = resolve_profile(raw_profile)
            elif config_path:
                path = Path(config_path)
                config = load_config(path) if path.exists() else YakuConfig()
            else:
                config, path = resolve_profile("default")

            config.app.mode = self.mode_combo.currentText()  # type: ignore[assignment]
            config.translator.backend = (
                "llama_cpp"
                if self.translator_combo.currentText() == "llama-cpp"
                else "deepl"
            )
            config.app.target_lang = self.target_lang_input.text().strip() or "en"
            save_config(config, path)
            return path

    return GuiSetupWizard()


def setup_wizard_command(
    profiles_dir: Path | str = "profiles",
    profile: str | None = None,
    config_path: str | None = None,
) -> int:
    """Entry point for ``uv run yaku --setup``.  Returns a process exit code."""
    try:
        path = run_setup_wizard(
            profiles_dir=profiles_dir,
            profile=profile,
            config_path=config_path,
        )
    except (KeyboardInterrupt, EOFError):
        print("\nSetup cancelled.")
        return 1
    return 0 if path is not None else 1


__all__ = ["SetupWizard", "run_setup_wizard", "setup_wizard_command", "profile_path"]
