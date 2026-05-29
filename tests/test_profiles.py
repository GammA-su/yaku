"""Tests for per-game profiles."""
from __future__ import annotations

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
from yaku.core.profiles import (
    create_profile,
    list_profiles,
    profile_exists,
    profile_path,
    resolve_profile,
    sanitize_profile_name,
)


# ---------------------------------------------------------------------------
# Name sanitization
# ---------------------------------------------------------------------------

def test_sanitize_keeps_valid_names():
    assert sanitize_profile_name("my-vn_01.test") == "my-vn_01.test"


def test_sanitize_replaces_spaces_and_specials():
    assert sanitize_profile_name("My Game!! 2") == "My-Game-2"


def test_sanitize_strips_path_traversal():
    # No separators or traversal survive.
    out = sanitize_profile_name("../../etc/passwd")
    assert "/" not in out and "\\" not in out and ".." not in out


def test_sanitize_empty_raises():
    with pytest.raises(ValueError):
        sanitize_profile_name("///")


def test_profile_path_uses_dir_and_extension(tmp_path):
    p = profile_path("game", tmp_path)
    assert p == tmp_path / "game.yaml"


# ---------------------------------------------------------------------------
# Create / resolve
# ---------------------------------------------------------------------------

def test_resolve_creates_missing_profile(tmp_path):
    config, path = resolve_profile("new-game", profiles_dir=tmp_path, base_config_path=None)
    assert path.exists()
    assert path == tmp_path / "new-game.yaml"
    assert isinstance(config, YakuConfig)


def test_resolve_loads_existing_profile(tmp_path):
    _, path = create_profile("g", profiles_dir=tmp_path, base_config_path=None)
    # Mutate on disk so we can prove it was loaded, not recreated.
    cfg = load_config(path)
    cfg.app.target_lang = "de"
    save_config(cfg, path)

    loaded, loaded_path = resolve_profile("g", profiles_dir=tmp_path, base_config_path=None)
    assert loaded_path == path
    assert loaded.app.target_lang == "de"


def test_create_existing_raises_without_overwrite(tmp_path):
    create_profile("dup", profiles_dir=tmp_path, base_config_path=None)
    with pytest.raises(FileExistsError):
        create_profile("dup", profiles_dir=tmp_path, base_config_path=None)


def test_create_overwrite_allowed(tmp_path):
    create_profile("dup", profiles_dir=tmp_path, base_config_path=None)
    # Should not raise.
    create_profile("dup", profiles_dir=tmp_path, base_config_path=None, overwrite=True)


def test_create_from_base_config(tmp_path):
    base = tmp_path / "base.yaml"
    cfg = YakuConfig()
    cfg.app.target_lang = "fr"
    save_config(cfg, base)

    created, _ = create_profile("seeded", profiles_dir=tmp_path, base_config_path=base)
    assert created.app.target_lang == "fr"


def test_list_and_exists(tmp_path):
    assert list_profiles(tmp_path) == []
    create_profile("alpha", profiles_dir=tmp_path, base_config_path=None)
    create_profile("beta", profiles_dir=tmp_path, base_config_path=None)
    assert list_profiles(tmp_path) == ["alpha", "beta"]
    assert profile_exists("alpha", tmp_path)
    assert not profile_exists("gamma", tmp_path)


# ---------------------------------------------------------------------------
# Per-profile persistence of window / OCR / overlay / replacement region
# ---------------------------------------------------------------------------

def test_profile_persists_window_ocr_and_replacement(tmp_path):
    config, path = resolve_profile("persist", profiles_dir=tmp_path, base_config_path=None)

    update_window_selection(config, hwnd=4321, title_contains="Test VN")
    update_ocr_region(config, Rect(x=10, y=20, w=300, h=80))
    update_replacement_region(config, NormalizedRect(0.1, 0.7, 0.8, 0.2))
    config.v1_overlay.x = 55
    config.v1_overlay.y = 66
    save_config(config, path)

    reloaded = load_config(path)
    assert reloaded.window.hwnd == 4321
    assert reloaded.window.title_contains == "Test VN"
    assert (reloaded.ocr.region.x, reloaded.ocr.region.w) == (10, 300)
    assert abs(reloaded.v2_mirror.replacement_region.y_ratio - 0.7) < 1e-6
    assert reloaded.v1_overlay.x == 55
