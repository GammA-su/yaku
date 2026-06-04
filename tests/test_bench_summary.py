"""Tests for yaku-bench-summary CLI script."""
from __future__ import annotations

import contextlib
import io
import json
import sys
from unittest.mock import patch
import pytest

from yaku.bench import summary


def test_percentile():
    # Odd number of elements
    vals = [10.0, 20.0, 30.0]
    assert summary.percentile(vals, 0.0) == 10.0
    assert summary.percentile(vals, 0.5) == 20.0
    assert summary.percentile(vals, 1.0) == 30.0

    # Even number of elements
    vals = [10.0, 20.0, 30.0, 40.0]
    assert summary.percentile(vals, 0.5) == 25.0
    # p90 calculation on 4 elements: (4-1)*0.9 = 2.7. 
    # Interpolation between index 2 (30.0) and index 3 (40.0) with weight 0.7:
    # 30.0 * 0.3 + 40.0 * 0.7 = 9.0 + 28.0 = 37.0
    assert summary.percentile(vals, 0.9) == 37.0
    
    # Empty list
    assert summary.percentile([], 0.5) == 0.0


def test_summary_main_calculates_and_prints_correctly(tmp_path):
    bench_file = tmp_path / "test_bench.jsonl"
    
    # Write 3 successful and 1 failed run
    runs = [
        {
            "ts": "2026-06-03T12:00:00Z",
            "translator": "llama_cpp",
            "model": "qwen9b",
            "base_url": "http://127.0.0.1:8080/v1",
            "source_text": "こんにちは",
            "translated_text": "Hello",
            "translate_ms": 100.0,
            "prompt_tokens": 10,
            "completion_tokens": 12,
            "tokens_per_second": 30.0,
            "chars_per_second": 50.0,
            "error": None,
        },
        {
            "ts": "2026-06-03T12:00:01Z",
            "translator": "llama_cpp",
            "model": "qwen9b",
            "base_url": "http://127.0.0.1:8080/v1",
            "source_text": "ありがとう",
            "translated_text": "Thank you",
            "translate_ms": 200.0,
            "prompt_tokens": 10,
            "completion_tokens": 14,
            "tokens_per_second": 40.0,
            "chars_per_second": 25.0,
            "error": None,
        },
        {
            "ts": "2026-06-03T12:00:02Z",
            "translator": "llama_cpp",
            "model": "qwen9b",
            "base_url": "http://127.0.0.1:8080/v1",
            "source_text": "さようなら",
            "translated_text": "Goodbye",
            "translate_ms": 300.0,
            "prompt_tokens": 10,
            "completion_tokens": 16,
            "tokens_per_second": 50.0,
            "chars_per_second": 16.7,
            "error": None,
        },
        {
            "ts": "2026-06-03T12:00:03Z",
            "translator": "llama_cpp",
            "model": "qwen9b",
            "base_url": "http://127.0.0.1:8080/v1",
            "source_text": "エラー行",
            "translated_text": None,
            "translate_ms": None,
            "prompt_tokens": None,
            "completion_tokens": None,
            "tokens_per_second": None,
            "chars_per_second": None,
            "error": "Timeout",
        },
    ]

    with open(bench_file, "w", encoding="utf-8") as f:
        for run in runs:
            f.write(json.dumps(run) + "\n")

    test_args = ["yaku-bench-summary", str(bench_file)]
    
    stdout_buf = io.StringIO()
    with patch("sys.argv", test_args), contextlib.redirect_stdout(stdout_buf):
        summary.main()
        
    output = stdout_buf.getvalue()
    
    # Assert stats are parsed and printed correctly
    assert "Group: Translator=llama_cpp | Model=qwen9b | Base URL=http://127.0.0.1:8080/v1" in output
    assert "Total Samples: 4" in output
    assert "Errors:        1" in output
    assert "Successes:     3" in output
    assert "Min:     100.0" in output
    assert "Average: 200.0" in output
    assert "Median:  200.0" in output
    assert "Max:     300.0" in output
    assert "Avg Chars/Sec:  30.6" in output  # (50.0 + 25.0 + 16.7)/3 = 30.5666...
    assert "Avg Tokens/Sec: 40.0" in output  # (30.0 + 40.0 + 50.0)/3 = 40.0
