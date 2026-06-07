from __future__ import annotations
import logging
from typing import Any, Optional
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QProgressBar,
    QMessageBox,
    QWidget,
    QCheckBox,
)

from yaku.audio.deps import check_audio_dependencies
from yaku.audio.model_manager import check_model_available
from yaku.audio.capture import choose_default_audio_device

_log = logging.getLogger("audio_setup_dialog")


class InstallWorker(QThread):
    finished = pyqtSignal(object)

    def __init__(self, use_gpu: bool = False) -> None:
        super().__init__()
        self.use_gpu = use_gpu

    def run(self) -> None:
        from yaku.audio.install import install_audio_pack
        try:
            result = install_audio_pack(use_gpu=self.use_gpu)
            self.finished.emit(result)
        except Exception as exc:
            from yaku.audio.install import AudioInstallResult
            self.finished.emit(AudioInstallResult(ok=False, message=str(exc)))


class DownloadWorker(QThread):
    finished = pyqtSignal(object)

    def __init__(self, config: Any) -> None:
        super().__init__()
        self.config = config

    def run(self) -> None:
        from yaku.audio.model_manager import download_model
        try:
            result = download_model(self.config)
            self.finished.emit(result)
        except Exception as exc:
            from yaku.audio.model_manager import ModelStatus
            self.finished.emit(ModelStatus(ok=False, model_id=self.config.audio.model, local_path=None, message=str(exc)))


