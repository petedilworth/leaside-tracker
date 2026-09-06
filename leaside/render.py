"""Render the SQLite contents to a static page in site/."""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import db, geo, sources

OUT = Path("site")


def collect(conn, areas, limit=400) -> dict:
    rows = conn.execute(
        "SELECT * FROM items WHERE category != 'registry'"
        " ORDER BY COALESCE(published_at, first_seen_at) DESC LIMIT ?",
        (limit,),
    ).fetchall()
    items = [dict(r) for r in rows]
    for it in items:
        it["area_name"] = areas.name(it["area"])
    counts = dict(
        conn.execute(
            "SELECT category, COUNT(*) FROM items WHERE category != 'registry'"
            " GROUP BY category"
        ).fetchall()
    )
    fetches = [
        dict(r)
        for r in conn.execute(
            "SELECT source_id, MAX(ran_at) ran_at, ok, item_count, error"
            " FROM fetch_log GROUP BY source_id ORDER BY source_id"
        ).fetchall()
    ]
    area_counts = dict(
        conn.execute(
            "SELECT COALESCE(area, 'none'), COUNT(*) FROM items"
            " WHERE category != 'registry' GROUP BY COALESCE(area, 'none')"
        ).fetchall()
    )
    area_names = {k: areas.name(None if k == "none" else k) for k in area_counts}
    return {
        "items": items,
        "counts": counts,
        "area_counts": area_counts,
        "area_names": area_names,
        "fetches": fetches,
    }


def run(db_path=db.DEFAULT_DB, config_path="config/sources.yaml") -> Path:
    conn = db.connect(db_path)
    areas = geo.Areas.load()
    cfg = sources.load(config_path)
    env = Environment(
        loader=FileSystemLoader("templates"), autoescape=select_autoescape(["html"])
    )
    data = collect(conn, areas)
    data["sources"] = cfg.sources
    data["areas"] = areas.features
    data["generated_at"] = db.utcnow()
    OUT.mkdir(exist_ok=True)
    target = OUT / "index.html"
    target.write_text(env.get_template("index.html").render(**data), encoding="utf-8")
    return target
