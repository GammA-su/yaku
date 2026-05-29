"""Yaku CLI entry point."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable


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
        "--profile",
        dest="profile",
        default=None,
        metavar="NAME",
        help="Per-game profile under profiles/<NAME>.yaml (created if missing)",
    )
    p.add_argument(
        "--mode",
        choices=["v1-overlay", "v2-mirror"],
        metavar="MODE",
        help="Operating mode: v1-overlay | v2-mirror",
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
    try:
        from yaku.ocr.factory import create_ocr
        ocr = create_ocr(config.ocr)
    except Exception as exc:
        print(f"[yaku] OCR backend unavailable ({exc}), using DummyOCR.")
        from yaku.ocr.dummy import DummyOCR
        ocr = DummyOCR("[OCR not configured]")

    # --- Translation backend ---
    try:
        from yaku.translate.factory import create_translator
        translator = create_translator(config.translator)
    except Exception as exc:
        print(f"[yaku] Translator backend unavailable ({exc}), using NullTranslator.")
        from yaku.translate.base import NullTranslator
        translator = NullTranslator()

    # --- Capture backend ---
    capture = None
    try:
        from yaku.core.capture import create_capture
        capture = create_capture(config.window)
    except Exception as exc:
        print(f"[yaku] Capture backend unavailable ({exc}).")
        print("       Install a capture backend: uv add dxcam / uv add mss")

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
    try:
        from yaku.ocr.factory import create_ocr
        ocr = create_ocr(config.ocr)
    except Exception as exc:
        print(f"[yaku] OCR backend unavailable ({exc}), using DummyOCR.")
        from yaku.ocr.dummy import DummyOCR
        ocr = DummyOCR("[OCR not configured]")

    # --- Translation backend ---
    try:
        from yaku.translate.factory import create_translator
        translator = create_translator(config.translator)
    except Exception as exc:
        print(f"[yaku] Translator backend unavailable ({exc}), using NullTranslator.")
        from yaku.translate.base import NullTranslator
        translator = NullTranslator()

    # --- Capture backend ---
    capture = None
    try:
        from yaku.core.capture import create_capture
        capture = create_capture(config.window)
    except Exception as exc:
        print(f"[yaku] Capture backend unavailable ({exc}).")
        print("       Install a capture backend: uv add dxcam / uv add mss")

    # --- Pipeline + renderer ---
    pipeline = V2Pipeline(ocr, translator, cache, config)
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
    norm = rect_to_normalized(rect, geom.width(), geom.height())

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


def run_app_controller(config, config_path: Path) -> int:
    if config.app.mode == "v1-overlay":
        return _cmd_run_v1(config, config_path)
    return _cmd_run_v2(config, config_path)


def _action_requested(args: argparse.Namespace) -> bool:
    return any(
        getattr(args, name)
        for name in (
            "setup",
            "health_check",
            "pick_window",
            "select_ocr_region",
            "select_replacement_region",
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
    if args.run:
        return run_app_controller(config, config_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
