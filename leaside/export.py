"""The complete log as two spreadsheets, rebuilt with the page.

    site/log/everything.csv   one row per thing ever collected, shown or not
    site/log/changes.csv      one row per event: first seen, changed, hidden, back
    site/log/sources.csv      every source: publisher, page, licence and its wording

The database holds the same and more (each source's full record), but a person
can open these in Excel. They are written with a byte-order mark because Excel
on Windows otherwise reads UTF-8 as the old Windows character set and turns
"café" into "cafÃ©".
"""
from __future__ import annotations

import csv
from pathlib import Path
from zoneinfo import ZoneInfo

from . import attribution, dates

TORONTO = ZoneInfo("America/Toronto")
CATEGORY_NAMES = {
    "city_notice": "City notice", "planning": "Planning", "permit": "Building permit",
    "ra_news": "Residents' association", "media": "Local news", "police_news": "Police news",
    "police_call": "Police call", "inspection": "Restaurant inspection",
    "business": "Business", "community": "Community", "councillor": "Councillor",
    "transit": "Transit", "crime": "Reported crime", "collision": "Collision",
}


def local(value) -> str:
    """"2026-10-05 22:34" in Toronto time, which is what a reader expects."""
    dt = dates.parse(value)
    return dt.astimezone(TORONTO).strftime("%Y-%m-%d %H:%M") if dt else ""


def status(row) -> str:
    if row["hidden_at"]:
        return f"Hidden: {row['hidden_reason']}"
    if row["routine"]:
        return "Routine, not shown"
    return "Shown"


def write(conn, areas, cfg, out_dir: Path) -> tuple[Path, Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    names = {s.id: s.name for s in cfg.sources}
    homes = {s.id: s.home for s in cfg.sources}
    terms = {s.id: (cfg.licence_of(s).name if cfg.licence_of(s) else "") for s in cfg.sources}
    changes = {r[0]: r[1] for r in conn.execute(
        "SELECT item_id, COUNT(*) FROM item_log WHERE event = 'changed' GROUP BY item_id")}

    everything = out_dir / "everything.csv"
    with everything.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["First seen (Toronto)", "Last seen (Toronto)", "Date of the event",
                    "Status", "Type", "Area", "Source", "Title", "Detail", "Link",
                    "Latitude", "Longitude", "Times changed", "Record id",
                    "Source page", "Terms of use"])
        for r in conn.execute(
            "SELECT * FROM items WHERE category != 'registry'"
            " ORDER BY COALESCE(published_at, first_seen_at) DESC"
        ):
            w.writerow([
                local(r["first_seen_at"]), local(r["last_seen_at"]),
                (r["published_at"] or "")[:10], status(r),
                CATEGORY_NAMES.get(r["category"], r["category"]),
                areas.name(r["area"]), names.get(r["source_id"], r["source_id"]),
                r["title"], r["summary"] or "",
                r["url"] or homes.get(r["source_id"]) or "",
                r["lat"] if r["lat"] is not None else "",
                r["lon"] if r["lon"] is not None else "",
                changes.get(r["id"], 0), r["id"],
                homes.get(r["source_id"]) or "", terms.get(r["source_id"], ""),
            ])

    log = out_dir / "changes.csv"
    with log.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["When (Toronto)", "What happened", "Type", "Area", "Source",
                    "Title now", "What changed", "Title before", "Detail before",
                    "Record id"])
        for r in conn.execute(
            """SELECT l.*, i.title AS now_title, i.category, i.area
               FROM item_log l LEFT JOIN items i ON i.id = l.item_id
               WHERE COALESCE(i.category, '') != 'registry'
               ORDER BY l.at DESC, l.id DESC"""
        ):
            event = {"new": "First seen", "changed": "Changed", "hidden": "Hidden",
                     "back": "Seen again"}.get(r["event"], r["event"])
            before = r["event"] == "changed"
            w.writerow([
                local(r["at"]), event,
                CATEGORY_NAMES.get(r["category"], r["category"] or ""),
                areas.name(r["area"]), names.get(r["source_id"], r["source_id"]),
                r["now_title"] or r["title"] or "", r["note"] or "",
                (r["title"] or "") if before else "",
                (r["summary"] or "")[:500] if before else "",
                r["item_id"],
            ])
    used = [r[0] for r in conn.execute(
        "SELECT DISTINCT source_id FROM items WHERE category != 'registry' ORDER BY source_id")]
    cited = attribution.for_sources(conn, cfg, used)
    source_list = out_dir / "sources.csv"
    with source_list.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Source", "Publisher", "Provides", "Page", "Terms of use",
                    "Terms link", "Required wording", "Records", "Newest record"])
        for c in cited["sources"]:
            lic = c["licence"]
            w.writerow([c["name"], c["publisher"], c["what"], c["home"] or "",
                        lic.name if lic else "", (lic.url or "") if lic else "",
                        lic.statement if lic else "", c["n"], (c["newest"] or "")[:10]])
    return everything, log, source_list
