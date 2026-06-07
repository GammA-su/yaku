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
        self.quick_form = QFormLayout(config_group)
        self.quick_form.setSpacing(12)
        self.quick_form.setContentsMargins(16, 20, 16, 16)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["v1-overlay", "v2-mirror", "v3-audio-overlay", "V1 Overlay Max - Full Window UI Translation", "V4 Yomitan Native Dictionary", "V1 Overlay + Yomitan Native Dictionary"])
        self.quick_form.addRow("Operation Mode", self.mode_combo)

        from PyQt6.QtWidgets import QSpinBox
        self.scan_interval_spin = QSpinBox()
        self.scan_interval_spin.setRange(50, 10000)
        self.scan_interval_spin.setSingleStep(100)
        self.scan_interval_spin.setSuffix(" ms")
        self.quick_form.addRow("Scan Interval", self.scan_interval_spin)

        self.max_regions_spin = QSpinBox()
        self.max_regions_spin.setRange(1, 100)
        self.quick_form.addRow("Max Regions", self.max_regions_spin)

        self.gui_ocr_warning = QLabel("Warning: v1-overlay-max requires PaddleOCR.")
        self.gui_ocr_warning.setStyleSheet("color: #ff5555; font-weight: bold; font-size: 10px;")
        self.quick_form.addRow("", self.gui_ocr_warning)

        self.render_mode_combo = QComboBox()
        self.render_mode_combo.addItems(["mask-text", "inpaint-text", "ai-text-edit"])
        self.quick_form.addRow("Render Mode", self.render_mode_combo)

        self.audio_source_combo = QComboBox()
        self.audio_source_combo.addItems(["auto", "loopback", "mic"])
        self.quick_form.addRow("Audio Source", self.audio_source_combo)

        self.audio_backend_label = QLabel("Kotoba Whisper")
        self.quick_form.addRow("Audio Backend", self.audio_backend_label)

        self.translator_combo = QComboBox()
        self.translator_combo.addItems(["llama-cpp", "deepl"])
        self.quick_form.addRow("Translation Backend", self.translator_combo)

        self.target_lang_input = QLineEdit("en")
        self.quick_form.addRow("Target Language", self.target_lang_input)

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

        self.btn_yomitan_region = QPushButton("Draw Yomitan Area")
        self.btn_yomitan_region.clicked.connect(self._select_yomitan_region)
        utils_grid.addWidget(self.btn_yomitan_region, 2, 0)

        self.btn_yomitan_dicts = QPushButton("Yomitan Dictionaries")
        self.btn_yomitan_dicts.clicked.connect(self._open_yomitan_dicts)
        utils_grid.addWidget(self.btn_yomitan_dicts, 2, 1)

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
        self.mode_combo.currentTextChanged.connect(self._update_ui_state)
        self.render_mode_combo.currentTextChanged.connect(self._save_quick_config)
        self.audio_source_combo.currentTextChanged.connect(self._save_quick_config)
        self.translator_combo.currentTextChanged.connect(self._save_quick_config)
        self.target_lang_input.editingFinished.connect(self._save_quick_config)
        self.scan_interval_spin.valueChanged.connect(self._save_quick_config)
        self.max_regions_spin.valueChanged.connect(self._save_quick_config)

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
            self.render_mode_combo.blockSignals(True)
            self.audio_source_combo.blockSignals(True)
            self.translator_combo.blockSignals(True)
            self.target_lang_input.blockSignals(True)
            self.scan_interval_spin.blockSignals(True)
            self.max_regions_spin.blockSignals(True)

            # Set mode combobox
            mode = config.app.mode or "v1-overlay"
            if mode == "v1-overlay-max":
                combo_text = "V1 Overlay Max - Full Window UI Translation"
            elif mode == "v4-yomitan":
                combo_text = "V4 Yomitan Native Dictionary"
            elif mode == "v1-yomitan":
                combo_text = "V1 Overlay + Yomitan Native Dictionary"
            else:
                combo_text = mode
            index = self.mode_combo.findText(combo_text)
            if index >= 0:
                self.mode_combo.setCurrentIndex(index)
                
            # Set render mode combobox
            rmode = config.v2_mirror.render_mode or "inpaint-text"
            index = self.render_mode_combo.findText(rmode)
            if index >= 0:
                self.render_mode_combo.setCurrentIndex(index)

            # Set audio source combobox
            asource = config.audio.source or "auto"
            index = self.audio_source_combo.findText(asource)
            if index >= 0:
                self.audio_source_combo.setCurrentIndex(index)
                
            # Set translator combobox
            translator = config.translator.backend or "llama_cpp"
            combo_translator = "llama-cpp" if translator == "llama_cpp" else "deepl"
            index = self.translator_combo.findText(combo_translator)
            if index >= 0:
                self.translator_combo.setCurrentIndex(index)
                
            # Set target language
            self.target_lang_input.setText(config.app.target_lang or "en")

            # Set scan interval and max regions
            self.scan_interval_spin.setValue(config.v1_overlay_max.scan_interval_ms)
            self.max_regions_spin.setValue(config.v1_overlay_max.max_regions)
        except Exception as exc:  # noqa: BLE001
            print(f"[yaku] Failed to load config into UI: {exc}")
        finally:
            self.mode_combo.blockSignals(False)
            self.render_mode_combo.blockSignals(False)
            self.audio_source_combo.blockSignals(False)
            self.translator_combo.blockSignals(False)
            self.target_lang_input.blockSignals(False)
            self.scan_interval_spin.blockSignals(False)
            self.max_regions_spin.blockSignals(False)

    def _save_quick_config(self) -> None:
        from yaku.core.config import save_config
        from yaku.core.profiles import resolve_profile
        try:
            config, config_path = resolve_profile(self.profile or "default")
            
            combo_text = self.mode_combo.currentText()
            if combo_text == "V1 Overlay Max - Full Window UI Translation":
                config.app.mode = "v1-overlay-max"
            elif combo_text == "V4 Yomitan Native Dictionary":
                config.app.mode = "v4-yomitan"
            elif combo_text == "V1 Overlay + Yomitan Native Dictionary":
                config.app.mode = "v1-yomitan"
            else:
                config.app.mode = combo_text  # type: ignore[assignment]
                
            config.v2_mirror.render_mode = self.render_mode_combo.currentText()  # type: ignore[assignment]
            config.audio.source = self.audio_source_combo.currentText()  # type: ignore[assignment]
            backend_val = self.translator_combo.currentText()
            config.translator.backend = "llama_cpp" if backend_val == "llama-cpp" else "deepl"  # type: ignore[assignment]
            config.app.target_lang = self.target_lang_input.text().strip() or "en"
            
            config.v1_overlay_max.scan_interval_ms = self.scan_interval_spin.value()
            config.v1_overlay_max.max_regions = self.max_regions_spin.value()
            
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
        mode = self.mode_combo.currentText()
        is_max = mode == "V1 Overlay Max - Full Window UI Translation"
        is_v2 = mode == "v2-mirror"
        is_v3 = mode == "v3-audio-overlay"
        is_yomitan = mode == "V4 Yomitan Native Dictionary"

        render_mode_label = self.quick_form.labelForField(self.render_mode_combo)
        if render_mode_label:
            render_mode_label.setVisible(is_v2)
        self.render_mode_combo.setVisible(is_v2)

        audio_source_label = self.quick_form.labelForField(self.audio_source_combo)
        if audio_source_label:
            audio_source_label.setVisible(is_v3)
        self.audio_source_combo.setVisible(is_v3)

        audio_backend_label = self.quick_form.labelForField(self.audio_backend_label)
        if audio_backend_label:
            audio_backend_label.setVisible(is_v3)
        self.audio_backend_label.setVisible(is_v3)

        translator_label = self.quick_form.labelForField(self.translator_combo)
        if translator_label:
            translator_label.setVisible(not is_yomitan and not is_v3)
        self.translator_combo.setVisible(not is_yomitan and not is_v3)

        target_lang_label = self.quick_form.labelForField(self.target_lang_input)
        if target_lang_label:
            target_lang_label.setVisible(not is_yomitan and not is_v3)
        self.target_lang_input.setVisible(not is_yomitan and not is_v3)

        scan_interval_label = self.quick_form.labelForField(self.scan_interval_spin)
        if scan_interval_label:
            scan_interval_label.setVisible(is_max)
        self.scan_interval_spin.setVisible(is_max)

        max_regions_label = self.quick_form.labelForField(self.max_regions_spin)
        if max_regions_label:
            max_regions_label.setVisible(is_max)
        self.max_regions_spin.setVisible(is_max)

        # ocr warning visibility
        ocr_backend = "paddleocr"
        try:
            from yaku.core.profiles import resolve_profile
            config, _ = resolve_profile(self.profile or "default")
            ocr_backend = config.ocr.backend
        except Exception:
            pass

        warning_visible = is_max and ocr_backend != "paddleocr"
        warning_label = self.quick_form.labelForField(self.gui_ocr_warning)
        if warning_label:
            warning_label.setVisible(warning_visible)
        self.gui_ocr_warning.setVisible(warning_visible)

        self.btn_ocr.setEnabled(not is_v3 and not is_max and not is_yomitan)
        self.btn_replacement.setEnabled(is_v2)
        self.btn_picker.setEnabled(not is_v3)
        
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
            self.render_mode_combo.setEnabled(False)
            self.audio_source_combo.setEnabled(False)
            self.translator_combo.setEnabled(False)
            self.target_lang_input.setEnabled(False)
            self.scan_interval_spin.setEnabled(False)
            self.max_regions_spin.setEnabled(False)
            
            if hasattr(self, "btn_yomitan_region"):
                self.btn_yomitan_region.setEnabled(False)
                self.btn_yomitan_dicts.setEnabled(False)
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
            self.render_mode_combo.setEnabled(is_v2)
            self.audio_source_combo.setEnabled(is_v3)
            self.translator_combo.setEnabled(not is_yomitan)
            self.target_lang_input.setEnabled(not is_yomitan)
            self.scan_interval_spin.setEnabled(is_max)
            self.max_regions_spin.setEnabled(is_max)
            
            if hasattr(self, "btn_yomitan_region"):
                self.btn_yomitan_region.setEnabled(is_yomitan)
                self.btn_yomitan_dicts.setEnabled(True)

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
                    from yaku.core.capture import normalize_screen_rect_to_window
                    norm = normalize_screen_rect_to_window(rect, config.window, geom.width(), geom.height())
                    update_replacement_region(config, norm)
                    save_config(config, config_path)
        finally:
            self.show()

    def _start(self) -> None:
        if self._run_process is not None and self._run_process.poll() is None:
            QMessageBox.information(self, "Yaku", "Yaku is already running.")
            return
            
        mode_val = self.mode_combo.currentText()
        if mode_val == "V1 Overlay Max - Full Window UI Translation":
            mode_arg = "v1-overlay-max"
        elif mode_val == "V4 Yomitan Native Dictionary":
            mode_arg = "v4-yomitan"
        elif mode_val == "V1 Overlay + Yomitan Native Dictionary":
            mode_arg = "v1-yomitan"
        else:
            mode_arg = mode_val
            
        args = [
            "--mode",
            mode_arg,
        ]
        if mode_arg != "v4-yomitan":
            args.extend([
                "--translator",
                self.translator_combo.currentText(),
                "--target-lang",
                self.target_lang_input.text().strip() or "en",
            ])
            
        if self.mode_combo.currentText() == "v2-mirror":
            args.extend(["--render-mode", self.render_mode_combo.currentText()])
        elif self.mode_combo.currentText() == "v3-audio-overlay":
            args.extend(["--audio-source", self.audio_source_combo.currentText()])
            
            from yaku.audio.deps import check_audio_dependencies
            from yaku.audio.model_manager import check_model_available
            from yaku.core.profiles import resolve_profile
            
            config, config_path = resolve_profile(self.profile or "default")
            deps_status = check_audio_dependencies()
            model_status = None
            if deps_status.ok:
                model_status = check_model_available(config)
                
            if not deps_status.ok or (model_status and not model_status.ok) or config.audio.device_id is None:
                from yaku.ui.audio_setup_dialog import AudioSetupDialog
                dialog = AudioSetupDialog(config, config_path, self)
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return
            
        from yaku.core.profiles import resolve_profile
        config, _ = resolve_profile(self.profile or "default")
        if config.app.debug:
            args.append("--debug")
            
        args.append("--run")
        
        self._run_process = self._run_command(args)
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

    def _select_yomitan_region(self) -> None:
        from yaku.core.profiles import resolve_profile
        config, config_path = resolve_profile(self.profile or "default")
        
        self.hide()
        QTimer.singleShot(200, lambda: self._do_select_yomitan_region(config, config_path))

    def _do_select_yomitan_region(self, config, config_path) -> None:
        from yaku.core.config import save_config
        from yaku.ui.region_selector import RegionSelector
        
        try:
            rect = RegionSelector().run_blocking()
            if rect is not None:
                config.v4_yomitan.region.x = rect.x
                config.v4_yomitan.region.y = rect.y
                config.v4_yomitan.region.w = rect.w
                config.v4_yomitan.region.h = rect.h
                config.v4_yomitan.region.is_set = True
                save_config(config, config_path)
        finally:
            self.show()

    def _open_yomitan_dicts(self) -> None:
        from yaku.core.profiles import resolve_profile
        from yaku.ui.dictionary_manager_dialog import DictionaryManagerDialog
        
        config, _ = resolve_profile(self.profile or "default")
        dialog = DictionaryManagerDialog(config, self)
        dialog.exec()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.process_timer.stop()
        self._stop_run_process()
        super().closeEvent(event)
