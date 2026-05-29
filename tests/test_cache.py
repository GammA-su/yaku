"""Tests for YakuCache (SQLite translation + frame-edit cache)."""
from __future__ import annotations

import pytest

from yaku.core.cache import YakuCache


@pytest.fixture
def cache(tmp_path):
    c = YakuCache(tmp_path / "test.sqlite3")
    yield c
    c.close()


# ---------------------------------------------------------------------------
# Translation cache
# ---------------------------------------------------------------------------

class TestTranslationCache:
    def test_miss_returns_none(self, cache):
        assert cache.get_translation("こんにちは", "en", "deepl") is None

    def test_put_then_get(self, cache):
        cache.put_translation("こんにちは", "en", "deepl", "Hello")
        assert cache.get_translation("こんにちは", "en", "deepl") == "Hello"

    def test_hit_count_starts_at_zero(self, cache):
        cache.put_translation("text", "en", "deepl", "result")
        row = cache._conn.execute(
            "SELECT hit_count FROM translations WHERE source_text = 'text'"
        ).fetchone()
        assert row[0] == 0

    def test_hit_count_increments_on_each_get(self, cache):
        cache.put_translation("text", "en", "llama_cpp", "result")
        cache.get_translation("text", "en", "llama_cpp")
        cache.get_translation("text", "en", "llama_cpp")
        row = cache._conn.execute(
            "SELECT hit_count FROM translations WHERE source_text = 'text'"
        ).fetchone()
        assert row[0] == 2

    def test_put_is_idempotent_first_write_wins(self, cache):
        cache.put_translation("text", "en", "deepl", "first")
        cache.put_translation("text", "en", "deepl", "second")  # must be ignored
        assert cache.get_translation("text", "en", "deepl") == "first"

    def test_miss_does_not_increment_anything(self, cache):
        # Just ensure no exception is raised on a miss
        result = cache.get_translation("nonexistent", "en", "deepl")
        assert result is None

    # backend_model variants ------------------------------------------------

    def test_backend_model_none_stored_and_retrieved(self, cache):
        cache.put_translation("src", "en", "llama_cpp", "translated", backend_model=None)
        assert cache.get_translation("src", "en", "llama_cpp", None) == "translated"

    def test_backend_model_string_stored_and_retrieved(self, cache):
        cache.put_translation("src", "en", "llama_cpp", "translated", backend_model="qwen2.5")
        assert cache.get_translation("src", "en", "llama_cpp", "qwen2.5") == "translated"

    def test_backend_model_none_and_string_are_separate_keys(self, cache):
        cache.put_translation("src", "en", "llama_cpp", "no-model",   backend_model=None)
        cache.put_translation("src", "en", "llama_cpp", "with-model", backend_model="qwen")
        assert cache.get_translation("src", "en", "llama_cpp", None)   == "no-model"
        assert cache.get_translation("src", "en", "llama_cpp", "qwen") == "with-model"

    def test_two_none_model_entries_conflict(self, cache):
        """Two puts with model=None for the same key should result in one row."""
        cache.put_translation("s", "en", "b", "v1", backend_model=None)
        cache.put_translation("s", "en", "b", "v2", backend_model=None)
        count = cache._conn.execute("SELECT COUNT(*) FROM translations").fetchone()[0]
        assert count == 1

    def test_different_target_lang_are_separate(self, cache):
        cache.put_translation("text", "en", "deepl", "English")
        cache.put_translation("text", "de", "deepl", "Deutsch")
        assert cache.get_translation("text", "en", "deepl") == "English"
        assert cache.get_translation("text", "de", "deepl") == "Deutsch"

    def test_different_backends_are_separate(self, cache):
        cache.put_translation("text", "en", "deepl",    "from deepl")
        cache.put_translation("text", "en", "llama_cpp", "from llama")
        assert cache.get_translation("text", "en", "deepl")    == "from deepl"
        assert cache.get_translation("text", "en", "llama_cpp") == "from llama"


# ---------------------------------------------------------------------------
# Frame-edit cache
# ---------------------------------------------------------------------------

class TestFrameEditCache:
    def test_miss_returns_none(self, cache):
        assert cache.get_frame_edit("abc123", "src", "dst", "mask-text") is None

    def test_put_then_get(self, cache):
        cache.put_frame_edit("hash1", "source", "translated", "mask-text")
        result = cache.get_frame_edit("hash1", "source", "translated", "mask-text")
        assert result is not None
        assert result["frame_hash"] == "hash1"
        assert result["render_mode"] == "mask-text"
        assert result["source_text"] == "source"
        assert result["translated_text"] == "translated"

    def test_metadata_roundtrip(self, cache):
        meta = {"font": "Arial", "size": 24, "color": [255, 255, 255]}
        cache.put_frame_edit(
            "hash2", "src", "dst", "inpaint-text",
            image_path="out/frame_001.png",
            metadata=meta,
        )
        result = cache.get_frame_edit("hash2", "src", "dst", "inpaint-text")
        assert result["metadata"] == meta
        assert result["image_path"] == "out/frame_001.png"

    def test_metadata_none_returns_none(self, cache):
        cache.put_frame_edit("hash3", "src", "dst", "mask-text")
        result = cache.get_frame_edit("hash3", "src", "dst", "mask-text")
        assert result["metadata"] is None

    def test_image_path_none(self, cache):
        cache.put_frame_edit("hash4", "src", "dst", "mask-text")
        result = cache.get_frame_edit("hash4", "src", "dst", "mask-text")
        assert result["image_path"] is None

    def test_put_is_idempotent_first_write_wins(self, cache):
        cache.put_frame_edit("h", "s", "t", "mask-text", image_path="first.png")
        cache.put_frame_edit("h", "s", "t", "mask-text", image_path="second.png")
        result = cache.get_frame_edit("h", "s", "t", "mask-text")
        assert result["image_path"] == "first.png"

    def test_different_render_modes_are_separate(self, cache):
        cache.put_frame_edit("h", "s", "t", "mask-text",    image_path="mask.png")
        cache.put_frame_edit("h", "s", "t", "inpaint-text", image_path="inpaint.png")
        assert cache.get_frame_edit("h", "s", "t", "mask-text")["image_path"] == "mask.png"
        assert cache.get_frame_edit("h", "s", "t", "inpaint-text")["image_path"] == "inpaint.png"

    def test_metadata_nested_types(self, cache):
        meta = {"nested": {"a": 1}, "list": [1, 2, 3], "flag": True}
        cache.put_frame_edit("hx", "s", "t", "ai-text-edit", metadata=meta)
        assert cache.get_frame_edit("hx", "s", "t", "ai-text-edit")["metadata"] == meta
