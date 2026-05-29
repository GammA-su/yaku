"""Translator factory — maps config backend name to a concrete translator."""
from __future__ import annotations

from yaku.core.config import TranslatorConfig
from yaku.core.errors import InvalidBackendError
from yaku.translate.base import BaseTranslator


def create_translator(config: TranslatorConfig) -> BaseTranslator:
    """Instantiate and return the translator described by *config*.

    Args:
        config: The ``[translator]`` section of :class:`~yaku.core.config.YakuConfig`.

    Returns:
        A ready-to-use :class:`~yaku.translate.base.BaseTranslator` instance.

    Raises:
        :class:`~yaku.core.errors.InvalidBackendError` for unknown backend names.
        :class:`~yaku.core.errors.TranslationError` when the backend cannot be
        initialised (e.g. missing DeepL API key).
    """
    if config.backend == "deepl":
        from yaku.translate.deepl_backend import DeepLTranslator
        return DeepLTranslator(config.deepl)

    if config.backend == "llama_cpp":
        from yaku.translate.llama_cpp_backend import LlamaCppTranslator
        return LlamaCppTranslator(config.llama_cpp)

    raise InvalidBackendError(
        f"Unknown translation backend: '{config.backend}'. "
        "Valid choices: deepl, llama_cpp"
    )
