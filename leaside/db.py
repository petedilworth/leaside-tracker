"""SQLite storage. One file, no server, safe to copy or delete."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path("data/leaside.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id            TEXT PRIMARY KEY,
    source_id     TEXT NOT NULL,
    category      TEXT NOT NULL,
    title         TEXT NOT NULL,
    url           TEXT,
    summary       TEXT,
    published_at  TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL,
    area          TEXT,
    lat           REAL,
    lon           REAL,
    raw           TEXT
);
CREATE INDEX IF NOT EXISTS items_published  ON items(published_at DESC);
CREATE INDEX IF NOT EXISTS items_source     ON items(source_id);
CREATE INDEX IF NOT EXISTS items_area       ON items(area);

CREATE TABLE IF NOT EXISTS fetch_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id   TEXT NOT NULL,
    ran_at      TEXT NOT NULL,
    ok          INTEGER NOT NULL,
    http_status INTEGER,
    item_count  INTEGER,
    error       TEXT
);

CREATE TABLE IF NOT EXISTS probe_results (
    source_id    TEXT PRIMARY KEY,
    checked_at   TEXT NOT NULL,
    ok           INTEGER NOT NULL,
    http_status  INTEGER,
    content_type TEXT,
    verdict      TEXT,
    detail       TEXT
);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path | str = DEFAULT_DB) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def item_id(source_id: str, key: str) -> str:
    return hashlib.sha1(f"{source_id}|{key}".encode()).hexdigest()


def upsert_item(conn: sqlite3.Connection, item: dict) -> bool:
    """Insert an item, or refresh last_seen_at if we already have it.

    Returns True when the item is new.
    """
    now = utcnow()
    key = item.get("external_id") or item.get("url") or item["title"]
    iid = item_id(item["source_id"], key)
    existing = conn.execute("SELECT id FROM items WHERE id = ?", (iid,)).fetchone()
    if existing:
        conn.execute("UPDATE items SET last_seen_at = ? WHERE id = ?", (now, iid))
        return False
    conn.execute(
        """INSERT INTO items
           (id, source_id, category, title, url, summary, published_at,
            first_seen_at, last_seen_at, area, lat, lon, raw)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            iid,
            item["source_id"],
            item.get("category", "other"),
            item["title"],
            item.get("url"),
            item.get("summary"),
            item.get("published_at"),
            now,
            now,
            item.get("area"),
            item.get("lat"),
            item.get("lon"),
            json.dumps(item.get("raw"), default=str) if item.get("raw") else None,
        ),
    )
    return True


def log_fetch(conn, source_id, ok, http_status=None, item_count=0, error=None):
    conn.execute(
        "INSERT INTO fetch_log (source_id, ran_at, ok, http_status, item_count, error)"
        " VALUES (?,?,?,?,?,?)",
        (source_id, utcnow(), 1 if ok else 0, http_status, item_count, error),
    )


def record_probe(conn, source_id, ok, http_status, content_type, verdict, detail):
    conn.execute(
        "INSERT INTO probe_results (source_id, checked_at, ok, http_status, content_type,"
        " verdict, detail) VALUES (?,?,?,?,?,?,?)"
        " ON CONFLICT(source_id) DO UPDATE SET checked_at=excluded.checked_at,"
        " ok=excluded.ok, http_status=excluded.http_status,"
        " content_type=excluded.content_type, verdict=excluded.verdict,"
        " detail=excluded.detail",
        (source_id, utcnow(), 1 if ok else 0, http_status, content_type, verdict, detail),
    )
