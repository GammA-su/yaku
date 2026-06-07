from __future__ import annotations
import sys
import pytest
from unittest.mock import MagicMock

# Ensure we don't import real packages during tests
# No real torch, faster_whisper, sounddevice, silero_vad, etc.
def test_check_audio_dependencies_lazy(monkeypatch):
    # Verify check_audio_dependencies uses find_spec and doesn't load actual modules
    import importlib.util
    from yaku.audio.deps import check_audio_dependencies
    
    orig_find_spec = importlib.util.find_spec
    called_specs = []
    
    def mock_find_spec(name, package=None):
        called_specs.append(name)
        return None
        
    monkeypatch.setattr(importlib.util, "find_spec", mock_find_spec)
    
    status = check_audio_dependencies()
    assert status.ok is False
    assert len(status.missing) > 0
    assert any(name in called_specs for name in ("sounddevice", "numpy", "faster_whisper", "silero_vad"))


def test_install_command_generation(monkeypatch):
    from yaku.audio.install import build_audio_install_command
    
    # 1. Normal mode (not frozen)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    # Mock shutil.which to find "uv"
    import shutil
    monkeypatch.setattr(shutil, "which", lambda cmd: "/usr/bin/uv" if cmd == "uv" else None)
    
    cmd = build_audio_install_command()
    # Should generate either uv pip install or python -m pip install
    assert cmd is not None
    assert any("pip" in c for c in cmd)


def test_packaged_build_install_gives_message(monkeypatch):
    from yaku.audio.install import install_audio_pack
    
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    
    res = install_audio_pack()
    assert res.ok is False
    assert "packaged build" in res.message


def test_model_manager_reports_missing_cleanly():
    from yaku.core.config import YakuConfig
    from yaku.audio.model_manager import check_model_available
    
    config = YakuConfig()
    config.audio.local_model_path = "non_existent_path_to_model"
    
    status = check_model_available(config)
    assert status.ok is False
    assert "does not exist" in status.message


def test_no_hardcoded_autotranslator_in_code():
    # Make sure we don't import or reference AutoTranslator anywhere
    import yaku.audio.deps
    import yaku.audio.install
    import yaku.audio.model_manager
    
    for module in (yaku.audio.deps, yaku.audio.install, yaku.audio.model_manager):
        filename = module.__file__
        with open(filename, encoding="utf-8") as f:
            content = f.read()
            assert "AutoTranslator" not in content or "AutoTranslator isolation" in content, \
                f"AutoTranslator reference found in {filename}"


def test_install_command_generation_gpu(monkeypatch):
    from yaku.audio.install import build_audio_install_command
    import shutil
    
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    
    # 1. Test UV installer with GPU
    monkeypatch.setattr(shutil, "which", lambda cmd: "/usr/bin/uv" if cmd == "uv" else None)
    cmd = build_audio_install_command(use_gpu=True)
    assert cmd is not None
    assert "--extra-index-url" in cmd
    assert "https://download.pytorch.org/whl/cu124" in cmd
    assert "--force-reinstall" in cmd
    assert "torch==2.6.0+cu124" in cmd
    assert "torchaudio==2.6.0+cu124" in cmd
    
    # 2. Test standard pip installer with GPU
    monkeypatch.setattr(shutil, "which", lambda cmd: None)
    cmd = build_audio_install_command(use_gpu=True)
    assert cmd is not None
    assert "--extra-index-url" in cmd
    assert "https://download.pytorch.org/whl/cu124" in cmd
    assert "--force-reinstall" in cmd
    assert "torch==2.6.0+cu124" in cmd
    assert "torchaudio==2.6.0+cu124" in cmd

