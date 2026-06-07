from __future__ import annotations

import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path

import pytest

from yaku.core.config import YakuConfig
from yaku.v4_yomitan.deinflect import deinflect
from yaku.v4_yomitan.dictionary_importer import import_dictionary_zip
from yaku.v4_yomitan.dictionary_index import DictionaryIndex
from yaku.v4_yomitan.dictionary_lookup import DictionaryLookup, flatten_glossary, extract_glossary_and_tags
from yaku.v4_yomitan.tokenize import (
    approximate_token_boxes,
    longest_match_lookup,
    tokenize_japanese,
)


def test_deinflection_rules():
    """Verify that common inflections resolve back to their dictionary base forms."""
    # Ichidan past polite
    candidates = deinflect("食べました")
    terms = [c.term for c in candidates]
    assert "食べる" in terms

    # Ichidan desire past
    candidates = deinflect("食べたかった")
    terms = [c.term for c in candidates]
    assert "食べる" in terms

    # Godan te-form
    candidates = deinflect("泳いで")
    terms = [c.term for c in candidates]
    assert "泳ぐ" in terms

    # Godan past
    candidates = deinflect("泳いだ")
    terms = [c.term for c in candidates]
    assert "泳ぐ" in terms

    # Godan conditional
    candidates = deinflect("書けば")
    terms = [c.term for c in candidates]
    assert "書く" in terms

    # Suru negative
    candidates = deinflect("しない")
    terms = [c.term for c in candidates]
    assert "する" in terms

    # Kuru past polite
    candidates = deinflect("来ました")
    terms = [c.term for c in candidates]
    assert "来る" in terms


def test_flatten_glossary():
    """Test that nested/structured glossary entries flatten cleanly to strings."""
    assert flatten_glossary("hello") == ["hello"]
    assert flatten_glossary(["one", "two"]) == ["one", "two"]
    assert flatten_glossary({"type": "text", "text": "structured"}) == ["structured"]
    assert flatten_glossary({"type": "list", "items": ["item1", "item2"]}) == ["item1", "item2"]
    assert flatten_glossary({"content": "content_text"}) == ["content_text"]
    assert flatten_glossary({"text": "fallback_text"}) == ["fallback_text"]


