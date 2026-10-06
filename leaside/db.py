"""SQLite storage. One file, no server. Nothing collected is ever deleted from it."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import dates, text

DEFAULT_DB = Path("data/leaside.db")
DEMO_DB = Path("data/demo.db")

# Enough for a few paragraphs. The page shows a trimmed version and
# lets you expand, so this is the ceiling, not what you read at a glance.
SUMMARY_CHARS = 2400

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

CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    new_items   INTEGER,
    seen_items  INTEGER,
    failed      INTEGER
);

CREATE TABLE IF NOT EXISTS digests (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    sent_at  TEXT NOT NULL,
    items    INTEGER,
    ok       INTEGER NOT NULL,
    detail   TEXT
);

-- The change log. Nothing in `items` is ever deleted; this records what happened
-- to each row over time. A 'changed' row holds the version that was REPLACED, so
-- the current version is always in `items` and every earlier one is here.
CREATE TABLE IF NOT EXISTS item_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id      TEXT NOT NULL,
    source_id    TEXT NOT NULL,
    at           TEXT NOT NULL,
    event        TEXT NOT NULL,      -- new, changed, hidden, back
    note         TEXT,               -- which fields changed, or why it was hidden
    title        TEXT,
    summary      TEXT,
    url          TEXT,
    published_at TEXT,
    lat          REAL,
    lon          REAL,
    raw          TEXT
);
CREATE INDEX IF NOT EXISTS item_log_item ON item_log(item_id);
CREATE INDEX IF NOT EXISTS item_log_at   ON item_log(at);
CREATE INDEX IF NOT EXISTS item_log_src  ON item_log(source_id, event);

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
    _migrate(conn)
    return conn


# Columns added after the first databases were created. Added in place, so a
# database from any earlier version keeps every row it already holds.
ADDED_COLUMNS = {
    "content_hash": "TEXT",
    "routine": "INTEGER NOT NULL DEFAULT 0",   # kept in the log, not shown or emailed
    "hidden_at": "TEXT",                       # kept in the log, no longer shown
    "hidden_reason": "TEXT",
}


def _migrate(conn: sqlite3.Connection) -> None:
    have = {r[1] for r in conn.execute("PRAGMA table_info(items)")}
    for name, decl in ADDED_COLUMNS.items():
        if name not in have:
            conn.execute(f"ALTER TABLE items ADD COLUMN {name} {decl}")
    conn.commit()


# What the page and the email consider. Everything else is still in the file.
SHOWN = "hidden_at IS NULL AND routine = 0"


def item_id(source_id: str, key: str) -> str:
    return hashlib.sha1(f"{source_id}|{key}".encode()).hexdigest()


def normalise(item: dict) -> dict:
    """Every write goes through here, so stored rows always share one shape.

    Titles and summaries are plain text. Dates are UTC ISO strings or None, which
    makes the text sort in the renderer a real date sort.
    """
    out = dict(item)
    out["title"] = text.clean(item.get("title"), 300) or "(untitled)"
    out["summary"] = text.clean(item.get("summary"), SUMMARY_CHARS)
    out["published_at"] = dates.to_iso(item.get("published_at"))
    return out


# Keys that change without the record changing: datastore row numbers that shift
# on every reload, map-layer object ids that are reused, edit stamps, and the
# City's full-text search column. Left in, every reload would log a false change.
VOLATILE_EXACT = {"_id", "objectid", "fid", "_full_text", "_rank"}
VOLATILE_PARTS = ("edited", "edit_date", "updated", "last_edit", "load_date")
CONTENT_FIELDS = ("title", "summary", "url", "published_at", "lat", "lon")


def _stable_raw(raw):
    if not isinstance(raw, dict):
        return raw
    return {k: v for k, v in raw.items()
            if k.lower() not in VOLATILE_EXACT
            and not any(part in k.lower() for part in VOLATILE_PARTS)}


def _storable_raw(raw):
    """The record as published, minus the City's search index, which is large
    and is not data."""
    if isinstance(raw, dict) and "_full_text" in raw:
        return {k: v for k, v in raw.items() if k != "_full_text"}
    return raw


def content_hash(item: dict) -> str:
    """A fingerprint of what the source said. Area is left out on purpose: it is
    this project's judgement, not the publisher's, and moving a boundary is not
    a change to the record."""
    body = {f: item.get(f) for f in CONTENT_FIELDS}
    body["raw"] = _stable_raw(item.get("raw"))
    return hashlib.sha1(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


def _log(conn, item_id, source_id, at, event, note=None, row=None, raw=None):
    row = row or {}
    conn.execute(
        """INSERT INTO item_log (item_id, source_id, at, event, note, title, summary, url,
                                 published_at, lat, lon, raw)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (item_id, source_id, at, event, note, row.get("title"), row.get("summary"),
         row.get("url"), row.get("published_at"), row.get("lat"), row.get("lon"), raw),
    )


