from __future__ import annotations
import sys
import pytest
from unittest.mock import MagicMock
from PyQt6.QtWidgets import QApplication

from yaku.core.config import YakuConfig
from yaku.audio.deps import AudioDepsStatus
from yaku.audio.model_manager import ModelStatus
from yaku.audio.capture import AudioDeviceInfo
from yaku.ui.app import get_app

def test_audio_setup_dialog_ui_state(monkeypatch):
    # Ensure QApplication is initialized
    app = get_app()
    
    config = YakuConfig()
    
    # Mock choose_default_audio_device globally in setup dialog context
    monkeypatch.setattr(
        "yaku.ui.audio_setup_dialog.choose_default_audio_device",
        lambda src: AudioDeviceInfo(
            id="0", index=0, name="Default Input", hostapi="MME",
            max_input_channels=2, is_loopback=False, is_default=True, sample_rate=16000
        )
    )
    
    # Mock deps checking to return missing
    monkeypatch.setattr(
        "yaku.ui.audio_setup_dialog.check_audio_dependencies",
        lambda: AudioDepsStatus(ok=False, missing=[], installed=[], message="Audio Pack is missing")
    )
    
    from yaku.ui.audio_setup_dialog import AudioSetupDialog
    
    # Open dialog in memory
    dialog = AudioSetupDialog(config)
    
    # Assert continue button is disabled
    assert dialog.btn_continue.isEnabled() is False
    assert dialog.btn_install_deps.isEnabled() is True
    assert dialog.btn_download_model.isEnabled() is False # Depends on package install first
    
    # Change deps checking to return success, model missing
    monkeypatch.setattr(
        "yaku.ui.audio_setup_dialog.check_audio_dependencies",
        lambda: AudioDepsStatus(ok=True, missing=[], installed=[], message="Audio Pack is installed")
    )
    monkeypatch.setattr(
        "yaku.ui.audio_setup_dialog.check_model_available",
        lambda cfg: ModelStatus(ok=False, model_id="dummy", local_path=None, message="Missing model")
    )
    
    # Re-run checks
    dialog.perform_checks()
    
    # Assert state updates accordingly
    assert dialog.btn_continue.isEnabled() is False
    assert dialog.btn_install_deps.isEnabled() is False
    assert dialog.btn_download_model.isEnabled() is True
    
    # Change both to success
    monkeypatch.setattr(
        "yaku.ui.audio_setup_dialog.check_model_available",
        lambda cfg: ModelStatus(ok=True, model_id="dummy", local_path="models/asr", message="Model found")
    )
    
    # Re-run checks
    dialog.perform_checks()
    
    # Now continue should be enabled
    assert dialog.btn_continue.isEnabled() is True
    # Device should be auto-selected and saved
    assert config.audio.device_id == 0
    assert config.audio.device_name == "Default Input"


def test_audio_setup_dialog_gpu_option(monkeypatch):
    app = get_app()
    config = YakuConfig()
    config.audio.device = "cpu"
    
    from PyQt6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", MagicMock())
    monkeypatch.setattr(QMessageBox, "critical", MagicMock())
    monkeypatch.setattr(QMessageBox, "warning", MagicMock())
    
    monkeypatch.setattr(
        "yaku.ui.audio_setup_dialog.choose_default_audio_device",
        lambda src: None
    )
    monkeypatch.setattr(
        "yaku.ui.audio_setup_dialog.check_audio_dependencies",
        lambda: AudioDepsStatus(ok=False, missing=[], installed=[], message="Audio Pack is missing")
    )
    
    from yaku.ui.audio_setup_dialog import AudioSetupDialog
    dialog = AudioSetupDialog(config)
    
    # 1. Initially unchecked (since device == "cpu")
    assert dialog.chk_use_gpu.isChecked() is False
    
    # 2. Check it -> config updates to "cuda"
    dialog.chk_use_gpu.setChecked(True)
    assert config.audio.device == "cuda"
    
    # 3. Mock install_audio_pack and make worker run synchronously
    from yaku.audio.install import AudioInstallResult
    mock_install = MagicMock(return_value=AudioInstallResult(ok=True, message="Success"))
    monkeypatch.setattr("yaku.audio.install.install_audio_pack", mock_install)
    
    from PyQt6.QtCore import QThread
    monkeypatch.setattr(QThread, "start", lambda self: self.run())
    
    dialog.start_install_deps()
    
    # Assert it was called with use_gpu=True
    mock_install.assert_called_once_with(use_gpu=True)
    
    # Uncheck it -> config updates to "cpu"
    dialog.chk_use_gpu.setChecked(False)
    assert config.audio.device == "cpu"
    
    # Try install again with GPU unchecked
    mock_install.reset_mock()
    dialog.start_install_deps()
    mock_install.assert_called_once_with(use_gpu=False)