class AudioSetupDialog(QDialog):
    def __init__(self, config: Any, config_path: Optional[Path] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent, Qt.WindowType.Dialog)
        self.setWindowTitle("Yaku Audio Pack Setup")
        self.resize(520, 360)
        self.config = config
        self.config_path = config_path
        self.install_worker: Optional[InstallWorker] = None
        self.download_worker: Optional[DownloadWorker] = None

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header Info
        header = QLabel("Yaku Audio Overlay Configuration")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff;")
        layout.addWidget(header)

        desc = QLabel(
            "V3 Audio Overlay requires additional packages and model files (approx. 75MB).\n"
            "This setup assistant will configure the necessary components."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(desc)

        # GPU Option
        self.chk_use_gpu = QCheckBox("Use GPU (CUDA) for Audio")
        self.chk_use_gpu.setChecked(self.config.audio.device == "cuda")
        self.chk_use_gpu.toggled.connect(self.on_gpu_toggled)
        layout.addWidget(self.chk_use_gpu)

        # Status Group
        self.lbl_deps = QLabel("Audio Packages: Checking...")
        self.lbl_model = QLabel("ASR Model: Checking...")
        self.lbl_device = QLabel("Audio Device: Checking...")
        
        for lbl in (self.lbl_deps, self.lbl_model, self.lbl_device):
            lbl.setStyleSheet("font-weight: bold; font-size: 12px;")
            layout.addWidget(lbl)

        # Busy indicator progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0) # Busy indicator
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.lbl_progress = QLabel("")
        self.lbl_progress.setWordWrap(True)
        self.lbl_progress.setStyleSheet("color: #38bdf8; font-size: 11px;")
        layout.addWidget(self.lbl_progress)

        # Controls Buttons
        ctrl_layout = QHBoxLayout()
        self.btn_install_deps = QPushButton("Install Audio Pack")
        self.btn_install_deps.clicked.connect(self.start_install_deps)
        ctrl_layout.addWidget(self.btn_install_deps)

        self.btn_download_model = QPushButton("Download Whisper Model")
        self.btn_download_model.clicked.connect(self.start_download_model)
        ctrl_layout.addWidget(self.btn_download_model)

        self.btn_choose_device = QPushButton("Choose Audio Device")
        self.btn_choose_device.clicked.connect(self.choose_audio_device)
        ctrl_layout.addWidget(self.btn_choose_device)
        layout.addLayout(ctrl_layout)

        # Divider
        layout.addStretch()

        # Action Buttons
        actions = QHBoxLayout()
        self.btn_recheck = QPushButton("Re-check")
        self.btn_recheck.clicked.connect(self.perform_checks)
        actions.addWidget(self.btn_recheck)
        actions.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        actions.addWidget(self.btn_cancel)

        self.btn_continue = QPushButton("Continue")
        self.btn_continue.setObjectName("btn_primary")
        self.btn_continue.clicked.connect(self.accept)
        actions.addWidget(self.btn_continue)
        layout.addLayout(actions)

        # Run checks on init
        self.perform_checks()

    def perform_checks(self) -> None:
        # Check Dependencies
        self.deps_status = check_audio_dependencies()
        if self.deps_status.ok:
            self.lbl_deps.setText("Audio Packages: Installed [OK]")
            self.lbl_deps.setStyleSheet("color: #44cc88; font-weight: bold;")
            self.btn_install_deps.setEnabled(False)
        else:
            self.lbl_deps.setText("Audio Packages: Missing")
            self.lbl_deps.setStyleSheet("color: #ff5555; font-weight: bold;")
            self.btn_install_deps.setEnabled(True)

        # Check Model
        if self.deps_status.ok:
            self.model_status = check_model_available(self.config)
            if self.model_status.ok:
                self.lbl_model.setText("ASR Model: Available [OK]")
                self.lbl_model.setStyleSheet("color: #44cc88; font-weight: bold;")
                self.btn_download_model.setEnabled(False)
            else:
                self.lbl_model.setText("ASR Model: Missing")
                self.lbl_model.setStyleSheet("color: #ff5555; font-weight: bold;")
                self.btn_download_model.setEnabled(True)
        else:
            self.lbl_model.setText("ASR Model: Needs Package Install first")
            self.lbl_model.setStyleSheet("color: #e2e8f0; font-weight: bold;")
            self.btn_download_model.setEnabled(False)

        # Check Device
        if self.deps_status.ok:
            selected_device_name = self.config.audio.device_name
            selected_device_id = self.config.audio.device_id
            
            if selected_device_id is not None:
                self.lbl_device.setText(f"Audio Device: {selected_device_name} (ID: {selected_device_id}) [OK]")
                self.lbl_device.setStyleSheet("color: #44cc88; font-weight: bold;")
                self.btn_choose_device.setEnabled(True)
            else:
                # Attempt to auto select device
                default_dev = choose_default_audio_device(self.config.audio.source)
                if default_dev:
                    self.config.audio.device_id = default_dev.index
                    self.config.audio.device_name = default_dev.name
                    # Save configuration
                    self.save_config_to_disk()
                    
                    self.lbl_device.setText(f"Audio Device: {default_dev.name} (Auto selected) [OK]")
                    self.lbl_device.setStyleSheet("color: #44ccff; font-weight: bold;")
                else:
                    self.lbl_device.setText("Audio Device: None selected / detected")
                    self.lbl_device.setStyleSheet("color: #ff5555; font-weight: bold;")
                self.btn_choose_device.setEnabled(True)
        else:
            self.lbl_device.setText("Audio Device: Needs Package Install first")
            self.lbl_device.setStyleSheet("color: #e2e8f0; font-weight: bold;")
            self.btn_choose_device.setEnabled(False)

        # Enable continue only if packages and model are OK
        has_deps = self.deps_status.ok
        has_model = has_deps and check_model_available(self.config).ok
        has_device = has_deps and self.config.audio.device_id is not None
        
        self.btn_continue.setEnabled(has_deps and has_model and has_device)

    def save_config_to_disk(self) -> None:
        if self.config_path:
            from yaku.core.config import save_config
            try:
                save_config(self.config, self.config_path)
            except Exception as exc:
                _log.warning(f"Could not save config to {self.config_path}: {exc}")

    def on_gpu_toggled(self, checked: bool) -> None:
        self.config.audio.device = "cuda" if checked else "cpu"
        self.save_config_to_disk()

    def start_install_deps(self) -> None:
        self.set_busy(True, "Installing Audio Pack python dependencies...")
        self.install_worker = InstallWorker(use_gpu=self.chk_use_gpu.isChecked())
        self.install_worker.finished.connect(self.on_install_deps_finished)
        self.install_worker.start()

    @pyqtSlot(object)
    def on_install_deps_finished(self, result: Any) -> None:
        self.set_busy(False)
        if result.ok:
            QMessageBox.information(self, "Success", "Dependencies installed successfully. Restarting packages check.")
        else:
            QMessageBox.critical(self, "Installation Failed", f"Installation failed:\n{result.message}")
        self.perform_checks()

    def start_download_model(self) -> None:
        self.set_busy(True, "Downloading Kotoba Whisper model files from Hugging Face...")
        self.download_worker = DownloadWorker(self.config)
        self.download_worker.finished.connect(self.on_download_model_finished)
        self.download_worker.start()

    @pyqtSlot(object)
    def on_download_model_finished(self, status: Any) -> None:
        self.set_busy(False)
        if status.ok:
            QMessageBox.information(self, "Success", "Model downloaded and cached successfully.")
        else:
            QMessageBox.critical(self, "Download Failed", f"Failed to download model:\n{status.message}")
        self.perform_checks()

    def choose_audio_device(self) -> None:
        from yaku.ui.audio_device_dialog import AudioDeviceDialog
        dialog = AudioDeviceDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if dialog.use_auto:
                self.config.audio.device_id = None
                self.config.audio.device_name = "Auto Select"
            elif dialog.selected_device:
                self.config.audio.device_id = dialog.selected_device.index
                self.config.audio.device_name = dialog.selected_device.name
            
            self.save_config_to_disk()
            self.perform_checks()

    def set_busy(self, busy: bool, message: str = "") -> None:
        self.progress_bar.setVisible(busy)
        self.lbl_progress.setText(message)
        
        self.btn_install_deps.setEnabled(not busy)
        self.btn_download_model.setEnabled(not busy)
        self.btn_choose_device.setEnabled(not busy)
        self.btn_recheck.setEnabled(not busy)
        self.btn_cancel.setEnabled(not busy)
        self.btn_continue.setEnabled(not busy)
        self.chk_use_gpu.setEnabled(not busy)
