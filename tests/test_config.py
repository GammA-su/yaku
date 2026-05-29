"""Tests for config loading, CLI overrides, and validation."""
from __future__ import annotations

from pathlib import Path

import pytest

from yaku.core.config import YakuConfig, apply_cli_overrides, load_config
from yaku.core.errors import ConfigError, InvalidBackendError, InvalidModeError

CONFIG_PATH = Path(__file__).parent.parent / "configs" / "default.yaml"


class _Args:
    """Minimal argparse-like namespace."""

    def __init__(self, **kwargs):
        self.mode = kwargs.get("mode", None)
        self.translator = kwargs.get("translator", None)
        self.target_lang = kwargs.get("target_lang", None)
        self.render_mode = kwargs.get("render_mode", None)
        self.debug = kwargs.get("debug", False)


def test_load_default_config():
    config = load_config(CONFIG_PATH)
    assert isinstance(config, YakuConfig)
    assert config.app.mode == "v1-overlay"
    assert config.app.target_lang == "en"
    assert config.app.tick_ms == 300
    assert config.translator.backend == "llama_cpp"
    assert config.ocr.backend == "paddleocr"
    assert config.window.capture_backend == "mss"
    assert config.v2_mirror.render_mode == "mask-text"


def test_cli_override_mode():
    config = load_config(CONFIG_PATH)
    apply_cli_overrides(config, _Args(mode="v2-mirror"))
    assert config.app.mode == "v2-mirror"


def test_cli_override_translator_deepl():
    config = load_config(CONFIG_PATH)
    apply_cli_overrides(config, _Args(translator="deepl"))
    assert config.translator.backend == "deepl"


def test_cli_override_translator_llama_cpp_hyphen():
    config = load_config(CONFIG_PATH)
    apply_cli_overrides(config, _Args(translator="llama-cpp"))
    assert config.translator.backend == "llama_cpp"


def test_cli_override_target_lang():
    config = load_config(CONFIG_PATH)
    apply_cli_overrides(config, _Args(target_lang="de"))
    assert config.app.target_lang == "de"


def test_cli_override_debug():
    config = load_config(CONFIG_PATH)
    config.app.debug = False
    apply_cli_overrides(config, _Args(debug=True))
    assert config.app.debug is True


def test_invalid_mode_raises_useful_error():
    config = load_config(CONFIG_PATH)
    with pytest.raises(InvalidModeError) as exc_info:
        apply_cli_overrides(config, _Args(mode="not-a-mode"))
    assert "not-a-mode" in str(exc_info.value)
    assert "v1-overlay" in str(exc_info.value) or "v2-mirror" in str(exc_info.value)


def test_invalid_translator_raises_useful_error():
    config = load_config(CONFIG_PATH)
    with pytest.raises(InvalidBackendError) as exc_info:
        apply_cli_overrides(config, _Args(translator="gpt-4"))
    assert "gpt-4" in str(exc_info.value)


def test_missing_config_file_raises():
    with pytest.raises(ConfigError):
        load_config(Path("nonexistent_dir/missing.yaml"))
