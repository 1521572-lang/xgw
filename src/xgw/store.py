"""Состояние XGW в SQLite: известные узлы, события, мета."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS nodes (
    fingerprint TEXT PRIMARY KEY,
    tag TEXT,
    role TEXT,
    name TEXT,
    source TEXT,
    address TEXT,
    port INTEGER,
    updated INTEGER
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL,
    kind TEXT,
    detail TEXT
);
"""


class Store:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.conn.commit()

    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def upsert_nodes(self, entries: list[dict]) -> None:
        self.conn.executemany(
            "INSERT INTO nodes (fingerprint, tag, role, name, source, address, port, updated) "
            "VALUES (:fingerprint, :tag, :role, :name, :source, :address, :port, :updated) "
            "ON CONFLICT(fingerprint) DO UPDATE SET tag=excluded.tag, role=excluded.role, "
            "name=excluded.name, source=excluded.source, address=excluded.address, "
            "port=excluded.port, updated=excluded.updated",
            entries,
        )
        self.conn.commit()

    def all_nodes(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM nodes ORDER BY role, tag").fetchall()
        return [dict(row) for row in rows]

    def add_event(self, kind: str, detail: str) -> None:
        self.conn.execute(
            "INSERT INTO events (ts, kind, detail) VALUES (?, ?, ?)",
            (time.time(), kind, detail),
        )
        self.conn.commit()

    def recent_events(self, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT ts, kind, detail FROM events ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]

    def dump_state(self) -> str:
        return json.dumps(
            {"meta": {r["key"]: r["value"] for r in self.conn.execute("SELECT * FROM meta")},
             "nodes": self.all_nodes(),
             "events": self.recent_events(10)},
            ensure_ascii=False,
            indent=2,
        )
