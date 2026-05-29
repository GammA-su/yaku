"""Tests for LlamaCppTranslator — all HTTP calls are mocked via a custom transport."""
from __future__ import annotations

import json

import httpx
import pytest

from yaku.core.config import LlamaCppConfig
from yaku.core.errors import TranslationError
from yaku.translate.llama_cpp_backend import (
    LlamaCppTranslator,
    _normalize_base_url,
    _strip_response,
)


# ---------------------------------------------------------------------------
# Transport helpers
# ---------------------------------------------------------------------------

class _CapturingTransport(httpx.BaseTransport):
    """Records the last request and returns a fixed response."""

    def __init__(self, response: httpx.Response) -> None:
        self.last_request: httpx.Request | None = None
        self._response = response

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.last_request = request
        return self._response


def _completion_response(content: str = "Hello") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [
                {"message": {"role": "assistant", "content": content}}
            ]
        },
    )


def _make_translator(
    transport: httpx.BaseTransport,
    **config_overrides,
) -> LlamaCppTranslator:
    config = LlamaCppConfig(**config_overrides) if config_overrides else LlamaCppConfig()
    return LlamaCppTranslator(config, _transport=transport)


# ---------------------------------------------------------------------------
# URL normalisation
# ---------------------------------------------------------------------------

def test_normalize_base_url_no_v1():
    assert _normalize_base_url("http://127.0.0.1:8080") == "http://127.0.0.1:8080/v1"


def test_normalize_base_url_already_has_v1():
    assert _normalize_base_url("http://127.0.0.1:8080/v1") == "http://127.0.0.1:8080/v1"


def test_normalize_base_url_trailing_slash():
    assert _normalize_base_url("http://127.0.0.1:8080/v1/") == "http://127.0.0.1:8080/v1"


def test_normalize_base_url_no_double_v1():
    url = _normalize_base_url("http://127.0.0.1:8080/v1")
    assert url.count("/v1") == 1


# ---------------------------------------------------------------------------
# Response stripping
# ---------------------------------------------------------------------------

def test_strip_plain_text_unchanged():
    assert _strip_response("Hello, world.") == "Hello, world."


def test_strip_leading_trailing_whitespace():
    assert _strip_response("  Hello  ") == "Hello"


def test_strip_markdown_triple_fence():
    raw = "```\nHello, world.\n```"
    assert _strip_response(raw) == "Hello, world."


def test_strip_markdown_fence_with_language():
    raw = "```text\nHello, world.\n```"
    assert _strip_response(raw) == "Hello, world."


def test_strip_surrounding_double_quotes():
    assert _strip_response('"Hello, world."') == "Hello, world."


def test_strip_surrounding_single_quotes():
    assert _strip_response("'Hello, world.'") == "Hello, world."


def test_strip_does_not_remove_internal_quotes():
    assert _strip_response("She said \"hi\".") == 'She said "hi".'


# ---------------------------------------------------------------------------
# Request structure
# ---------------------------------------------------------------------------

def test_sends_chat_completions_request():
    transport = _CapturingTransport(_completion_response())
    translator = _make_translator(transport)
    translator.translate("こんにちは", [], "en")

    assert transport.last_request is not None
    assert "/chat/completions" in str(transport.last_request.url)


def test_sends_correct_model(monkeypatch):
    transport = _CapturingTransport(_completion_response())
    translator = _make_translator(transport, model="my-model")
    translator.translate("text", [], "en")

    body = json.loads(transport.last_request.content)
    assert body["model"] == "my-model"


def test_sends_temperature_and_max_tokens():
    transport = _CapturingTransport(_completion_response())
    translator = _make_translator(transport, temperature=0.5, max_tokens=128)
    translator.translate("text", [], "en")

    body = json.loads(transport.last_request.content)
    assert body["temperature"] == 0.5
    assert body["max_tokens"] == 128


