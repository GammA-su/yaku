from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from yaku.v4_yomitan.deinflect import deinflect


@dataclass
class DictionaryEntry:
    id: int
    expression: str
    reading: str
    definition_tags: list[str]
    rules: list[str]
    score: int
    glossary: list[str]
    sequence: int
    term_tags: list[str]
    dictionary_title: str
    reasons: list[str] = field(default_factory=list)
    pitches: list[str] = field(default_factory=list)
    frequencies: list[str] = field(default_factory=list)


COMMON_POS_WORDS = {
    "noun", "pronoun", "adjective", "adverb", "verb", "conjunction", 
    "particle", "interjection", "prefix", "suffix", "expression", 
    "intransitive verb", "transitive verb", "suru verb", "godan verb", 
    "ichidan verb", "adjectival noun", "pre-noun adjectival", "counter", 
    "copula", "auxiliary", "auxiliary verb", "auxiliary adjective", 
    "temporal noun", "adverbial noun", "proper noun"
}


def flatten_glossary(item: Any) -> list[str]:
    """Recursively flattens Yomitan structured glossary content into plain strings."""
    if isinstance(item, str):
        return [item]
    elif isinstance(item, list):
        res = []
        for sub in item:
            res.extend(flatten_glossary(sub))
        return res
    elif isinstance(item, dict):
        t = item.get("type")
        if t == "text":
            return flatten_glossary(item.get("text", ""))
        elif t == "list":
            return flatten_glossary(item.get("items", []))
        else:
            content = item.get("content", "")
            if content:
                return flatten_glossary(content)
            text_val = item.get("text", "")
            if text_val:
                return flatten_glossary(text_val)
    return []


def extract_glossary_and_tags(item: Any) -> tuple[list[str], list[str]]:
    """Recursively extracts glossaries and part-of-speech tags from Yomitan content."""
    glossary = []
    pos_tags = []

    def recurse(node: Any):
        if isinstance(node, str):
            glossary.append(node)
            return
        if isinstance(node, list):
            for sub in node:
                recurse(sub)
            return
        if isinstance(node, dict):
            # Check for specific Yomitan data attributes
            data = node.get("data")
            if isinstance(data, dict):
                content_type = data.get("content")
                if content_type == "part-of-speech-info":
                    content_val = node.get("content", "")
                    if isinstance(content_val, str) and content_val:
                        pos_tags.append(content_val)
                    elif isinstance(content_val, list):
                        for c in content_val:
                            if isinstance(c, str):
                                pos_tags.append(c)
                    return
                elif content_type in {"extra-info", "attribution", "example-sentence", "example-sentence-a", "example-sentence-b"}:
                    return

            t = node.get("type")
            if t == "text":
                recurse(node.get("text", ""))
            elif t == "list":
                recurse(node.get("items", []))
            else:
                content = node.get("content", "")
                if content:
                    recurse(content)
                text_val = node.get("text", "")
                if text_val:
                    recurse(text_val)

    recurse(item)

    # Post-process: filter common POS words from glossary list and move to pos_tags
    cleaned_glossary = []
    for g in glossary:
        g_stripped = g.strip()
        if not g_stripped:
            continue
        if g_stripped.lower() in COMMON_POS_WORDS:
            if g_stripped not in pos_tags:
                pos_tags.append(g_stripped)
        else:
            cleaned_glossary.append(g)

    return cleaned_glossary, pos_tags


