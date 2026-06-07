from __future__ import annotations
import re
import unicodedata
from collections import deque

_PUNCTUATION_RE = re.compile(r"[\s。、，,.!！?？…・「」『』（）()\[\]【】\-ー~〜]+")


def normalize_japanese_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    return _PUNCTUATION_RE.sub("", normalized).strip()


class TranscriptCleanup:
    def __init__(self, min_transcript_chars: int = 2, dedupe_window: int = 5) -> None:
        self.min_transcript_chars = min_transcript_chars
        self.dedupe_window = dedupe_window
        self.history: deque[str] = deque(maxlen=dedupe_window)

    def clean(self, text: str) -> str:
        """Perform basic whitespace cleanup."""
        return re.sub(r"\s+", " ", text).strip()

    def should_ignore(self, text: str) -> bool:
        """
        Check if the transcript is too short or is a duplicate of a recent transcript.
        """
        cleaned = self.clean(text)
        normalized = normalize_japanese_text(cleaned)

        # Ignore if less than minimum characters (excluding punctuation)
        if len(normalized) < self.min_transcript_chars:
            return True

        # Check for duplicates in sliding window
        for past_text in self.history:
            past_norm = normalize_japanese_text(past_text)
            if past_norm == normalized:
                return True

        return False

    def add_to_history(self, text: str) -> None:
        self.history.append(text)

    def clear(self) -> None:
        self.history.clear()
