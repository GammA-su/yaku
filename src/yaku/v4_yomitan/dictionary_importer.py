from __future__ import annotations

import hashlib
import json
import sqlite3
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class ImportResult:
    ok: bool
    title: str | None
    terms_imported: int
    meta_imported: int
    tags_imported: int
    error: str | None = None


def import_dictionary_zip(zip_path: Path, index_path: Path, force: bool = False) -> ImportResult:
    zip_path = Path(zip_path)
    if not zip_path.exists():
        return ImportResult(False, None, 0, 0, 0, f"File not found: {zip_path}")

    sha256_hash = hashlib.sha256()
    try:
        with open(zip_path, "rb") as f:
            for byte_block in iter(lambda: f.read(65536), b""):
                sha256_hash.update(byte_block)
    except Exception as exc:
        return ImportResult(False, None, 0, 0, 0, f"Failed to compute hash: {exc}")
    source_sha256 = sha256_hash.hexdigest()

    from yaku.v4_yomitan.dictionary_index import DictionaryIndex
    db = DictionaryIndex(index_path)
    conn = db.connect()

    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            namelist = z.namelist()
            if "index.json" not in namelist:
                return ImportResult(False, None, 0, 0, 0, "Missing index.json in dictionary ZIP")

            with z.open("index.json") as f:
                manifest = json.loads(f.read().decode("utf-8"))

            title = manifest.get("title")
            if not title:
                return ImportResult(False, None, 0, 0, 0, "Missing title in index.json")

            revision = manifest.get("revision", "")
            format_ver = manifest.get("format", 1)

            cursor = conn.cursor()
            cursor.execute("SELECT id, source_sha256 FROM dictionaries WHERE title = ?;", (title,))
            existing = cursor.fetchone()
            if existing:
                if existing["source_sha256"] == source_sha256 and not force:
                    return ImportResult(True, title, 0, 0, 0)
                else:
                    conn.execute("DELETE FROM dictionaries WHERE id = ?;", (existing["id"],))

            imported_at = datetime.now().astimezone().isoformat()
            cursor.execute(
                "INSERT INTO dictionaries (title, revision, format, source_path, source_sha256, imported_at) VALUES (?, ?, ?, ?, ?, ?);",
                (title, revision, format_ver, str(zip_path), source_sha256, imported_at)
            )
            dictionary_id = cursor.lastrowid

            terms_count = 0
            meta_count = 0
            tags_count = 0

            term_banks = sorted([name for name in namelist if name.startswith("term_bank_")])
            term_meta_banks = sorted([name for name in namelist if name.startswith("term_meta_bank_")])
            tag_banks = sorted([name for name in namelist if name.startswith("tag_bank_")])

            for bank_name in term_banks:
                with z.open(bank_name) as f:
                    bank_data = json.loads(f.read().decode("utf-8"))
                
                terms_batch = []
                for item in bank_data:
                    if not isinstance(item, list) or len(item) < 1:
                        continue
                    
                    expression = item[0]
                    reading = item[1] if len(item) > 1 else ""
                    definition_tags = item[2] if len(item) > 2 else ""
                    rules = item[3] if len(item) > 3 else ""
                    score = item[4] if len(item) > 4 else 0
                    glossary = item[5] if len(item) > 5 else []
                    sequence = item[6] if len(item) > 6 else 0
                    term_tags = item[7] if len(item) > 7 else ""
                    
                    glossary_json = json.dumps(glossary, ensure_ascii=False)
                    raw_json = json.dumps(item, ensure_ascii=False)
                    
                    terms_batch.append((
                        dictionary_id, expression, reading, definition_tags,
                        rules, score, glossary_json, sequence, term_tags, raw_json
                    ))

                if terms_batch:
                    cursor.execute("SELECT MAX(id) FROM terms;")
                    max_id_before = cursor.fetchone()[0] or 0

                    cursor.executemany(
                        "INSERT INTO terms (dictionary_id, expression, reading, definition_tags, rules, score, glossary_json, sequence, term_tags, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
                        terms_batch
                    )
                    
                    cursor.execute("SELECT id, expression, reading FROM terms WHERE dictionary_id = ? AND id > ?;", (dictionary_id, max_id_before))
                    inserted_rows = cursor.fetchall()
                    search_batch = []
                    for row in inserted_rows:
                        tid = row["id"]
                        exp = row["expression"]
                        read = row["reading"]
                        search_batch.append((exp, read, tid))
                    
                    cursor.executemany(
                        "INSERT INTO term_search (expression, reading, term_id) VALUES (?, ?, ?);",
                        search_batch
                    )
                    terms_count += len(terms_batch)

            for bank_name in term_meta_banks:
                with z.open(bank_name) as f:
                    bank_data = json.loads(f.read().decode("utf-8"))
                
                meta_batch = []
                for item in bank_data:
                    if not isinstance(item, list) or len(item) < 3:
                        continue
                    expression = item[0]
                    mode = item[1]
                    data = item[2]
                    data_json = json.dumps(data, ensure_ascii=False)
                    raw_json = json.dumps(item, ensure_ascii=False)
                    
                    meta_batch.append((
                        dictionary_id, expression, mode, data_json, raw_json
                    ))
                
                if meta_batch:
                    cursor.executemany(
                        "INSERT INTO term_meta (dictionary_id, expression, mode, data_json, raw_json) VALUES (?, ?, ?, ?, ?);",
                        meta_batch
                    )
                    meta_count += len(meta_batch)

            for bank_name in tag_banks:
                with z.open(bank_name) as f:
                    bank_data = json.loads(f.read().decode("utf-8"))
                
                tags_batch = []
                for item in bank_data:
                    if not isinstance(item, list) or len(item) < 1:
                        continue
                    name = item[0]
                    category = item[1] if len(item) > 1 else ""
                    order_num = item[2] if len(item) > 2 else 0
                    notes = item[3] if len(item) > 3 else ""
                    score = item[4] if len(item) > 4 else 0
                    raw_json = json.dumps(item, ensure_ascii=False)
                    
                    tags_batch.append((
                        dictionary_id, name, category, order_num, notes, score, raw_json
                    ))

                if tags_batch:
                    cursor.executemany(
                        "INSERT INTO tags (dictionary_id, name, category, order_num, notes, score, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?);",
                        tags_batch
                    )
                    tags_count += len(tags_batch)

            conn.commit()
            db.close()
            return ImportResult(True, title, terms_count, meta_count, tags_count)

    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            db.close()
        except Exception:
            pass
        return ImportResult(False, None, 0, 0, 0, f"Import error: {exc}")
