"""Pull every runnable source into SQLite."""
from __future__ import annotations

from pathlib import Path

from . import dates, db, geo, http, sources
from .fetchers import REGISTRY, arcgis, ckan

# Sources whose items can be re-keyed from their stored record. After a key fix,
# rows stored under the old key are hidden (never deleted) as superseded.
REKEY = {"ckan_dinesafe": ckan.inspection_external_id}
# Rows moved to a corrected key before the fetch is stored, so the ones that have
# aged out of the publisher's window keep their place under the new key.
RENAME = {"arcgis_multi": arcgis.feature_key, "arcgis_feature": arcgis.feature_key}


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
                title, url = _discover(src, cfg, fetcher, layers)
                items, status = arcgis.fetch_features(
                    src, fetcher, areas, layer_url=url,
                    label=arcgis.offence_label(title) if title else None)
            elif src.kind == "arcgis_multi":
                items, status = [], 200
                for title, url in _discover_many(src, cfg, fetcher, layers):
                    got, status = arcgis.fetch_features(
                        src, fetcher, areas, layer_url=url,
                        label=arcgis.offence_label(title))
                    print(f"        {arcgis.offence_label(title):<28} {len(got):>4} in area")
                    items += got
            else:
                items, status = REGISTRY[src.kind](src, fetcher, areas)
            for it in items:
                if it.get("area"):
                    continue          # set from real coordinates; do not second-guess it
                it["area"] = (
                    areas.match_text(it.get("title"), it.get("summary")) or src.area
                )

            if src.max_age_days:
                # Kept, all of them. The window only decides what is new enough to
                # email; it used to throw older items away before they were stored.
                older = sum(1 for it in items
                            if not dates.within_days(it.get("published_at"), src.max_age_days))
                if older:
                    print(f"        {older} older than {src.max_age_days} days: "
                          f"kept in the log, left out of the email")
            undated = sum(
                1 for it in items
                if it.get("published_at") and dates.to_iso(it["published_at"]) is None
            )
            items, merged = db.collapse_same_key(items)
            if merged:
                print(f"        {merged} rows shared a key with another row; one kept per key")
            if src.kind in RENAME and items:
                moved = db.rekey(conn, src.id, RENAME[src.kind])
                if moved["renamed"] or moved["superseded"]:
                    print(f"        re-keyed {moved['renamed']} stored records"
                          + (f", {moved['superseded']} duplicates hidden"
                             if moved["superseded"] else ""))
            before_log = conn.execute("SELECT COUNT(*) FROM item_log WHERE source_id = ?"
                                      " AND event = 'changed'", (src.id,)).fetchone()[0]
            new = sum(db.upsert_item(conn, it) for it in items)
            changed = conn.execute("SELECT COUNT(*) FROM item_log WHERE source_id = ?"
                                   " AND event = 'changed'", (src.id,)).fetchone()[0] - before_log
            superseded = (db.hide_superseded(conn, src.id, REKEY[src.kind])
                          if src.kind in REKEY else 0)
            db.log_fetch(conn, src.id, True, status, len(items))
            totals["new"] += new
            totals["seen"] += len(items)
            tail = (f", {changed} changed" if changed else "") + (
                f", {superseded} superseded rows hidden" if superseded else "")
            print(f"  ok    {src.id:<32} {len(items):>5} items, {new:>4} new{tail}")
            if undated:
                sample = next(it["published_at"] for it in items
                              if it.get("published_at")
                              and dates.to_iso(it["published_at"]) is None)
                print(f"        {undated} dates could not be read, e.g. {sample!r}")
        except Exception as exc:
            db.log_fetch(conn, src.id, False, None, 0, f"{type(exc).__name__}: {exc}"[:500])
            totals["failed"] += 1
            print(f"  FAIL  {src.id:<32} {type(exc).__name__}: {exc}")
        conn.commit()

    fixed = db.refresh_all(conn, areas, cfg)
    if fixed["demo_removed"]:
        print(f"\n  removed {fixed['demo_removed']} leftover demo items")
    if fixed["retired_hidden"]:
        print(f"  hid {fixed['retired_hidden']} rows from sources no longer configured "
              f"(kept in the log)")
    print(f"  refreshed {fixed['rows']} stored items, {fixed['changed']} corrected")
    db.finish_run(conn, run_id, totals)
    return totals


def _catalogue(src, cfg, fetcher, cache):
    parent = cfg.by_id(src.discover_from)
    if parent is None:
        raise RuntimeError(f"{src.id}: discover_from '{src.discover_from}' is not a source")
    if parent.id not in cache:
        resp = fetcher.get(parent.url, timeout=parent.timeout, retries=parent.retries)
        resp.raise_for_status()
        cache[parent.id] = arcgis.catalogue_entries(resp.text)
    return parent, cache[parent.id]


def _write_catalogue(parent, entries) -> Path:
    listing = Path(f"config/{parent.id}-catalogue.md")
    titles = arcgis.queryable_titles(entries)
    listing.write_text(
        f"# Datasets published by {parent.name}\n\n"
        f"{len(titles)} of them can be queried directly. Send this file to Claude "
        f"when a layer cannot be found.\n\n"
        + "\n".join(f"- {t}" for t in titles) + "\n",
        encoding="utf-8",
    )
    return listing


def _discover_many(src, cfg, fetcher, cache) -> list[tuple[str, str]]:
    parent, entries = _catalogue(src, cfg, fetcher, cache)
    found = arcgis.find_layers(entries, src.discover_match)
    if not found:
        listing = _write_catalogue(parent, entries)
        raise RuntimeError(
            f"none of {src.discover_match!r} matched a layer. Available names: {listing}"
        )
    missing = [m for m in src.discover_match
               if not any(m.lower() in t.lower() for t, _ in found)]
    if missing:
        print(f"        note: no layer named {', '.join(missing)}")
    return found


def _discover(src, cfg, fetcher, cache) -> tuple[str | None, str]:
    """Return (dataset title, layer url). The title becomes the item label."""
    if src.url:
        return None, src.url
    parent, entries = _catalogue(src, cfg, fetcher, cache)
    found = arcgis.find_layers(entries, src.discover_match)
    if not found:
        listing = _write_catalogue(parent, entries)
        raise RuntimeError(
            f"no layer matching {src.discover_match!r}. Available names: {listing}"
        )
    return found[0]
