"""Pydantic config models, YAML load/save, and CLI override application."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Optional

import yaml
from pydantic import BaseModel, Field

from yaku.core.errors import (
    ConfigError,
    InvalidBackendError,
    InvalidModeError,
    InvalidRenderModeError,
)

if TYPE_CHECKING:
    from yaku.core.image_utils import NormalizedRect, Rect


class AppConfig(BaseModel):
    mode: Literal["v1-overlay", "v2-mirror"] = "v1-overlay"
    target_lang: str = "en"
    tick_ms: int = 300
    debug: bool = False


class WindowConfig(BaseModel):
    title_contains: str = ""
    hwnd: Optional[int] = None
    capture_backend: Literal["auto", "dxcam", "mss", "win32"] = "mss"


class OCRRegion(BaseModel):
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0


class OCRConfig(BaseModel):
    backend: Literal["manga_ocr", "paddleocr", "dummy"] = "paddleocr"
    region: OCRRegion = Field(default_factory=OCRRegion)
    hash_threshold: int = 0
    min_chars: int = 1


class LlamaCppConfig(BaseModel):
    base_url: str = "http://127.0.0.1:8080/v1"
    model: str = "qwen-local"
    temperature: float = 0.2
    max_tokens: int = 256


class DeepLConfig(BaseModel):
    api_key_env: str = "DEEPL_API_KEY"
    target_lang: str = "EN-US"
    formality: str = "default"
    use_context: bool = True


class TranslatorConfig(BaseModel):
    backend: Literal["llama_cpp", "deepl"] = "llama_cpp"
    context_lines: int = 3
    llama_cpp: LlamaCppConfig = Field(default_factory=LlamaCppConfig)
    deepl: DeepLConfig = Field(default_factory=DeepLConfig)


class GlossaryEntry(BaseModel):
    source: str
    target: str
    note: str = ""


class GlossaryConfig(BaseModel):
    enabled: bool = True
    entries: list[GlossaryEntry] = Field(default_factory=list)


class V1OverlayConfig(BaseModel):
    x: int = 100
    y: int = 700
    w: int = 900
    h: int = 120
    locked: bool = False
    click_through: bool = True
    opacity: float = 0.85
    font_family: str = "Arial"
    font_size: int = 28
    background_opacity: float = 0.55
    text_outline: bool = True
    save_geometry_on_exit: bool = True
    show_source_in_debug: bool = True
    show_status_badge: bool = True
    pending_behavior: Literal["keep_previous", "show_pending"] = "keep_previous"
    duplicate_suppression_window: int = 3


class ReplacementRegion(BaseModel):
    x_ratio: float = 0.08
    y_ratio: float = 0.72
    w_ratio: float = 0.84
    h_ratio: float = 0.20


class InpaintConfig(BaseModel):
    backend: str = "opencv"
    mask_padding: int = 6
    method: Literal["telea", "ns"] = "telea"
    radius: int = 3
    fallback_to_mask_text: bool = True
    debug_draw_mask: bool = False


class AITextEditConfig(BaseModel):
    enabled: bool = False
    backend: str = "external_http"
    endpoint: str = "http://127.0.0.1:7860"
    timeout_sec: int = 30
    fallback: Literal["inpaint-text", "mask-text"] = "inpaint-text"
    deterministic_text_after_ai: bool = True


class V2MirrorConfig(BaseModel):
    fullscreen: bool = False
    preserve_aspect_ratio: bool = True
    forward_input: bool = True
    input_focus_mode: Literal[
        "send_input_only", "focus_then_send", "disabled"
    ] = "send_input_only"
    replacement_region: ReplacementRegion = Field(default_factory=ReplacementRegion)
    render_mode: Literal["mask-text", "inpaint-text", "ai-text-edit"] = "mask-text"
    inpaint: InpaintConfig = Field(default_factory=InpaintConfig)
    ai_text_edit: AITextEditConfig = Field(default_factory=AITextEditConfig)


class CacheConfig(BaseModel):
    sqlite_path: str = "out/yaku_cache.sqlite3"
    cache_translations: bool = True
    cache_edited_frames: bool = True


class YakuConfig(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    window: WindowConfig = Field(default_factory=WindowConfig)
    ocr: OCRConfig = Field(default_factory=OCRConfig)
    translator: TranslatorConfig = Field(default_factory=TranslatorConfig)
    v1_overlay: V1OverlayConfig = Field(default_factory=V1OverlayConfig)
    v2_mirror: V2MirrorConfig = Field(default_factory=V2MirrorConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    glossary: GlossaryConfig = Field(default_factory=GlossaryConfig)


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------

def load_config(path: str | Path) -> YakuConfig:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    with open(path, encoding="utf-8") as fh:
        data: dict[str, Any] = yaml.safe_load(fh) or {}
    try:
        return YakuConfig.model_validate(data)
    except Exception as exc:
        raise ConfigError(f"Invalid config at {path}: {exc}") from exc


def save_config(config: YakuConfig, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(config.model_dump(), fh, default_flow_style=False, allow_unicode=True)


# ---------------------------------------------------------------------------
# CLI override
# ---------------------------------------------------------------------------

_VALID_MODES: frozenset[str] = frozenset({"v1-overlay", "v2-mirror"})
_VALID_RENDER_MODES: frozenset[str] = frozenset({"mask-text", "inpaint-text", "ai-text-edit"})
_TRANSLATOR_CLI_MAP: dict[str, str] = {"llama-cpp": "llama_cpp", "deepl": "deepl"}


def apply_cli_overrides(config: YakuConfig, args: Any) -> None:
    """Mutate *config* in-place according to parsed CLI arguments."""

    mode: str | None = getattr(args, "mode", None)
    if mode is not None:
        if mode not in _VALID_MODES:
            raise InvalidModeError(
                f"Invalid mode '{mode}'. Valid modes: {', '.join(sorted(_VALID_MODES))}"
            )
        config.app.mode = mode  # type: ignore[assignment]

    translator: str | None = getattr(args, "translator", None)
    if translator is not None:
        normalized = _TRANSLATOR_CLI_MAP.get(translator, translator)
        if normalized not in {"deepl", "llama_cpp"}:
            raise InvalidBackendError(
                f"Invalid translator '{translator}'. Valid choices: deepl, llama-cpp"
            )
        config.translator.backend = normalized  # type: ignore[assignment]

    target_lang: str | None = getattr(args, "target_lang", None)
    if target_lang is not None:
        config.app.target_lang = target_lang

    render_mode: str | None = getattr(args, "render_mode", None)
    if render_mode is not None:
        if render_mode not in _VALID_RENDER_MODES:
            raise InvalidRenderModeError(
                f"Invalid render mode '{render_mode}'. "
                f"Valid modes: {', '.join(sorted(_VALID_RENDER_MODES))}"
            )
        config.v2_mirror.render_mode = render_mode  # type: ignore[assignment]

    if getattr(args, "debug", False):
        config.app.debug = True


# ---------------------------------------------------------------------------
# Selective field updaters — used by CLI setup commands
# ---------------------------------------------------------------------------

def update_ocr_region(config: YakuConfig, rect: "Rect") -> None:
    """Write pixel-space *rect* into ``config.ocr.region``."""
    config.ocr.region.x = rect.x
    config.ocr.region.y = rect.y
    config.ocr.region.w = rect.w
    config.ocr.region.h = rect.h


def update_replacement_region(config: YakuConfig, norm: "NormalizedRect") -> None:
    """Write normalised *norm* into ``config.v2_mirror.replacement_region``."""
    config.v2_mirror.replacement_region.x_ratio = norm.x_ratio
    config.v2_mirror.replacement_region.y_ratio = norm.y_ratio
    config.v2_mirror.replacement_region.w_ratio = norm.w_ratio
    config.v2_mirror.replacement_region.h_ratio = norm.h_ratio


def update_window_selection(
    config: YakuConfig,
    hwnd: int | None,
    title_contains: str,
) -> None:
    """Write window-selection fields into ``config.window``."""
    config.window.hwnd = hwnd
    config.window.title_contains = title_contains


def update_overlay_geometry(
    config: YakuConfig,
    x: int,
    y: int,
    w: int,
    h: int,
) -> None:
    """Write current overlay geometry back into ``config.v1_overlay``."""
    config.v1_overlay.x = x
    config.v1_overlay.y = y
    config.v1_overlay.w = w
    config.v1_overlay.h = h
