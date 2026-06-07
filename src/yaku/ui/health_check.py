"""Environment & configuration health checks for Yaku.

Runs a series of non-destructive checks and reports ``pass`` / ``warn`` /
``fail`` for each.  Designed to be importable and unit-testable: every check is
a standalone function returning a :class:`CheckResult`, and none of them call
external paid APIs.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from yaku.core.config import YakuConfig, load_config
from yaku.core.env import load_env_file
from yaku.core.logging import get_logger

_log = get_logger("health_check")

PASS = "pass"
WARN = "warn"
FAIL = "fail"

_SYMBOL = {PASS: "[ OK ]", WARN: "[WARN]", FAIL: "[FAIL]"}
_SEVERITY = {PASS: 0, WARN: 1, FAIL: 2}


@dataclass
class CheckResult:
    name: str
    status: str
    message: str


def _module_available(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def _dir_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=path):
            pass
        return True
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_config_loads(config_path: Path | str | None) -> CheckResult:
    name = "Config"
    if config_path is None:
        return CheckResult(name, PASS, "Using in-memory default config.")
    path = Path(config_path)
    if not path.exists():
        return CheckResult(name, WARN, f"{path} not found; defaults will be used.")
    try:
        load_config(path)
    except Exception as exc:  # noqa: BLE001
        return CheckResult(name, FAIL, f"Failed to load {path}: {exc}")
    return CheckResult(name, PASS, f"Loaded {path}.")


def check_translator(config: YakuConfig) -> CheckResult:
    backend = config.translator.backend
    if backend in ("deepl", "llama_cpp"):
        return CheckResult("Translator", PASS, f"Backend '{backend}' is valid.")
    return CheckResult(
        "Translator", FAIL, f"Unknown translator backend '{backend}'."
    )


def check_deepl_key(config: YakuConfig) -> CheckResult:
    load_env_file()
    env = config.translator.deepl.api_key_env
    if config.translator.deepl.api_key:
        return CheckResult("DeepL API key", PASS, "API key is configured in settings (not validated).")
    if os.environ.get(env):
        # Never log the value itself.
        return CheckResult("DeepL API key", PASS, f"{env} is set in environment (not validated).")
    return CheckResult(
        "DeepL API key",
        FAIL,
        f"{env} is not set in environment and no key configured in settings. Set it in Settings.",
    )


def check_llama_cpp(config: YakuConfig, *, timeout: float = 2.0) -> CheckResult:
    """Best-effort GET of the llama.cpp ``/models`` endpoint (never fatal)."""
    base = config.translator.llama_cpp.base_url
    if config.translator.llama_cpp.port:
        base = f"http://127.0.0.1:{config.translator.llama_cpp.port}/v1"
    base = base.rstrip("/")
    url = f"{base}/models"
    try:
        import httpx

        resp = httpx.get(url, timeout=timeout)
        if resp.status_code < 500:
            return CheckResult("llama.cpp server", PASS, f"Reachable at {base}.")
        return CheckResult(
            "llama.cpp server", WARN, f"{base} returned HTTP {resp.status_code}."
        )
    except Exception as exc:  # noqa: BLE001 — unreachable is only a warning
        return CheckResult(
            "llama.cpp server",
            WARN,
            f"Not reachable at {base} ({type(exc).__name__}). Start it before --run.",
        )


def check_ocr(config: YakuConfig) -> CheckResult:
    backend = config.ocr.backend
    if backend == "dummy":
        return CheckResult("OCR backend", PASS, "DummyOCR (no model needed).")
    module, install = {
        "manga_ocr": ("manga_ocr", "uv add manga-ocr"),
        "paddleocr": ("paddleocr", "uv add paddleocr paddlepaddle"),
    }.get(backend, (None, None))
    if module is None:
        return CheckResult("OCR backend", FAIL, f"Unknown OCR backend '{backend}'.")
    if _module_available(module):
        return CheckResult("OCR backend", PASS, f"'{backend}' is importable.")
    return CheckResult(
        "OCR backend", WARN, f"'{backend}' not installed. Install: {install}"
    )


def check_capture(config: YakuConfig) -> CheckResult:
    backend = config.window.capture_backend
    have_dxcam = _module_available("dxcam")
    have_mss = _module_available("mss")

    if backend == "dxcam":
        ok, hint = have_dxcam, "uv add dxcam"
    elif backend == "mss":
        ok, hint = have_mss, "uv add mss"
    elif backend == "win32":
        return CheckResult("Capture backend", WARN, "win32 capture not implemented; use dxcam/mss.")
    else:  # auto
        if have_dxcam or have_mss:
            which = "mss" if have_mss else "dxcam"
            return CheckResult("Capture backend", PASS, f"auto -> {which} available.")
        return CheckResult(
            "Capture backend", FAIL, "No capture backend. Install: uv add mss (or dxcam)."
        )

    if ok:
        return CheckResult("Capture backend", PASS, f"'{backend}' available.")
    return CheckResult("Capture backend", FAIL, f"'{backend}' not installed. {hint}")


def check_input_forward(config: YakuConfig) -> CheckResult:
    name = "Input forwarding"
    if config.app.mode != "v2-mirror" or not config.v2_mirror.forward_input:
        return CheckResult(name, PASS, "Not required (disabled or v1-overlay).")
    if sys.platform != "win32":
        return CheckResult(
            name, WARN, f"Unsupported on {sys.platform}; mirror display still works."
        )
    if _module_available("win32gui"):
        return CheckResult(name, PASS, "pywin32 available.")
    return CheckResult(name, WARN, "pywin32 not installed. Install: uv add pywin32")


def check_cache_writable(config: YakuConfig) -> CheckResult:
    parent = Path(config.cache.sqlite_path).parent
    if _dir_writable(parent):
        return CheckResult("Cache DB", PASS, f"Writable: {parent}/")
    return CheckResult("Cache DB", FAIL, f"Not writable: {parent}/")


def check_out_dir_writable(_config: YakuConfig | None = None) -> CheckResult:
    out = Path("out")
    if _dir_writable(out):
        return CheckResult("Output dir", PASS, "out/ is writable.")
    return CheckResult("Output dir", FAIL, "out/ is not writable.")


def check_audio_dependencies(config: YakuConfig) -> CheckResult:
    name = "Audio dependencies"
    if config.app.mode != "v3-audio-overlay":
        return CheckResult(name, PASS, "Not required by active mode.")

    missing = []
    for pkg, name_import in [
        ("sounddevice", "sounddevice"),
        ("silero-vad", "silero_vad"),
        ("faster-whisper", "faster_whisper"),
        ("torch", "torch"),
        ("torchaudio", "torchaudio"),
    ]:
        if not _module_available(name_import):
            missing.append(pkg)

    if not missing:
        return CheckResult(name, PASS, "All audio packages are available.")
    return CheckResult(
        name,
        WARN,
        f"Missing audio packages: {', '.join(missing)}. "
        "Install via: pip install sounddevice silero-vad faster-whisper torch torchaudio"
    )


def check_cuda_availability(config: YakuConfig) -> CheckResult:
    name = "CUDA acceleration"
    if config.app.mode != "v3-audio-overlay":
        return CheckResult(name, PASS, "Not required by active mode.")

    if not _module_available("torch"):
        return CheckResult(name, WARN, "torch package is missing; cannot check CUDA.")

    import torch
    if torch.cuda.is_available():
        return CheckResult(name, PASS, f"CUDA is available (Device: {torch.cuda.get_device_name(0)}).")
    
    device = config.audio.device
    if device == "cuda":
        return CheckResult(name, FAIL, "CUDA requested in config but not available in PyTorch.")
    return CheckResult(name, PASS, "CUDA not available, running on CPU (CPU mode).")


def check_audio_devices_available(config: YakuConfig) -> CheckResult:
    name = "Audio input devices"
    if config.app.mode != "v3-audio-overlay":
        return CheckResult(name, PASS, "Not required by active mode.")

    if not _module_available("sounddevice"):
        return CheckResult(name, WARN, "sounddevice package missing; cannot query devices.")

    try:
        from yaku.audio.capture import list_audio_devices
        devices = list_audio_devices()
        if not devices:
            return CheckResult(name, FAIL, "No audio input/loopback devices detected on the system.")
        return CheckResult(name, PASS, f"Detected {len(devices)} input/loopback device(s).")
    except Exception as exc:
        return CheckResult(name, FAIL, f"Failed to list audio devices: {exc}")


def check_autotranslator_isolation(config: YakuConfig) -> CheckResult:
    name = "AutoTranslator isolation"
    import sys
    for path in sys.path:
        if "AutoTranslator" in path:
            return CheckResult(name, WARN, f"AutoTranslator path '{path}' detected in sys.path. Ensure clean separation.")
    return CheckResult(name, PASS, "Isolated from C:\\Projecyt\\AutoTranslator.")


def check_paddleocr_available(config: YakuConfig) -> CheckResult:
    name = "PaddleOCR package"
    is_max = config.app.mode == "v1-overlay-max"
    status_if_missing = FAIL if is_max else WARN
    if _module_available("paddleocr"):
        return CheckResult(name, PASS, "paddleocr is installed and importable.")
    else:
        return CheckResult(
            name,
            status_if_missing,
            "paddleocr is not installed. Install with: uv add paddleocr paddlepaddle"
        )


def check_ocr_backend_supports_boxes(config: YakuConfig) -> CheckResult:
    name = "OCR bounding boxes"
    is_max = config.app.mode == "v1-overlay-max"
    backend = config.ocr.backend
    if backend == "paddleocr":
        return CheckResult(name, PASS, "PaddleOCR backend supports bounding boxes.")
    elif backend == "dummy":
        return CheckResult(name, PASS, "DummyOCR supports bounding boxes (testing only).")
    else:
        status = FAIL if is_max else PASS
        return CheckResult(
            name,
            status,
            f"OCR backend '{backend}' does not support bounding boxes. PaddleOCR is required for v1-overlay-max."
        )


def check_window_capture_works(config: YakuConfig) -> CheckResult:
    name = "VN window capture"
    try:
        from yaku.core.capture import _window_rect, create_capture
        rect = _window_rect(config.window)
        if rect is None:
            if config.window.hwnd or config.window.title_contains:
                return CheckResult(
                    name,
                    FAIL,
                    f"Selected window (HWND: {config.window.hwnd}, title: '{config.window.title_contains}') is not found or not visible."
                )
            else:
                return CheckResult(
                    name,
                    WARN,
                    "No target window selected in config. Using fallback/monitor capture."
                )
        
        cap = create_capture(config.window)
        try:
            img = cap.capture_frame()
            if img:
                return CheckResult(
                    name,
                    PASS,
                    f"Target window found at {rect} and captured successfully ({img.width}x{img.height})."
                )
            else:
                return CheckResult(name, FAIL, "Captured frame is empty.")
        finally:
            cap.close()
    except Exception as exc:
        return CheckResult(name, FAIL, f"Window capture check failed: {exc}")


def check_yomitan_region(config: YakuConfig) -> CheckResult:
    name = "Yomitan Region"
    region = config.v4_yomitan.region
    if not region.is_set or region.w <= 0 or region.h <= 0:
        return CheckResult(name, FAIL, "Yomitan region is not set or has invalid size. Draw the region first.")
    return CheckResult(name, PASS, f"Yomitan region is set: {region.x},{region.y} {region.w}x{region.h}")


def check_yomitan_dictionaries(config: YakuConfig) -> CheckResult:
    name = "Yomitan Dictionaries"
    db_path = Path(config.v4_yomitan.dictionaries.index_path)
    if not db_path.exists():
        return CheckResult(name, WARN, f"SQLite index database does not exist at {db_path}. Run --import-yomitan-dictionaries first.")
        
    try:
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM dictionaries;")
        dict_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM terms;")
        term_count = cursor.fetchone()[0]
        conn.close()
        
        if dict_count == 0:
            return CheckResult(name, WARN, "No dictionaries imported in the SQLite database index.")
        return CheckResult(name, PASS, f"Database index has {dict_count} dictionary/dictionaries ({term_count:,} terms).")
    except Exception as exc:
        return CheckResult(name, FAIL, f"Failed to query dictionary database: {exc}")


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def run_health_checks(
    config: YakuConfig, config_path: Path | str | None = None
) -> list[CheckResult]:
    """Run all checks relevant to *config* and return the results in order."""
    results: list[CheckResult] = [
        check_config_loads(config_path),
        check_translator(config),
    ]
    if config.translator.backend == "deepl":
        results.append(check_deepl_key(config))
    elif config.translator.backend == "llama_cpp":
        results.append(check_llama_cpp(config))

    results.append(check_ocr(config))
    results.append(check_paddleocr_available(config))
    results.append(check_ocr_backend_supports_boxes(config))
    results.append(check_window_capture_works(config))
    results.append(check_capture(config))
    results.append(check_input_forward(config))
    results.append(check_audio_dependencies(config))
    results.append(check_cuda_availability(config))
    results.append(check_audio_devices_available(config))
    results.append(check_autotranslator_isolation(config))
    results.append(check_cache_writable(config))
    results.append(check_out_dir_writable(config))

    if config.app.mode in {"v4-yomitan", "v1-yomitan"}:
        if config.app.mode == "v1-yomitan":
            name = "OCR Region (for V1+Yomitan)"
            region = config.ocr.region
            if region.w <= 0 or region.h <= 0:
                results.append(CheckResult(name, FAIL, "OCR region is not set or is empty. Draw the region first."))
            else:
                results.append(CheckResult(name, PASS, f"OCR region is set: {region.x},{region.y} {region.w}x{region.h}"))
        else:
            results.append(check_yomitan_region(config))
            
        results.append(check_yomitan_dictionaries(config))

    return results


def overall_status(results: list[CheckResult]) -> str:
    worst = PASS
    for r in results:
        if _SEVERITY[r.status] > _SEVERITY[worst]:
            worst = r.status
    return worst


def format_report(results: list[CheckResult]) -> str:
    lines = [f"  {_SYMBOL[r.status]}  {r.name}: {r.message}" for r in results]
    status = overall_status(results)
    summary = {
        PASS: "All checks passed.",
        WARN: "Completed with warnings.",
        FAIL: "One or more checks FAILED.",
    }[status]
    lines.append("")
    lines.append(f"  Overall: {_SYMBOL[status]}  {summary}")
    return "\n".join(lines)


def run_and_print(config: YakuConfig, config_path: Path | str | None = None) -> int:
    """Run checks, print the report, and return a process exit code."""
    results = run_health_checks(config, config_path)
    print("Yaku health check")
    print("=" * 60)
    print(format_report(results))
    return 1 if overall_status(results) == FAIL else 0
