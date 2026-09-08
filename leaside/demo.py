"""Load the test fixtures into a SEPARATE database so the site can be seen offline.

Writes to data/demo.db and never to the real data/leaside.db. An earlier version
wrote into the real database, and the demo items then lived on your page forever.
Fixture items are still tagged [demo] so ingest can purge any that got in that way.
"""
from __future__ import annotations

from pathlib import Path

from . import db, geo, sources
from .fetchers import arcgis, notices, rss_feed

FIX = Path("tests/fixtures")


def run(db_path=db.DEMO_DB) -> int:
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