def test_dictionary_importer_and_lookup():
    """Test full dictionary ZIP import, SQLite indexing, and lookup API."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        db_file = tmp_path / "test_index.sqlite3"
        zip_file = tmp_path / "test_dict.zip"

        # 1. Create a dummy Yomitan ZIP
        manifest = {
            "title": "Test dict",
            "revision": "r1",
            "format": 3
        }
        # [expression, reading, definition_tags, rules, score, glossary, sequence, term_tags]
        terms = [
            ["食べる", "たべる", "v1", "v1", 10, ["to eat", "to consume"], 1, "verb"],
            ["泳ぐ", "およぐ", "v5", "v5", 5, ["to swim"], 2, "verb"],
        ]
        term_meta = [
            ["食べる", "pitch", {"position": 2}],
            ["食べる", "freq", {"dictionary": "novels", "frequency": 120}],
        ]
        tags = [
            ["v1", "part-of-speech", 1, "Ichidan verb", 10]
        ]

        with zipfile.ZipFile(zip_file, "w") as zf:
            zf.writestr("index.json", json.dumps(manifest))
            zf.writestr("term_bank_1.json", json.dumps(terms))
            zf.writestr("term_meta_bank_1.json", json.dumps(term_meta))
            zf.writestr("tag_bank_1.json", json.dumps(tags))

        # 2. Import into temporary database
        res = import_dictionary_zip(zip_file, db_file)
        assert res.ok is True
        assert res.title == "Test dict"
        assert res.terms_imported == 2
        assert res.meta_imported == 2
        assert res.tags_imported == 1

        # 3. Lookup exact matches
        lookup = DictionaryLookup(db_file)
        exact_entries = lookup.lookup_exact("食べる")
        assert len(exact_entries) == 1
        entry = exact_entries[0]
        assert entry.expression == "食べる"
        assert entry.reading == "たべる"
        assert entry.glossary == ["to eat", "to consume"]
        assert entry.rules == ["v1"]
        assert "v1" in entry.definition_tags
        assert "verb" in entry.term_tags
        assert entry.dictionary_title == "Test dict"
        
        # Verify metadata loading
        assert "Pitch 2" in entry.pitches
        assert "novels: 120" in entry.frequencies

        # 4. Lookup with deinflection (tabemashita -> taberu)
        deinf_entries = lookup.lookup_with_deinflection("食べました")
        assert len(deinf_entries) == 1
        assert deinf_entries[0].expression == "食べる"
        assert deinf_entries[0].reasons == ["polite past"]

        # 5. Test cascade delete on dictionary removal
        db_index = DictionaryIndex(db_file)
        conn = db_index.connect()
        cursor = conn.cursor()
        
        # Enable foreign keys
        conn.execute("PRAGMA foreign_keys = ON;")
        cursor.execute("DELETE FROM dictionaries WHERE title = ?;", ("Test dict",))
        conn.commit()

        # Verify associated terms, search terms and meta are fully removed
        cursor.execute("SELECT COUNT(*) FROM terms;")
        assert cursor.fetchone()[0] == 0
        cursor.execute("SELECT COUNT(*) FROM term_search;")
        assert cursor.fetchone()[0] == 0
        cursor.execute("SELECT COUNT(*) FROM term_meta;")
        assert cursor.fetchone()[0] == 0
        cursor.execute("SELECT COUNT(*) FROM tags;")
        assert cursor.fetchone()[0] == 0
        conn.close()
        lookup.db.close()


def test_tokenization_and_longest_match():
    """Verify Japanese script character tokenization and longest prefix database matching."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = Path(tmpdir) / "test_index.sqlite3"
        zip_file = Path(tmpdir) / "test_dict.zip"

        # Create zip dictionary with overlapping terms
        manifest = {"title": "Test Overlap", "revision": "1", "format": 3}
        terms = [
            ["日本", "にほん", "", "", 10, ["Japan"], 1, ""],
            ["日本語", "にほんご", "", "", 20, ["Japanese language"], 2, ""],
        ]
        with zipfile.ZipFile(zip_file, "w") as zf:
            zf.writestr("index.json", json.dumps(manifest))
            zf.writestr("term_bank_1.json", json.dumps(terms))

        import_dictionary_zip(zip_file, db_file)
        lookup = DictionaryLookup(db_file)

        # Test character-level tokenization
        text = "日本語を勉強する"
        tokens = tokenize_japanese(text)
        assert len(tokens) == len(text)
        assert tokens[0].surface == "日"
        assert tokens[0].index == 0

        # Test approximate token boxes (monospaced split check)
        line_box = (100, 200, 80, 20)  # x, y, w, h
        boxes = approximate_token_boxes(text, line_box, tokens)
        assert len(boxes) == len(text)
        assert boxes[0].box == (100, 200, 10, 20)
        assert boxes[1].box == (110, 200, 10, 20)

        # Test longest prefix match lookup
        # Hovering over index 0 ("日本語...")
        matched_str, entries = longest_match_lookup(text, 0, lookup)
        assert matched_str == "日本語"
        assert len(entries) == 1
        assert entries[0].expression == "日本語"

        # Hovering over index 1 ("本語...") -> should match "日本" since "本" is the start and "日本語" starts from index 0
        matched_str2, entries2 = longest_match_lookup(text, 1, lookup)
        assert matched_str2 == ""  # "本語" has no entries starting from "本"
        
        lookup.db.close()


def test_extract_glossary_and_tags():
    """Verify that extract_glossary_and_tags isolates glossaries and POS tags, skipping extra-info/attribution."""
    structured_content = [
        {
            "type": "structured-content",
            "content": [
                {
                    "tag": "div",
                    "data": {"content": "sense-group"},
                    "content": [
                        {
                            "tag": "span",
                            "title": "noun (common) (futsuumeishi)",
                            "data": {"class": "tag", "code": "n", "content": "part-of-speech-info"},
                            "content": "noun"
                        },
                        {
                            "tag": "div",
                            "data": {"content": "sense"},
                            "content": [
                                {
                                    "tag": "ul",
                                    "data": {"content": "glossary"},
                                    "content": {"tag": "li", "content": "school"}
                                },
                                {
                                    "tag": "div",
                                    "data": {"content": "extra-info"},
                                    "content": "Example sentence text"
                                }
                            ]
                        }
                    ]
                },
                {
                    "tag": "div",
                    "data": {"content": "attribution"},
                    "content": "JMdict attribution"
                }
            ]
        }
    ]

    glossary, pos_tags = extract_glossary_and_tags(structured_content)
    assert glossary == ["school"]
    assert pos_tags == ["noun"]

    # Test plain string with POS tag
    glossary2, pos_tags2 = extract_glossary_and_tags(["noun", "school"])
    assert glossary2 == ["school"]
    assert pos_tags2 == ["noun"]

