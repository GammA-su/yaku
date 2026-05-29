"""Tests for OCR text normalization utilities."""
from __future__ import annotations

import pytest

from yaku.core.pipeline import _is_meaningful_ocr_text
from yaku.core.text_cleanup import (
    clean_text,
    cleanup_ocr_text,
    normalize_whitespace,
    remove_empty_lines,
)


# ---------------------------------------------------------------------------
# cleanup_ocr_text — primary API
# ---------------------------------------------------------------------------

def test_cleanup_fullwidth_space_converted():
    assert cleanup_ocr_text("hello　world") == "hello world"


def test_cleanup_multiple_fullwidth_spaces():
    result = cleanup_ocr_text("　　text　")
    assert result == "text"


def test_cleanup_removes_empty_lines():
    result = cleanup_ocr_text("line one\n\nline two")
    assert result == "line one\nline two"


def test_cleanup_removes_whitespace_only_lines():
    result = cleanup_ocr_text("line one\n   \nline two")
    assert result == "line one\nline two"


def test_cleanup_deduplicates_consecutive_lines():
    text = "こんにちは\nこんにちは\nありがとう"
    assert cleanup_ocr_text(text) == "こんにちは\nありがとう"


def test_cleanup_triple_consecutive_deduplicates_to_one():
    text = "A\nA\nA\nB"
    assert cleanup_ocr_text(text) == "A\nB"


def test_cleanup_keeps_non_consecutive_duplicates():
    text = "A\nB\nA"
    assert cleanup_ocr_text(text) == "A\nB\nA"


def test_cleanup_preserves_japanese_punctuation():
    text = "これは、テストです。\n「こんにちは！」\n…それだけ？"
    result = cleanup_ocr_text(text)
    for char in "、。「」！…？":
        assert char in result, f"Expected Japanese punctuation {char!r} to be preserved"


def test_cleanup_preserves_middle_dot_and_long_vowel():
    text = "コーヒー・ラテ"
    assert cleanup_ocr_text(text) == "コーヒー・ラテ"


def test_cleanup_collapses_intraline_ascii_spaces():
    result = cleanup_ocr_text("hello   world")
    assert result == "hello world"


def test_cleanup_strips_line_leading_trailing_space():
    result = cleanup_ocr_text("  hello  \n  world  ")
    assert result == "hello\nworld"


def test_cleanup_empty_string():
    assert cleanup_ocr_text("") == ""


def test_cleanup_only_whitespace_returns_empty():
    assert cleanup_ocr_text("   \n\n   ") == ""


def test_cleanup_single_line_no_change():
    assert cleanup_ocr_text("plain text") == "plain text"


def test_cleanup_is_idempotent():
    text = "こんにちは　世界\n\nこんにちは　世界\nありがとう"
    once = cleanup_ocr_text(text)
    twice = cleanup_ocr_text(once)
    assert once == twice


# ---------------------------------------------------------------------------
# normalize_whitespace — backwards-compat helper
# ---------------------------------------------------------------------------

def test_normalize_whitespace_collapses_spaces():
    assert normalize_whitespace("hello   world") == "hello world"


def test_normalize_whitespace_strips_edges():
    assert normalize_whitespace("  leading and trailing  ") == "leading and trailing"


def test_normalize_whitespace_tabs():
    assert normalize_whitespace("a\t\tb") == "a b"


def test_normalize_whitespace_newlines_flattened():
    assert normalize_whitespace("line one\nline two") == "line one line two"


# ---------------------------------------------------------------------------
# remove_empty_lines — backwards-compat helper
# ---------------------------------------------------------------------------

def test_remove_empty_lines_drops_blank():
    result = remove_empty_lines("line one\n\nline two\n\n\nline three")
    assert result == "line one\nline two\nline three"


def test_remove_empty_lines_drops_whitespace_only():
    result = remove_empty_lines("a\n   \nb")
    assert result == "a\nb"


def test_remove_empty_lines_preserves_content_lines():
    text = "no blanks\nhere"
    assert remove_empty_lines(text) == text


# ---------------------------------------------------------------------------
# clean_text — backwards-compat helper
# ---------------------------------------------------------------------------

def test_clean_text_flattens_and_normalizes():
    result = clean_text("  hello   world  \n\n  foo  bar  \n  ")
    assert result == "hello world foo bar"
    assert "  " not in result


def test_clean_text_empty_string():
    assert clean_text("") == ""


def test_clean_text_only_whitespace():
    assert clean_text("   \n\n   ") == ""


def test_punctuation_only_ocr_text_is_not_meaningful():
    assert not _is_meaningful_ocr_text("...")
    assert not _is_meaningful_ocr_text("・・・")
    assert _is_meaningful_ocr_text("そういえば")
