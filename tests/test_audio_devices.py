from __future__ import annotations
import sys
import pytest
from unittest.mock import MagicMock

def test_audio_device_parsing(monkeypatch):
    # Fake sounddevice query_devices
    mock_sd = MagicMock()
    mock_sd.query_devices.return_value = [
        {"name": "Realtek Microphone", "max_input_channels": 2, "default_samplerate": 48000.0, "hostapi": 0},
        {"name": "Steam Streaming Speakers (WASAPI Loopback)", "max_input_channels": 2, "default_samplerate": 48000.0, "hostapi": 1},
        {"name": "Oculus Microphone", "max_input_channels": 1, "default_samplerate": 44100.0, "hostapi": 0},
    ]
    mock_sd.query_hostapis.return_value = [
        {"name": "MME"},
        {"name": "Windows WASAPI"}
    ]
    mock_sd.default.device = [0, 0]
    
    # Inject fake sounddevice module into sys.modules and yaku.audio.capture
    monkeypatch.setitem(sys.modules, "sounddevice", mock_sd)
    import yaku.audio.capture
    monkeypatch.setattr(yaku.audio.capture, "sd", mock_sd)
    
    devices = yaku.audio.capture.list_audio_devices()
    
    assert len(devices) == 3
    assert devices[0].name == "Realtek Microphone"
    assert devices[0].is_loopback is False
    assert devices[0].is_default is True
    
    assert devices[1].name == "Steam Streaming Speakers (WASAPI Loopback)"
    assert devices[1].is_loopback is True
    
    # Auto chooses loopback first
    best_auto = yaku.audio.capture.choose_default_audio_device("auto")
    assert best_auto is not None
    assert best_auto.is_loopback is True
    assert "Loopback" in best_auto.name
    
    # Mic chooses non-loopback input
    best_mic = yaku.audio.capture.choose_default_audio_device("mic")
    assert best_mic is not None
    assert best_mic.is_loopback is False
    assert "Microphone" in best_mic.name
    
    # Loopback chooses loopback
    best_loop = yaku.audio.capture.choose_default_audio_device("loopback")
    assert best_loop is not None
    assert best_loop.is_loopback is True


def test_no_sounddevice_installed(monkeypatch):
    import yaku.audio.capture
    monkeypatch.setattr(yaku.audio.capture, "sd", None)
    
    devices = yaku.audio.capture.list_audio_devices()
    assert devices == []
    
    best = yaku.audio.capture.choose_default_audio_device("auto")
    assert best is None
