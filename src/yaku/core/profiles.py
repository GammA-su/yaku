"""Per-game configuration profiles.

A profile is just a full :class:`~yaku.core.config.YakuConfig` YAML stored under
``profiles/<name>.yaml``.  Running with ``--profile <name>`` loads (or creates)
that file and uses it as the live config, so window selection, OCR region,
overlay geometry, and replacement region are all saved per game.
"""
from __future__ import annotations

import re
from pathlib import Path

from yaku.core.config import YakuConfig, load_config, save_config
from yaku.core.logging import get_logger

_log = get_logger("profiles")

PROFILES_DIR = Path("profiles")
DEFAULT_BASE_CONFIG = Path("configs") / "default.yaml"

_VALID_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_profile_name(name: str) -> str:
    """Return a filesystem-safe profile name (no path separators/traversal).

    Letters, digits, ``.``, ``_`` and ``-`` are kept; any other run of
    characters becomes a single ``-``.  Leading/trailing dots and dashes are
    stripped.  Raises :class:`ValueError` for an empty result.
    """
    cleaned = _VALID_NAME.sub("-", name.strip()).strip(".-")
    if not cleaned:
        raise ValueError(f"Invalid profile name: {name!r}")
    return cleaned


def profile_path(name: str, profiles_dir: Path | str = PROFILES_DIR) -> Path:
    """Return the YAML path for *name* under *profiles_dir*."""
    return Path(profiles_dir) / f"{sanitize_profile_name(name)}.yaml"


def list_profiles(profiles_dir: Path | str = PROFILES_DIR) -> list[str]:
    """Return sorted profile names found in *profiles_dir* (without extension)."""
    directory = Path(profiles_dir)
    if not directory.exists():
        return []
    return sorted(p.stem for p in directory.glob("*.yaml"))


def profile_exists(name: str, profiles_dir: Path | str = PROFILES_DIR) -> bool:
    return profile_path(name, profiles_dir).exists()


def _base_config(base_config_path: Path | str | None) -> YakuConfig:
    """Load the base config to seed a new profile, or fall back to defaults."""
    if base_config_path is not None:
        path = Path(base_config_path)
        if path.exists():
            try:
                return load_config(path)
            except Exception as exc:  # noqa: BLE001 — never block profile creation
                _log.warning("Base config %s unusable (%s); using defaults.", path, exc)
    return YakuConfig()


def create_profile(
    name: str,
    *,
    profiles_dir: Path | str = PROFILES_DIR,
    base_config_path: Path | str | None = DEFAULT_BASE_CONFIG,
    overwrite: bool = False,
) -> tuple[YakuConfig, Path]:
    """Create a new profile seeded from the base config and return it.

    Raises :class:`FileExistsError` if it already exists and *overwrite* is
    ``False``.
    """
    path = profile_path(name, profiles_dir)
    if path.exists() and not overwrite:
        raise FileExistsError(f"Profile already exists: {path}")
    config = _base_config(base_config_path)
    save_config(config, path)
    _log.info("Created profile %s", path)
    return config, path


def resolve_profile(
    name: str,
    *,
    profiles_dir: Path | str = PROFILES_DIR,
    base_config_path: Path | str | None = DEFAULT_BASE_CONFIG,
) -> tuple[YakuConfig, Path]:
    """Load profile *name*, creating it from the base config if it is missing.

    Returns ``(config, path)``.  The returned path is where subsequent
    ``save_config`` calls should write so edits persist to the profile.
    """
    path = profile_path(name, profiles_dir)
    if path.exists():
        return load_config(path), path
    _log.info("Profile %s not found; creating from base config.", path)
    return create_profile(
        name, profiles_dir=profiles_dir, base_config_path=base_config_path
    )