def test_settings_panel_gpu_option(monkeypatch):
    app = get_app()
    config = YakuConfig()
    config.audio.device = "cpu"
    
    from PyQt6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", MagicMock(return_value=QMessageBox.StandardButton.No))
    monkeypatch.setattr(QMessageBox, "information", MagicMock())
    monkeypatch.setattr(QMessageBox, "critical", MagicMock())
    monkeypatch.setattr(QMessageBox, "warning", MagicMock())
    
    from yaku.ui.settings_panel import SettingsPanel
    
    panel = SettingsPanel(config, config_path=None)
    
    # 1. Initially unchecked (since device == "cpu")
    assert panel._use_gpu_chk.isChecked() is False
    
    # 2. Check it -> save -> updates device to "cuda"
    panel._use_gpu_chk.setChecked(True)
    panel._save()
    assert config.audio.device == "cuda"
    
    # 3. Uncheck it -> save -> updates device to "cpu"
    panel._use_gpu_chk.setChecked(False)
    panel._save()
    assert config.audio.device == "cpu"


def test_settings_panel_gpu_toggled_installs(monkeypatch):
    app = get_app()
    config = YakuConfig()
    config.audio.device = "cpu"
    
    # Mock deps checking to return success so it prompts to reinstall
    monkeypatch.setattr(
        "yaku.audio.deps.check_audio_dependencies",
        lambda: AudioDepsStatus(ok=True, missing=[], installed=[], message="Audio Pack is installed")
    )
    
    from yaku.ui.settings_panel import SettingsPanel
    from PyQt6.QtWidgets import QMessageBox
    from PyQt6.QtCore import QThread
    
    # Mock MessageBox.question to return Yes
    mock_question = MagicMock(return_value=QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "question", mock_question)
    monkeypatch.setattr(QMessageBox, "information", MagicMock())
    monkeypatch.setattr(QMessageBox, "critical", MagicMock())
    monkeypatch.setattr(QMessageBox, "warning", MagicMock())
    
    # Mock install_audio_pack
    from yaku.audio.install import AudioInstallResult
    mock_install = MagicMock(return_value=AudioInstallResult(ok=True, message="Success"))
    monkeypatch.setattr("yaku.audio.install.install_audio_pack", mock_install)
    
    # Make QThread start synchronously
    monkeypatch.setattr(QThread, "start", lambda self: self.run())
    
    panel = SettingsPanel(config, config_path=None)
    
    # 1. Check GPU checkbox -> should prompt to install GPU version
    panel._use_gpu_chk.setChecked(True)
    
    # Check that QMessageBox.question was called and mock_install was called with use_gpu=True
    mock_question.assert_called_once()
    mock_install.assert_called_once_with(use_gpu=True)
    
    # 2. Uncheck GPU checkbox -> should prompt to reinstall CPU version
    mock_question.reset_mock()
    mock_install.reset_mock()
    panel._use_gpu_chk.setChecked(False)
    
    mock_question.assert_called_once()
    mock_install.assert_called_once_with(use_gpu=False)


