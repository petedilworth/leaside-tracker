"""SQLite storage. One file, no server, safe to copy or delete."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import dates, text

DEFAULT_DB = Path("data/leaside.db")
DEMO_DB = Path("data/demo.db")

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


def normalise(item: dict) -> dict:
    """Every write goes through here, so stored rows always share one shape.

    Titles and summaries are plain text. Dates are UTC ISO strings or None, which
    makes the text sort in the renderer a real date sort.
    """
    out = dict(item)
    out["title"] = text.clean(item.get("title"), 300) or "(untitled)"
    out["summary"] = text.clean(item.get("summary"), 1500)
    out["published_at"] = dates.to_iso(item.get("published_at"))
    return out


def upsert_item(conn: sqlite3.Connection, item: dict) -> bool:
    """Insert an item, or bring an existing one up to date.

    An existing row gets its derived fields refreshed - area, date, cleaned text -
    so an improvement to the matching or parsing logic reaches rows we already hold.
    Only first_seen_at is fixed for life. Returns True when the item is new.
    """
    now = utcnow()
    key = item.get("external_id") or item.get("url") or item["title"]
    iid = item_id(item["source_id"], key)
    item = normalise(item)
    existing = conn.execute("SELECT id FROM items WHERE id = ?", (iid,)).fetchone()
    if existing:
        conn.execute(
            """UPDATE items SET last_seen_at = ?, title = ?, summary = ?,
                   published_at = ?, area = ?, lat = ?, lon = ?, url = ?
               WHERE id = ?""",
            (
                now, item["title"], item.get("summary"), item.get("published_at"),
                item.get("area"), item.get("lat"), item.get("lon"), item.get("url"), iid,
            ),
        )
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


def refresh_all(conn: sqlite3.Connection, areas, cfg) -> dict:
    """Re-derive text, dates and areas for every stored row.

    Runs at the end of each ingest. It is what carries a logic fix to rows that
    have already dropped out of their feed and will never be fetched again.
    """
    counts = {"rows": 0, "changed": 0, "demo_removed": 0}
    cur = conn.execute("DELETE FROM items WHERE title LIKE '[demo] %'")
    counts["demo_removed"] = cur.rowcount
    for row in conn.execute(
        "SELECT id, source_id, title, summary, published_at, area, lat, lon FROM items"
    ).fetchall():
        counts["rows"] += 1
        fixed = normalise({"title": row["title"], "summary": row["summary"],
                           "published_at": row["published_at"]})
        if row["lat"] is not None and row["lon"] is not None:
            area = areas.match_point(row["lat"], row["lon"]) or row["area"]
        else:
            src = cfg.by_id(row["source_id"])
            area = (areas.match_text(fixed["title"], fixed["summary"])
                    or (src.area if src else None) or row["area"])
        if (fixed["title"], fixed["summary"], fixed["published_at"], area) != (
            row["title"], row["summary"], row["published_at"], row["area"]
        ):
            conn.execute(
                "UPDATE items SET title=?, summary=?, published_at=?, area=? WHERE id=?",
                (fixed["title"], fixed["summary"], fixed["published_at"], area, row["id"]),
            )
            counts["changed"] += 1
    conn.commit()
    return counts


def drop_unseen(conn: sqlite3.Connection, source_id: str, since: str) -> int:
    """Remove rows from a snapshot source that were not in the latest snapshot.

    Feeds are a stream and old entries are worth keeping. A dataset is a photograph:
    if a row is no longer in it, it should not be on the page either. Without this,
    every run of a dataset whose internal row numbers shift leaves a full duplicate set.
    """
    cur = conn.execute(
        "DELETE FROM items WHERE source_id = ? AND last_seen_at < ?", (source_id, since)
    )
    return cur.rowcount


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
