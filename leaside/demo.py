"""Load the test fixtures into a SEPARATE database so the site can be seen offline.

Writes to data/demo.db and never to the real data/leaside.db. An earlier version
wrote into the real database, and the demo items then lived on your page forever.
Fixture items are still tagged [demo] so ingest can purge any that got in that way.
"""
from __future__ import annotations

from pathlib import Path

from datetime import datetime, timedelta, timezone

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
        cfg.by_id("tps_reported_crime"),
        areas,
    )

    from datetime import datetime, timedelta, timezone

    items.append({
        "source_id": "tps_traffic_collisions",
        "category": "collision",
        "title": "Collision",
        "url": None,
        "summary": "Late-arriving police record, to show the Since control working",
        "published_at": (datetime.now(timezone.utc) - timedelta(days=900)).isoformat(
            timespec="seconds"),
        "external_id": "demo-old-collision",
        "area": "leaside",
        "lat": 43.705,
        "lon": -79.365,
    })

    new = 0
    for n, it in enumerate(items):
        it["title"] = f"[demo] {it['title']}"
        # spread across the last few days so the day headings and filters have work to do
        if it["external_id"] != "demo-old-collision":
            it["published_at"] = (
                datetime.now(timezone.utc) - timedelta(days=n, hours=3 * n)
            ).isoformat(timespec="seconds")
        if not it.get("area"):
            it["area"] = areas.match_text(it["title"], it.get("summary"))
        new += db.upsert_item(conn, it)
        db.log_fetch(conn, it["source_id"], True, 200, 1)
    conn.commit()
    return new
