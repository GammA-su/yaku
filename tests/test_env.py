"""Tests for local .env loading."""
from __future__ import annotations

import os

import httpx

from yaku.core.config import DeepLConfig
from yaku.core.env import load_env_file
from yaku.translate.deepl_backend import DeepLTranslator


class _OkTransport(httpx.BaseTransport):
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"translations": [{"text": "ok"}]})


def test_load_env_file_sets_values(monkeypatch, tmp_path):
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)
    monkeypatch.delenv("YAKU_OTHER", raising=False)
    monkeypatch.delenv("YAKU_EXPORTED", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        """
        # local secrets
        DEEPL_API_KEY="from-file"
        YAKU_OTHER=value # comment
        export YAKU_EXPORTED='yes'
        """,
        encoding="utf-8",
    )

    loaded = load_env_file(env_file)

    assert loaded["DEEPL_API_KEY"] == "from-file"
    assert os.environ["DEEPL_API_KEY"] == "from-file"
    assert os.environ["YAKU_OTHER"] == "value"
    assert os.environ["YAKU_EXPORTED"] == "yes"


def test_load_env_file_does_not_override_existing(monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPL_API_KEY", "from-shell")
    env_file = tmp_path / ".env"
    env_file.write_text("DEEPL_API_KEY=from-file\n", encoding="utf-8")

    load_env_file(env_file)

    assert os.environ["DEEPL_API_KEY"] == "from-shell"


def test_deepl_translator_reads_default_dotenv(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)
    (tmp_path / ".env").write_text("DEEPL_API_KEY=from-file\n", encoding="utf-8")

    translator = DeepLTranslator(DeepLConfig(), _transport=_OkTransport())

    assert translator.backend_name == "deepl"