def upsert_item(conn: sqlite3.Connection, item: dict, seen_at: str | None = None) -> bool:
    """Insert an item, or bring an existing one up to date. Never removes anything.

    An existing row gets its derived fields refreshed - area, date, cleaned text -
    so an improvement to the matching or parsing logic reaches rows we already hold.
    When what the source says has changed, the version being replaced is copied
    into the change log first, so no earlier version is lost. A row that had been
    hidden comes back. Only first_seen_at is fixed for life. Returns True when new.
    """
    now = seen_at or utcnow()
    key = item.get("external_id") or item.get("url") or item["title"]
    iid = item_id(item["source_id"], key)
    item = normalise(item)
    raw = _storable_raw(item.get("raw"))
    raw_text = json.dumps(raw, default=str) if raw else None
    digest = content_hash({**item, "raw": raw})
    routine = 1 if item.get("routine") else 0
    existing = conn.execute("SELECT * FROM items WHERE id = ?", (iid,)).fetchone()
    if existing:
        if existing["content_hash"] and existing["content_hash"] != digest:
            changed = [f for f in CONTENT_FIELDS if existing[f] != item.get(f)]
            if existing["raw"] != raw_text:
                changed.append("record")
            _log(conn, iid, item["source_id"], now, "changed",
                 ", ".join(changed) or "record", dict(existing), existing["raw"])
        if existing["hidden_at"]:
            _log(conn, iid, item["source_id"], now, "back",
                 f"seen again after being hidden: {existing['hidden_reason']}",
                 {"title": item["title"]})
        conn.execute(
            """UPDATE items SET last_seen_at = MAX(last_seen_at, ?), title = ?, summary = ?,
                   published_at = ?, area = ?, lat = ?, lon = ?, url = ?, raw = ?,
                   content_hash = ?, routine = ?, hidden_at = NULL, hidden_reason = NULL
               WHERE id = ?""",
            (
                now, item["title"], item.get("summary"), item.get("published_at"),
                item.get("area"), item.get("lat"), item.get("lon"), item.get("url"),
                raw_text, digest, routine, iid,
            ),
        )
        return False
    conn.execute(
        """INSERT INTO items
           (id, source_id, category, title, url, summary, published_at,
            first_seen_at, last_seen_at, area, lat, lon, raw, content_hash, routine)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
            raw_text,
            digest,
            routine,
        ),
    )
    _log(conn, iid, item["source_id"], now, "new", None,
         {"title": item["title"], "url": item.get("url"),
          "published_at": item.get("published_at")})
    return True


def hide(conn: sqlite3.Connection, iid: str, source_id: str, reason: str) -> None:
    """Take a row off the page and out of the email. It stays in the file and
    in the downloadable log, marked with the reason."""
    now = utcnow()
    conn.execute("UPDATE items SET hidden_at = ?, hidden_reason = ? WHERE id = ?",
                 (now, reason, iid))
    title = conn.execute("SELECT title FROM items WHERE id = ?", (iid,)).fetchone()
    _log(conn, iid, source_id, now, "hidden", reason, {"title": title[0] if title else None})


def rekey(conn: sqlite3.Connection, source_id: str, key_for_raw) -> dict:
    """Move rows to the key the parser now produces, keeping them and their history.

    Run before a fetch's items are stored. A row whose correct key is free is
    renamed in place, with its log entries, so records that have aged out of the
    publisher's window keep their place. A row whose correct key is already taken
    is a duplicate and is hidden as superseded. Nothing is deleted.
    """
    out = {"renamed": 0, "superseded": 0}
    for row in conn.execute(
        "SELECT id, raw FROM items WHERE source_id = ? AND raw IS NOT NULL", (source_id,)
    ).fetchall():
        try:
            key = key_for_raw(json.loads(row["raw"]))
        except (ValueError, TypeError, KeyError):
            continue
        if not key:
            continue
        new_id = item_id(source_id, key)
        if new_id == row["id"]:
            continue
        if conn.execute("SELECT 1 FROM items WHERE id = ?", (new_id,)).fetchone():
            hide(conn, row["id"], source_id, "superseded by a corrected record")
            out["superseded"] += 1
        else:
            conn.execute("UPDATE items SET id = ? WHERE id = ?", (new_id, row["id"]))
            conn.execute("UPDATE item_log SET item_id = ? WHERE item_id = ?", (new_id, row["id"]))
            out["renamed"] += 1
    return out


def collapse_same_key(items: list[dict]) -> tuple[list[dict], int]:
    """One item per key within a single fetch, chosen the same way every run.

    Sources publish several rows under one key - the City lists each person in a
    serious collision separately under one collision number. Stored one after the
    other, the last row won, and which row came last varied, so the record flipped
    between people on every run and logged a false change each time. The row kept
    is the one with the lowest fingerprint: arbitrary, but always the same one.
    """
    groups: dict[str, list[dict]] = {}
    order = []
    for it in items:
        key = it.get("external_id") or it.get("url") or it["title"]
        if key not in groups:
            order.append(key)
        groups.setdefault(key, []).append(it)
    out, merged = [], 0
    for key in order:
        group = groups[key]
        if len(group) > 1:
            merged += len(group) - 1
            group = sorted(group, key=lambda it: content_hash(
                {**normalise(it), "raw": _storable_raw(it.get("raw"))}))
        out.append(group[0])
    return out, merged


def hide_superseded(conn: sqlite3.Connection, source_id: str, key_for_raw) -> int:
    """Hide rows stored under a key the parser no longer produces.

    When a fix changes how records are keyed - DineSafe's renamed columns merged
    every inspection on one date into a single item - the corrected items arrive
    as new rows and the faulty ones would sit beside them forever. Nothing is
    deleted: the faulty rows are hidden, with the reason, and stay in the log.
    """
    n = 0
    for row in conn.execute(
        "SELECT id, raw FROM items WHERE source_id = ? AND hidden_at IS NULL AND raw IS NOT NULL",
        (source_id,),
    ).fetchall():
        try:
            key = key_for_raw(json.loads(row["raw"]))
        except (ValueError, TypeError, KeyError):
            continue
        if key and item_id(source_id, key) != row["id"]:
            hide(conn, row["id"], source_id, "superseded by a corrected record")
            n += 1
    return n


def refresh_all(conn: sqlite3.Connection, areas, cfg) -> dict:
    """Re-derive text, dates and areas for every stored row.

    Runs at the end of each ingest. It is what carries a logic fix to rows that
    have already dropped out of their feed and will never be fetched again.
    """
    counts = {"rows": 0, "changed": 0, "demo_removed": 0, "retired_hidden": 0}
    # Demo rows were never collected from anywhere; they are the one thing removed.
    cur = conn.execute("DELETE FROM items WHERE title LIKE '[demo] %'")
    counts["demo_removed"] = cur.rowcount

    # Rows whose source is no longer configured come off the page, but they are
    # kept: what was collected stays collected. They come back if the source does.
    known = {s.id for s in cfg.sources}
    for row in conn.execute(
        "SELECT id, source_id FROM items WHERE hidden_at IS NULL"
    ).fetchall():
        if row["source_id"] not in known:
            hide(conn, row["id"], row["source_id"], "source no longer configured")
            counts["retired_hidden"] += 1
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


def start_run(conn: sqlite3.Connection) -> int:
    cur = conn.execute("INSERT INTO runs (started_at) VALUES (?)", (utcnow(),))
    conn.commit()
    return cur.lastrowid


def finish_run(conn: sqlite3.Connection, run_id: int, totals: dict) -> None:
    conn.execute(
        "UPDATE runs SET finished_at=?, new_items=?, seen_items=?, failed=? WHERE id=?",
        (utcnow(), totals["new"], totals["seen"], totals["failed"], run_id),
    )
    conn.commit()


def recent_runs(conn: sqlite3.Connection, n: int = 2) -> list[str]:
    """Start times of the latest runs, newest first."""
    return [r[0] for r in conn.execute(
        "SELECT started_at FROM runs ORDER BY started_at DESC LIMIT ?", (n,))]


def last_digest(conn: sqlite3.Connection) -> str | None:
    """When the last digest was sent successfully. Everything newer is unreported."""
    row = conn.execute(
        "SELECT sent_at FROM digests WHERE ok = 1 ORDER BY sent_at DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else None


def record_digest(conn: sqlite3.Connection, items: int, ok: bool, detail: str = "") -> None:
    conn.execute(
        "INSERT INTO digests (sent_at, items, ok, detail) VALUES (?,?,?,?)",
        (utcnow(), items, 1 if ok else 0, detail[:500]),
    )
    conn.commit()


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
