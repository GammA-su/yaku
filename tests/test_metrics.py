"""Tests for MetricsLogger and LatencyEvent sanitization."""
from __future__ import annotations

import json
from pathlib import Path
from yaku.core.metrics import LatencyEvent, MetricsLogger


def test_logger_creates_parent_dir_and_writes_jsonl(tmp_path):
    log_file = tmp_path / "subdir" / "yaku_latency.jsonl"
    logger = MetricsLogger(log_file, enabled=True)

    event = LatencyEvent(
        ts="2026-06-03T12:00:00Z",
        mode="v1-overlay",
        ocr_backend="paddleocr",
        translator="deepl",
        model=None,
        base_url="https://api-free.deepl.com/v2/translate",
        render_mode=None,
        capture_ms=10.0,
        hash_ms=5.0,
        ocr_ms=100.0,
        translate_ms=250.0,
        render_ms=0.0,
        total_ms=365.0,
        cache_hit=False,
        source_chars=10,
        translated_chars=15,
        source_preview="こんにちは",
        translation_preview="Hello",
        prompt_tokens=None,
        completion_tokens=None,
        tokens_per_second=None,
        error=None,
    )

    logger.log_event(event)

    # Verify directory and file were created
    assert log_file.exists()

    # Read and parse JSONL
    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 1
    
    data = json.loads(lines[0])
    assert data["mode"] == "v1-overlay"
    assert data["translator"] == "deepl"
    assert data["translate_ms"] == 250.0


def test_logger_sanitizes_secrets_in_base_url(tmp_path):
    log_file = tmp_path / "secrets.jsonl"
    logger = MetricsLogger(log_file, enabled=True)

    event = LatencyEvent(
        ts="2026-06-03T12:00:00Z",
        mode="v2-mirror",
        ocr_backend="paddleocr",
        translator="llama_cpp",
        model="qwen",
        base_url="http://127.0.0.1:8080/v1?key=supersecret123&auth=mytoken&other=val",
        render_mode="inpaint-text",
        capture_ms=10.0,
        hash_ms=5.0,
        ocr_ms=100.0,
        translate_ms=250.0,
        render_ms=30.0,
        total_ms=395.0,
        cache_hit=False,
        source_chars=10,
        translated_chars=15,
        source_preview="こんにちは",
        translation_preview="Hello",
        prompt_tokens=10,
        completion_tokens=15,
        tokens_per_second=20.0,
        error=None,
    )

    logger.log_event(event)

    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    data = json.loads(lines[0])
    # key and auth must be redacted, other must not
    assert "supersecret123" not in data["base_url"]
    assert "mytoken" not in data["base_url"]
    assert "key=[REDACTED]" in data["base_url"]
    assert "auth=[REDACTED]" in data["base_url"]
    assert "other=val" in data["base_url"]


def test_logger_when_disabled_does_not_write(tmp_path):
    log_file = tmp_path / "disabled.jsonl"
    logger = MetricsLogger(log_file, enabled=False)

    event = LatencyEvent(
        ts="2026-06-03T12:00:00Z",
        mode="v1-overlay",
        ocr_backend="dummy",
        translator="null",
        model=None,
        base_url=None,
        render_mode=None,
        capture_ms=0.0,
        hash_ms=0.0,
        ocr_ms=0.0,
        translate_ms=0.0,
        render_ms=0.0,
        total_ms=0.0,
        cache_hit=True,
        source_chars=0,
        translated_chars=0,
        source_preview=None,
        translation_preview=None,
        prompt_tokens=None,
        completion_tokens=None,
        tokens_per_second=None,
        error=None,
    )

    logger.log_event(event)
    assert not log_file.exists()
