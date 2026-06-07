from __future__ import annotations

import unicodedata


def contains_japanese(text: str) -> bool:
    """Return True if the text contains any Japanese characters (Hiragana, Katakana, CJK Kanji, or JP punctuation)."""
    for char in text:
        cp = ord(char)
        if (
            (0x3040 <= cp <= 0x309F) or  # Hiragana
            (0x30A0 <= cp <= 0x30FF) or  # Katakana
            (0x4E00 <= cp <= 0x9FAF) or  # CJK Unified Ideographs (Kanji)
            (0x3000 <= cp <= 0x303F) or  # CJK Symbols and Punctuation (Japanese punctuation)
            (0xFF66 <= cp <= 0xFF9F)     # Halfwidth Katakana
        ):
            return True
    return False


def japanese_ratio(text: str) -> float:
    """Return the ratio of Japanese characters (excluding whitespace) to total characters."""
    if not text:
        return 0.0

    filtered_chars = [c for c in text if not c.isspace()]
    if not filtered_chars:
        return 0.0

    jp_count = 0
    for char in filtered_chars:
        cp = ord(char)
        if (
            (0x3040 <= cp <= 0x309F) or  # Hiragana
            (0x30A0 <= cp <= 0x30FF) or  # Katakana
            (0x4E00 <= cp <= 0x9FAF) or  # Kanji
            (0x3000 <= cp <= 0x303F) or  # JP punctuation
            (0xFF66 <= cp <= 0xFF9F)     # Halfwidth Katakana
        ):
            jp_count += 1

    return jp_count / len(filtered_chars)


def clean_ocr_text(text: str) -> str:
    """Clean OCR text by normalizing Unicode and stripping leading/trailing whitespace."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKC", text)
    return normalized.strip()
