"""Shared translator interface, result dataclass, and prompt builders."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Sequence


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class TranslationResult:
    """Returned by every translator backend."""

    source_text: str
    translated_text: str
    target_lang: str
    backend: str
    backend_model: str | None = None
    cached: bool = False
    raw_source_text: str = ""
    ocr_ms: float | None = None
    translation_ms: float | None = None
    raw: dict | None = None
    metrics: object | None = None  # PipelineMetrics (avoids an import cycle)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class BaseTranslator(ABC):
    """Protocol all translation backends must satisfy."""

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Short identifier used as the cache key (e.g. ``'deepl'``, ``'llama_cpp'``)."""

    @property
    def backend_model(self) -> str | None:
        """Model name / version used, or ``None`` when the backend has no concept of a model."""
        return None

    @abstractmethod
    def translate(
        self,
        text: str,
        context: list[str],
        target_lang: str,
        glossary: Sequence[Any] | None = None,
    ) -> TranslationResult:
        """Translate *text* and return a populated :class:`TranslationResult`.

        Args:
            text:        Source-language text to translate.
            context:     Previous dialogue lines (oldest first) to help the model.
                         Pass an empty list when no context is available.
            target_lang: BCP-47 / ISO language code for the target language.
            glossary:    Optional glossary entries with ``source``, ``target``,
                         and optional ``note`` attributes/keys.
        """

    def close(self) -> None:
        """Release any held resources (HTTP clients, model handles, …)."""


# ---------------------------------------------------------------------------
# Null / fallback translator
# ---------------------------------------------------------------------------

class NullTranslator(BaseTranslator):
    """Pass-through translator that returns the source text unchanged.

    Used as a fallback when no real backend is configured or available.
    """

    @property
    def backend_name(self) -> str:
        return "null"

    def translate(
        self,
        text: str,
        context: list[str],
        target_lang: str,
        glossary: Sequence[Any] | None = None,
    ) -> TranslationResult:
        return TranslationResult(
            source_text=text,
            translated_text=text,
            target_lang=target_lang,
            backend="null",
        )


# ---------------------------------------------------------------------------
# Prompt builders — shared by backends and independently testable
# ---------------------------------------------------------------------------

def build_system_prompt(target_lang: str) -> str:
    """Return the system instruction string for the given target language.

    The prompt instructs the model to translate faithfully and return *only*
    the translated line — no explanations, no commentary.
    """
    return (
        f"You are translating Japanese visual novel dialogue into natural {target_lang}.\n"
        "Preserve tone, emotion, names, honorific nuance, and speaker intent.\n"
        "Do not explain.\n"
        "Return only the translated line."
    )


def _entry_value(entry: Any, key: str, default: str = "") -> str:
    if isinstance(entry, dict):
        value = entry.get(key, default)
    else:
        value = getattr(entry, key, default)
    return "" if value is None else str(value)


def format_glossary_lines(glossary: Sequence[Any] | None) -> list[str]:
    """Return prompt/context lines for enabled glossary entries."""
    if not glossary:
        return []
    lines: list[str] = []
    for entry in glossary:
        source = _entry_value(entry, "source").strip()
        target = _entry_value(entry, "target").strip()
        note = _entry_value(entry, "note").strip()
        if not source or not target:
            continue
        line = f"- {source} => {target}"
        if note:
            line += f" ({note})"
        lines.append(line)
    return lines


def build_user_message(
    text: str,
    context: list[str],
    glossary: Sequence[Any] | None = None,
) -> str:
    """Return the user message string combining previous context and current text.

    Format when context is non-empty::

        Previous context:
        - line 1
        - line 2
        Current Japanese:
        <text>

    Format when context is empty::

        Current Japanese:
        <text>
    """
    parts: list[str] = []
    glossary_lines = format_glossary_lines(glossary)
    if glossary_lines:
        parts.append("Glossary:")
        parts.extend(glossary_lines)
    if context:
        parts.append("Previous context:")
        for line in context:
            parts.append(f"- {line}")
    parts.append("Current Japanese:")
    parts.append(text)
    return "\n".join(parts)
