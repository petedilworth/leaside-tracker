"""Render the SQLite contents to a static page in site/.

The page is a reader, not a dump. It carries enough data attributes for the browser
to do the parts that depend on the reader: local time, "since you last looked",
read state. The server only knows dates and when the last two runs happened.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import db, geo, sources

OUT = Path("site")
WINDOW_DAYS = 120


def collect(conn, areas, cfg, window_days: int = WINDOW_DAYS) -> dict:
    since = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat(
        timespec="seconds"
    )
    rows = conn.execute(
        "SELECT * FROM items WHERE category != 'registry'"
        " AND COALESCE(published_at, first_seen_at) >= ?"
        " ORDER BY COALESCE(published_at, first_seen_at) DESC",
        (since,),
    ).fetchall()
    names = {s.id: s.name for s in cfg.sources}
    items = []
    for r in rows:
        it = dict(r)
        it["area_name"] = areas.name(it["area"])
        it["source_name"] = names.get(it["source_id"], it["source_id"])
        it["when"] = it["published_at"] or it["first_seen_at"]
        items.append(it)

    runs = db.recent_runs(conn, 2)
    latest_run = runs[0] if runs else None
    new_this_run = sum(1 for it in items if latest_run and it["first_seen_at"] >= latest_run)

    counts, area_counts = {}, {}
    for it in items:
        counts[it["category"]] = counts.get(it["category"], 0) + 1
        key = it["area"] or "none"
        area_counts[key] = area_counts.get(key, 0) + 1
    area_names = {k: areas.name(None if k == "none" else k) for k in area_counts}

    fetches = [
        dict(r)
        for r in conn.execute(
            "SELECT source_id, MAX(ran_at) ran_at, ok, item_count, error"
            " FROM fetch_log GROUP BY source_id ORDER BY ok, source_id"
        ).fetchall()
    ]
    for f in fetches:
        f["source_name"] = names.get(f["source_id"], f["source_id"])

    return {
        "items": items,
        "counts": counts,
        "area_counts": area_counts,
        "area_names": area_names,
        "fetches": fetches,
        "latest_run": latest_run,
        "previous_run": runs[1] if len(runs) > 1 else None,
        "new_this_run": new_this_run,
        "window_days": window_days,
    }


def run(db_path=db.DEFAULT_DB, config_path="config/sources.yaml",
        out_name="index.html") -> Path:
    conn = db.connect(db_path)
    areas = geo.Areas.load()
    cfg = sources.load(config_path)
    env = Environment(
        loader=FileSystemLoader("templates"), autoescape=select_autoescape(["html"])
    )
    data = collect(conn, areas, cfg)
    data["sources"] = cfg.sources
    data["generated_at"] = db.utcnow()
    OUT.mkdir(exist_ok=True)
    target = OUT / out_name
    target.write_text(env.get_template("index.html").render(**data), encoding="utf-8")
    return target
