"""Tests for the health-check module."""
from __future__ import annotations

from yaku.core.config import YakuConfig
from yaku.ui.health_check import (
    FAIL,
    PASS,
    WARN,
    CheckResult,
    check_cache_writable,
    check_config_loads,
    check_deepl_key,
    check_ocr,
    check_out_dir_writable,
    check_translator,
    format_report,
    overall_status,
    run_health_checks,
)

_VALID = {PASS, WARN, FAIL}


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def test_config_loads_missing_is_warn(tmp_path):
    res = check_config_loads(tmp_path / "nope.yaml")
    assert res.status == WARN


def test_config_loads_none_is_pass():
    assert check_config_loads(None).status == PASS


def test_config_loads_valid(tmp_path):
    from yaku.core.config import save_config
    path = tmp_path / "c.yaml"
    save_config(YakuConfig(), path)
    assert check_config_loads(path).status == PASS


def test_translator_valid():
    cfg = YakuConfig()
    cfg.translator.backend = "deepl"
    assert check_translator(cfg).status == PASS
    cfg.translator.backend = "llama_cpp"
    assert check_translator(cfg).status == PASS


def test_translator_unknown_fails():
    cfg = YakuConfig()
    object.__setattr__(cfg.translator, "backend", "bogus")
    assert check_translator(cfg).status == FAIL


def test_deepl_key_missing_fails(monkeypatch):
    cfg = YakuConfig()
    cfg.translator.backend = "deepl"
    cfg.translator.deepl.api_key_env = "YAKU_TEST_KEY_XYZ"
    monkeypatch.delenv("YAKU_TEST_KEY_XYZ", raising=False)
    res = check_deepl_key(cfg)
    assert res.status == FAIL
    # The message must NOT contain a key value (we never set one).
    assert "YAKU_TEST_KEY_XYZ" in res.message


def test_deepl_key_present_passes(monkeypatch):
    cfg = YakuConfig()
    cfg.translator.deepl.api_key_env = "YAKU_TEST_KEY_XYZ"
    monkeypatch.setenv("YAKU_TEST_KEY_XYZ", "super-secret-value")
    res = check_deepl_key(cfg)
    assert res.status == PASS
    # Secret value must never appear in the message.
    assert "super-secret-value" not in res.message


def test_ocr_dummy_passes():
    cfg = YakuConfig()
    cfg.ocr.backend = "dummy"
    assert check_ocr(cfg).status == PASS


def test_ocr_paddle_warns_with_install_hint_when_absent():
    cfg = YakuConfig()
    cfg.ocr.backend = "paddleocr"
    res = check_ocr(cfg)
    # paddleocr is not a project dependency; expect a warn + install hint.
    if res.status == WARN:
        assert "uv add paddleocr" in res.message
    else:
        assert res.status == PASS  # installed in this environment


def test_cache_writable(tmp_path):
    cfg = YakuConfig()
    cfg.cache.sqlite_path = str(tmp_path / "sub" / "cache.sqlite3")
    assert check_cache_writable(cfg).status == PASS


def test_out_dir_writable():
    assert check_out_dir_writable().status == PASS


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def test_run_health_checks_returns_results():
    cfg = YakuConfig()
    cfg.ocr.backend = "dummy"
    results = run_health_checks(cfg, None)
    assert results
    assert all(isinstance(r, CheckResult) for r in results)
    assert all(r.status in _VALID for r in results)
    names = {r.name for r in results}
    assert "Translator" in names
    assert "Cache DB" in names


def test_deepl_branch_included_only_for_deepl():
    cfg = YakuConfig()
    cfg.translator.backend = "deepl"
    names = {r.name for r in run_health_checks(cfg, None)}
    assert "DeepL API key" in names
    assert "llama.cpp server" not in names


def test_overall_status_picks_worst():
    results = [
        CheckResult("a", PASS, ""),
        CheckResult("b", WARN, ""),
        CheckResult("c", FAIL, ""),
    ]
    assert overall_status(results) == FAIL
    assert overall_status(results[:2]) == WARN
    assert overall_status(results[:1]) == PASS


def test_format_report_contains_overall():
    report = format_report([CheckResult("a", PASS, "ok")])
    assert "Overall" in report
    assert "a: ok" in report
