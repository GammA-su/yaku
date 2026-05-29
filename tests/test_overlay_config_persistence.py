"""Overlay config persistence helpers."""
from __future__ import annotations

from yaku.core.config import YakuConfig, load_config, save_config, update_overlay_geometry


def test_overlay_geometry_update_function():
    config = YakuConfig()

    update_overlay_geometry(config, x=12, y=34, w=560, h=78)

    assert config.v1_overlay.x == 12
    assert config.v1_overlay.y == 34
    assert config.v1_overlay.w == 560
    assert config.v1_overlay.h == 78


def test_overlay_geometry_persists_roundtrip(tmp_path):
    path = tmp_path / "config.yaml"
    config = YakuConfig()
    update_overlay_geometry(config, x=101, y=202, w=303, h=404)

    save_config(config, path)
    loaded = load_config(path)

    assert loaded.v1_overlay.x == 101
    assert loaded.v1_overlay.y == 202
    assert loaded.v1_overlay.w == 303
    assert loaded.v1_overlay.h == 404
