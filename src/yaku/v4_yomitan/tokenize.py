from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from yaku.v4_yomitan.dictionary_lookup import DictionaryLookup, DictionaryEntry


@dataclass
class JapaneseToken:
    surface: str
    index: int  # character index in the original line


@dataclass
class TokenBox:
    token: JapaneseToken
    box: tuple[int, int, int, int]  # x, y, w, h in image/screen coordinates


def tokenize_japanese(text: str) -> list[JapaneseToken]:
    """Tokenize Japanese text. Falls back to character-by-character for coordinate precision."""
    tokens = []
    for idx, char in enumerate(text):
        if not char.isspace():
            tokens.append(JapaneseToken(surface=char, index=idx))
    return tokens


def approximate_token_boxes(
    line_text: str,
    line_box: tuple[int, int, int, int],
    tokens: list[JapaneseToken]
) -> list[TokenBox]:
    """Approximates screen coordinate bounding boxes for each token in a text line."""
    x, y, w, h = line_box
    n = len(line_text)
    if n == 0:
        return []

    char_w = w / n
    token_boxes = []
    for token in tokens:
        idx = token.index
        # Calculate approximate horizontal position of the character
        cx = int(x + idx * char_w)
        cw = int(char_w)
        token_boxes.append(TokenBox(token=token, box=(cx, y, cw, h)))

    return token_boxes


def longest_match_lookup(
    line_text: str,
    char_index: int,
    dictionary_lookup: DictionaryLookup,
    max_len: int = 12
) -> tuple[str, list[DictionaryEntry]]:
    """
    Looks up the longest matching substring starting at char_index in line_text.
    Queries dictionary_lookup with deinflection.
    Returns the matched substring and the list of DictionaryEntry objects.
    """
    if char_index < 0 or char_index >= len(line_text):
        return "", []

    substring = line_text[char_index : char_index + max_len]
    
    # Try prefixes from longest to shortest
    for i in range(len(substring), 0, -1):
        prefix = substring[:i]
        entries = dictionary_lookup.lookup_with_deinflection(prefix)
        if entries:
            return prefix, entries

    return "", []
