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
    mode: Literal["v1-overlay", "v2-mirror", "v3-audio-overlay", "v1-overlay-max", "v4-yomitan", "v1-yomitan"] = "v1-overlay"
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
    port: int = 8080
    base_url: str = "http://127.0.0.1:8080/v1"
    model: str = "qwen-local"
    temperature: float = 0.2
    max_tokens: int = 256
    use_hosted: bool = False
    api_key_env: str = "longapikey"
    disable_reasoning: bool = True


class DeepLConfig(BaseModel):
    api_key: Optional[str] = None
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


class TextRegion(BaseModel):
    x_ratio: float = 0.12
    y_ratio: float = 0.76
    w_ratio: float = 0.76
    h_ratio: float = 0.14


class RenderTextConfig(BaseModel):
    font_path: Optional[str] = None
    font_family: str = "Noto Sans"
    font_size: Optional[int] = None
    auto_fit: bool = True
    min_font_size: int = 14
    max_font_size: int = 42
    line_spacing: float = 1.15
    stroke_width: int = 2
    sample_style_from_source: bool = True
    fallback_fill: list[int] = Field(default_factory=lambda: [255, 255, 255])
    fallback_stroke: list[int] = Field(default_factory=lambda: [0, 0, 0])


class InpaintConfig(BaseModel):
    backend: str = "opencv"
    mask_padding: int = 4
    method: Literal["telea", "ns"] = "telea"
    radius: int = 3
    fallback_to_mask_text: bool = True
    debug_draw_mask: bool = False


class AITextEditConfig(BaseModel):
    enabled: bool = False
    backend: str = "external_http"
    endpoint: str = "http://127.0.0.1:7861/edit"
    timeout_sec: int = 30
    fallback: Literal["inpaint-text", "mask-text"] = "inpaint-text"
    deterministic_text_after_ai: bool = True
    send_style_hint: bool = True
    save_debug_payloads: bool = False
    debug_dir: str = "out/debug/ai_text_edit"
    allow_resize_output: bool = True


class V2MirrorConfig(BaseModel):
    fullscreen: bool = False
    preserve_aspect_ratio: bool = True
    forward_input: bool = True
    input_focus_mode: Literal[
        "send_input_only", "focus_then_send", "disabled"
    ] = "send_input_only"
    replacement_region: ReplacementRegion = Field(default_factory=ReplacementRegion)
    text_region: TextRegion = Field(default_factory=TextRegion)
    render_mode: Literal["mask-text", "inpaint-text", "ai-text-edit"] = "inpaint-text"
    inpaint: InpaintConfig = Field(default_factory=InpaintConfig)
    render_text: RenderTextConfig = Field(default_factory=RenderTextConfig)
    ai_text_edit: AITextEditConfig = Field(default_factory=AITextEditConfig)


class V1OverlayMaxOverlayConfig(BaseModel):
    font_family: str = "Arial"
    font_size: int = 13
    max_width: int = 260
    padding: int = 6
    opacity: float = 0.82
    background: list[int] = Field(default_factory=lambda: [0, 0, 0])
    foreground: list[int] = Field(default_factory=lambda: [255, 255, 255])
    anchor: str = "right"
    avoid_offscreen: bool = True
    show_source_in_debug: bool = True


class V1OverlayMaxCacheConfig(BaseModel):
    enabled: bool = True


class V1OverlayMaxConfig(BaseModel):
    enabled: bool = True
    scan_scope: str = "window"
    scan_interval_ms: int = 1500
    hash_threshold: int = 6
    max_regions: int = 30
    min_text_chars: int = 1
    japanese_only: bool = True
    translate_individual_regions: bool = True
    merge_nearby_boxes: bool = True
    merge_distance_px: int = 16
    require_ocr_boxes: bool = True
    force_paddleocr_warning: bool = True
    overlay: V1OverlayMaxOverlayConfig = Field(default_factory=V1OverlayMaxOverlayConfig)
    cache: V1OverlayMaxCacheConfig = Field(default_factory=V1OverlayMaxCacheConfig)


class V4YomitanRegionConfig(BaseModel):
    x: int = 0
    y: int = 0
    w: int = 800
    h: int = 300
    is_set: bool = False


class V4YomitanDictionariesConfig(BaseModel):
    enabled: bool = True
    dictionary_dir: str = "dictionaries"
    index_path: str = "out/yomitan_index.sqlite3"
    auto_import_on_start: bool = True
    imported_manifest_path: str = "out/yomitan_imported.json"
    max_glossary_items: int = 6


class V4YomitanPopupConfig(BaseModel):
    font_family: str = "Arial"
    font_size: int = 14
    max_width: int = 520
    max_height: int = 420
    opacity: float = 0.95
    show_reading: bool = True
    show_frequency: bool = True
    show_pitch: bool = True
    show_tags: bool = True
    show_source_sentence: bool = True
    show_dictionary_name: bool = True


class V4YomitanDebugConfig(BaseModel):
    save_ocr_region: bool = False
    debug_dir: str = "out/debug/v4_yomitan"


