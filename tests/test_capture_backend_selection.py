"""Tests for capture backend selection."""
from __future__ import annotations

from yaku.core.config import WindowConfig


def test_auto_capture_prefers_mss(monkeypatch):
    import yaku.core.capture as capture

    created: list[str] = []

    class FakeMSS:
        def __init__(self) -> None:
            created.append("mss")

    class FakeDXCam:
        def __init__(self) -> None:
            created.append("dxcam")

    monkeypatch.setattr(capture, "MSSCapture", FakeMSS)
    monkeypatch.setattr(capture, "DXCamCapture", FakeDXCam)

    selected = capture.create_capture(WindowConfig(capture_backend="auto"))

    assert isinstance(selected, FakeMSS)
    assert created == ["mss"]


def test_window_config_defaults_to_mss():
    assert WindowConfig().capture_backend == "mss"
