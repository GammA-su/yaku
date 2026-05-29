"""Tests for config persistence helpers — no GUI or display required."""
from __future__ import annotations

from pathlib import Path

import pytest

from yaku.core.config import (
    YakuConfig,
    load_config,
    save_config,
    update_ocr_region,
    update_replacement_region,
    update_window_selection,
)
from yaku.core.image_utils import NormalizedRect, Rect


# ---------------------------------------------------------------------------
# OCR region
# ---------------------------------------------------------------------------

def test_ocr_region_persisted(tmp_path):
    config = YakuConfig()
    update_ocr_region(config, Rect(x=100, y=200, w=300, h=50))

    cfg = tmp_path / "c.yaml"
    save_config(config, cfg)
    loaded = load_config(cfg)

    assert loaded.ocr.region.x == 100
    assert loaded.ocr.region.y == 200
    assert loaded.ocr.region.w == 300
    assert loaded.ocr.region.h == 50


def test_ocr_region_zero_values_persisted(tmp_path):
    config = YakuConfig()
    update_ocr_region(config, Rect(x=0, y=0, w=0, h=0))
    cfg = tmp_path / "c.yaml"
    save_config(config, cfg)
    loaded = load_config(cfg)
    assert loaded.ocr.region.w == 0
    assert loaded.ocr.region.h == 0


def test_ocr_region_update_does_not_clobber_other_fields(tmp_path):
    config = YakuConfig()
    config.app.target_lang = "de"
    config.translator.backend = "deepl"  # type: ignore[assignment]
    update_ocr_region(config, Rect(x=50, y=100, w=200, h=40))

    cfg = tmp_path / "c.yaml"
    save_config(config, cfg)
    loaded = load_config(cfg)

    assert loaded.app.target_lang == "de"
    assert loaded.translator.backend == "deepl"
    assert loaded.ocr.region.x == 50


# ---------------------------------------------------------------------------
# Replacement region (normalised)
# ---------------------------------------------------------------------------

def test_replacement_region_normalized_correctly(tmp_path):
    config = YakuConfig()
    norm = NormalizedRect(x_ratio=0.1, y_ratio=0.7, w_ratio=0.8, h_ratio=0.15)
    update_replacement_region(config, norm)

    cfg = tmp_path / "c.yaml"
    save_config(config, cfg)
    loaded = load_config(cfg)
    rr = loaded.v2_mirror.replacement_region

    assert abs(rr.x_ratio - 0.1) < 1e-6
    assert abs(rr.y_ratio - 0.7) < 1e-6
    assert abs(rr.w_ratio - 0.8) < 1e-6
    assert abs(rr.h_ratio - 0.15) < 1e-6


def test_replacement_region_boundary_values(tmp_path):
    config = YakuConfig()
    update_replacement_region(
        config,
        NormalizedRect(x_ratio=0.0, y_ratio=0.0, w_ratio=1.0, h_ratio=1.0),
    )
    cfg = tmp_path / "c.yaml"
    save_config(config, cfg)
    loaded = load_config(cfg)
    rr = loaded.v2_mirror.replacement_region
    assert rr.x_ratio == 0.0
    assert rr.w_ratio == 1.0


def test_replacement_region_update_does_not_clobber_other_fields(tmp_path):
    config = YakuConfig()
    config.app.mode = "v2-mirror"  # type: ignore[assignment]
    update_replacement_region(config, NormalizedRect(0.05, 0.8, 0.9, 0.1))

    cfg = tmp_path / "c.yaml"
    save_config(config, cfg)
    loaded = load_config(cfg)

    assert loaded.app.mode == "v2-mirror"
    assert abs(loaded.v2_mirror.replacement_region.x_ratio - 0.05) < 1e-6


# ---------------------------------------------------------------------------
# Window selection
# ---------------------------------------------------------------------------

def test_window_selection_persisted(tmp_path):
    config = YakuConfig()
    update_window_selection(config, hwnd=99999, title_contains="My VN Game")

    cfg = tmp_path / "c.yaml"
    save_config(config, cfg)
    loaded = load_config(cfg)

    assert loaded.window.hwnd == 99999
    assert loaded.window.title_contains == "My VN Game"


def test_window_selection_null_hwnd(tmp_path):
    config = YakuConfig()
    update_window_selection(config, hwnd=None, title_contains="partial title")

    cfg = tmp_path / "c.yaml"
    save_config(config, cfg)
    loaded = load_config(cfg)

    assert loaded.window.hwnd is None
    assert loaded.window.title_contains == "partial title"


# ---------------------------------------------------------------------------
# Config path override
# ---------------------------------------------------------------------------

def test_config_path_override_creates_parent_dirs(tmp_path):
    deep = tmp_path / "a" / "b" / "c" / "config.yaml"
    config = YakuConfig()
    config.app.mode = "v2-mirror"  # type: ignore[assignment]
    save_config(config, deep)

    assert deep.exists()
    loaded = load_config(deep)
    assert loaded.app.mode == "v2-mirror"


def test_config_path_override_independent_files(tmp_path):
    path_a = tmp_path / "a.yaml"
    path_b = tmp_path / "b.yaml"

    cfg_a = YakuConfig()
    cfg_a.app.target_lang = "de"
    save_config(cfg_a, path_a)

    cfg_b = YakuConfig()
    cfg_b.app.target_lang = "ja"
    save_config(cfg_b, path_b)

    loaded_a = load_config(path_a)
    loaded_b = load_config(path_b)

    assert loaded_a.app.target_lang == "de"
    assert loaded_b.app.target_lang == "ja"


def test_load_config_missing_file_raises():
    from yaku.core.errors import ConfigError
    with pytest.raises(ConfigError):
        load_config(Path("/nonexistent/path/config.yaml"))


# ---------------------------------------------------------------------------
# Multiple updates before a single save
# ---------------------------------------------------------------------------

def test_multiple_updates_before_save(tmp_path):
    config = YakuConfig()
    update_ocr_region(config, Rect(10, 20, 100, 50))
    update_window_selection(config, 42, "SomeGame")
    update_replacement_region(config, NormalizedRect(0.1, 0.7, 0.8, 0.2))

    cfg = tmp_path / "c.yaml"
    save_config(config, cfg)
    loaded = load_config(cfg)

    assert loaded.ocr.region.x == 10
    assert loaded.window.hwnd == 42
    assert loaded.window.title_contains == "SomeGame"
    assert abs(loaded.v2_mirror.replacement_region.x_ratio - 0.1) < 1e-6
