"""Simple PyQt6 settings panel for V1 overlay runtime options."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from yaku.core.config import YakuConfig, save_config


class SettingsPanel(QDialog):
    """Small functional settings dialog that saves back to the active config."""

    def __init__(
        self,
        config: YakuConfig,
        config_path: Optional[Path],
        parent: Optional[QWidget] = None,
        *,
        on_saved: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Tool)
        self.setWindowTitle("Yaku Settings")
        self.resize(500, 480)
        self._config = config
        self._config_path = config_path
        self._on_saved = on_saved

        root = QVBoxLayout(self)
        root.setSpacing(16)
        root.setContentsMargins(20, 20, 20, 20)

        # Header Section
        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)
        self.title_lbl = QLabel("Configuration Settings")
        self.title_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #ffffff;")
        self.subtitle_lbl = QLabel("Fine-tune translator parameters and overlay aesthetics.")
        self.subtitle_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
        header_layout.addWidget(self.title_lbl)
        header_layout.addWidget(self.subtitle_lbl)
        root.addLayout(header_layout)

        # Config Form
        form = QFormLayout()
        form.setSpacing(12)
        form.setContentsMargins(4, 8, 4, 8)
        root.addLayout(form)

        self._backend = QComboBox()
        self._backend.addItems(["llama_cpp", "deepl"])
        self._backend.setCurrentText(config.translator.backend)
        form.addRow("Translator backend", self._backend)

        self._ocr_backend = QComboBox()
        self._ocr_backend.addItems(["paddleocr", "manga_ocr", "dummy"])
        self._ocr_backend.setCurrentText(config.ocr.backend)
        form.addRow("OCR backend", self._ocr_backend)

        self._target_lang = QComboBox()
        self._target_lang.setEditable(True)
        self._target_lang.addItems(["en", "EN-US", "DE", "FR", "ES", "JA"])
        self._target_lang.setCurrentText(config.app.target_lang)
        form.addRow("Target language", self._target_lang)

        self._audio_source = QComboBox()
        self._audio_source.addItems(["auto", "loopback", "mic"])
        self._audio_source.setCurrentText(config.audio.source)
        form.addRow("Audio Source", self._audio_source)

        # Selected device display
        self._audio_device_lbl = QLabel(config.audio.device_name or "Auto Select")
        self._audio_device_btn = QPushButton("Choose Device...")
        self._audio_device_btn.clicked.connect(self._on_choose_audio_device)
        
        device_layout = QHBoxLayout()
        device_layout.addWidget(self._audio_device_lbl, 1)
        device_layout.addWidget(self._audio_device_btn)
        form.addRow("Audio Device", device_layout)

        # GPU acceleration checkbox
        self._use_gpu_chk = QCheckBox("Use GPU (CUDA) for Audio")
        self._use_gpu_chk.setChecked(config.audio.device == "cuda")
        self._use_gpu_chk.toggled.connect(self._on_use_gpu_toggled)
        form.addRow("GPU Acceleration", self._use_gpu_chk)

        # VAD Parameters
        self._chunk_seconds = QDoubleSpinBox()
        self._chunk_seconds.setRange(1.0, 30.0)
        self._chunk_seconds.setSingleStep(0.5)
        self._chunk_seconds.setValue(config.audio.chunk_seconds)
        form.addRow("Max Segment Duration (sec)", self._chunk_seconds)

        self._vad_threshold = QDoubleSpinBox()
        self._vad_threshold.setRange(0.01, 1.00)
        self._vad_threshold.setSingleStep(0.05)
        self._vad_threshold.setDecimals(2)
        self._vad_threshold.setValue(config.audio.vad_threshold)
        form.addRow("VAD Threshold", self._vad_threshold)

        self._min_speech_ms = QSpinBox()
        self._min_speech_ms.setRange(10, 5000)
        self._min_speech_ms.setSingleStep(50)
        self._min_speech_ms.setValue(config.audio.min_speech_ms)
        form.addRow("Min Speech Duration (ms)", self._min_speech_ms)

        self._min_silence_ms = QSpinBox()
        self._min_silence_ms.setRange(10, 5000)
        self._min_silence_ms.setSingleStep(50)
        self._min_silence_ms.setValue(config.audio.min_silence_ms)
        form.addRow("Min Silence Duration (ms)", self._min_silence_ms)

        self._merge_speech_gap_ms = QSpinBox()
        self._merge_speech_gap_ms.setRange(0, 10000)
        self._merge_speech_gap_ms.setSingleStep(50)
        self._merge_speech_gap_ms.setValue(config.audio.merge_speech_gap_ms)
        form.addRow("Merge Speech Gap (ms)", self._merge_speech_gap_ms)

        self._vad_tail_ms = QSpinBox()
        self._vad_tail_ms.setRange(0, 5000)
        self._vad_tail_ms.setSingleStep(50)
        self._vad_tail_ms.setValue(config.audio.vad_tail_ms)
        form.addRow("VAD Tail (ms)", self._vad_tail_ms)

        # Audio pack status, setup button, install/download buttons
        self._audio_status_lbl = QLabel("")
        self._audio_setup_btn = QPushButton("Check Audio Setup...")
        self._audio_setup_btn.clicked.connect(self._on_check_audio_setup)
        
        self._audio_install_btn = QPushButton("Install Audio Pack")
        self._audio_install_btn.clicked.connect(self._on_install_audio_pack)
        
        self._audio_download_btn = QPushButton("Download Model")
        self._audio_download_btn.clicked.connect(self._on_download_model)

        status_layout = QHBoxLayout()
        status_layout.addWidget(self._audio_status_lbl, 1)
        status_layout.addWidget(self._audio_setup_btn)
        status_layout.addWidget(self._audio_install_btn)
        status_layout.addWidget(self._audio_download_btn)
        form.addRow("Audio Pack Status", status_layout)

        # Audio progress / busy label
        self._audio_progress = QLabel("")
        self._audio_progress.setStyleSheet("color: #38bdf8; font-size: 11px;")
        form.addRow("", self._audio_progress)

        # DeepL API Key input
        self._deepl_key = QLineEdit()
        self._deepl_key.setText(config.translator.deepl.api_key or "")
        self._deepl_key.setPlaceholderText("Enter DeepL API Key (prioritized)...")
        form.addRow("DeepL API Key", self._deepl_key)

        # llama.cpp Hosted LLM checkbox
        self._use_hosted = QCheckBox("Use hosted LLM (https://llm.iosys.fr/v1)")
        self._use_hosted.setChecked(config.translator.llama_cpp.use_hosted)
        self._use_hosted.toggled.connect(self._on_use_hosted_changed)
        form.addRow("Hosted LLM", self._use_hosted)

        # llama.cpp Port input
        self._llamacpp_port = QSpinBox()
        self._llamacpp_port.setRange(1, 65535)
        self._llamacpp_port.setValue(config.translator.llama_cpp.port or 8080)
        form.addRow("llama.cpp Port", self._llamacpp_port)

        # llama.cpp Address input
        self._llamacpp_address = QLineEdit()
        self._llamacpp_address.setText(config.translator.llama_cpp.base_url or "")
        self._llamacpp_address.setPlaceholderText("Enter llama.cpp base URL (e.g., http://127.0.0.1:8080/v1)...")
        form.addRow("llama.cpp Address", self._llamacpp_address)

        self._overlay_opacity = QDoubleSpinBox()
        self._overlay_opacity.setRange(0.10, 1.00)
        self._overlay_opacity.setSingleStep(0.05)
        self._overlay_opacity.setDecimals(2)
        self._overlay_opacity.setValue(config.v1_overlay.opacity)
        form.addRow("Overlay opacity", self._overlay_opacity)

        self._background_opacity = QDoubleSpinBox()
        self._background_opacity.setRange(0.00, 1.00)
        self._background_opacity.setSingleStep(0.05)
        self._background_opacity.setDecimals(2)
        self._background_opacity.setValue(config.v1_overlay.background_opacity)
        form.addRow("Background opacity", self._background_opacity)

        self._font_size = QSpinBox()
        self._font_size.setRange(8, 96)
        self._font_size.setValue(config.v1_overlay.font_size)
        form.addRow("Font size (px)", self._font_size)

        self._click_through = QCheckBox("Enable click-through overlay")
        self._click_through.setChecked(config.v1_overlay.click_through)
        form.addRow("Overlay interaction", self._click_through)

        self._locked = QCheckBox("Lock position and size")
        self._locked.setChecked(config.v1_overlay.locked)
        form.addRow("Overlay bounds", self._locked)

        self._tick_ms = QSpinBox()
        self._tick_ms.setRange(50, 5000)
        self._tick_ms.setSingleStep(50)
        self._tick_ms.setValue(config.app.tick_ms)
        form.addRow("Tick interval (ms)", self._tick_ms)

        # Yomitan Dictionaries
        self._dict_manager_btn = QPushButton("Manage Dictionaries...")
        self._dict_manager_btn.clicked.connect(self._on_manage_dicts)
        form.addRow("Yomitan Dictionaries", self._dict_manager_btn)

        self._on_use_hosted_changed(config.translator.llama_cpp.use_hosted)
        self._refresh_audio_status()

        # Action Buttons Layout (replacing standard QDialogButtonBox)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_cancel.setMinimumWidth(80)

        self.btn_save = QPushButton("Save Settings")
        self.btn_save.setObjectName("btn_primary")
        self.btn_save.clicked.connect(self._save)
        self.btn_save.setMinimumWidth(110)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_save)
        root.addLayout(btn_layout)

    def _save(self) -> None:
        self._config.translator.backend = self._backend.currentText()  # type: ignore[assignment]
        self._config.ocr.backend = self._ocr_backend.currentText()  # type: ignore[assignment]
        self._config.app.target_lang = self._target_lang.currentText().strip() or "en"
        self._config.audio.source = self._audio_source.currentText()  # type: ignore[assignment]
        self._config.audio.device = "cuda" if self._use_gpu_chk.isChecked() else "cpu"
        self._config.audio.chunk_seconds = self._chunk_seconds.value()
        self._config.audio.vad_threshold = self._vad_threshold.value()
        self._config.audio.min_speech_ms = self._min_speech_ms.value()
        self._config.audio.min_silence_ms = self._min_silence_ms.value()
        self._config.audio.merge_speech_gap_ms = self._merge_speech_gap_ms.value()
        self._config.audio.vad_tail_ms = self._vad_tail_ms.value()
        
        # Save our new settings fields
        deepl_key = self._deepl_key.text().strip()
        self._config.translator.deepl.api_key = deepl_key if deepl_key else None
        self._config.translator.llama_cpp.port = self._llamacpp_port.value()
        self._config.translator.llama_cpp.base_url = self._llamacpp_address.text().strip() or None
        self._config.translator.llama_cpp.use_hosted = self._use_hosted.isChecked()

        self._config.v1_overlay.opacity = self._overlay_opacity.value()
        self._config.v1_overlay.background_opacity = self._background_opacity.value()
        self._config.v1_overlay.font_size = self._font_size.value()
        self._config.v1_overlay.click_through = self._click_through.isChecked()
        self._config.v1_overlay.locked = self._locked.isChecked()
        self._config.app.tick_ms = self._tick_ms.value()

        if self._config_path is not None:
            save_config(self._config, self._config_path)
        if self._on_saved is not None:
            self._on_saved()
        self.accept()

    def _on_manage_dicts(self) -> None:
        from yaku.ui.dictionary_manager_dialog import DictionaryManagerDialog
        dialog = DictionaryManagerDialog(self._config, self)
        dialog.exec()

    def _on_use_hosted_changed(self, checked: bool) -> None:
        self._llamacpp_port.setEnabled(not checked)
        self._llamacpp_address.setEnabled(not checked)

    def _on_choose_audio_device(self) -> None:
        from yaku.audio.deps import check_audio_dependencies
        if not check_audio_dependencies().ok:
            QMessageBox.warning(self, "Audio Pack Required", "Please install the Audio Pack first via 'Check Audio Setup'.")
            return

        from yaku.ui.audio_device_dialog import AudioDeviceDialog
        dialog = AudioDeviceDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if dialog.use_auto:
                self._config.audio.device_id = None
                self._config.audio.device_name = "Auto Select"
            elif dialog.selected_device:
                self._config.audio.device_id = dialog.selected_device.index
                self._config.audio.device_name = dialog.selected_device.name
            self._audio_device_lbl.setText(self._config.audio.device_name)

    def _on_check_audio_setup(self) -> None:
        from yaku.ui.audio_setup_dialog import AudioSetupDialog
        dialog = AudioSetupDialog(self._config, self._config_path, self)
        dialog.exec()
        self._refresh_audio_status()
        self._audio_device_lbl.setText(self._config.audio.device_name or "Auto Select")
        self._use_gpu_chk.setChecked(self._config.audio.device == "cuda")
        self._chunk_seconds.setValue(self._config.audio.chunk_seconds)
        self._vad_threshold.setValue(self._config.audio.vad_threshold)
        self._min_speech_ms.setValue(self._config.audio.min_speech_ms)
        self._min_silence_ms.setValue(self._config.audio.min_silence_ms)
        self._merge_speech_gap_ms.setValue(self._config.audio.merge_speech_gap_ms)
        self._vad_tail_ms.setValue(self._config.audio.vad_tail_ms)

    def _refresh_audio_status(self) -> None:
        from yaku.audio.deps import check_audio_dependencies
        from yaku.audio.model_manager import check_model_available
        
        deps_status = check_audio_dependencies()
        self._audio_status_lbl.setText(deps_status.message)
        
        self._audio_install_btn.setVisible(not deps_status.ok)
        
        if deps_status.ok:
            model_status = check_model_available(self._config)
            self._audio_download_btn.setVisible(not model_status.ok)
        else:
            self._audio_download_btn.setVisible(False)
            
        if deps_status.ok:
            model_ok = check_model_available(self._config).ok
            if model_ok:
                self._audio_status_lbl.setStyleSheet("color: #44cc88; font-weight: bold;")
            else:
                self._audio_status_lbl.setStyleSheet("color: #ffaa55; font-weight: bold;")
        else:
            self._audio_status_lbl.setStyleSheet("color: #ff5555; font-weight: bold;")

    def _on_install_audio_pack(self, use_gpu: Optional[bool] = None) -> None:
        from yaku.ui.audio_setup_dialog import InstallWorker
        if use_gpu is None:
            use_gpu = self._use_gpu_chk.isChecked()
        self._audio_install_btn.setEnabled(False)
        self._audio_setup_btn.setEnabled(False)
        self._audio_download_btn.setEnabled(False)
        self._use_gpu_chk.setEnabled(False)
        self._audio_progress.setText("Installing Audio Pack dependencies (GPU)..." if use_gpu else "Installing Audio Pack dependencies...")
        
        self._install_worker = InstallWorker(use_gpu=use_gpu)
        self._install_worker.finished.connect(self._on_install_finished)
        self._install_worker.start()
        
    def _on_install_finished(self, result: Any) -> None:
        self._audio_install_btn.setEnabled(True)
        self._audio_setup_btn.setEnabled(True)
        self._use_gpu_chk.setEnabled(True)
        self._audio_progress.setText("")
        if result.ok:
            QMessageBox.information(self, "Success", "Audio Pack installed successfully.")
        else:
            QMessageBox.critical(self, "Error", f"Failed to install Audio Pack:\n{result.message}")
        self._refresh_audio_status()
        
    def _on_download_model(self) -> None:
        from yaku.ui.audio_setup_dialog import DownloadWorker
        self._audio_install_btn.setEnabled(False)
        self._audio_setup_btn.setEnabled(False)
        self._audio_download_btn.setEnabled(False)
        self._audio_progress.setText("Downloading Kotoba Whisper model...")
        
        self._download_worker = DownloadWorker(self._config)
        self._download_worker.finished.connect(self._on_download_finished)
        self._download_worker.start()
        
    def _on_download_finished(self, status: Any) -> None:
        self._audio_setup_btn.setEnabled(True)
        self._audio_progress.setText("")
        if status.ok:
            QMessageBox.information(self, "Success", "Model downloaded successfully.")
        else:
            QMessageBox.critical(self, "Error", f"Failed to download model:\n{status.message}")
        self._refresh_audio_status()

    def _on_use_gpu_toggled(self, checked: bool) -> None:
        if checked:
            from yaku.audio.deps import check_audio_dependencies
            if check_audio_dependencies().ok:
                reply = QMessageBox.question(
                    self,
                    "Install GPU Audio Pack",
                    "Enabling GPU (CUDA) for Audio requires installing the GPU-accelerated version of PyTorch. "
                    "This will replace the CPU version.\n\n"
                    "Would you like to run the installation now?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self._on_install_audio_pack(use_gpu=True)
        else:
            from yaku.audio.deps import check_audio_dependencies
            if check_audio_dependencies().ok:
                reply = QMessageBox.question(
                    self,
                    "Reinstall CPU Audio Pack",
                    "Disabling GPU (CUDA) for Audio. Would you like to reinstall the CPU-only version of PyTorch "
                    "to save disk space and replace the GPU version?\n\n"
                    "Would you like to run the installation now?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self._on_install_audio_pack(use_gpu=False)
