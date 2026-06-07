from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from yaku.v4_yomitan.dictionary_schema import init_db


class DictionaryIndex:
    """Manages SQLite connection lifecycle for Yomitan dictionaries."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        
        init_db(self._conn)
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def get_connection(self) -> sqlite3.Connection:
        return self.connect()