def test_sends_system_and_user_messages():
    transport = _CapturingTransport(_completion_response())
    translator = _make_translator(transport)
    translator.translate("こんにちは", [], "en")

    body = json.loads(transport.last_request.content)
    roles = [m["role"] for m in body["messages"]]
    assert "system" in roles
    assert "user" in roles


def test_system_message_mentions_target_lang():
    transport = _CapturingTransport(_completion_response())
    translator = _make_translator(transport)
    translator.translate("text", [], "German")

    body = json.loads(transport.last_request.content)
    system_content = next(m["content"] for m in body["messages"] if m["role"] == "system")
    assert "German" in system_content


def test_user_message_includes_current_text():
    transport = _CapturingTransport(_completion_response())
    translator = _make_translator(transport)
    translator.translate("こんにちは", [], "en")

    body = json.loads(transport.last_request.content)
    user_content = next(m["content"] for m in body["messages"] if m["role"] == "user")
    assert "こんにちは" in user_content


def test_user_message_includes_context():
    transport = _CapturingTransport(_completion_response())
    translator = _make_translator(transport)
    translator.translate("CURRENT", ["PREV_LINE_1", "PREV_LINE_2"], "en")

    body = json.loads(transport.last_request.content)
    user_content = next(m["content"] for m in body["messages"] if m["role"] == "user")
    assert "PREV_LINE_1" in user_content
    assert "PREV_LINE_2" in user_content


# ---------------------------------------------------------------------------
# Parsed response
# ---------------------------------------------------------------------------

def test_mocked_response_parsed():
    transport = _CapturingTransport(_completion_response("Hello, world."))
    translator = _make_translator(transport)
    result = translator.translate("こんにちは", [], "en")

    assert result.translated_text == "Hello, world."
    assert result.backend == "llama_cpp"
    assert result.cached is False
    assert result.source_text == "こんにちは"
    assert result.target_lang == "en"


def test_backend_model_matches_config():
    transport = _CapturingTransport(_completion_response())
    translator = _make_translator(transport, model="qwen2.5")
    result = translator.translate("text", [], "en")
    assert result.backend_model == "qwen2.5"


def test_response_strips_markdown_fence():
    transport = _CapturingTransport(_completion_response("```\nHello\n```"))
    translator = _make_translator(transport)
    result = translator.translate("text", [], "en")
    assert result.translated_text == "Hello"


def test_response_strips_surrounding_quotes():
    transport = _CapturingTransport(_completion_response('"Hello"'))
    translator = _make_translator(transport)
    result = translator.translate("text", [], "en")
    assert result.translated_text == "Hello"


def test_result_raw_contains_choices():
    transport = _CapturingTransport(_completion_response("Hi"))
    translator = _make_translator(transport)
    result = translator.translate("text", [], "en")
    assert result.raw is not None
    assert "choices" in result.raw


# ---------------------------------------------------------------------------
# Base URL variants
# ---------------------------------------------------------------------------

def test_base_url_without_v1_still_hits_completions():
    config = LlamaCppConfig(base_url="http://127.0.0.1:8080")
    transport = _CapturingTransport(_completion_response())
    translator = LlamaCppTranslator(config, _transport=transport)
    translator.translate("text", [], "en")
    assert "/v1/chat/completions" in str(transport.last_request.url)


def test_base_url_with_v1_does_not_double():
    config = LlamaCppConfig(base_url="http://127.0.0.1:8080/v1")
    transport = _CapturingTransport(_completion_response())
    translator = LlamaCppTranslator(config, _transport=transport)
    translator.translate("text", [], "en")
    url = str(transport.last_request.url)
    assert url.count("/v1") == 1
    assert "/v1/chat/completions" in url


# ---------------------------------------------------------------------------
# HTTP error handling
# ---------------------------------------------------------------------------

def test_http_500_raises_translation_error():
    transport = _CapturingTransport(httpx.Response(500, text="Internal Server Error"))
    translator = _make_translator(transport)

    with pytest.raises(TranslationError) as exc_info:
        translator.translate("text", [], "en")
    assert "500" in str(exc_info.value)
