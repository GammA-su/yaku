"""Tests for yaku-bench-translate CLI script."""
from __future__ import annotations

import json
import sys
from unittest.mock import MagicMock, patch
import pytest

from yaku.bench import translate_bench
from yaku.translate.base import BaseTranslator, TranslationResult


class _FakeTranslator(BaseTranslator):
    @property
    def backend_name(self) -> str:
        return "fake_backend"

    @property
    def backend_model(self) -> str | None:
        return "fake-model-123"

    def translate(self, text, context, target_lang, glossary=None) -> TranslationResult:
        # Mock completions timings payload
        return TranslationResult(
            source_text=text,
            translated_text=f"Translated: {text}",
            target_lang=target_lang,
            backend="fake_backend",
            backend_model="fake-model-123",
            prompt_tokens=10,
            completion_tokens=15,
            tokens_per_second=25.0,
            base_url="http://fake-endpoint.com/v1?key=sensitivepass123",
        )


def test_bench_translate_runs_and_outputs_jsonl(tmp_path):
    input_file = tmp_path / "vn_input.txt"
    input_file.write_text("こんにちは\nさようなら\n", encoding="utf-8")
    
    out_file = tmp_path / "bench_results.jsonl"
    
    test_args = [
        "yaku-bench-translate",
        "--input", str(input_file),
        "--translator", "llama-cpp",
        "--target-lang", "en",
        "--repeat", "2",
        "--warmup", "1",
        "--out", str(out_file),
        "--base-url", "http://fake-endpoint.com/v1?key=sensitivepass123",
        "--model", "fake-model-123",
    ]
    
    fake_translator = _FakeTranslator()
    
    with patch("sys.argv", test_args), \
         patch("yaku.bench.translate_bench.create_translator", return_value=fake_translator) as mock_create:
        
        translate_bench.main()
        
        # Verify translator was initialized
        mock_create.assert_called_once()
        
        # Check output JSONL
        assert out_file.exists()
        with open(out_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        # 2 lines in input * 2 repeats = 4 results
        assert len(lines) == 4
        
        for line in lines:
            data = json.loads(line)
            assert data["translator"] == "llama_cpp"
            assert data["model"] == "fake-model-123"
            # Ensure base_url secrets are redacted
            assert "sensitivepass123" not in data["base_url"]
            assert "key=[REDACTED]" in data["base_url"]
            assert data["translated_text"].startswith("Translated:")
            assert data["prompt_tokens"] == 10
            assert data["completion_tokens"] == 15
            assert data["tokens_per_second"] == 25.0
            assert isinstance(data["translate_ms"], float)
            assert isinstance(data["chars_per_second"], float)
            assert data["error"] is None
