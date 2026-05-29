"""Tests for ContextMemory rolling dialogue context window."""
from __future__ import annotations

import pytest

from yaku.core.context_memory import ContextMemory


# ---------------------------------------------------------------------------
# Basic add / read
# ---------------------------------------------------------------------------

def test_empty_memory_returns_empty_lists():
    mem = ContextMemory()
    assert mem.previous_source_lines(5) == []
    assert mem.previous_translation_lines(5) == []


def test_add_single_entry_and_read_source():
    mem = ContextMemory()
    mem.add("こんにちは", "Hello")
    assert mem.previous_source_lines(1) == ["こんにちは"]


def test_add_multiple_entries_source_order():
    mem = ContextMemory()
    mem.add("こんにちは", "Hello")
    mem.add("ありがとう", "Thank you")
    assert mem.previous_source_lines(2) == ["こんにちは", "ありがとう"]


def test_previous_source_limited_by_n():
    mem = ContextMemory()
    for i in range(5):
        mem.add(f"line{i}", f"L{i}")
    result = mem.previous_source_lines(2)
    assert result == ["line3", "line4"]


# ---------------------------------------------------------------------------
# Translation lines
# ---------------------------------------------------------------------------

def test_previous_translation_lines_basic():
    mem = ContextMemory()
    mem.add("src1", "T1")
    mem.add("src2", "T2")
    assert mem.previous_translation_lines(2) == ["T1", "T2"]


def test_previous_translation_skips_none_entries():
    mem = ContextMemory()
    mem.add("src1", None)           # no translation yet
    mem.add("src2", "translated")
    assert mem.previous_translation_lines(5) == ["translated"]


def test_previous_translation_all_none():
    mem = ContextMemory()
    mem.add("src1")
    mem.add("src2")
    assert mem.previous_translation_lines(5) == []


def test_previous_translation_limited_by_n():
    mem = ContextMemory()
    for i in range(5):
        mem.add(f"s{i}", f"t{i}")
    result = mem.previous_translation_lines(2)
    assert result == ["t3", "t4"]


# ---------------------------------------------------------------------------
# Max-lines eviction
# ---------------------------------------------------------------------------

def test_max_lines_evicts_oldest():
    mem = ContextMemory(max_lines=3)
    for i in range(5):
        mem.add(f"line{i}", f"L{i}")
    assert len(mem) == 3
    assert mem.previous_source_lines(3) == ["line2", "line3", "line4"]


def test_len_reflects_actual_entries():
    mem = ContextMemory(max_lines=10)
    for i in range(4):
        mem.add(f"s{i}")
    assert len(mem) == 4


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------

def test_reset_clears_all_entries():
    mem = ContextMemory()
    mem.add("text", "translation")
    mem.reset()
    assert len(mem) == 0
    assert mem.previous_source_lines(5) == []
    assert mem.previous_translation_lines(5) == []


# ---------------------------------------------------------------------------
# as_prompt_context
# ---------------------------------------------------------------------------

def test_as_prompt_context_includes_source_and_translation():
    mem = ContextMemory()
    mem.add("こんにちは", "Hello")
    result = mem.as_prompt_context(1)
    assert "こんにちは" in result
    assert "Hello" in result


def test_as_prompt_context_includes_speaker():
    mem = ContextMemory()
    mem.add("セリフ", "Dialogue", speaker="Alice")
    result = mem.as_prompt_context(1)
    assert "Alice" in result
    assert "セリフ" in result


def test_as_prompt_context_n_zero_returns_empty():
    mem = ContextMemory()
    mem.add("text", "translation")
    assert mem.as_prompt_context(0) == ""


def test_as_prompt_context_without_translation():
    mem = ContextMemory()
    mem.add("source text only")
    result = mem.as_prompt_context(1)
    assert "source text only" in result
    assert "=>" not in result


def test_as_prompt_context_multiple_entries():
    mem = ContextMemory()
    mem.add("line A", "trans A")
    mem.add("line B", "trans B")
    result = mem.as_prompt_context(2)
    assert "line A" in result
    assert "trans A" in result
    assert "line B" in result
    assert "trans B" in result


def test_as_prompt_context_n_exceeds_stored():
    mem = ContextMemory()
    mem.add("only one")
    result = mem.as_prompt_context(10)
    assert "only one" in result


# ---------------------------------------------------------------------------
# n=0 edge cases
# ---------------------------------------------------------------------------

def test_previous_source_lines_n_zero():
    mem = ContextMemory()
    mem.add("text", "translation")
    assert mem.previous_source_lines(0) == []


def test_previous_translation_lines_n_zero():
    mem = ContextMemory()
    mem.add("text", "translation")
    assert mem.previous_translation_lines(0) == []
