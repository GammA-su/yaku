"""Translation benchmark summary CLI script."""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import List, Optional


def percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * pct
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    d0 = sorted_vals[int(f)] * (c - k)
    d1 = sorted_vals[int(c)] * (k - f)
    return d0 + d1


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze translation latency benchmark results.")
    parser.add_argument("file_path", help="Path to benchmark JSONL output file.")
    args = parser.parse_args()

    file_path = Path(args.file_path)
    if not file_path.exists():
        print(f"Error: file '{file_path}' does not exist.", file=sys.stderr)
        sys.exit(1)

    # Grouping key -> list of records
    groups = defaultdict(list)

    with open(file_path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                translator = record.get("translator") or "unknown"
                model = record.get("model") or "None"
                base_url = record.get("base_url") or "None"
                
                key = (translator, model, base_url)
                groups[key].append(record)
            except Exception as exc:
                print(f"Warning: line {idx} is invalid JSON: {exc}", file=sys.stderr)

    if not groups:
        print("No benchmark records found.", file=sys.stderr)
        sys.exit(1)

    for (translator, model, base_url), records in sorted(groups.items()):
        total = len(records)
        errors = sum(1 for r in records if r.get("error") is not None)
        successes = total - errors

        latencies = [
            r["translate_ms"]
            for r in records
            if r.get("error") is None and r.get("translate_ms") is not None
        ]
        
        chars_secs = [
            r["chars_per_second"]
            for r in records
            if r.get("error") is None and r.get("chars_per_second") is not None
        ]

        tokens_secs = [
            r["tokens_per_second"]
            for r in records
            if r.get("error") is None and r.get("tokens_per_second") is not None
        ]

        print("=" * 70)
        print(f"Group: Translator={translator} | Model={model} | Base URL={base_url}")
        print("=" * 70)
        print(f"Total Samples: {total}")
        print(f"Errors:        {errors}")
        print(f"Successes:     {successes}")
        print()

        if successes > 0 and latencies:
            min_ms = min(latencies)
            max_ms = max(latencies)
            avg_ms = sum(latencies) / len(latencies)
            med_ms = percentile(latencies, 0.50)
            p90_ms = percentile(latencies, 0.90)
            p95_ms = percentile(latencies, 0.95)

            print("Successful Latency Stats (ms):")
            print(f"  Min:     {min_ms:.1f}")
            print(f"  Average: {avg_ms:.1f}")
            print(f"  Median:  {med_ms:.1f}")
            print(f"  P90:     {p90_ms:.1f}")
            print(f"  P95:     {p95_ms:.1f}")
            print(f"  Max:     {max_ms:.1f}")
            print()

            avg_chars = sum(chars_secs) / len(chars_secs) if chars_secs else 0.0
            avg_tokens_str = "N/A"
            if tokens_secs:
                avg_tokens = sum(tokens_secs) / len(tokens_secs)
                avg_tokens_str = f"{avg_tokens:.1f}"

            print("Speed Stats:")
            print(f"  Avg Chars/Sec:  {avg_chars:.1f}")
            print(f"  Avg Tokens/Sec: {avg_tokens_str}")
        else:
            print("No successful runs in this group to calculate latency stats.")
        print()


if __name__ == "__main__":
    main()
