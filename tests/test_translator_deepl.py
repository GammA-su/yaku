"""Tests for DeepLTranslator — all HTTP calls are mocked via a custom transport."""
from __future__ import annotations

import json

import httpx
import pytest

from yaku.core.cache import YakuCache
from yaku.core.config import DeepLConfig
from yaku.core.errors import TranslationError
from yaku.core.pipeline import translate_with_cache
from yaku.translate.deepl_backend import DeepLTranslator


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


class _ErrorTransport(httpx.BaseTransport):
    """Raises AssertionError if any request is attempted — used to verify cache hits."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        raise AssertionError(
            f"HTTP request to {request.url} was made but should have been served from cache"
        )


def _deepl_ok(translated_text: str = "Hello") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "translations": [
                {"detected_source_language": "JA", "text": translated_text}
            ]
        },
    )


def _make_translator(
    config: DeepLConfig,
    transport: httpx.BaseTransport,
    monkeypatch,
    api_key: str = "test-api-key",
) -> DeepLTranslator:
    monkeypatch.setenv(config.api_key_env, api_key)
    return DeepLTranslator(config, _transport=transport)


# ---------------------------------------------------------------------------
# API key validation
# ---------------------------------------------------------------------------

def test_missing_key_raises_translation_error(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)
    config = DeepLConfig(api_key_env="DEEPL_API_KEY")
    with pytest.raises(TranslationError) as exc_info:
        DeepLTranslator(config)
    msg = str(exc_info.value)
    assert "DEEPL_API_KEY" in msg
    assert "llama-cpp" in msg


def test_missing_custom_env_var_name(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MY_DEEPL_KEY", raising=False)
    config = DeepLConfig(api_key_env="MY_DEEPL_KEY")
    with pytest.raises(TranslationError) as exc_info:
        DeepLTranslator(config)
    assert "MY_DEEPL_KEY" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Successful translation
# ---------------------------------------------------------------------------

def test_mocked_response_parsed(monkeypatch):
    config = DeepLConfig()
    transport = _CapturingTransport(_deepl_ok("Hello, world."))
    translator = _make_translator(config, transport, monkeypatch)

    result = translator.translate("こんにちは、世界。", [], "EN-US")

    assert result.translated_text == "Hello, world."
    assert result.backend == "deepl"
    assert result.target_lang == "EN-US"
    assert result.source_text == "こんにちは、世界。"
    assert result.cached is False
    assert result.raw is not None


def test_result_raw_contains_api_data(monkeypatch):
    config = DeepLConfig()
    transport = _CapturingTransport(_deepl_ok("Hi"))
    translator = _make_translator(config, transport, monkeypatch)

    result = translator.translate("こんにちは", [], "EN-US")
    assert "translations" in result.raw  # type: ignore[index]


# ---------------------------------------------------------------------------
# Context forwarding
# ---------------------------------------------------------------------------

def test_sends_context_when_use_context_true(monkeypatch):
    config = DeepLConfig(use_context=True)
    transport = _CapturingTransport(_deepl_ok())
    translator = _make_translator(config, transport, monkeypatch)

    translator.translate("現在のテキスト", ["前の行1", "前の行2"], "EN-US")

    body = json.loads(transport.last_request.content)
    assert "context" in body
    assert "前の行1" in body["context"]
    assert "前の行2" in body["context"]


def test_omits_context_when_use_context_false(monkeypatch):
    config = DeepLConfig(use_context=False)
    transport = _CapturingTransport(_deepl_ok())
    translator = _make_translator(config, transport, monkeypatch)

    translator.translate("text", ["prev line"], "EN-US")

    body = json.loads(transport.last_request.content)
    assert "context" not in body


def test_omits_context_when_context_list_empty(monkeypatch):
    config = DeepLConfig(use_context=True)
    transport = _CapturingTransport(_deepl_ok())
    translator = _make_translator(config, transport, monkeypatch)

    translator.translate("text", [], "EN-US")

    body = json.loads(transport.last_request.content)
    assert "context" not in body


# ---------------------------------------------------------------------------
# Request structure
# ---------------------------------------------------------------------------

def test_request_sends_text_as_list(monkeypatch):
    config = DeepLConfig()
    transport = _CapturingTransport(_deepl_ok())
    translator = _make_translator(config, transport, monkeypatch)

    translator.translate("こんにちは", [], "EN-US")

    body = json.loads(transport.last_request.content)
    assert isinstance(body["text"], list)
    assert body["text"] == ["こんにちは"]


def test_request_sends_target_lang(monkeypatch):
    config = DeepLConfig()
    transport = _CapturingTransport(_deepl_ok())
    translator = _make_translator(config, transport, monkeypatch)

    translator.translate("text", [], "DE")

    body = json.loads(transport.last_request.content)
    assert body["target_lang"] == "DE"


# ---------------------------------------------------------------------------
# HTTP error handling
# ---------------------------------------------------------------------------

def test_http_403_raises_translation_error(monkeypatch):
    config = DeepLConfig()
    error_resp = httpx.Response(403, json={"message": "Authorization failure."})
    transport = _CapturingTransport(error_resp)
    translator = _make_translator(config, transport, monkeypatch)

    with pytest.raises(TranslationError) as exc_info:
        translator.translate("text", [], "EN-US")
    assert "403" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Cache integration
# ---------------------------------------------------------------------------

def test_cache_hit_avoids_http_call(monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPL_API_KEY", "test-key")
    config = DeepLConfig()

    # Pre-populate cache
    cache = YakuCache(tmp_path / "cache.sqlite3")
    cache.put_translation("こんにちは", "EN-US", "deepl", "Hello (cached)")

    # Translator with a transport that would explode on any HTTP call
    translator = DeepLTranslator(config, _transport=_ErrorTransport())

    result = translate_with_cache(cache, translator, "こんにちは", [], "EN-US")

    assert result.translated_text == "Hello (cached)"
    assert result.cached is True
    cache.close()


def test_cache_miss_calls_backend_and_stores_result(monkeypatch, tmp_path):
    config = DeepLConfig()
    transport = _CapturingTransport(_deepl_ok("Fresh translation"))
    translator = _make_translator(config, transport, monkeypatch)

    cache = YakuCache(tmp_path / "cache.sqlite3")
    result = translate_with_cache(cache, translator, "ありがとう", [], "EN-US")

    assert result.translated_text == "Fresh translation"
    assert result.cached is False

    # Second call must hit cache (transport would fail if called again)
    transport2 = _CapturingTransport(_deepl_ok("SHOULD NOT APPEAR"))
    translator2 = _make_translator(config, transport2, monkeypatch)
    result2 = translate_with_cache(cache, translator2, "ありがとう", [], "EN-US")
    assert result2.cached is True
    assert result2.translated_text == "Fresh translation"

    cache.close()
