"""SQLite persistence (thread-safe, single connection guarded by a lock)."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=OFF;
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS brands (
  id TEXT PRIMARY KEY, name TEXT, slug TEXT, avatar TEXT, raw TEXT,
  first_seen TEXT, last_seen TEXT, status TEXT DEFAULT 'active');
CREATE TABLE IF NOT EXISTS containers (
  id TEXT PRIMARY KEY, brand_id TEXT, kind TEXT, name TEXT, raw TEXT,
  expected_assets INTEGER, scan_complete INTEGER DEFAULT 0,
  first_seen TEXT, last_seen TEXT, status TEXT DEFAULT 'active');
CREATE TABLE IF NOT EXISTS folders (
  id TEXT PRIMARY KEY, brand_id TEXT, container_id TEXT, parent_id TEXT, name TEXT,
  path TEXT, created_at TEXT, modified_at TEXT, raw TEXT,
  first_seen TEXT, last_seen TEXT, status TEXT DEFAULT 'active');
CREATE TABLE IF NOT EXISTS assets (
  id TEXT PRIMARY KEY, brand_id TEXT, container_id TEXT, folder_id TEXT, folder_path TEXT,
  title TEXT, filename TEXT, extension TEXT, mime TEXT, size INTEGER, typename TEXT, category TEXT,
  created_at TEXT, modified_at TEXT, fingerprint TEXT, file_fingerprint TEXT, raw TEXT,
  status TEXT DEFAULT 'active',
  download_status TEXT DEFAULT 'pending', local_path TEXT, sha256 TEXT, downloaded_at TEXT,
  duplicate_of TEXT, error TEXT, attempts INTEGER DEFAULT 0,
  first_seen TEXT, last_seen TEXT);
CREATE INDEX IF NOT EXISTS ix_assets_brand ON assets(brand_id, status);
CREATE INDEX IF NOT EXISTS ix_assets_sha ON assets(sha256);
CREATE TABLE IF NOT EXISTS guideline_pages (
  id TEXT PRIMARY KEY, brand_id TEXT, guideline_id TEXT, parent_id TEXT, title TEXT, url TEXT,
  kind TEXT, path TEXT, position INTEGER, hidden INTEGER DEFAULT 0, modified_at TEXT,
  content_hash TEXT, markdown_path TEXT, raw TEXT, status TEXT DEFAULT 'active',
  export_status TEXT DEFAULT 'pending', error TEXT, first_seen TEXT, last_seen TEXT);
CREATE TABLE IF NOT EXISTS collections (id TEXT PRIMARY KEY, brand_id TEXT, library_id TEXT, name TEXT);
CREATE TABLE IF NOT EXISTS essentials (brand_id TEXT PRIMARY KEY, raw TEXT, fetched_at TEXT);
CREATE TABLE IF NOT EXISTS relationships (
  src_type TEXT, src_id TEXT, rel TEXT, dst_type TEXT, dst_id TEXT, brand_id TEXT,
  PRIMARY KEY (src_type, src_id, rel, dst_type, dst_id));
CREATE TABLE IF NOT EXISTS sync_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, started_at TEXT, finished_at TEXT,
  status TEXT, summary TEXT);
CREATE TABLE IF NOT EXISTS changes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER, entity TEXT, entity_id TEXT,
  change TEXT, name TEXT, brand_id TEXT);
CREATE INDEX IF NOT EXISTS ix_changes_run ON changes(run_id);
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY, kind TEXT, status TEXT, params TEXT, progress TEXT,
  started_at TEXT, finished_at TEXT, error TEXT, result TEXT);
CREATE TABLE IF NOT EXISTS chunks (
  id TEXT PRIMARY KEY, brand_id TEXT, text TEXT, metadata TEXT, vector BLOB, dim INTEGER);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(id UNINDEXED, text, tokenize='unicode61 remove_diacritics 2');
"""


class Database:
    def __init__(self, path: Path | str) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        with self._lock:
            cur = self._conn.execute(sql, tuple(params))
            self._conn.commit()
            return cur.rowcount

    def executemany(self, sql: str, rows: Iterable[Iterable[Any]]) -> None:
        with self._lock:
            self._conn.executemany(sql, [tuple(r) for r in rows])
            self._conn.commit()

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, tuple(params)).fetchall()]

    def one(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def scalar(self, sql: str, params: Iterable[Any] = (), default: Any = 0) -> Any:
        with self._lock:
            row = self._conn.execute(sql, tuple(params)).fetchone()
        return row[0] if row and row[0] is not None else default

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- settings ------------------------------------------------------------
    def get_settings(self) -> dict[str, Any]:
        return {r["key"]: json.loads(r["value"]) for r in self.query("SELECT key, value FROM settings")}

    def put_settings(self, values: dict[str, Any]) -> None:
        self.executemany(
            "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            [(k, json.dumps(v)) for k, v in values.items()],
        )
