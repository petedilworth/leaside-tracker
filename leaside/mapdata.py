"""Police records grouped by the point the police placed them at, for the map.

The police move every record to the nearest intersection on purpose. In the log
on 23 October 2026, 10,970 located police records sat on just 873 distinct
points, and one point - Rosedale subway station - held 524. A pin per record
would stack hundreds of pins on one spot and show one. So the map has one
circle per point and layer, sized by how many records it holds.

Crime and the police collision layer carry no street names. Police calls and
the City's serious-collision records do. A point with no name of its own
borrows the name of the nearest named point within NAME_RADIUS_M, said as
"near", or is left unnamed rather than guessed.
"""
from __future__ import annotations

import json
import math

from . import db

LAYERS = [
    {"key": "crime", "name": "Reported crime", "one": "reported crime", "many": "reported crimes"},
    {"key": "collision", "name": "Collisions", "one": "collision", "many": "collisions"},
    {"key": "police_call", "name": "Police calls", "one": "police call", "many": "police calls"},
]
LAYER_INDEX = {l["key"]: i for i, l in enumerate(LAYERS)}
NAME_RADIUS_M = 60


def _metres(a, b) -> float:
    """Distance between two (lat, lon) points; flat-earth is plenty at this scale."""
    dy = (a[0] - b[0]) * 111_320
    dx = (a[1] - b[1]) * 111_320 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


def _tidy_street(text: str | None) -> str | None:
    if not text:
        return None
    parts = [p.strip() for p in text.replace(" - ", " & ").split("&") if p.strip()]
    parts = [p.title() for p in parts if p.lower() != "none"]
    return " & ".join(dict.fromkeys(parts)) or None


def _street_of(row, raw: dict) -> str | None:
    """The street name a record carries, if any."""
    if row["category"] == "police_call" and " near " in row["title"]:
        return _tidy_street(row["title"].split(" near ", 1)[1])
    if row["source_id"] == "city_ksi_collisions":
        return _tidy_street(" & ".join(str(raw.get(k) or "") for k in ("stname1", "stname2")))
    return None


# Crime types a reader recognises, in the order the filter shows them. The
# police's own categories hide two of them: theft from a car is filed as
# "NonMCI" under $5,000 and "Theft Over" above it, and bike thefts carry no
# category at all, only bike fields.
CRIME_TYPES = ["Assault", "Break and enter", "Car theft", "Theft from a car",
               "Bike theft", "Robbery", "Other"]


# The date slider's steps. Even steps along the slider, uneven in time: the
# records span twenty years but the interesting part is the recent months, and a
# linear twenty-year slider would leave the last 90 days as a sliver at one end.
STOPS = [
    (7, "1 week", "1 wk"), (14, "2 weeks", ""), (30, "1 month", "1 mo"), (61, "2 months", ""),
    (91, "3 months", "3 mo"), (182, "6 months", ""), (365, "1 year", "1 yr"),
    (730, "2 years", ""), (1095, "3 years", "3 yr"), (1826, "5 years", ""),
    (3652, "10 years", "10 yr"), (0, "everything", "All"),
]
DEFAULT_STOP = 6       # 1 year: crime arrives three months late, so less looks empty


def crime_type(raw: dict) -> str:
    offence = str(raw.get("OFFENCE") or raw.get("PRIMARY_OFFENCE") or "").lower()
    category = str(raw.get("CSI_CATEGORY") or "").lower()
    if any(k.startswith("BIKE_") for k in raw) or "bicycle" in offence:
        return "Bike theft"
    if "theft from motor vehicle" in offence:
        return "Theft from a car"
    for name, keys in (("Assault", ("assault",)), ("Break and enter", ("break and enter", "b&e")),
                       ("Car theft", ("auto theft", "theft of motor vehicle")),
                       ("Robbery", ("robbery",))):
        if any(k in category or k in offence for k in keys):
            return name
    return "Other"


