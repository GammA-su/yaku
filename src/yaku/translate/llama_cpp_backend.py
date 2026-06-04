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
        
        if config.use_hosted:
            base_url = "https://llm.iosys.fr/v1"
            self._model = "qwen-local"
            self._temperature = 0.2
            self._max_tokens = 128
            api_key = "longapikey"
        else:
            base_url = config.base_url
            if config.port:
                base_url = f"http://127.0.0.1:{config.port}/v1"
            self._model = config.model
            self._temperature = config.temperature
            self._max_tokens = config.max_tokens
            
            api_key = ""
            if config.api_key_env:
                import os
                from yaku.core.env import load_env_file
                load_env_file()
                api_key = os.environ.get(config.api_key_env, "")

        self._base_url = _normalize_base_url(base_url)
        self._completions_url = f"{self._base_url}/chat/completions"
        
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
                
        self._client = httpx.Client(timeout=30.0, transport=_transport, headers=headers)

    # ------------------------------------------------------------------
    # BaseTranslator interface
    # ------------------------------------------------------------------

    @property
    def backend_name(self) -> str:
        return "llama_cpp"

    @property
    def backend_model(self) -> str | None:
        return self._model

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
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }

        try:
            resp = self._client.post(self._completions_url, json=body)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if self._config.use_hosted and exc.response.status_code >= 500:
                raise TranslationError(
                    "LLM is not up, Please use one locally, sorry for the inconvenience."
                ) from exc
            raise TranslationError(
                f"llama.cpp API error {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.RequestError as exc:
            if self._config.use_hosted:
                raise TranslationError(
                    "LLM is not up, Please use one locally, sorry for the inconvenience."
                ) from exc
            raise TranslationError(f"llama.cpp request failed: {exc}") from exc
        except Exception as exc:
            raise TranslationError(f"llama.cpp request failed: {exc}") from exc

        data = resp.json()
        try:
            raw_text: str = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise TranslationError(
                f"Unexpected llama.cpp response structure: {data}"
            ) from exc

        usage = data.get("usage") or {}
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")

        verbose_timings = data.get("__verbose", {})
        tokens_per_second = None
        if isinstance(verbose_timings, dict):
            timings = verbose_timings.get("timings") or {}
            tokens_per_second = timings.get("predicted_per_second")

        return TranslationResult(
            source_text=text,
            translated_text=_strip_response(raw_text),
            target_lang=target_lang,
            backend="llama_cpp",
            backend_model=self._model,
            raw=data,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            tokens_per_second=tokens_per_second,
            base_url=self._base_url,
        )

    def close(self) -> None:
        self._client.close()
