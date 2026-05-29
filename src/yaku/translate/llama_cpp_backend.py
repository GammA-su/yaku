"""llama.cpp OpenAI-compatible chat/completions translation backend."""
from __future__ import annotations

import re
from typing import Any, Optional, Sequence

import httpx

from yaku.core.config import LlamaCppConfig
from yaku.core.errors import TranslationError
from yaku.translate.base import (
    BaseTranslator,
    TranslationResult,
    build_system_prompt,
    build_user_message,
)


def _normalize_base_url(url: str) -> str:
    """Ensure the URL ends with ``/v1`` exactly once.

    Accepts both ``http://host:port`` and ``http://host:port/v1``.
    """
    url = url.rstrip("/")
    if not url.endswith("/v1"):
        url += "/v1"
    return url


def _strip_response(text: str) -> str:
    """Remove common model decoration from a response string.

    Strips (in order):
    1. Markdown triple-backtick fences: ``\\`\\`\\`...\\`\\`\\``
    2. Surrounding double- or single-quotes wrapping the whole text.
    3. Leading / trailing whitespace.
    """
    text = text.strip()

    # Triple-backtick fences (```optional-lang\\ncontents\\n```)
    fenced = re.fullmatch(r"```[^\n]*\n(.*)\n```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()

    # Surrounding matching quotes
    if len(text) >= 2 and (
        (text[0] == '"' and text[-1] == '"')
        or (text[0] == "'" and text[-1] == "'")
    ):
        text = text[1:-1]

    return text.strip()


class LlamaCppTranslator(BaseTranslator):
    """Calls a llama.cpp server's OpenAI-compatible ``/v1/chat/completions`` endpoint.

    Pass ``_transport`` (an :class:`httpx.BaseTransport`) to inject a mock
    during tests.
    """

    def __init__(
        self,
        config: LlamaCppConfig,
        *,
        _transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self._config = config
        self._base_url = _normalize_base_url(config.base_url)
        self._completions_url = f"{self._base_url}/chat/completions"
        self._client = httpx.Client(timeout=30.0, transport=_transport)

    # ------------------------------------------------------------------
    # BaseTranslator interface
    # ------------------------------------------------------------------

    @property
    def backend_name(self) -> str:
        return "llama_cpp"

    @property
    def backend_model(self) -> str | None:
        return self._config.model

    def translate(
        self,
        text: str,
        context: list[str],
        target_lang: str,
        glossary: Sequence[Any] | None = None,
    ) -> TranslationResult:
        system_msg = build_system_prompt(target_lang)
        user_msg = build_user_message(text, context, glossary)

        body = {
            "model": self._config.model,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            "temperature": self._config.temperature,
            "max_tokens": self._config.max_tokens,
        }

        try:
            resp = self._client.post(self._completions_url, json=body)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise TranslationError(
                f"llama.cpp API error {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.RequestError as exc:
            raise TranslationError(f"llama.cpp request failed: {exc}") from exc

        data = resp.json()
        try:
            raw_text: str = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise TranslationError(
                f"Unexpected llama.cpp response structure: {data}"
            ) from exc

        return TranslationResult(
            source_text=text,
            translated_text=_strip_response(raw_text),
            target_lang=target_lang,
            backend="llama_cpp",
            backend_model=self._config.model,
            raw=data,
        )

    def close(self) -> None:
        self._client.close()