def _label(row, raw: dict) -> tuple[str, str]:
    """(what happened, detail) in the reader's words."""
    title, summary = row["title"], row["summary"] or ""
    if row["category"] == "police_call":
        return title.split(" near ")[0], ""
    if row["category"] == "crime":
        what = raw.get("OFFENCE") or raw.get("PRIMARY_OFFENCE") or title.split(" at ")[0]
        where = raw.get("PREMISES_TYPE") or ""
        return str(what), str(where)
    # collisions: the title already says what; the first detail is the useful one
    detail = summary.split(" · ")[0] if summary else ""
    if row["source_id"] == "city_ksi_collisions":
        detail = "Killed or seriously injured" + (f" · {detail}" if detail else "")
    return title.split(" at ")[0], detail


def build(conn, areas, cfg) -> dict:
    rows = conn.execute(
        "SELECT * FROM items WHERE category IN ('crime', 'collision', 'police_call')"
        f" AND {db.SHOWN} AND lat IS NOT NULL AND lon IS NOT NULL"
        " ORDER BY COALESCE(published_at, first_seen_at) DESC"
    ).fetchall()
    sources = [s for s in cfg.sources if s.category in ("crime", "collision", "police_call")]
    src_index = {s.id: i for i, s in enumerate(sources)}
    strings: dict[str, int] = {}

    def code(text: str) -> int:
        return strings.setdefault(text, len(strings))

    spots: dict[tuple, dict] = {}
    for r in rows:
        try:
            raw = json.loads(r["raw"]) if r["raw"] else {}
        except ValueError:
            raw = {}
        key = (round(r["lat"], 5), round(r["lon"], 5))
        spot = spots.setdefault(key, {"lat": key[0], "lon": key[1], "names": {},
                                      "area": r["area"], "r": []})
        street = _street_of(r, raw)
        if street:
            spot["names"][street] = spot["names"].get(street, 0) + 1
        what, detail = _label(r, raw)
        kind = (CRIME_TYPES.index(crime_type(raw)) if r["category"] == "crime" else -1)
        spot["r"].append([LAYER_INDEX[r["category"]],
                          (r["published_at"] or r["first_seen_at"] or "")[:10],
                          code(what), code(detail), src_index.get(r["source_id"], -1), kind])

    named = [(s["lat"], s["lon"], max(s["names"], key=s["names"].get))
             for s in spots.values() if s["names"]]
    out = []
    for s in spots.values():
        if s["names"]:
            name, exact = max(s["names"], key=s["names"].get), True
        else:
            best = min(named, key=lambda n: _metres((s["lat"], s["lon"]), n[:2]), default=None)
            near = best and _metres((s["lat"], s["lon"]), best[:2]) <= NAME_RADIUS_M
            name, exact = (best[2], False) if near else (None, False)
        out.append({"lat": s["lat"], "lon": s["lon"], "name": name, "exact": exact,
                    "area": areas.name(s["area"]), "r": s["r"]})
    out.sort(key=lambda s: -len(s["r"]))
    return {
        # The project's area outlines, for orientation. GeoJSON is lon,lat; the map wants lat,lon.
        "areas": [{"name": f["properties"]["name"],
                   "ring": [[lat, lon] for lon, lat in f["geometry"]["coordinates"][0]]}
                  for f in areas.features],
        "layers": LAYERS,
        "crime_types": CRIME_TYPES,
        "type_totals": [sum(1 for sp in out for r in sp["r"] if r[0] == 0 and r[5] == i)
                        for i in range(len(CRIME_TYPES))],
        "stops": [{"days": d, "label": label, "tick": tick} for d, label, tick in STOPS],
        "default_stop": DEFAULT_STOP,
        "oldest": min((r[1] for sp in out for r in sp["r"] if r[1]), default=None),
        "sources": [{"name": s.name, "credit": s.credit, "home": s.home} for s in sources],
        "strings": list(strings),
        "spots": out,
        "records": len(rows),
    }


def payload(data: dict) -> str:
    """The data as JSON that is safe inside a <script> element.

    It is inlined rather than fetched because the page is also opened straight
    from disk on Windows, where browsers refuse to fetch a neighbouring file.
    "</" is escaped so no text in the data can close the script element.
    """
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
