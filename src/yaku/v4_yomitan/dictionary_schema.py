from __future__ import annotations

import sqlite3

CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS dictionaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT UNIQUE,
    revision TEXT,
    format INTEGER,
    source_path TEXT,
    source_sha256 TEXT,
    imported_at TEXT
);

CREATE TABLE IF NOT EXISTS terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dictionary_id INTEGER,
    expression TEXT,
    reading TEXT,
    definition_tags TEXT,
    rules TEXT,
    score INTEGER,
    glossary_json TEXT,
    sequence INTEGER,
    term_tags TEXT,
    raw_json TEXT,
    FOREIGN KEY(dictionary_id) REFERENCES dictionaries(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS term_search (
    expression TEXT,
    reading TEXT,
    term_id INTEGER,
    FOREIGN KEY(term_id) REFERENCES terms(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS term_meta (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dictionary_id INTEGER,
    expression TEXT,
    mode TEXT,
    data_json TEXT,
    raw_json TEXT,
    FOREIGN KEY(dictionary_id) REFERENCES dictionaries(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dictionary_id INTEGER,
    name TEXT,
    category TEXT,
    order_num INTEGER,
    notes TEXT,
    score INTEGER,
    raw_json TEXT,
    FOREIGN KEY(dictionary_id) REFERENCES dictionaries(id) ON DELETE CASCADE
);
"""

CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_terms_expression ON terms(expression);
CREATE INDEX IF NOT EXISTS idx_terms_reading ON terms(reading);
CREATE INDEX IF NOT EXISTS idx_term_search_expression ON term_search(expression);
CREATE INDEX IF NOT EXISTS idx_term_search_reading ON term_search(reading);
CREATE INDEX IF NOT EXISTS idx_term_meta_expression ON term_meta(expression);
"""


def init_db(conn: sqlite3.Connection) -> None:
    """Initialize SQLite tables and indexes."""
    conn.execute("PRAGMA foreign_keys = ON;")
    with conn:
        conn.executescript(CREATE_TABLES)
        conn.executescript(CREATE_INDEXES)
