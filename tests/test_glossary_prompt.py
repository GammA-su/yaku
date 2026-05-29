"""Glossary prompt/context behavior."""
from __future__ import annotations

import json

import httpx

from yaku.core.config import DeepLConfig, GlossaryEntry, LlamaCppConfig
from yaku.translate.base import build_user_message
from yaku.translate.deepl_backend import DeepLTranslator
from yaku.translate.llama_cpp_backend import LlamaCppTranslator


class _CapturingTransport(httpx.BaseTransport):
    def __init__(self, response: httpx.Response) -> None:
        self.last_request: httpx.Request | None = None
        self._response = response

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.last_request = request
        return self._response


def test_user_message_includes_glossary_entries():
    msg = build_user_message(
        "先輩、待って！",
        [],
        [GlossaryEntry(source="先輩", target="senpai", note="Keep honorific.")],
    )

    assert "Glossary:" in msg
    assert "先輩 => senpai" in msg
    assert "Keep honorific." in msg


def test_llama_cpp_request_includes_glossary():
    transport = _CapturingTransport(
        httpx.Response(200, json={"choices": [{"message": {"content": "Senpai!"}}]})
    )
    translator = LlamaCppTranslator(LlamaCppConfig(), _transport=transport)

    translator.translate(
        "先輩！",
        [],
        "en",
        glossary=[GlossaryEntry(source="先輩", target="senpai")],
    )

    assert transport.last_request is not None
    body = json.loads(transport.last_request.content)
    user = next(m["content"] for m in body["messages"] if m["role"] == "user")
    assert "Glossary:" in user
    assert "先輩 => senpai" in user


def test_deepl_context_includes_glossary(monkeypatch):
    monkeypatch.setenv("DEEPL_API_KEY", "test-key")
    transport = _CapturingTransport(
        httpx.Response(200, json={"translations": [{"text": "Hey, big brother."}]})
    )
    translator = DeepLTranslator(config=DeepLConfig(), _transport=transport)

    translator.translate(
        "お兄ちゃん",
        ["previous line"],
        "EN-US",
        glossary=[GlossaryEntry(source="お兄ちゃん", target="big brother")],
    )

    assert transport.last_request is not None
    body = json.loads(transport.last_request.content)
    assert "previous line" in body["context"]
    assert "お兄ちゃん => big brother" in body["context"]
