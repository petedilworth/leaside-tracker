"""The Police calls page: every call we logged, newest first, plus the long view.

Two kinds of data, kept apart because they count different things:

- Our own log of the police's public calls map, from 3 October 2026. Each call
  has a time, a type, a division and the nearest intersection. The map leaves
  out medical, domestic, sexual assault and suicide calls, and before the hourly
  timer we missed some, so it is a part of what police attend, not all of it.
- The police's yearly count of every call attended per City neighbourhood, 2015
  onward (tps_calls_attended). All types together, no months.

The browser does the counting, so the cards, the month table and the list all
follow the same filters without a rebuild.
"""
from __future__ import annotations

import json

from . import calltypes, db, mapdata
from .fetchers import tps_yearly

YEARLY_SOURCE = "tps_calls_attended"


def _calls(conn, areas) -> list[dict]:
    groups = calltypes.groups()
    rows = conn.execute(
        "SELECT title, published_at, first_seen_at, area, lat, lon, raw FROM items"
        f" WHERE category = 'police_call' AND {db.SHOWN}"
        " ORDER BY COALESCE(published_at, first_seen_at) DESC").fetchall()
    out = []
    for r in rows:
        try:
            raw = json.loads(r["raw"]) if r["raw"] else {}
        except ValueError:
            raw = {}
        police = calltypes.call_type_of({"raw": raw, "title": r["title"]})
        group, kind = calltypes.classify(police)
        street = (mapdata._tidy_street(r["title"].split(" near ", 1)[1])
                  if " near " in r["title"] else None)
        out.append({
            "t": r["published_at"] or r["first_seen_at"],
            "p": r["title"].split(" near ")[0],          # the police's words
            "g": groups.index(group),
            "k": kind or "",                             # the owner's name for it
            "a": r["area"],
            "s": street,
            "d": raw.get("DIVISION"),
            "lat": None if r["lat"] is None else round(r["lat"], 5),
            "lon": None if r["lon"] is None else round(r["lon"], 5),
        })
    return out


def _yearly(conn, areas) -> list[dict]:
    """One panel per City neighbourhood: its yearly counts and which of our areas it holds."""
    counts: dict[str, dict[int, int]] = {}
    for (raw,) in conn.execute(
            "SELECT raw FROM items WHERE source_id = ? AND hidden_at IS NULL", (YEARLY_SOURCE,)):
        try:
            r = json.loads(raw)
            counts.setdefault(r["neighbourhood"], {})[int(r["year"])] = int(r["calls"])
        except (ValueError, KeyError, TypeError):
            continue
    panels = []
    for hood in tps_yearly.our_neighbourhoods(areas):
        if hood not in counts:
            continue
        covers = [f["properties"]["name"] for f in areas.features
                  if hood in f["properties"].get("official", [])]
        years = sorted(counts[hood])
        panels.append({"name": hood, "covers": covers, "years": years,
                       "counts": [counts[hood][y] for y in years]})
    return panels


def build(conn, areas, cfg) -> dict:
    calls = _calls(conn, areas)
    return {
        "calls": calls,
        "groups": calltypes.groups(),
        "other": calltypes.other(),
        "ignored": calltypes.ignored(),
        "areas": [{"key": k, "name": areas.name(k)} for k in areas.keys()],
        "yearly": _yearly(conn, areas),
        "first": min((c["t"] for c in calls if c["t"]), default=None),
        "generated": db.utcnow(),
    }


def payload(data: dict) -> str:
    return mapdata.payload(data)
