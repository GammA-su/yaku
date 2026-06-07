from __future__ import annotations
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Mock sounddevice package for tests before importing modules that depend on it
if "sounddevice" not in sys.modules:
    mock_sd = MagicMock()
    mock_sd.query_devices.return_value = [
        {"name": "Default Device", "max_input_channels": 2, "default_samplerate": 44100.0, "hostapi": 0}
    ]
    mock_sd.query_hostapis.return_value = [{"name": "MME"}]
    sys.modules["sounddevice"] = mock_sd

import pytest

from yaku.core.config import YakuConfig
from yaku.core.cache import YakuCache
from yaku.main import build_parser
from yaku.audio.base import BaseASRBackend, ASRResult
from yaku.audio.transcript_cleanup import TranscriptCleanup
from yaku.v3_audio_overlay.audio_overlay_controller import AudioOverlayController
from yaku.v1_overlay.overlay_window import OverlayWindow
from yaku.audio.audio_pipeline import AudioPipeline
from yaku.ui.health_check import check_audio_dependencies, check_autotranslator_isolation
from yaku.ui.app import get_app
from yaku.translate.base import TranslationResult


@pytest.fixture(autouse=True)
def mock_audio_deps(monkeypatch):
    # Mock check_audio_dependencies in yaku.audio.deps to return success
    from yaku.audio.deps import AudioDepsStatus
    import yaku.audio.deps
    monkeypatch.setattr(
        yaku.audio.deps,
        "check_audio_dependencies",
        lambda: AudioDepsStatus(
            ok=True,
            missing=[],
            installed=[],
            message="Audio Pack is installed"
        )
    )



class FakeASRBackend(BaseASRBackend):
    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.transcribe_count = 0

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def transcribe(self, audio, start_sec=0.0) -> ASRResult:
        self.transcribe_count += 1
        return ASRResult(
            text="テスト ASR",
            language="ja",
            start_time=start_sec,
            end_time=start_sec + len(audio) / 16000.0,
            confidence=0.99,
        )


class FakeTranslator:
    def __init__(self) -> None:
        self.backend_name = "fake"
        self.backend_model = "model_fake"
        self.calls = 0

    def translate(self, text, context, target_lang, glossary=None):
        self.calls += 1
        return TranslationResult(
            source_text=text,
            translated_text="Translated " + text,
            target_lang=target_lang,
            backend="fake",
            backend_model="model_fake",
        )


@pytest.fixture
def cache(tmp_path):
    c = YakuCache(tmp_path / "cache.sqlite3")
    yield c
    c.close()


def test_v3_mode_config_loads():
    # Verify that default configuration contains audio block
    config = YakuConfig()
    assert config.audio is not None
    assert config.audio.enabled is True
    assert config.audio.backend == "kotoba_whisper"


def test_cli_accepts_v3_mode():
    parser = build_parser()
    args = parser.parse_args(["--mode", "v3-audio-overlay", "--audio-source", "mic"])
    assert args.mode == "v3-audio-overlay"
    assert args.audio_source == "mic"


def test_transcript_cleanup_suppresses_duplicates_and_empty():
    cleanup = TranscriptCleanup(min_transcript_chars=2, dedupe_window=2)
    # Ignore empty or punctuation-only
    assert cleanup.should_ignore("  ") is True
    assert cleanup.should_ignore("。、！") is True
    
    # Ignore too short
    assert cleanup.should_ignore("あ") is True # 1 char < 2 chars threshold
    
    # Valid
    assert cleanup.should_ignore("こんにちは") is False
    cleanup.add_to_history("こんにちは")
    
    # Duplicate
    assert cleanup.should_ignore("こんにちは") is True
    
    # Valid again after sliding window shift
    cleanup.add_to_history("テストです")
    cleanup.add_to_history("お元気ですか")
    assert cleanup.should_ignore("こんにちは") is False


