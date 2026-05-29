"""Rolling context window of recent dialogue lines for LLM translation prompts."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Optional


@dataclass
class _Entry:
    source_text: str
    translated_text: Optional[str]
    speaker: Optional[str]


class ContextMemory:
    """Fixed-size sliding window of ``(source, translation, speaker)`` entries.

    Keeps the most recent *max_lines* dialogue lines.  Older entries are
    automatically evicted when the window is full.

    Typical usage::

        ctx = ContextMemory(max_lines=5)
        ctx.add("こんにちは", translated_text="Hello", speaker="Hanako")
        prompt_block = ctx.as_prompt_context(n=3)
    """

    def __init__(self, max_lines: int = 20) -> None:
        """
        Args:
            max_lines: Maximum number of entries to retain.
        """
        self._entries: deque[_Entry] = deque(maxlen=max_lines)

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    def add(
        self,
        source_text: str,
        translated_text: Optional[str] = None,
        speaker: Optional[str] = None,
        *,
        suppress_window: int = 0,
    ) -> None:
        """Append a dialogue line.  Oldest entry is dropped when the window is full.

        Args:
            source_text:     Original source-language text.
            translated_text: Optional translated text for this line.
            speaker:         Optional speaker label.
            suppress_window: When > 0, skip adding this entry if *source_text*
                             already appears among the last *suppress_window*
                             entries.  Prevents the same line from cluttering
                             the context when OCR re-reads the same text.
        """
        if suppress_window > 0:
            recent = [e.source_text for e in list(self._entries)[-suppress_window:]]
            if source_text in recent:
                return
        self._entries.append(_Entry(source_text, translated_text, speaker))

    def reset(self) -> None:
        """Clear all stored entries."""
        self._entries.clear()

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def previous_source_lines(self, n: int) -> list[str]:
        """Return the last *n* source texts in chronological order (oldest first).

        Returns an empty list when *n* is 0 or no entries exist.
        """
        if n <= 0:
            return []
        return [e.source_text for e in list(self._entries)[-n:]]

    def previous_translation_lines(self, n: int) -> list[str]:
        """Return the last *n* non-``None`` translated texts (oldest first).

        Entries with ``translated_text=None`` are skipped, so the returned
        list may be shorter than *n*.
        """
        if n <= 0:
            return []
        translated = [
            e.translated_text
            for e in self._entries
            if e.translated_text is not None
        ]
        return translated[-n:]

    def as_prompt_context(self, n: int) -> str:
        """Format the last *n* entries as a plain-text block for LLM prompting.

        Each entry is rendered as::

            [Speaker: ]source_text
            => translated_text   (omitted when translation is None)

        Entries are separated by blank lines.  Returns ``""`` when *n* is 0.
        """
        if n <= 0:
            return ""
        entries = list(self._entries)[-n:]
        parts: list[str] = []
        for e in entries:
            prefix = f"{e.speaker}: " if e.speaker else ""
            line = f"{prefix}{e.source_text}"
            if e.translated_text is not None:
                line += f"\n=> {e.translated_text}"
            parts.append(line)
        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._entries)
