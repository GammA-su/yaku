"""DeepL REST API v2 translation backend."""
from __future__ import annotations

import os
from typing import Any, Optional, Sequence

import httpx

from yaku.core.config import DeepLConfig
from yaku.core.env import load_env_file
from yaku.core.errors import TranslationError
from yaku.translate.base import BaseTranslator, TranslationResult, format_glossary_lines

_TRANSLATE_URL = "https://api-free.deepl.com/v2/translate"


class DeepLTranslator(BaseTranslator):
    """Calls the DeepL free-tier REST API.

    Pass ``_transport`` (an :class:`httpx.BaseTransport`) to inject a mock
    during tests — it is forwarded straight to the underlying
    :class:`httpx.Client`.
    """

    def __init__(
        self,
        config: DeepLConfig,
        *,
        _transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        load_env_file()
        api_key = os.environ.get(config.api_key_env, "")
        if not api_key:
            raise TranslationError(
                f"{config.api_key_env} is missing. "
                "Set it or use --translator llama-cpp."
            )
        self._config = config
        self._client = httpx.Client(
            headers={"Authorization": f"DeepL-Auth-Key {api_key}"},
            timeout=15.0,
            transport=_transport,
        )

    # ------------------------------------------------------------------
    # BaseTranslator interface
    # ------------------------------------------------------------------

    @property
    def backend_name(self) -> str:
        return "deepl"

    def translate(
        self,
        text: str,
        context: list[str],
        target_lang: str,
        glossary: Sequence[Any] | None = None,
    ) -> TranslationResult:
        body: dict = {
            "text": [text],
            "target_lang": target_lang,
        }
        if self._config.formality and self._config.formality != "default":
            body["formality"] = self._config.formality
        if self._config.use_context:
            context_parts = list(context)
            glossary_lines = format_glossary_lines(glossary)
            if glossary_lines:
                context_parts.append("Glossary:")
                context_parts.extend(glossary_lines)
            if context_parts:
                body["context"] = "\n".join(context_parts)

        try:
            resp = self._client.post(_TRANSLATE_URL, json=body)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise TranslationError(
                f"DeepL API error {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.RequestError as exc:
            raise TranslationError(f"DeepL request failed: {exc}") from exc

        data = resp.json()
        try:
            translated = data["translations"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise TranslationError(
                f"Unexpected DeepL response structure: {data}"
            ) from exc

        return TranslationResult(
            source_text=text,
            translated_text=translated,
            target_lang=target_lang,
            backend="deepl",
            raw=data,
        )

    def close(self) -> None:
        self._client.close()