class V4YomitanConfig(BaseModel):
    enabled: bool = True
    region: V4YomitanRegionConfig = Field(default_factory=V4YomitanRegionConfig)
    scan_scope: str = "region"
    scan_interval_ms: int = 1000
    hash_threshold: int = 6
    ocr_backend_required: str = "paddleocr"
    japanese_only: bool = True
    tokenizer: str = "simple"
    hover_trigger: str = "none"
    lookup_on_hover: bool = True
    lookup_on_click: bool = True
    max_hover_results: int = 8
    dictionaries: V4YomitanDictionariesConfig = Field(default_factory=V4YomitanDictionariesConfig)
    popup: V4YomitanPopupConfig = Field(default_factory=V4YomitanPopupConfig)
    debug: V4YomitanDebugConfig = Field(default_factory=V4YomitanDebugConfig)


class MetricsConfig(BaseModel):
    enabled: bool = True
    log_jsonl: bool = True
    log_path: str = "out/metrics/yaku_latency.jsonl"
    include_text_preview: bool = True
    preview_chars: int = 80
    slow_event_ms: int = 1500


class CacheConfig(BaseModel):
    sqlite_path: str = "out/yaku_cache.sqlite3"
    cache_translations: bool = True
    cache_edited_frames: bool = True


class AudioConfig(BaseModel):
    enabled: bool = True
    backend: Literal["kotoba_whisper"] = "kotoba_whisper"
    source: Literal["auto", "mic", "loopback"] = "auto"
    device_name: Optional[str] = None
    device_id: Optional[int] = None
    sample_rate: int = 16000
    chunk_seconds: float = 7.0
    vad_threshold: float = 0.30
    min_speech_ms: int = 350
    min_silence_ms: int = 450
    merge_speech_gap_ms: int = 900
    vad_tail_ms: int = 350
    vad_enabled: bool = True
    min_transcript_chars: int = 2
    dedupe_window: int = 5
    language: str = "ja"
    model: str = "kotoba-tech/kotoba-whisper-v2.0-faster"
    device: str = "auto"
    compute_type: str = "auto"
    local_model_path: Optional[str] = None
    download_models: bool = True
    model_cache_dir: str = "models/asr"
    install_state: Literal["auto", "installed", "missing", "failed"] = "auto"
    auto_install_prompt: bool = True
    optional_dependencies_group: str = "audio"


class YakuConfig(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    window: WindowConfig = Field(default_factory=WindowConfig)
    ocr: OCRConfig = Field(default_factory=OCRConfig)
    translator: TranslatorConfig = Field(default_factory=TranslatorConfig)
    v1_overlay: V1OverlayConfig = Field(default_factory=V1OverlayConfig)
    v1_overlay_max: V1OverlayMaxConfig = Field(default_factory=V1OverlayMaxConfig)
    v4_yomitan: V4YomitanConfig = Field(default_factory=V4YomitanConfig)
    v2_mirror: V2MirrorConfig = Field(default_factory=V2MirrorConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    glossary: GlossaryConfig = Field(default_factory=GlossaryConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)



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

_VALID_MODES: frozenset[str] = frozenset({"v1-overlay", "v2-mirror", "v3-audio-overlay", "v1-overlay-max", "v4-yomitan", "v1-yomitan"})
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

    audio_source: str | None = getattr(args, "audio_source", None)
    if audio_source is not None:
        if audio_source not in {"auto", "mic", "loopback"}:
            raise ConfigError(f"Invalid audio source '{audio_source}'. Valid: auto, mic, loopback")
        config.audio.source = audio_source  # type: ignore[assignment]

    audio_device_name: str | None = getattr(args, "audio_device_name", None)
    if audio_device_name is not None:
        config.audio.device_name = audio_device_name

    vad_threshold: float | None = getattr(args, "vad_threshold", None)
    if vad_threshold is not None:
        config.audio.vad_threshold = vad_threshold

    min_speech_ms: int | None = getattr(args, "min_speech_ms", None)
    if min_speech_ms is not None:
        config.audio.min_speech_ms = min_speech_ms

    min_silence_ms: int | None = getattr(args, "min_silence_ms", None)
    if min_silence_ms is not None:
        config.audio.min_silence_ms = min_silence_ms

    merge_speech_gap_ms: int | None = getattr(args, "merge_speech_gap_ms", None)
    if merge_speech_gap_ms is not None:
        config.audio.merge_speech_gap_ms = merge_speech_gap_ms

    vad_tail_ms: int | None = getattr(args, "vad_tail_ms", None)
    if vad_tail_ms is not None:
        config.audio.vad_tail_ms = vad_tail_ms

    max_segment_sec: float | None = getattr(args, "max_segment_sec", None)
    if max_segment_sec is not None:
        config.audio.chunk_seconds = max_segment_sec

    dictionary_dir: str | None = getattr(args, "dictionary_dir", None)
    if dictionary_dir is not None:
        config.v4_yomitan.dictionaries.dictionary_dir = dictionary_dir

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
