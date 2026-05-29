"""Tests for shared prompt builder functions in yaku.translate.base."""
from __future__ import annotations

from yaku.translate.base import build_system_prompt, build_user_message


# ---------------------------------------------------------------------------
# build_system_prompt
# ---------------------------------------------------------------------------

def test_system_prompt_includes_target_lang():
    prompt = build_system_prompt("English")
    assert "English" in prompt


def test_system_prompt_forbids_explanation():
    prompt = build_system_prompt("English")
    assert "Do not explain" in prompt


def test_system_prompt_return_only_translated_line():
    prompt = build_system_prompt("English")
    assert "Return only the translated line" in prompt


def test_system_prompt_mentions_visual_novel():
    prompt = build_system_prompt("English")
    assert "visual novel" in prompt.lower()


def test_system_prompt_preserves_nuance_instruction():
    prompt = build_system_prompt("German")
    # tone / emotion / honorific should all be mentioned
    assert "tone" in prompt.lower() or "emotion" in prompt.lower()


def test_system_prompt_different_languages():
    en = build_system_prompt("English")
    de = build_system_prompt("German")
    assert "English" in en
    assert "German" in de
    assert en != de


# ---------------------------------------------------------------------------
# build_user_message
# ---------------------------------------------------------------------------

def test_user_message_includes_current_japanese():
    msg = build_user_message("こんにちは", [])
    assert "こんにちは" in msg


def test_user_message_marks_current_section():
    msg = build_user_message("今日もいい天気", [])
    assert "Current Japanese" in msg


def test_user_message_no_context_header_when_empty():
    msg = build_user_message("text", [])
    assert "Previous context" not in msg


def test_user_message_includes_previous_context():
    msg = build_user_message("現在のテキスト", ["以前の行1", "以前の行2"])
    assert "以前の行1" in msg
    assert "以前の行2" in msg


def test_user_message_marks_context_section():
    msg = build_user_message("text", ["prev line"])
    assert "Previous context" in msg


def test_user_message_context_appears_before_current():
    msg = build_user_message("CURRENT", ["PREV"])
    prev_pos = msg.index("PREV")
    curr_pos = msg.index("CURRENT")
    assert prev_pos < curr_pos


def test_user_message_context_lines_use_bullet_prefix():
    msg = build_user_message("text", ["line A", "line B"])
    assert "- line A" in msg
    assert "- line B" in msg


def test_user_message_multiple_context_lines():
    ctx = ["line1", "line2", "line3"]
    msg = build_user_message("current", ctx)
    for line in ctx:
        assert line in msg
