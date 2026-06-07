from __future__ import annotations

from yaku.ocr.japanese_filter import contains_japanese, japanese_ratio, clean_ocr_text


def test_contains_japanese():
    assert contains_japanese("日本語") is True
    assert contains_japanese("ひらがな") is True
    assert contains_japanese("カタカナ") is True
    assert contains_japanese("半角ｶﾀｶﾅ") is True
    assert contains_japanese("Hello World") is False
    assert contains_japanese("12345!@#") is False
    assert contains_japanese("Hello 日本語") is True


def test_japanese_ratio():
    assert japanese_ratio("日本語") == 1.0
    assert japanese_ratio("日本語 abc") == 3 / 6  # excluding space -> '日本語abc'
    assert japanese_ratio("abc") == 0.0
    assert japanese_ratio("") == 0.0


def test_clean_ocr_text():
    assert clean_ocr_text("  日本語  ") == "日本語"
    assert clean_ocr_text("Hello\u3000World") == "Hello World"
