"""Translation benchmark CLI script."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from yaku.core.config import TranslatorConfig, LlamaCppConfig, DeepLConfig
from yaku.core.errors import TranslationError
from yaku.translate.factory import create_translator


def _sanitize_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return url
    return re.sub(r"(key|token|auth)=[^&]+", r"\1=[REDACTED]", url)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run translation speed benchmarks.")
    parser.add_argument("--input", required=True, help="Path to input text file (one Japanese line per line).")
    parser.add_argument(
        "--translator",
        required=True,
        choices=["deepl", "llama-cpp", "llama_cpp"],
        help="Translator backend to use.",
    )
    parser.add_argument("--target-lang", required=True, help="Target language code (e.g. EN-US or en).")
    parser.add_argument("--repeat", type=int, default=1, help="Number of repetitions over the input dataset.")
    parser.add_argument("--warmup", type=int, default=1, help="Number of warmup runs before timing starts.")
    parser.add_argument("--out", required=True, help="Output JSONL file path to save results.")
    parser.add_argument("--base-url", help="Override base URL for llama.cpp backend.")
    parser.add_argument("--api-key-env", help="Override environment variable name for translator API key.")
    parser.add_argument("--model", help="Override model name for llama.cpp.")

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: input file '{input_path}' does not exist.", file=sys.stderr)
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    if not lines:
        print(f"Error: input file '{input_path}' contains no dialogue lines.", file=sys.stderr)
        sys.exit(1)

    backend = "llama_cpp" if args.translator in ("llama-cpp", "llama_cpp") else "deepl"

    deepl_cfg = DeepLConfig(target_lang=args.target_lang)
    llama_cfg = LlamaCppConfig()

    if backend == "deepl":
        if args.api_key_env:
            deepl_cfg.api_key_env = args.api_key_env
    else:  # llama_cpp
        llama_cfg.use_hosted = False
        if args.base_url:
            llama_cfg.base_url = args.base_url
            llama_cfg.port = 0
        if args.model:
            llama_cfg.model = args.model
        if args.api_key_env:
            llama_cfg.api_key_env = args.api_key_env

    config = TranslatorConfig(
        backend=backend,
        deepl=deepl_cfg,
        llama_cpp=llama_cfg,
    )

    try:
        translator = create_translator(config)
    except Exception as exc:
        print(f"Error initializing translator: {exc}", file=sys.stderr)
        sys.exit(1)

    # 1. Warmup
    if args.warmup > 0:
        print(f"Running {args.warmup} warmup translation(s)...", flush=True)
        warmup_line = lines[0]
        for i in range(args.warmup):
            try:
                # Call translate directly to bypass cache
                translator.translate(warmup_line, [], args.target_lang)
            except Exception as exc:
                print(f"Warmup warning (run {i+1} failed): {exc}", file=sys.stderr)

    # Prepare output path
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 2. Benchmark Loop
    print(f"Starting benchmark (repeats={args.repeat}, total lines={len(lines)})...", flush=True)
    results = []
    
    with open(out_path, "a", encoding="utf-8") as out_file:
        for rep in range(args.repeat):
            print(f"Repetition {rep + 1}/{args.repeat}...", flush=True)
            for idx, line in enumerate(lines):
                ts = datetime.now(timezone.utc).isoformat()
                start_time = time.perf_counter()
                
                translated_text = None
                translate_ms = None
                prompt_tokens = None
                completion_tokens = None
                tokens_per_second = None
                chars_per_second = None
                error_msg = None
                
                try:
                    result = translator.translate(line, [], args.target_lang)
                    translate_ms = (time.perf_counter() - start_time) * 1000.0
                    translated_text = result.translated_text
                    prompt_tokens = result.prompt_tokens
                    completion_tokens = result.completion_tokens
                    tokens_per_second = result.tokens_per_second
                    
                    if translate_ms > 0:
                        chars_per_second = len(line) / (translate_ms / 1000.0)
                except Exception as exc:
                    error_msg = str(exc)
                    print(f"Warning: line {idx+1} failed to translate: {exc}", file=sys.stderr)

                raw_base_url = translator._client.base_url if hasattr(translator, "_client") else None
                if not raw_base_url and hasattr(translator, "_completions_url"):
                    raw_base_url = translator._completions_url
                
                # If we have base_url in results from TranslationResult, prefer it
                if 'result' in locals() and result and result.base_url:
                    raw_base_url = result.base_url

                base_url_str = str(raw_base_url) if raw_base_url else None
                sanitized_url = _sanitize_url(base_url_str)

                entry = {
                    "ts": ts,
                    "translator": backend,
                    "model": translator.backend_model,
                    "base_url": sanitized_url,
                    "source_text": line,
                    "translated_text": translated_text,
                    "translate_ms": translate_ms,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "tokens_per_second": tokens_per_second,
                    "chars_per_second": chars_per_second,
                    "error": error_msg,
                }
                
                line_json = json.dumps(entry, ensure_ascii=False) + "\n"
                out_file.write(line_json)
                out_file.flush()

    print(f"Benchmark finished. Results appended to {out_path}", flush=True)


if __name__ == "__main__":
    main()
