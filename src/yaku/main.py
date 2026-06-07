"""Yaku CLI entry point."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable


# Monkey-patch paddlex dependency checks to bypass PyInstaller metadata issues
try:
    import paddlex.utils.deps
    paddlex.utils.deps.is_dep_available = lambda *args, **kwargs: True
    paddlex.utils.deps.is_extra_available = lambda *args, **kwargs: True
    paddlex.utils.deps.require_deps = lambda *args, **kwargs: None
    paddlex.utils.deps.require_extra = lambda *args, **kwargs: None
except BaseException:
    pass


# ---------------------------------------------------------------------------
# Graceful-shutdown helper
# ---------------------------------------------------------------------------

def _safe(label: str, fn: Callable[[], None]) -> None:
    """Run a cleanup step, logging (never raising) on failure."""
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 — shutdown must continue
        from yaku.core.logging import get_logger
        get_logger("main").error("Shutdown step '%s' failed: %s", label, exc)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="yaku",
        description="Yaku - AI visual novel translator",
    )
    p.add_argument(
        "--config",
        dest="config_path",
        default=None,
        metavar="PATH",
        help="Config YAML file (default: configs/default.yaml)",
    )
    p.add_argument(
        "--dictionary-dir",
        dest="dictionary_dir",
        default=None,
        metavar="PATH",
        help="Override path to Yomitan dictionary import directory",
    )
    p.add_argument(
        "--profile",
        dest="profile",
        default=None,
        metavar="NAME",
        help="Per-game profile under profiles/<NAME>.yaml (created if missing)",
    )
    p.add_argument(
        "--mode",
        choices=["v1-overlay", "v2-mirror", "v3-audio-overlay", "v1-overlay-max", "v4-yomitan", "v1-yomitan"],
        metavar="MODE",
        help="Operating mode: v1-overlay | v2-mirror | v3-audio-overlay | v1-overlay-max | v4-yomitan | v1-yomitan",
    )
    p.add_argument(
        "--translator",
        choices=["deepl", "llama-cpp"],
        metavar="TRANSLATOR",
        help="Translation backend: deepl | llama-cpp",
    )
    p.add_argument(
        "--target-lang",
        dest="target_lang",
        metavar="LANG",
        help="Target language code (e.g. en, de, EN-US)",
    )
    p.add_argument(
        "--render-mode",
        dest="render_mode",
        choices=["mask-text", "inpaint-text", "ai-text-edit"],
        metavar="RENDER_MODE",
        help="v2-mirror render mode: mask-text | inpaint-text | ai-text-edit",
    )
    p.add_argument(
        "--audio-source",
        dest="audio_source",
        choices=["auto", "mic", "loopback"],
        help="Audio capture source (auto | mic | loopback)",
    )
    p.add_argument(
        "--audio-device-name",
        dest="audio_device_name",
        help="Optional audio device name substring match",
    )
    p.add_argument(
        "--vad-threshold",
        dest="vad_threshold",
        type=float,
        help="VAD speech detection threshold (default: 0.30)",
    )
    p.add_argument(
        "--min-speech-ms",
        dest="min_speech_ms",
        type=int,
        help="VAD minimum speech duration in milliseconds (default: 350)",
    )
    p.add_argument(
        "--min-silence-ms",
        dest="min_silence_ms",
        type=int,
        help="VAD minimum silence duration in milliseconds (default: 450)",
    )
    p.add_argument(
        "--merge-speech-gap-ms",
        dest="merge_speech_gap_ms",
        type=int,
        help="VAD merge speech gap in milliseconds (default: 900)",
    )
    p.add_argument(
        "--vad-tail-ms",
        dest="vad_tail_ms",
        type=int,
        help="VAD speech tail padding in milliseconds (default: 350)",
    )
    p.add_argument(
        "--max-segment-sec",
        dest="max_segment_sec",
        type=float,
        help="Maximum speech segment duration in seconds (default: 7.0)",
    )
    p.add_argument("--debug", action="store_true", help="Enable verbose debug logging")
    p.add_argument(
        "--cli",
        action="store_true",
        help="Use terminal setup instead of GUI setup when combined with --setup.",
    )

    actions = p.add_mutually_exclusive_group()
    actions.add_argument("--run", action="store_true", help="Start the application")
    actions.add_argument(
        "--setup", action="store_true", dest="setup",
        help="Open the GUI setup wizard. Use --setup --cli for terminal setup.",
    )
    actions.add_argument(
        "--health-check", action="store_true", dest="health_check",
        help="Run environment/config health checks and exit",
    )
    actions.add_argument(
        "--pick-window", action="store_true", dest="pick_window",
        help="Interactively pick the target VN window and save to config",
    )
    actions.add_argument(
        "--select-ocr-region", action="store_true", dest="select_ocr_region",
        help="Draw the OCR capture region and save to config",
    )
    actions.add_argument(
        "--select-replacement-region", action="store_true", dest="select_replacement_region",
        help="Draw the v2-mirror text replacement region and save to config",
    )
    actions.add_argument(
        "--check-audio", action="store_true", dest="check_audio",
        help="Check audio dependencies, model availability, and devices, then exit",
    )
    actions.add_argument(
        "--install-audio-pack", action="store_true", dest="install_audio_pack",
        help="Install the optional Audio Pack dependencies, then exit",
    )
    actions.add_argument(
        "--download-asr-model", action="store_true", dest="download_asr_model",
        help="Download the Kotoba Whisper model files, then exit",
    )
    actions.add_argument(
        "--select-yomitan-region", action="store_true", dest="select_yomitan_region",
        help="Draw the Yomitan scan region and save to config, then exit",
    )
    actions.add_argument(
        "--import-yomitan-dictionaries", action="store_true", dest="import_yomitan_dictionaries",
        help="Batch import Yomitan dictionary ZIP files from the dictionary directory, then exit",
    )
    actions.add_argument(
        "--rebuild-yomitan-index", action="store_true", dest="rebuild_yomitan_index",
        help="Rebuild the Yomitan SQLite index and re-import all ZIP dictionaries, then exit",
    )
    return p


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------

def _cmd_run_v1(config, config_path: Path) -> int:
    """Launch the v1-overlay mode."""
    from yaku.core.cache import YakuCache
    from yaku.core.pipeline import V1Pipeline
    from yaku.ui.app import get_app
    from yaku.v1_overlay.overlay_controller import OverlayController
    from yaku.v1_overlay.overlay_window import OverlayWindow

    app = get_app()

    # --- Cache ---
    cache_path = Path(config.cache.sqlite_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache = YakuCache(cache_path)

    # --- OCR backend ---
    from yaku.core.logging import get_logger
    main_logger = get_logger("main")
    try:
        from yaku.ocr.factory import create_ocr
        ocr = create_ocr(config.ocr)
    except Exception as exc:
        main_logger.exception("OCR backend unavailable, using DummyOCR.")
        from yaku.ocr.dummy import DummyOCR
        ocr = DummyOCR("[OCR not configured]")

    # --- Translation backend ---
    try:
        from yaku.translate.factory import create_translator
        translator = create_translator(config.translator)
    except Exception as exc:
        main_logger.exception("Translator backend unavailable, using NullTranslator.")
        from yaku.translate.base import NullTranslator
        translator = NullTranslator()

    # --- Capture backend ---
    capture = None
    try:
        from yaku.core.capture import create_capture
        capture = create_capture(config.window)
    except Exception as exc:
        main_logger.exception("Capture backend unavailable.")

    # --- Pipeline ---
    pipeline = V1Pipeline(ocr, translator, cache, config, capture=capture)

    # --- Overlay window ---
    window = OverlayWindow(config.v1_overlay)
    window.apply_config(config.v1_overlay)
    window.set_debug_visible(config.v1_overlay.show_source_in_debug and config.app.debug)
    window.show()

    # --- Controller ---
    controller = OverlayController(config, window, pipeline, config_path)
    controller.start()

    print(
        "[yaku] v1-overlay running.  "
        "F7=lock  F8=force OCR  Shift+F8=retranslate  "
        "F9=pause  F10=debug  F11=settings  F6=OCR region"
    )
    exit_code = app.exec()

    # --- Graceful shutdown (each step isolated; never aborts the others) ---
    _safe("controller.stop", controller.stop)

    def _save_geometry() -> None:
        if config.v1_overlay.save_geometry_on_exit:
            from yaku.core.config import save_config, update_overlay_geometry
            x, y, w, h = window.current_geometry()
            update_overlay_geometry(config, x, y, w, h)
            save_config(config, config_path)

    _safe("save_geometry", _save_geometry)
    _safe("cache.close", cache.close)
    if capture is not None:
        _safe("capture.close", capture.close)
    if hasattr(translator, "close"):
        _safe("translator.close", translator.close)

    return exit_code


def _cmd_run_v1_max(config, config_path: Path) -> int:
    """Launch the v1-overlay-max mode."""
    from yaku.core.cache import YakuCache
    from yaku.ui.app import get_app
    from yaku.v1_overlay_max.max_overlay_controller import MaxOverlayController
    from yaku.v1_overlay_max.max_overlay_window import MaxOverlayWindow

    app = get_app()

    # --- Cache ---
    cache_path = Path(config.cache.sqlite_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache = YakuCache(cache_path)

    # --- OCR backend ---
    from yaku.core.logging import get_logger
    main_logger = get_logger("main")
    try:
        from yaku.ocr.factory import create_ocr
        ocr = create_ocr(config.ocr)
    except Exception as exc:
        main_logger.exception("OCR backend unavailable, using DummyOCR.")
        from yaku.ocr.dummy import DummyOCR
        ocr = DummyOCR("[OCR not configured]")

    # --- Translation backend ---
    try:
        from yaku.translate.factory import create_translator
        translator = create_translator(config.translator)
    except Exception as exc:
        main_logger.exception("Translator backend unavailable, using NullTranslator.")
        from yaku.translate.base import NullTranslator
        translator = NullTranslator()

    # --- Capture backend ---
    capture = None
    try:
        from yaku.core.capture import create_capture
        capture = create_capture(config.window)
    except Exception as exc:
        main_logger.exception("Capture backend unavailable.")

    # --- Overlay window ---
    window = MaxOverlayWindow(config)
    if capture is not None:
        try:
            ox, oy = capture.source_origin()
            frame = capture.capture_frame()
            dpr = window.devicePixelRatioF()
            if dpr <= 0:
                dpr = 1.0
            window.setGeometry(
                int(ox / dpr),
                int(oy / dpr),
                int(frame.width / dpr),
                int(frame.height / dpr)
            )
        except Exception:
            pass
    window.show()

    # --- Controller ---
    controller = MaxOverlayController(
        config=config,
        window=window,
        ocr=ocr,
        translator=translator,
        cache=cache,
        capture=capture,
        config_path=config_path,
    )
    controller.start()

    print(
        "[yaku] v1-overlay-max running.  "
        "F8=force scan  F9=pause  F10=toggle debug  Esc=exit"
    )
    exit_code = app.exec()

    # --- Graceful shutdown ---
    _safe("controller.stop", controller.stop)
    _safe("cache.close", cache.close)
    if capture is not None:
        _safe("capture.close", capture.close)
    if hasattr(translator, "close"):
        _safe("translator.close", translator.close)

    return exit_code


def _cmd_run_v2(config, config_path: Path) -> int:
    """Launch the v2-mirror mode."""
    from yaku.core.cache import YakuCache
    from yaku.core.pipeline import V2Pipeline
    from yaku.ui.app import get_app
    from yaku.v2_mirror.frame_renderer import FrameRenderer
    from yaku.v2_mirror.mirror_controller import MirrorController
    from yaku.v2_mirror.mirror_window import MirrorWindow

    app = get_app()

    # --- Cache ---
    cache_path = Path(config.cache.sqlite_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache = YakuCache(cache_path)

    # --- OCR backend ---
    from yaku.core.logging import get_logger
    main_logger = get_logger("main")
    try:
        from yaku.ocr.factory import create_ocr
        ocr = create_ocr(config.ocr)
    except Exception as exc:
        main_logger.exception("OCR backend unavailable, using DummyOCR.")
        from yaku.ocr.dummy import DummyOCR
        ocr = DummyOCR("[OCR not configured]")

    # --- Translation backend ---
    try:
        from yaku.translate.factory import create_translator
        translator = create_translator(config.translator)
    except Exception as exc:
        main_logger.exception("Translator backend unavailable, using NullTranslator.")
        from yaku.translate.base import NullTranslator
        translator = NullTranslator()

    # --- Capture backend ---
    capture = None
    try:
        from yaku.core.capture import create_capture
        capture = create_capture(config.window)
    except Exception as exc:
        main_logger.exception("Capture backend unavailable.")

    # --- Pipeline + renderer ---
    pipeline = V2Pipeline(ocr, translator, cache, config, capture=capture)
    renderer = FrameRenderer(config.v2_mirror, cache=cache)

    # --- Input forwarder ---
    from yaku.v2_mirror.input_forward import create_input_forwarder
    forwarder = create_input_forwarder(
        config.v2_mirror.input_focus_mode,
        config.window.hwnd,
        forward_input=config.v2_mirror.forward_input,
    )

    # --- Window ---
    window = MirrorWindow()
    if config.v2_mirror.fullscreen:
        window.showFullScreen()
    else:
        window.show()

    # --- Controller ---
    controller = MirrorController(
        config, window, pipeline, renderer, capture, forwarder, config_path
    )
    controller.start()

    print(
        "[yaku] v2-mirror running.  "
        "F8=force OCR  F9=pause  F10=debug  F11=fullscreen  Esc=exit"
    )
    exit_code = app.exec()

    # --- Graceful shutdown (each step isolated; never aborts the others) ---
    _safe("controller.stop", controller.stop)
    _safe("forwarder.close", forwarder.close)
    _safe("renderer.close", renderer.close)
    _safe("cache.close", cache.close)
    if capture is not None:
        _safe("capture.close", capture.close)
    if hasattr(translator, "close"):
        _safe("translator.close", translator.close)

    return exit_code


def _cmd_run_v3(config, config_path: Path) -> int:
    """Launch the v3-audio-overlay mode."""
    from yaku.core.cache import YakuCache
    from yaku.ui.app import get_app
    from yaku.v1_overlay.overlay_window import OverlayWindow
    from yaku.audio.kotoba_whisper_backend import KotobaWhisperBackend
    from yaku.audio.audio_pipeline import AudioPipeline
    from yaku.v3_audio_overlay.audio_overlay_controller import AudioOverlayController
    from yaku.audio.deps import check_audio_dependencies
    from yaku.audio.model_manager import check_model_available
    from yaku.audio.capture import choose_default_audio_device

    # 1. Check dependencies
    deps_status = check_audio_dependencies()
    if not deps_status.ok:
        print("Audio Pack is not installed.")
        print("Run: uv sync --extra audio")
        print("Or open the GUI and click Install Audio Pack.")
        sys.exit(1)

    # 2. Check model availability
    model_status = check_model_available(config)
    if not model_status.ok:
        print(f"ASR model is not available: {model_status.message}")
        print("Run: uv run yaku --download-asr-model")
        print("Or open the GUI and click Download Whisper Model.")
        sys.exit(1)

    # 3. Ensure a device is selected
    if config.audio.device_id is None:
        default_dev = choose_default_audio_device(config.audio.source)
        if default_dev:
            config.audio.device_id = default_dev.index
            config.audio.device_name = default_dev.name
            from yaku.core.config import save_config
            try:
                save_config(config, config_path)
            except Exception:
                pass
        else:
            print("No audio devices found.")
            sys.exit(1)

    app = get_app()

    # --- Cache ---
    cache_path = Path(config.cache.sqlite_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache = YakuCache(cache_path)

    # --- ASR backend ---
    from yaku.core.logging import get_logger
    main_logger = get_logger("main")
    
    asr_backend = KotobaWhisperBackend(
        config=config,
        model_name=config.audio.model,
        device=config.audio.device,
        compute_type=config.audio.compute_type,
        language=config.audio.language,
        local_model_path=config.audio.local_model_path,
        download_models=config.audio.download_models,
    )

    # --- Translation backend ---
    try:
        from yaku.translate.factory import create_translator
        translator = create_translator(config.translator)
    except Exception as exc:
        main_logger.exception("Translator backend unavailable, using NullTranslator.")
        from yaku.translate.base import NullTranslator
        translator = NullTranslator()

    # --- Audio pipeline ---
    pipeline = AudioPipeline(config.audio, asr_backend)

    # --- Overlay window ---
    window = OverlayWindow(config.v1_overlay)
    window.apply_config(config.v1_overlay)
    window.set_debug_visible(config.v1_overlay.show_source_in_debug and config.app.debug)
    window.show()

    # --- Controller ---
    controller = AudioOverlayController(
        config, window, pipeline, translator, cache, config_path
    )
    controller.start()

    print(
        "[yaku] v3-audio-overlay running.  "
        "F7=lock  F9=pause  F10=debug  F11=settings  Esc=close"
    )
    exit_code = app.exec()

    # --- Graceful shutdown ---
    _safe("controller.stop", controller.stop)

    def _save_geometry() -> None:
        if config.v1_overlay.save_geometry_on_exit:
            from yaku.core.config import save_config, update_overlay_geometry
            x, y, w, h = window.current_geometry()
            update_overlay_geometry(config, x, y, w, h)
            save_config(config, config_path)

    _safe("save_geometry", _save_geometry)
    _safe("cache.close", cache.close)
    if hasattr(translator, "close"):
        _safe("translator.close", translator.close)

    return exit_code


def _cmd_pick_window(config, config_path: Path) -> int:
    from yaku.core.config import save_config, update_window_selection
    from yaku.ui.window_picker import pick_window_cli

    win = pick_window_cli()
    if win is None:
        return 1
    update_window_selection(config, win.hwnd, win.title)
    save_config(config, config_path)
    print(f"Saved: hwnd={win.hwnd}  title={win.title!r}")
    print(f"Config written to: {config_path}")
    return 0


def _cmd_select_ocr_region(config, config_path: Path) -> int:
    from yaku.core.config import save_config, update_ocr_region
    from yaku.ui.app import get_app
    from yaku.ui.region_selector import RegionSelector

    get_app()
    rect = RegionSelector().run_blocking()
    if rect is None:
        print("Selection cancelled.")
        return 1
    update_ocr_region(config, rect)
    save_config(config, config_path)
    print(f"OCR region saved: x={rect.x} y={rect.y} w={rect.w} h={rect.h}")
    print(f"Config written to: {config_path}")
    return 0


def _cmd_select_replacement_region(config, config_path: Path) -> int:
    from PyQt6.QtWidgets import QApplication

    from yaku.core.config import save_config, update_replacement_region
    from yaku.core.image_utils import rect_to_normalized
    from yaku.ui.app import get_app
    from yaku.ui.region_selector import RegionSelector

    get_app()
    rect = RegionSelector().run_blocking()
    if rect is None:
        print("Selection cancelled.")
        return 1

    app = QApplication.instance()
    geom = app.primaryScreen().geometry()
    
    from yaku.core.capture import normalize_screen_rect_to_window
    norm = normalize_screen_rect_to_window(rect, config.window, geom.width(), geom.height())

    update_replacement_region(config, norm)
    save_config(config, config_path)
    print(
        f"Replacement region saved: "
        f"x_ratio={norm.x_ratio:.4f}  y_ratio={norm.y_ratio:.4f}  "
        f"w_ratio={norm.w_ratio:.4f}  h_ratio={norm.h_ratio:.4f}"
    )
    print(f"Config written to: {config_path}")
    return 0


# ---------------------------------------------------------------------------
# Dispatchable command wrappers
# ---------------------------------------------------------------------------

def launch_main_gui(profile: str | None = None, config_path: str | None = None) -> int:
    from yaku.ui.app import launch_main_gui as _launch_main_gui

    return _launch_main_gui(profile=profile, config_path=config_path)


def launch_setup_wizard_gui(
    profile: str | None = None,
    config_path: str | None = None,
) -> int:
    from yaku.ui.app import launch_setup_wizard_gui as _launch_setup_wizard_gui

    return _launch_setup_wizard_gui(profile=profile, config_path=config_path)


def run_terminal_setup(profile: str | None = None, config_path: str | None = None) -> int:
    from yaku.ui.setup_wizard import setup_wizard_command

    return setup_wizard_command(profile=profile, config_path=config_path)


def run_health_check_cli(config, config_path: Path) -> int:
    from yaku.ui.health_check import run_and_print

    return run_and_print(config, config_path)


def run_pick_window(config, config_path: Path) -> int:
    return _cmd_pick_window(config, config_path)


def run_select_ocr_region(config, config_path: Path) -> int:
    return _cmd_select_ocr_region(config, config_path)


def run_select_replacement_region(config, config_path: Path) -> int:
    return _cmd_select_replacement_region(config, config_path)


def run_select_yomitan_region(config, config_path: Path) -> int:
    return _cmd_select_yomitan_region(config, config_path)


def run_app_controller(config, config_path: Path) -> int:
    if config.app.mode == "v1-overlay":
        return _cmd_run_v1(config, config_path)
    elif config.app.mode == "v1-overlay-max":
        return _cmd_run_v1_max(config, config_path)
    elif config.app.mode == "v3-audio-overlay":
        return _cmd_run_v3(config, config_path)
    elif config.app.mode == "v4-yomitan":
        return _cmd_run_v4(config, config_path)
    elif config.app.mode == "v1-yomitan":
        return _cmd_run_v1_yomitan(config, config_path)
    return _cmd_run_v2(config, config_path)


def _cmd_run_v1_yomitan(config, config_path: Path) -> int:
    """Launch the combo v1-yomitan mode (V1 translation overlay + Yomitan lookup)."""
    from yaku.core.cache import YakuCache
    from yaku.core.pipeline import V1Pipeline
    from yaku.ui.app import get_app
    from yaku.v1_overlay.overlay_controller import OverlayController
    from yaku.v1_overlay.overlay_window import OverlayWindow
    from yaku.v4_yomitan.yomitan_controller import YomitanController

    app = get_app()

    # --- Cache ---
    cache_path = Path(config.cache.sqlite_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache = YakuCache(cache_path)

    # --- OCR backend ---
    from yaku.core.logging import get_logger
    main_logger = get_logger("main")
    try:
        from yaku.ocr.factory import create_ocr
        ocr = create_ocr(config.ocr)
    except Exception as exc:
        main_logger.exception("OCR backend unavailable, using DummyOCR.")
        from yaku.ocr.dummy import DummyOCR
        ocr = DummyOCR("[OCR not configured]")

    # --- Translation backend ---
    try:
        from yaku.translate.factory import create_translator
        translator = create_translator(config.translator)
    except Exception as exc:
        main_logger.exception("Translator backend unavailable, using NullTranslator.")
        from yaku.translate.base import NullTranslator
        translator = NullTranslator()

    # --- Capture backend ---
    capture = None
    try:
        from yaku.core.capture import create_capture
        capture = create_capture(config.window)
    except Exception as exc:
        main_logger.exception("Capture backend unavailable.")

    # --- Pipeline ---
    pipeline = V1Pipeline(ocr, translator, cache, config, capture=capture)

    # --- Overlay window ---
    window = OverlayWindow(config.v1_overlay)
    window.apply_config(config.v1_overlay)
    window.set_debug_visible(config.v1_overlay.show_source_in_debug and config.app.debug)
    window.show()

    # --- V1 Controller ---
    controller_v1 = OverlayController(config, window, pipeline, config_path)
    controller_v1.start()

    # --- Yomitan Controller ---
    controller_yomitan = YomitanController(config, config_path)
    controller_yomitan.start()

    print(
        "[yaku] v1-yomitan combo running.  "
        "V1: F7=lock  F8=force OCR  Shift+F8=retranslate  "
        "F9=pause  F10=debug  F11=settings  F6=OCR region  "
        "Yomitan: hover over words in the OCR region for dictionary lookups."
    )
    exit_code = app.exec()

    # --- Graceful shutdown ---
    _safe("controller_v1.stop", controller_v1.stop)
    _safe("controller_yomitan.stop", controller_yomitan.stop)

    def _save_geometry() -> None:
        if config.v1_overlay.save_geometry_on_exit:
            from yaku.core.config import save_config, update_overlay_geometry
            x, y, w, h = window.current_geometry()
            update_overlay_geometry(config, x, y, w, h)
            save_config(config, config_path)

    _safe("save_geometry", _save_geometry)
    _safe("cache.close", cache.close)
    if capture is not None:
        _safe("capture.close", capture.close)
    if hasattr(translator, "close"):
        _safe("translator.close", translator.close)

    return exit_code


def _cmd_run_v4(config, config_path: Path) -> int:
    """Launch the v4-yomitan mode."""
    from yaku.ui.app import get_app
    from yaku.v4_yomitan.yomitan_controller import YomitanController

    app = get_app()
    controller = YomitanController(config, config_path)
    controller.start()
    try:
        return app.exec()
    finally:
        controller.stop()


def _cmd_select_yomitan_region(config, config_path: Path) -> int:
    from yaku.core.config import save_config
    from yaku.ui.app import get_app
    from yaku.ui.region_selector import RegionSelector

    get_app()
    rect = RegionSelector().run_blocking()
    if rect is None:
        print("Selection cancelled.")
        return 1
    config.v4_yomitan.region.x = rect.x
    config.v4_yomitan.region.y = rect.y
    config.v4_yomitan.region.w = rect.w
    config.v4_yomitan.region.h = rect.h
    config.v4_yomitan.region.is_set = True
    save_config(config, config_path)
    print(f"Yomitan region saved: x={rect.x} y={rect.y} w={rect.w} h={rect.h}")
    print(f"Config written to: {config_path}")
    return 0


def _cmd_import_yomitan_dictionaries(config, config_path: Path, dict_dir_override: str | None) -> int:
    from yaku.v4_yomitan.dictionary_importer import import_dictionary_zip

    dict_dir_path = Path(dict_dir_override) if dict_dir_override else Path(config.v4_yomitan.dictionaries.dictionary_dir)
    if not dict_dir_path.exists():
        print(f"Dictionary directory does not exist: {dict_dir_path}")
        return 1

    zip_files = list(dict_dir_path.glob("*.zip"))
    if not zip_files:
        print(f"No dictionary zip archives found in {dict_dir_path}")
        return 0

    db_path = Path(config.v4_yomitan.dictionaries.index_path)
    print(f"Importing {len(zip_files)} dictionaries into {db_path}...")

    success_count = 0
    for zf in zip_files:
        print(f"Importing {zf.name}...")
        try:
            res = import_dictionary_zip(zf, db_path, force=True)
            if res.ok:
                print(f"  Successfully imported '{res.title}'!")
                print(f"  Terms: {res.terms_imported:,} | Metas: {res.meta_imported:,} | Tags: {res.tags_imported:,}")
                success_count += 1
            else:
                print(f"  Failed to import {zf.name}: {res.error}")
        except Exception as exc:
            print(f"  Error importing {zf.name}: {exc}")

    print(f"Import finished. {success_count}/{len(zip_files)} succeeded.")
    return 0 if success_count == len(zip_files) else 1


def _cmd_rebuild_yomitan_index(config, config_path: Path, dict_dir_override: str | None) -> int:
    db_path = Path(config.v4_yomitan.dictionaries.index_path)
    if db_path.exists():
        print(f"Deleting existing database index at {db_path}...")
        try:
            db_path.unlink()
        except Exception as exc:
            print(f"Failed to delete database index: {exc}")
            return 1

    from yaku.v4_yomitan.dictionary_index import DictionaryIndex
    try:
        db = DictionaryIndex(db_path)
        db.connect()
        db.close()
        print("Schema reinitialized successfully.")
    except Exception as exc:
        print(f"Failed to initialize schema: {exc}")
        return 1

    return _cmd_import_yomitan_dictionaries(config, config_path, dict_dir_override)


def _action_requested(args: argparse.Namespace) -> bool:
    return any(
        getattr(args, name)
        for name in (
            "setup",
            "health_check",
            "pick_window",
            "select_ocr_region",
            "select_replacement_region",
            "check_audio",
            "install_audio_pack",
            "download_asr_model",
            "select_yomitan_region",
            "import_yomitan_dictionaries",
            "rebuild_yomitan_index",
            "run",
        )
    )


def _resolve_config(args: argparse.Namespace):
    from yaku.core.config import YakuConfig, load_config

    if args.profile:
        from yaku.core.profiles import resolve_profile

        return resolve_profile(args.profile)

    config_path = (
        Path(args.config_path) if args.config_path else Path("configs") / "default.yaml"
    )
    config = load_config(config_path) if config_path.exists() else YakuConfig()
    return config, config_path


def _cmd_check_audio(config) -> int:
    from yaku.audio.deps import check_audio_dependencies
    from yaku.audio.model_manager import check_model_available
    from yaku.audio.capture import list_audio_devices
    
    print("=== Yaku Audio Check ===")
    deps = check_audio_dependencies()
    print(f"Dependencies: {'OK' if deps.ok else 'MISSING'}")
    print(f"  Message: {deps.message}")
    for d in deps.installed:
        print(f"  - {d.name}: Installed")
    for d in deps.missing:
        print(f"  - {d.name}: MISSING")
        
    print("\nASR Model:")
    if deps.ok:
        model_status = check_model_available(config)
        print(f"  Model ID: {config.audio.model}")
        print(f"  Status: {'OK' if model_status.ok else 'MISSING'}")
        print(f"  Message: {model_status.message}")
    else:
        print("  Cannot check model status: audio dependencies are missing.")
        
    print("\nAudio Devices:")
    if deps.ok:
        try:
            devices = list_audio_devices()
            print(f"  Found {len(devices)} device(s):")
            for dev in devices:
                default_str = " (default)" if dev.is_default else ""
                loopback_str = " (loopback)" if dev.is_loopback else ""
                print(f"  - [{dev.index}] {dev.name}{default_str}{loopback_str} (Host: {dev.hostapi})")
        except Exception as exc:
            print(f"  Failed to list audio devices: {exc}")
    else:
        print("  Cannot query audio devices: sounddevice/numpy missing.")
        
    return 0


def _cmd_install_audio_pack() -> int:
    from yaku.audio.install import install_audio_pack
    print("Installing Audio Pack dependencies...")
    res = install_audio_pack()
    if res.ok:
        print(f"Installation succeeded!\n{res.message}")
        return 0
    else:
        print(f"Installation failed: {res.message}")
        if res.stdout:
            print(f"stdout:\n{res.stdout}")
        if res.stderr:
            print(f"stderr:\n{res.stderr}")
        return 1


def _cmd_download_asr_model(config) -> int:
    from yaku.audio.deps import check_audio_dependencies
    deps = check_audio_dependencies()
    if not deps.ok:
        print("Cannot download model: Audio Pack dependencies are missing.")
        print("Please run: uv run yaku --install-audio-pack")
        return 1
        
    from yaku.audio.model_manager import download_model
    print(f"Downloading ASR model: {config.audio.model}...")
    res = download_model(config)
    if res.ok:
        print(f"Model download succeeded: {res.message}")
        return 0
    else:
        print(f"Model download failed: {res.message}")
        return 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    from yaku.core.env import load_env_file

    load_env_file()

    parser = build_parser()
    args = parser.parse_args(argv)

    from yaku.core.logging import setup_logging

    if not _action_requested(args):
        return launch_main_gui(profile=args.profile, config_path=args.config_path)

    if args.setup and not args.cli:
        setup_logging(getattr(args, "debug", False))
        return launch_setup_wizard_gui(profile=args.profile, config_path=args.config_path)

    if args.setup and args.cli:
        setup_logging(getattr(args, "debug", False))
        return run_terminal_setup(profile=args.profile, config_path=args.config_path)

    from yaku.core.config import apply_cli_overrides

    config, config_path = _resolve_config(args)
    apply_cli_overrides(config, args)
    setup_logging(config.app.debug)

    if args.health_check:
        return run_health_check_cli(config, config_path)
    if args.pick_window:
        return run_pick_window(config, config_path)
    if args.select_ocr_region:
        return run_select_ocr_region(config, config_path)
    if args.select_replacement_region:
        return run_select_replacement_region(config, config_path)
    if args.select_yomitan_region:
        return run_select_yomitan_region(config, config_path)
    if args.import_yomitan_dictionaries:
        return _cmd_import_yomitan_dictionaries(config, config_path, args.dictionary_dir)
    if args.rebuild_yomitan_index:
        return _cmd_rebuild_yomitan_index(config, config_path, args.dictionary_dir)
    if args.check_audio:
        return _cmd_check_audio(config)
    if args.install_audio_pack:
        return _cmd_install_audio_pack()
    if args.download_asr_model:
        return _cmd_download_asr_model(config)
    if args.run:
        return run_app_controller(config, config_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
