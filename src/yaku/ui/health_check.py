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
    if os.environ.get(env):
        # Never log the value itself.
        return CheckResult("DeepL API key", PASS, f"{env} is set (not validated).")
    return CheckResult(
        "DeepL API key",
        FAIL,
        f"{env} is not set. PowerShell: $env:{env}=\"...\"  |  bash: export {env}=...",
    )


def check_llama_cpp(config: YakuConfig, *, timeout: float = 2.0) -> CheckResult:
    """Best-effort GET of the llama.cpp ``/models`` endpoint (never fatal)."""
    base = config.translator.llama_cpp.base_url.rstrip("/")
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
    results.append(check_capture(config))
    results.append(check_input_forward(config))
    results.append(check_cache_writable(config))
    results.append(check_out_dir_writable(config))
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
