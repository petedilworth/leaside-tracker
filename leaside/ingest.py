"""Pull every runnable source into SQLite."""
from __future__ import annotations

from . import dates, db, geo, http, sources
from .fetchers import REGISTRY, arcgis


def run(config_path="config/sources.yaml", db_path=db.DEFAULT_DB, only=None) -> dict:
    cfg = sources.load(config_path)
    areas = geo.Areas.load()
    fetcher = http.Fetcher(cfg.user_agent, cfg.timeout, cfg.delay)
    conn = db.connect(db_path)
    layers = {}
    totals = {"new": 0, "seen": 0, "failed": 0}

    for src in cfg.sources:
        if not src.runnable or (only and src.id not in only):
            continue
        try:
            if src.kind == "arcgis_feature":
                url = src.url or _discover(src, cfg, fetcher, layers)
                items, status = arcgis.fetch_features(src, fetcher, areas, layer_url=url)
            else:
                items, status = REGISTRY[src.kind](src, fetcher, areas)
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
            new = sum(db.upsert_item(conn, it) for it in items)
            db.log_fetch(conn, src.id, True, status, len(items))
            totals["new"] += new
            totals["seen"] += len(items)
            print(f"  ok    {src.id:<32} {len(items):>5} items, {new:>4} new")
        except Exception as exc:
            db.log_fetch(conn, src.id, False, None, 0, f"{type(exc).__name__}: {exc}"[:500])
            totals["failed"] += 1
            print(f"  FAIL  {src.id:<32} {type(exc).__name__}: {exc}")
        conn.commit()
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
        raise RuntimeError(
            f"{src.id}: no layer in {parent.id} matching '{src.discover_match}'"
        )
    return url