def test_controller_lifecycle_calls_pipeline(cache):
    get_app()
    config = YakuConfig()
    config.app.mode = "v3-audio-overlay"
    
    # Create fake ASR backend and pipeline
    asr_backend = FakeASRBackend()
    pipeline = AudioPipeline(config.audio, asr_backend)
    
    window = OverlayWindow(config.v1_overlay)
    translator = FakeTranslator()
    
    controller = AudioOverlayController(config, window, pipeline, translator, cache)
    
    # Start controller
    controller.start()
    assert asr_backend.started is True
    
    # Stop controller
    controller.stop()
    assert asr_backend.stopped is True


def test_controller_handles_asr_result_and_updates_overlay(cache):
    get_app()
    config = YakuConfig()
    config.app.mode = "v3-audio-overlay"
    
    asr_backend = FakeASRBackend()
    pipeline = AudioPipeline(config.audio, asr_backend)
    window = OverlayWindow(config.v1_overlay)
    
    res = TranslationResult(
        source_text="日本語テスト",
        translated_text="English Test",
        target_lang="en",
        backend="fake",
    )
    
    controller = AudioOverlayController(config, window, pipeline, FakeTranslator(), cache)
    controller._on_result(res)
    
    assert window.translated_text() == "English Test"
    assert window.source_text() == "日本語テスト"


def test_health_check_warns_on_missing_deps():
    config = YakuConfig()
    config.app.mode = "v3-audio-overlay"
    
    import yaku.ui.health_check
    orig_module_available = yaku.ui.health_check._module_available
    yaku.ui.health_check._module_available = lambda mod: False
    
    try:
        res = check_audio_dependencies(config)
        assert res.status == "warn"
        assert "Missing audio packages" in res.message
    finally:
        yaku.ui.health_check._module_available = orig_module_available


def test_isolation_no_hardcoded_autotranslator():
    # Verify no hardcoded C:\Projecyt\AutoTranslator in Yaku config files
    config_dir = Path(__file__).parent.parent / "configs"
    for config_file in config_dir.glob("*.yaml"):
        content = config_file.read_text(encoding="utf-8")
        assert "AutoTranslator" not in content, f"AutoTranslator absolute path found in config file {config_file}"

    # Also check package configuration files
    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    assert "AutoTranslator" not in pyproject_path.read_text(encoding="utf-8")
    
    config = YakuConfig()
    res = check_autotranslator_isolation(config)
    assert res.status == "pass"


def test_v3_startup_checks_dependencies_missing():
    config = YakuConfig()
    from yaku.audio.deps import AudioDepsStatus
    import yaku.audio.deps
    
    orig = yaku.audio.deps.check_audio_dependencies
    yaku.audio.deps.check_audio_dependencies = lambda: AudioDepsStatus(
        ok=False, missing=[], installed=[], message="Audio Pack is missing"
    )
    
    try:
        pipeline = AudioPipeline(config.audio, FakeASRBackend())
        with pytest.raises(ImportError) as exc_info:
            pipeline.start()
        assert "Audio Pack is missing" in str(exc_info.value)
    finally:
        yaku.audio.deps.check_audio_dependencies = orig


def test_cli_missing_deps_exits_gracefully(monkeypatch):
    import yaku.main
    from yaku.audio.deps import AudioDepsStatus
    import yaku.audio.deps
    
    monkeypatch.setattr(
        yaku.audio.deps,
        "check_audio_dependencies",
        lambda: AudioDepsStatus(ok=False, missing=[], installed=[], message="Audio Pack is missing")
    )
    
    exit_codes = []
    def mock_exit(code):
        exit_codes.append(code)
        raise SystemExit(code)
        
    monkeypatch.setattr(sys, "exit", mock_exit)
    
    with pytest.raises(SystemExit):
        yaku.main.main(["--mode", "v3-audio-overlay", "--run"])
    
    assert 1 in exit_codes
