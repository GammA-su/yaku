"""OCR text normalization utilities.

All public functions are pure (no side effects, no I/O).
Japanese punctuation is preserved; text is never romanized or translated.
"""
from __future__ import annotations

import re

# U+3000 IDEOGRAPHIC SPACE (full-width blank used in Japanese typography)
_FULLWIDTH_SPACE = "　"


# ---------------------------------------------------------------------------
# Primary entry point
# ---------------------------------------------------------------------------

def cleanup_ocr_text(text: str) -> str:
    """Normalize raw OCR output for downstream processing.

    Operations applied in order:

    1. Convert full-width spaces (U+3000) to ASCII spaces.
    2. Split on newlines; strip leading/trailing whitespace from every line.
    3. Remove blank / whitespace-only lines.
    4. Remove consecutive duplicate lines (OCR double-read artefacts).
    5. Collapse runs of ASCII whitespace *within* each line to a single space.
    6. Join remaining lines with ``\\n``.

    Invariants:

    - Japanese punctuation (。、！？「」…・ー) is **preserved unchanged**.
    - Text is **never romanized or translated**.
    - The function is idempotent: ``cleanup_ocr_text(cleanup_ocr_text(s)) == cleanup_ocr_text(s)``.
    """
    if not text:
        return ""

    # Step 1 — full-width space → ASCII space
    text = text.replace(_FULLWIDTH_SPACE, " ")

    # Steps 2–3 — split, strip, drop empties
    lines: list[str] = [line.strip() for line in text.splitlines()]
    lines = [ln for ln in lines if ln]

    # Step 4 — deduplicate consecutive identical lines
    lines = _deduplicate_consecutive(lines)

    # Step 5 — collapse intra-line whitespace runs
    lines = [re.sub(r"[ \t]+", " ", ln) for ln in lines]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _deduplicate_consecutive(lines: list[str]) -> list[str]:
    """Remove lines that are identical to their immediate predecessor."""
    if not lines:
        return []
    result = [lines[0]]
    for line in lines[1:]:
        if line != result[-1]:
            result.append(line)
    return result


# ---------------------------------------------------------------------------
# Backwards-compatible helpers (used by existing tests and callers)
# ---------------------------------------------------------------------------

def normalize_whitespace(text: str) -> str:
    """Collapse all whitespace (including newlines) to a single space and strip."""
    return re.sub(r"\s+", " ", text).strip()


def remove_empty_lines(text: str) -> str:
    """Drop blank or whitespace-only lines, preserving non-empty ones."""
    return "\n".join(line for line in text.splitlines() if line.strip())


def clean_text(text: str) -> str:
    """Remove empty lines then flatten the result to a single-line string."""
    return normalize_whitespace(remove_empty_lines(text))
