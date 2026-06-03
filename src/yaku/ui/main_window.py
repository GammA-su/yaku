"""Main GUI launcher window."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class MainWindow(QMainWindow):
    """Launcher dashboard for Yaku."""

    def __init__(self, profile: str | None = None, config_path: str | None = None) -> None:
        super().__init__()
        self.profile = profile
        self.config_path = config_path
        self._run_process: subprocess.Popen | None = None

        self.setWindowTitle("Yaku Launcher")
        self.resize(680, 480)

        # Main Root Widget
        root = QWidget(self)
        self.setCentralWidget(root)

        main_layout = QVBoxLayout(root)
        main_layout.setSpacing(16)
        main_layout.setContentsMargins(24, 24, 24, 24)

        # 1. Header Row
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)
        self.title_label = QLabel("YAKU")
        self.title_label.setObjectName("header_title")
        self.subtitle_label = QLabel("AI Visual Novel Translator")
        self.subtitle_label.setObjectName("header_subtitle")
        title_vbox.addWidget(self.title_label)
        title_vbox.addWidget(self.subtitle_label)
        header_layout.addLayout(title_vbox)
        
        header_layout.addStretch()
        
        # Profile selector dropdown instead of badge
        self.profile_combo = QComboBox()
        self.profile_combo.setObjectName("profile_combo")
        self.profile_combo.setMinimumWidth(160)
        self.profile_combo.setStyleSheet(
            "QComboBox#profile_combo {"
            "color: #6366f1; background-color: #1e1b4b; "
            "border: 1px solid #312e81; border-radius: 12px; "
            "padding: 4px 12px 4px 12px; font-weight: bold; font-size: 11px;"
            "}"
            "QComboBox#profile_combo::drop-down {"
            "subcontrol-origin: padding; subcontrol-position: top right;"
            "width: 20px; border-left: none; background: transparent;"
            "}"
            "QComboBox#profile_combo::down-arrow {"
            "image: none; border: solid #6366f1; border-width: 0 2px 2px 0;"
            "display: inline-block; padding: 2px; width: 4px; height: 4px;"
            "transform: rotate(45deg); margin-right: 8px;"
            "}"
            "QComboBox#profile_combo QAbstractItemView {"
            "background-color: #1e1b4b; border: 1px solid #312e81;"
            "selection-background-color: #4f46e5; selection-color: #ffffff;"
            "color: #6366f1;"
            "}"
        )
        header_layout.addWidget(self.profile_combo)

        # Settings button next to profile selector
        self.btn_settings = QPushButton("Settings")
        self.btn_settings.setObjectName("btn_settings")
        self.btn_settings.setMinimumWidth(90)
        self.btn_settings.setStyleSheet(
            "QPushButton#btn_settings {"
            "color: #f8fafc; background-color: #1e293b; "
            "border: 1px solid #334155; border-radius: 12px; "
            "padding: 4px 12px; font-weight: bold; font-size: 11px;"
            "min-height: 18px;"
            "}"
            "QPushButton#btn_settings:hover {"
            "background-color: #334155; "
            "border-color: #6366f1;"
            "}"
        )
        self.btn_settings.clicked.connect(self._open_settings)
        header_layout.addWidget(self.btn_settings)

        main_layout.addWidget(header_widget)

        # 2. Columns Row (Dashboard controls + Settings)
        cols_layout = QHBoxLayout()
        cols_layout.setSpacing(16)

        # Left Column: Controller / Status
        control_group = QGroupBox("Status & Control")
        control_vbox = QVBoxLayout(control_group)
        control_vbox.setSpacing(12)
        control_vbox.setContentsMargins(16, 20, 16, 16)

        status_hbox = QHBoxLayout()
        status_hbox.addWidget(QLabel("Engine Status:"))
        self.status_badge = QLabel("STOPPED")
        self.status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_hbox.addWidget(self.status_badge)
        control_vbox.addLayout(status_hbox)

        control_vbox.addStretch()

        self.btn_start = QPushButton("Start Translation")
        self.btn_start.setObjectName("btn_primary")
        self.btn_start.clicked.connect(self._start)
        self.btn_start.setMinimumHeight(36)
        control_vbox.addWidget(self.btn_start)

        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setObjectName("btn_danger")
        self.btn_stop.clicked.connect(self._stop)
        self.btn_stop.setMinimumHeight(36)
        control_vbox.addWidget(self.btn_stop)

        cols_layout.addWidget(control_group, 4)

        # Right Column: Quick Config
        config_group = QGroupBox("Quick Configuration")
        form = QFormLayout(config_group)
        form.setSpacing(12)
        form.setContentsMargins(16, 20, 16, 16)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["v1-overlay", "v2-mirror"])
        form.addRow("Operation Mode", self.mode_combo)

        self.translator_combo = QComboBox()
        self.translator_combo.addItems(["llama-cpp", "deepl"])
        form.addRow("Translation Backend", self.translator_combo)

        self.target_lang_input = QLineEdit("en")
        form.addRow("Target Language", self.target_lang_input)

        cols_layout.addWidget(config_group, 6)
        main_layout.addLayout(cols_layout)

        # 3. Utilities Grid Row
        utils_group = QGroupBox("Utilities & Calibration")
        utils_grid = QGridLayout(utils_group)
        utils_grid.setSpacing(12)
        utils_grid.setContentsMargins(16, 20, 16, 16)

        self.btn_wizard = QPushButton("Setup Wizard")
        self.btn_wizard.clicked.connect(self._open_setup_wizard)
        utils_grid.addWidget(self.btn_wizard, 0, 0)

        self.btn_picker = QPushButton("Pick VN Window")
        self.btn_picker.clicked.connect(self._pick_window)
        utils_grid.addWidget(self.btn_picker, 0, 1)

        self.btn_ocr = QPushButton("Draw OCR Area")
        self.btn_ocr.clicked.connect(self._select_ocr_region)
        utils_grid.addWidget(self.btn_ocr, 0, 2)

        self.btn_replacement = QPushButton("Draw Replacement Area")
        self.btn_replacement.clicked.connect(self._select_replacement_region)
        utils_grid.addWidget(self.btn_replacement, 1, 0)

        self.btn_health = QPushButton("Diagnostics")
        self.btn_health.clicked.connect(self._health_check)
        utils_grid.addWidget(self.btn_health, 1, 1)

        self.btn_logs = QPushButton("System Logs")
        self.btn_logs.clicked.connect(self._show_logs)
        utils_grid.addWidget(self.btn_logs, 1, 2)

        main_layout.addWidget(utils_group)

        # QTimer for monitoring the background process
        self.process_timer = QTimer(self)
        self.process_timer.setInterval(500)
        self.process_timer.timeout.connect(self._monitor_process)

        # Setup profile combo items and connect slot
        self._refresh_profiles()
        self.profile_combo.currentTextChanged.connect(self._on_profile_changed)

        # Load configuration values into inputs
        self._load_config_into_ui()

        # Connect change signals for quick config inputs
        self.mode_combo.currentTextChanged.connect(self._save_quick_config)
        self.translator_combo.currentTextChanged.connect(self._save_quick_config)
        self.target_lang_input.editingFinished.connect(self._save_quick_config)

        self._update_ui_state()

    def _refresh_profiles(self) -> None:
        from yaku.core.profiles import list_profiles

        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()

        profiles = list_profiles()
        if "default" not in profiles:
            profiles.insert(0, "default")

        self.profile_combo.addItems(profiles)

        active = self.profile or "default"
        index = self.profile_combo.findText(active)
        if index >= 0:
            self.profile_combo.setCurrentIndex(index)
            self.profile = active
        else:
            self.profile_combo.setCurrentIndex(0)
            self.profile = self.profile_combo.currentText()

        self.profile_combo.blockSignals(False)

    def _on_profile_changed(self, text: str) -> None:
        if not text:
            return
        self.profile = text
        self._load_config_into_ui()

    def _load_config_into_ui(self) -> None:
        from yaku.core.config import load_config, YakuConfig
        from yaku.core.profiles import resolve_profile
        
        try:
            if self.profile:
                config, _ = resolve_profile(self.profile)
            elif self.config_path:
                path = Path(self.config_path)
                config = load_config(path) if path.exists() else YakuConfig()
            else:
                config, _ = resolve_profile("default")
                
            # Block signals so we don't save back while loading
            self.mode_combo.blockSignals(True)
            self.translator_combo.blockSignals(True)
            self.target_lang_input.blockSignals(True)

            # Set mode combobox
            mode = config.app.mode or "v1-overlay"
            index = self.mode_combo.findText(mode)
            if index >= 0:
                self.mode_combo.setCurrentIndex(index)
                
            # Set translator combobox
            translator = config.translator.backend or "llama_cpp"
            combo_translator = "llama-cpp" if translator == "llama_cpp" else "deepl"
            index = self.translator_combo.findText(combo_translator)
            if index >= 0:
                self.translator_combo.setCurrentIndex(index)
                
            # Set target language
            self.target_lang_input.setText(config.app.target_lang or "en")
        except Exception as exc:  # noqa: BLE001
            print(f"[yaku] Failed to load config into UI: {exc}")
        finally:
            self.mode_combo.blockSignals(False)
            self.translator_combo.blockSignals(False)
            self.target_lang_input.blockSignals(False)

    def _save_quick_config(self) -> None:
        from yaku.core.config import save_config
        from yaku.core.profiles import resolve_profile
        try:
            config, config_path = resolve_profile(self.profile or "default")
            config.app.mode = self.mode_combo.currentText()  # type: ignore[assignment]
            backend_val = self.translator_combo.currentText()
            config.translator.backend = "llama_cpp" if backend_val == "llama-cpp" else "deepl"  # type: ignore[assignment]
            config.app.target_lang = self.target_lang_input.text().strip() or "en"
            save_config(config, config_path)
        except Exception as exc:  # noqa: BLE001
            print(f"[yaku] Failed to save quick config: {exc}")

    def _open_settings(self) -> None:
        from yaku.core.profiles import resolve_profile
        from yaku.ui.settings_panel import SettingsPanel
        
        config, config_path = resolve_profile(self.profile or "default")
        dialog = SettingsPanel(config, config_path, self, on_saved=self._load_config_into_ui)
        dialog.exec()

    def _update_ui_state(self) -> None:
        is_running = self._run_process is not None and self._run_process.poll() is None
        
        if is_running:
            self.status_badge.setText("RUNNING")
            self.status_badge.setStyleSheet(
                "color: #10b981; background-color: #064e3b; "
                "border: 1px solid #10b98144; border-radius: 4px; "
                "font-weight: bold; padding: 4px 10px; font-size: 11px;"
            )
            self.btn_start.setEnabled(False)
            self.btn_stop.setEnabled(True)
            self.mode_combo.setEnabled(False)
            self.translator_combo.setEnabled(False)
            self.target_lang_input.setEnabled(False)
        else:
            self.status_badge.setText("STOPPED")
            self.status_badge.setStyleSheet(
                "color: #94a3b8; background-color: #1e293b; "
                "border: 1px solid #334155; border-radius: 4px; "
                "font-weight: bold; padding: 4px 10px; font-size: 11px;"
            )
            self.btn_start.setEnabled(True)
            self.btn_stop.setEnabled(False)
            self.mode_combo.setEnabled(True)
            self.translator_combo.setEnabled(True)
            self.target_lang_input.setEnabled(True)

    def _monitor_process(self) -> None:
        if self._run_process is not None:
            if self._run_process.poll() is not None:
                self._run_process = None
                self.process_timer.stop()
                self._update_ui_state()

    def _base_command(self) -> list[str]:
        if getattr(sys, "frozen", False):
            cmd = [sys.executable]
        else:
            cmd = [sys.executable, "-m", "yaku.main"]
        if self.profile:
            cmd.extend(["--profile", self.profile])
        if self.config_path:
            cmd.extend(["--config", self.config_path])
        return cmd

    def _run_command(self, args: list[str]) -> subprocess.Popen | None:
        try:
            return subprocess.Popen(self._base_command() + args)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Yaku", f"Could not start command:\n{exc}")
            return None

    def _open_setup_wizard(self) -> None:
        from yaku.ui.setup_wizard import SetupWizard
        wizard = SetupWizard(profile=self.profile, config_path=self.config_path)
        if wizard.exec():
            raw_profile = wizard.profile_input.text().strip() or self.profile or "default"
            self.profile = raw_profile
            self._refresh_profiles()
            self._load_config_into_ui()

    def _pick_window(self) -> None:
        from yaku.core.config import save_config, update_window_selection
        from yaku.core.profiles import resolve_profile
        from yaku.ui.window_picker import pick_window_gui
        
        config, config_path = resolve_profile(self.profile or "default")
        win = pick_window_gui(self)
        if win is not None:
            update_window_selection(config, win.hwnd, win.title)
            save_config(config, config_path)
            QMessageBox.information(
                self, "Window Selected", f"Target window saved:\n{win.title}\n(HWND: {win.hwnd})"
            )

    def _select_ocr_region(self) -> None:
        from yaku.core.profiles import resolve_profile
        config, config_path = resolve_profile(self.profile or "default")
        
        self.hide()
        QTimer.singleShot(200, lambda: self._do_select_ocr_region(config, config_path))

    def _do_select_ocr_region(self, config, config_path) -> None:
        from yaku.core.config import save_config, update_ocr_region
        from yaku.ui.region_selector import RegionSelector
        
        try:
            rect = RegionSelector().run_blocking()
            if rect is not None:
                update_ocr_region(config, rect)
                save_config(config, config_path)
        finally:
            self.show()

    def _select_replacement_region(self) -> None:
        from yaku.core.profiles import resolve_profile
        config, config_path = resolve_profile(self.profile or "default")
        
        self.hide()
        QTimer.singleShot(200, lambda: self._do_select_replacement_region(config, config_path))

    def _do_select_replacement_region(self, config, config_path) -> None:
        from PyQt6.QtWidgets import QApplication
        
        from yaku.core.config import save_config, update_replacement_region
        from yaku.core.image_utils import rect_to_normalized
        from yaku.ui.region_selector import RegionSelector
        
        try:
            rect = RegionSelector().run_blocking()
            if rect is not None:
                app = QApplication.instance()
                if app is not None:
                    geom = app.primaryScreen().geometry()
                    norm = rect_to_normalized(rect, geom.width(), geom.height())
                    update_replacement_region(config, norm)
                    save_config(config, config_path)
        finally:
            self.show()

    def _start(self) -> None:
        if self._run_process is not None and self._run_process.poll() is None:
            QMessageBox.information(self, "Yaku", "Yaku is already running.")
            return
            
        self._run_process = self._run_command(
            [
                "--mode",
                self.mode_combo.currentText(),
                "--translator",
                self.translator_combo.currentText(),
                "--target-lang",
                self.target_lang_input.text().strip() or "en",
                "--run",
            ]
        )
        if self._run_process is not None:
            self.process_timer.start()
            self._update_ui_state()

    def _stop(self) -> None:
        self._stop_run_process()
        self.process_timer.stop()
        self._update_ui_state()

    def _stop_run_process(self) -> None:
        process = self._run_process
        self._run_process = None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)

    def _health_check(self) -> None:
        from yaku.core.profiles import resolve_profile
        from yaku.ui.health_check_dialog import HealthCheckDialog
        
        config, config_path = resolve_profile(self.profile or "default")
        dialog = HealthCheckDialog(config, config_path, self)
        dialog.exec()

    def _show_logs(self) -> None:
        path = Path("out") / "yaku.log"
        if not path.exists():
            QMessageBox.information(self, "Yaku logs", "No log file found yet.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Yaku Logs")
        dialog.resize(760, 480)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("System Logs")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #ffffff;")
        layout.addWidget(title)

        viewer = QTextEdit()
        viewer.setReadOnly(True)
        # Read last 12000 chars of logs
        viewer.setPlainText(path.read_text(encoding="utf-8", errors="replace")[-12000:])
        # Auto scroll to bottom
        viewer.verticalScrollBar().setValue(viewer.verticalScrollBar().maximum())
        layout.addWidget(viewer)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(dialog.accept)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

        dialog.exec()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.process_timer.stop()
        self._stop_run_process()
        super().closeEvent(event)
