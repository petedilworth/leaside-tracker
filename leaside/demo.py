"""Load the test fixtures into the database so the site can be seen without network.

Useful for working on templates offline, and for confirming the pipeline is wired up
before any real endpoint is known to work. Fixture items are tagged so they are obvious.
"""
from __future__ import annotations

from pathlib import Path

from . import db, geo, sources
from .fetchers import arcgis, notices, rss_feed

FIX = Path("tests/fixtures")


def run(db_path=db.DEFAULT_DB) -> int:
    cfg = sources.load()
    areas = geo.Areas.load()
    conn = db.connect(db_path)
    items: list[dict] = []

    items += rss_feed.parse((FIX / "ra_feed.xml").read_text(encoding="utf-8"), cfg.by_id("ra_leaside"))
    items += notices.parse((FIX / "notices.json").read_text(encoding="utf-8"), cfg.by_id("city_public_notices"))
    items += arcgis.parse_features(
        (FIX / "arcgis_features.json").read_text(encoding="utf-8"),
        cfg.by_id("tps_major_crime_indicators"),
        areas,
    )

    new = 0
    for it in items:
        it["title"] = f"[demo] {it['title']}"
        if not it.get("area"):
            it["area"] = areas.match_text(it["title"], it.get("summary"))
        new += db.upsert_item(conn, it)
        db.log_fetch(conn, it["source_id"], True, 200, 1)
    conn.commit()
    return new