class DictionaryLookup:
    """Handles querying the SQLite Yomitan index with deinflection logic."""

    def __init__(self, db_path: Path | str) -> None:
        from yaku.v4_yomitan.dictionary_index import DictionaryIndex
        self.db = DictionaryIndex(db_path)

    def lookup_exact(self, surface: str, limit: int = 20) -> list[DictionaryEntry]:
        """Performs an exact match query on the term expression."""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT t.*, d.title as dictionary_title
            FROM terms t
            JOIN term_search ts ON t.id = ts.term_id
            JOIN dictionaries d ON t.dictionary_id = d.id
            WHERE ts.expression = ?
            LIMIT ?
        """
        cursor.execute(query, (surface, limit))
        rows = cursor.fetchall()
        
        entries = []
        for row in rows:
            try:
                raw_glossary = json.loads(row["glossary_json"])
                glossary, pos_tags = extract_glossary_and_tags(raw_glossary)
            except Exception:
                glossary = [row["glossary_json"]]
                pos_tags = []
                if glossary and glossary[0].strip().lower() in COMMON_POS_WORDS:
                    pos_tags.append(glossary[0].strip())
                    glossary = []

            def_tags = row["definition_tags"].split() if row["definition_tags"] else []
            for tag in pos_tags:
                if tag not in def_tags:
                    def_tags.append(tag)

            term_tags = row["term_tags"].split() if row["term_tags"] else []
            row_rules = row["rules"].split() if row["rules"] else []

            entry = DictionaryEntry(
                id=row["id"],
                expression=row["expression"],
                reading=row["reading"],
                definition_tags=def_tags,
                rules=row_rules,
                score=row["score"],
                glossary=glossary,
                sequence=row["sequence"],
                term_tags=term_tags,
                dictionary_title=row["dictionary_title"],
                reasons=[]
            )
            entries.append(entry)

        self._populate_meta(entries, cursor)
        entries.sort(key=lambda x: -x.score)
        return entries

    def lookup_with_deinflection(self, surface: str, limit: int = 20) -> list[DictionaryEntry]:
        """Deinflects the surface form and queries the database for valid matching rules."""
        candidates = deinflect(surface)
        candidate_map = {}
        for c in candidates:
            candidate_map.setdefault(c.term, []).append(c)

        terms_to_query = list(candidate_map.keys())
        if not terms_to_query:
            return []

        conn = self.db.get_connection()
        cursor = conn.cursor()

        # Batch query matching expressions
        placeholders = ",".join("?" for _ in terms_to_query)
        query = f"""
            SELECT t.*, d.title as dictionary_title
            FROM terms t
            JOIN term_search ts ON t.id = ts.term_id
            JOIN dictionaries d ON t.dictionary_id = d.id
            WHERE ts.expression IN ({placeholders})
        """
        cursor.execute(query, terms_to_query)
        rows = cursor.fetchall()

        entries = []
        for row in rows:
            expression = row["expression"]
            row_rules = row["rules"].split() if row["rules"] else []
            row_rules_set = set(row_rules)

            matching_candidates = candidate_map.get(expression, [])
            for cand in matching_candidates:
                # Intersect candidate rules with term's allowed deinflection rules
                cand_rules_set = set(cand.rules)
                if not row_rules_set or not cand_rules_set or row_rules_set.intersection(cand_rules_set):
                    try:
                        raw_glossary = json.loads(row["glossary_json"])
                        glossary, pos_tags = extract_glossary_and_tags(raw_glossary)
                    except Exception:
                        glossary = [row["glossary_json"]]
                        pos_tags = []
                        if glossary and glossary[0].strip().lower() in COMMON_POS_WORDS:
                            pos_tags.append(glossary[0].strip())
                            glossary = []

                    def_tags = row["definition_tags"].split() if row["definition_tags"] else []
                    for tag in pos_tags:
                        if tag not in def_tags:
                            def_tags.append(tag)

                    term_tags = row["term_tags"].split() if row["term_tags"] else []

                    entry = DictionaryEntry(
                        id=row["id"],
                        expression=row["expression"],
                        reading=row["reading"],
                        definition_tags=def_tags,
                        rules=row_rules,
                        score=row["score"],
                        glossary=glossary,
                        sequence=row["sequence"],
                        term_tags=term_tags,
                        dictionary_title=row["dictionary_title"],
                        reasons=cand.reasons
                    )
                    entries.append(entry)

        self._populate_meta(entries, cursor)
        # Sort by: 1. shortest deinflection path (exact first), 2. highest score
        entries.sort(key=lambda x: (len(x.reasons or []), -x.score))
        return entries[:limit]

    def _populate_meta(self, entries: list[DictionaryEntry], cursor: sqlite3.Cursor) -> None:
        """Helper to fetch and attach term pitch and frequency metadata."""
        matched_expressions = list({e.expression for e in entries})
        if not matched_expressions:
            return

        placeholders = ",".join("?" for _ in matched_expressions)
        meta_query = f"""
            SELECT expression, mode, data_json
            FROM term_meta
            WHERE expression IN ({placeholders})
        """
        cursor.execute(meta_query, matched_expressions)
        meta_rows = cursor.fetchall()

        meta_map = {}
        for m_row in meta_rows:
            expr = m_row["expression"]
            mode = m_row["mode"]
            try:
                data = json.loads(m_row["data_json"])
            except Exception:
                data = m_row["data_json"]
            meta_map.setdefault(expr, {}).setdefault(mode, []).append(data)

        for entry in entries:
            expr = entry.expression
            entry_meta = meta_map.get(expr, {})

            # Pitch accent mapping
            pitches = []
            for p_data in entry_meta.get("pitch", []):
                if isinstance(p_data, dict):
                    pos = p_data.get("position")
                    if pos is not None:
                        pitches.append(f"Pitch {pos}")
                elif isinstance(p_data, list):
                    for item in p_data:
                        if isinstance(item, dict):
                            pos = item.get("position")
                            if pos is not None:
                                pitches.append(f"Pitch {pos}")
            entry.pitches = pitches

            # Frequency mapping
            frequencies = []
            for f_data in entry_meta.get("freq", []):
                if isinstance(f_data, dict):
                    db_name = f_data.get("dictionary", "")
                    val = f_data.get("frequency") or f_data.get("value")
                    disp = f_data.get("displayValue")
                    if disp:
                        frequencies.append(f"{db_name}: {disp}" if db_name else disp)
                    elif val is not None:
                        frequencies.append(f"{db_name}: {val}" if db_name else str(val))
                elif isinstance(f_data, (int, str)):
                    frequencies.append(str(f_data))
            entry.frequencies = frequencies
