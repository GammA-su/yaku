"""Tests for text layout utilities in yaku.render.text_fit."""
from __future__ import annotations

import pytest
from PIL import ImageFont

from yaku.render.text_fit import wrap_text_to_width


# Use PIL's default font (always available, no file path needed)
@pytest.fixture(scope="module")
def font():
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# wrap_text_to_width
# ---------------------------------------------------------------------------

def test_wrap_returns_nonempty(font):
    lines = wrap_text_to_width("Hello world", font, max_width=200)
    assert lines
    assert any(line for line in lines)


def test_wrap_empty_string_returns_single_empty_line(font):
    assert wrap_text_to_width("", font, 200) == [""]


def test_wrap_short_text_stays_single_line(font):
    text = "Hi"
    lines = wrap_text_to_width(text, font, max_width=5000)
    assert len(lines) == 1
    assert lines[0] == "Hi"


def test_wrap_long_text_splits_into_multiple_lines(font):
    # Very long text that definitely exceeds 1 pixel
    long_text = " ".join(["word"] * 50)
    lines = wrap_text_to_width(long_text, font, max_width=50)
    assert len(lines) > 1


def test_wrap_each_line_fits_max_width(font):
    from yaku.render.text_fit import _measure_width
    long_text = " ".join([f"word{i}" for i in range(40)])
    max_w = 60
    lines = wrap_text_to_width(long_text, font, max_width=max_w)
    for line in lines:
        width = _measure_width(font, line)
        # Each line (except single oversized words) must fit
        words = line.split()
        if len(words) > 1:
            assert width <= max_w, f"Line {line!r} is too wide ({width} > {max_w})"


def test_wrap_preserves_explicit_newlines(font):
    text = "line one\nline two"
    lines = wrap_text_to_width(text, font, max_width=5000)
    assert len(lines) == 2
    assert lines[0] == "line one"
    assert lines[1] == "line two"


def test_wrap_blank_paragraph_produces_empty_string(font):
    text = "before\n\nafter"
    lines = wrap_text_to_width(text, font, max_width=5000)
    assert "" in lines
    assert "before" in lines
    assert "after" in lines


def test_wrap_single_word_always_on_own_line(font):
    lines = wrap_text_to_width("superlongword", font, max_width=1)
    assert len(lines) == 1
    assert lines[0] == "superlongword"


def test_wrap_multiple_paragraphs(font):
    text = "para one\npara two\npara three"
    lines = wrap_text_to_width(text, font, max_width=5000)
    assert lines == ["para one", "para two", "para three"]


def test_wrap_whitespace_only_text(font):
    lines = wrap_text_to_width("   ", font, max_width=200)
    assert lines == [""]


def test_wrap_returns_list_of_strings(font):
    lines = wrap_text_to_width("test", font, max_width=100)
    assert isinstance(lines, list)
    assert all(isinstance(l, str) for l in lines)
