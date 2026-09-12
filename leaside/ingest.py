"""Pull every runnable source into SQLite."""
from __future__ import annotations

from pathlib import Path

from . import dates, db, geo, http, sources
from .fetchers import REGISTRY, arcgis


def run(config_path="config/sources.yaml", db_path=db.DEFAULT_DB, only=None) -> dict:
    cfg = sources.load(config_path)
    areas = geo.Areas.load()
    fetcher = http.Fetcher(cfg.user_agent, cfg.timeout, cfg.delay)
    conn = db.connect(db_path)
    layers = {}
    totals = {"new": 0, "seen": 0, "failed": 0}
    run_id = db.start_run(conn)

    for src in cfg.sources:
        if not src.runnable or (only and src.id not in only):
            continue
        started = db.utcnow()
        try:
            if src.kind == "arcgis_feature":
                url = src.url or _discover(src, cfg, fetcher, layers)
                items, status = arcgis.fetch_features(src, fetcher, areas, layer_url=url)
            else:
                items, status = REGISTRY[src.kind](src, fetcher, areas)
            for it in items:
                if it.get("area"):
                    continue          # set from real coordinates; do not second-guess it
                it["area"] = (
                    areas.match_text(it.get("title"), it.get("summary")) or src.area
                )

            if src.max_age_days:
                before = len(items)
                items = [
                    it for it in items
                    if dates.within_days(it.get("published_at"), src.max_age_days)
                ]
                dropped = before - len(items)
                if dropped:
                    print(f"        dropped {dropped} items older than "
                          f"{src.max_age_days} days")
            undated = sum(
                1 for it in items
                if it.get("published_at") and dates.to_iso(it["published_at"]) is None
            )
            new = sum(db.upsert_item(conn, it) for it in items)
            removed = db.drop_unseen(conn, src.id, started) if src.snapshot else 0
            db.log_fetch(conn, src.id, True, status, len(items))
            totals["new"] += new
            totals["seen"] += len(items)
            tail = f", {removed} stale removed" if removed else ""
            print(f"  ok    {src.id:<32} {len(items):>5} items, {new:>4} new{tail}")
            if undated:
                sample = next(it["published_at"] for it in items
                              if dates.to_iso(it.get("published_at")) is None)
                print(f"        {undated} dates could not be read, e.g. {sample!r}")
        except Exception as exc:
            db.log_fetch(conn, src.id, False, None, 0, f"{type(exc).__name__}: {exc}"[:500])
            totals["failed"] += 1
            print(f"  FAIL  {src.id:<32} {type(exc).__name__}: {exc}")
        conn.commit()

    fixed = db.refresh_all(conn, areas, cfg)
    if fixed["demo_removed"]:
        print(f"\n  removed {fixed['demo_removed']} leftover demo items")
    if fixed["orphans_removed"]:
        print(f"  removed {fixed['orphans_removed']} rows left behind by retired sources")
    print(f"  refreshed {fixed['rows']} stored items, {fixed['changed']} corrected")
    db.finish_run(conn, run_id, totals)
    return totals


def _discover(src, cfg, fetcher, cache) -> str:
    parent = cfg.by_id(src.discover_from)
    if parent is None:
        raise RuntimeError(f"{src.id}: discover_from '{src.discover_from}' is not a source")
    if parent.id not in cache:
        resp = fetcher.get(parent.url)
        resp.raise_for_status()
        cache[parent.id] = arcgis.catalogue_entries(resp.text)
    url = arcgis.find_layer(cache[parent.id], src.discover_match)
    if not url:
        listing = Path(f"config/{parent.id}-catalogue.md")
        titles = arcgis.queryable_titles(cache[parent.id])
        listing.write_text(
            f"# Datasets published by {parent.name}\n\n"
            f"{len(titles)} of them can be queried directly. Send this file to Claude "
            f"when a layer cannot be found.\n\n"
            + "\n".join(f"- {t}" for t in titles)
            + "\n",
            encoding="utf-8",
        )
        raise RuntimeError(
            f"no layer matching {src.discover_match!r}. "
            f"The {len(titles)} available names are listed in {listing}"
        )
    return url
