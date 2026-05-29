"""SQLite-backed translation and edited-frame metadata cache."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class YakuCache:
    """Persistent SQLite cache for translations and frame-edit metadata.

    **translations** table stores ``(source_text, target_lang, backend,
    backend_model) → translated_text`` with a hit counter so hot entries can
    be prioritised.

    **frame_edits** table stores ``(frame_hash, source_text, translated_text,
    render_mode) → image_path + arbitrary JSON metadata`` for edited frames
    that are expensive to regenerate.

    Both tables use ``INSERT OR IGNORE`` semantics — the first write wins and
    subsequent identical keys are silently dropped.

    ``backend_model=None`` is stored as SQL ``NULL``.  A functional unique
    index on ``COALESCE(backend_model, '')`` ensures that two rows with the
    same ``(source, lang, backend)`` and ``NULL`` model still conflict, which
    the standard ``UNIQUE`` clause on a nullable column would not guarantee.
    """

    def __init__(self, sqlite_path: Path) -> None:
        self._path = Path(sqlite_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self.init_db()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def init_db(self) -> None:
        """Create tables and indexes if they do not already exist."""
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS translations (
                    id              INTEGER PRIMARY KEY,
                    source_text     TEXT    NOT NULL,
                    target_lang     TEXT    NOT NULL,
                    backend         TEXT    NOT NULL,
                    backend_model   TEXT,
                    translated_text TEXT    NOT NULL,
                    created_at      TEXT    NOT NULL,
                    hit_count       INTEGER NOT NULL DEFAULT 0
                );

                -- Functional index treats NULL model as '' so NULL,NULL conflicts.
                CREATE UNIQUE INDEX IF NOT EXISTS idx_translations_key
                ON translations(
                    source_text,
                    target_lang,
                    backend,
                    COALESCE(backend_model, '')
                );

                CREATE TABLE IF NOT EXISTS frame_edits (
                    id              INTEGER PRIMARY KEY,
                    frame_hash      TEXT NOT NULL,
                    source_text     TEXT NOT NULL,
                    translated_text TEXT NOT NULL,
                    render_mode     TEXT NOT NULL,
                    image_path      TEXT,
                    metadata_json   TEXT,
                    created_at      TEXT NOT NULL,
                    UNIQUE(frame_hash, source_text, translated_text, render_mode)
                );
                """
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # Translation cache
    # ------------------------------------------------------------------

    def get_translation(
        self,
        source_text: str,
        target_lang: str,
        backend: str,
        backend_model: Optional[str] = None,
    ) -> Optional[str]:
        """Return cached translated text, or ``None`` on miss.

        Increments ``hit_count`` on every cache hit.
        """
        with self._lock:
            row = self._conn.execute(
                """SELECT id, translated_text FROM translations
                   WHERE source_text  = ?
                     AND target_lang  = ?
                     AND backend      = ?
                     AND backend_model IS ?""",
                (source_text, target_lang, backend, backend_model),
            ).fetchone()
            if row is None:
                return None
            self._conn.execute(
                "UPDATE translations SET hit_count = hit_count + 1 WHERE id = ?",
                (row["id"],),
            )
            self._conn.commit()
            return row["translated_text"]

    def put_translation(
        self,
        source_text: str,
        target_lang: str,
        backend: str,
        translated_text: str,
        backend_model: Optional[str] = None,
    ) -> None:
        """Insert a translation entry.  Silently no-ops if the key already exists."""
        with self._lock:
            self._conn.execute(
                """INSERT OR IGNORE INTO translations
                   (source_text, target_lang, backend, backend_model,
                    translated_text, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (source_text, target_lang, backend, backend_model,
                 translated_text, _now_iso()),
            )
            self._conn.commit()

    def overwrite_translation(
        self,
        source_text: str,
        target_lang: str,
        backend: str,
        translated_text: str,
        backend_model: Optional[str] = None,
    ) -> None:
        """Insert or replace a translation entry for manual edits/retranslation."""
        with self._lock:
            self._conn.execute(
                """DELETE FROM translations
                   WHERE source_text  = ?
                     AND target_lang  = ?
                     AND backend      = ?
                     AND backend_model IS ?""",
                (source_text, target_lang, backend, backend_model),
            )
            self._conn.execute(
                """INSERT INTO translations
                   (source_text, target_lang, backend, backend_model,
                    translated_text, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (source_text, target_lang, backend, backend_model,
                 translated_text, _now_iso()),
            )
            self._conn.commit()

    def delete_translation(
        self,
        source_text: str,
        target_lang: str,
        backend: str,
        backend_model: Optional[str] = None,
    ) -> None:
        """Delete a cached translation so the backend is called on the next request."""
        with self._lock:
            self._conn.execute(
                """DELETE FROM translations
                   WHERE source_text  = ?
                     AND target_lang  = ?
                     AND backend      = ?
                     AND backend_model IS ?""",
                (source_text, target_lang, backend, backend_model),
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # Frame-edit cache
    # ------------------------------------------------------------------

    def get_frame_edit(
        self,
        frame_hash: str,
        source_text: str,
        translated_text: str,
        render_mode: str,
    ) -> Optional[dict[str, Any]]:
        """Return a frame-edit record as a dict, or ``None`` on miss.

        The returned dict includes all DB columns plus a ``metadata`` key
        containing the deserialized JSON (or ``None`` if no metadata was
        stored).
        """
        with self._lock:
            row = self._conn.execute(
                """SELECT * FROM frame_edits
                   WHERE frame_hash      = ?
                     AND source_text     = ?
                     AND translated_text = ?
                     AND render_mode     = ?""",
                (frame_hash, source_text, translated_text, render_mode),
            ).fetchone()
            if row is None:
                return None
            result: dict[str, Any] = dict(row)
            raw: Optional[str] = result.get("metadata_json")
            result["metadata"] = json.loads(raw) if raw else None
            return result

    def put_frame_edit(
        self,
        frame_hash: str,
        source_text: str,
        translated_text: str,
        render_mode: str,
        image_path: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Insert a frame-edit record.  Silently no-ops if the key already exists."""
        meta_json = json.dumps(metadata) if metadata is not None else None
        with self._lock:
            self._conn.execute(
                """INSERT OR IGNORE INTO frame_edits
                   (frame_hash, source_text, translated_text, render_mode,
                    image_path, metadata_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (frame_hash, source_text, translated_text, render_mode,
                 image_path, meta_json, _now_iso()),
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        with self._lock:
            self._conn.close()
