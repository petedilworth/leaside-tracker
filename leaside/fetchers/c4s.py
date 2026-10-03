"""Toronto Police calls for service: what officers are attending right now.

The police publish a public map of calls in progress - call type, division and
nearest intersection - refreshed every twenty minutes, each call shown for about
four hours and then gone. Medical, sexual assault, suicide and domestic calls are
withheld by the publisher. Polled every half hour, that four-hour window becomes
a lasting log of what police did in the neighbourhood, months before the same
events reach the reported-crime dataset.

The exact layer address is not confirmed from this machine, so the source lists
candidate addresses and, failing those, walks the publisher's ArcGIS directory for
a service whose name looks like calls-for-service. Whatever answers is printed,
so the config can be pinned to it once the health report comes back.

Nothing here is an exact address. The publisher places every call at the nearest
intersection, and the page says so.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

from .. import fields
from . import arcgis

TYPE = dict(exact=("CALL_TYPE", "EVENT_TYPE", "CALLTYPE", "EVENTTYPE", "TYPE",
                   "Call_Type", "Event_Type", "INCIDENT_TYPE", "DESCRIPTION"),
            contains=("call_type", "event_type", "calltype", "eventtype",
                      "incident", "type", "desc"),
            exclude=("geometry", "shape", "unit", "premise", "prem", "subtype_code"))
WHEN = dict(exact=("DISPATCH_TIME", "ARRIVAL_TIME", "ARRIVED", "DISPATCHED",
                   "EVENT_TIME", "CALL_TIME", "TIME", "DATE", "OCC_DATE"),
            contains=("dispatch", "arriv", "on_scene", "event_time", "call_time",
                      "time", "date"),
            exclude=("edit", "update", "load", "creat", "modif", "clear"))
WHERE = dict(exact=("INTERSECTION", "CROSS_STREETS", "CROSS_STREET", "LOCATION",
                    "ADDRESS", "STREET", "Intersection", "Location"),
             contains=("intersect", "cross", "location", "address", "street", "where"),
             exclude=("type", "code", "id"))
DIVISION = dict(exact=("DIVISION", "DIV", "Division"), contains=("division", "div"),
                exclude=("subdiv",))
# OBJECTID is deliberately not here. On a rolling four-hour layer the row numbers
# are reused, so two different calls a day apart would collapse into one item.
# Without a real event number the key is time + type + place instead.
ID = dict(exact=("EVENT_ID", "EVENT_NUMBER", "EVENT_NUM", "CALL_ID", "EVENT_UNIQUE_ID",
                 "INCIDENT_ID", "ID"),
          contains=("event_id", "event_num", "call_id", "incident_id", "unique"),
          exclude=("type", "object"))

DIRECTORIES = (
    # Toronto Police's ArcGIS Online organisation; the reported-crime layers live here.
    "https://services.arcgis.com/S9th0jAJ7bqgIRjw/arcgis/rest/services",
    # The host the public map itself is served from.
    "https://c4s.torontopolice.on.ca/arcgis/rest/services",
)
NAME_HINT = re.compile(r"c4s|calls?[_ ]?for[_ ]?service|cad[_ ]?public|dispatch", re.I)


def _mercator_to_wgs84(x: float, y: float) -> tuple[float, float]:
    """ArcGIS defaults to Web Mercator metres. The query asks for degrees, but a
    layer that ignores outSR must still land on the map."""
    lon = x / 20037508.34 * 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * y / 20037508.34)))
    return lat, lon


def _coords(feat: dict, wkid: int | None):
    geom = feat.get("geometry") or {}
    x, y = geom.get("x"), geom.get("y")
    if x is None and isinstance(geom.get("coordinates"), list):
        x, y = geom["coordinates"][0], geom["coordinates"][1]
    if x is None or y is None:
        return None, None
    x, y = float(x), float(y)
    if wkid in (102100, 3857) or abs(x) > 180 or abs(y) > 90:
        return _mercator_to_wgs84(x, y)
    return y, x


def _local_clock(iso: str | None) -> str | None:
    """"14:35 Toronto" from a UTC timestamp, for the summary line.

    The page converts timestamps for the reader; the stored summary is plain text
    and would otherwise say a time nobody in Toronto recognises.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from .. import dates

    dt = dates.parse(iso)
    if dt is None:
        return None
    local = dt.astimezone(ZoneInfo("America/Toronto"))
    return f"{local:%H:%M} on {local:%a} {local.day} {local:%b}"


def parse_calls(text: str, source, areas, stats: dict | None = None) -> list[dict]:
    data = json.loads(text)
    if data.get("error"):
        raise RuntimeError(f"{source.id}: {data['error'].get('message', 'query rejected')}")
    wkid = ((data.get("spatialReference") or {}).get("latestWkid")
            or (data.get("spatialReference") or {}).get("wkid"))
    tally = stats if stats is not None else {}
    for key in ("features", "no_geometry", "outside_areas", "kept"):
        tally.setdefault(key, 0)
    items = []
    for feat in data.get("features", []):
        tally["features"] += 1
        attrs = feat.get("attributes") or feat.get("properties") or {}
        lat, lon = _coords(feat, wkid)
        if lat is None:
            tally["no_geometry"] += 1
        _, where = fields.pick(attrs, **WHERE)
        area = areas.match_point(lat, lon) or areas.match_text(where)
        if not area:
            tally["outside_areas"] += 1
            continue
        tally["kept"] += 1
        _, kind = fields.pick(attrs, **TYPE)
        _, when_raw = fields.pick(attrs, **WHEN)
        _, division = fields.pick(attrs, **DIVISION)
        _, event_id = fields.pick(attrs, **ID)
        when = arcgis._epoch_to_iso(_number_or_text(when_raw))
        kind = _tidy(kind) or "Police call"
        title = f"{kind} near {where.strip()}" if where else kind
        clock = _local_clock(when)
        detail = [f"Police attended at {clock}" if clock else "Police attended",
                  f"{division} Division" if division and "div" not in str(division).lower()
                  else division,
                  "Placed at the nearest intersection by the police, not the address"]
        items.append({
            "source_id": source.id,
            "category": source.category,
            "title": title,
            "url": None,
            "summary": " · ".join(d for d in detail if d),
            "published_at": when,
            "external_id": (f"event:{event_id}" if event_id
                            else "composite:" + "|".join([when or "", kind, where or ""])),
            "area": area,
            "lat": lat,
            "lon": lon,
            "raw": attrs,
        })
    return items


def _number_or_text(value):
    if value is None:
        return None
    try:
        return int(str(value))
    except ValueError:
        return value


def _tidy(value) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if text.isupper():
        text = text.title()
    return text


def _is_layer(info: dict) -> bool:
    return isinstance(info, dict) and "fields" in info and "layers" not in info


def _walk_directory(http, root: str, timeout, retries) -> list[str]:
    """Every service under a services root (and one level of folders) whose name
    looks like calls-for-service. Returns layer-zero URLs."""
    found = []
    seen_services = []
    try:
        top = http.get(f"{root}?f=json", timeout=timeout, retries=retries).json()
    except Exception as exc:  # directory listing off, host down, not JSON
        print(f"        directory {root}: {type(exc).__name__}")
        return found
    listings = [(root, top)]
    for folder in top.get("folders") or []:
        try:
            listings.append((f"{root}/{folder}",
                             http.get(f"{root}/{folder}?f=json", timeout=timeout,
                                      retries=retries).json()))
        except Exception:
            continue
    for base, listing in listings:
        for svc in listing.get("services") or []:
            name, kind = svc.get("name", ""), svc.get("type", "")
            seen_services.append(name)
            if kind in ("FeatureServer", "MapServer") and NAME_HINT.search(name):
                short = name.split("/")[-1]
                found.append(f"{base}/{short}/{kind}/0")
    if seen_services:
        Path("config").mkdir(exist_ok=True)
        Path(f"config/tps-calls-catalogue.md").write_text(
            f"# Services under {root}\n\n" + "\n".join(f"- {n}" for n in sorted(seen_services))
            + "\n", encoding="utf-8")
    return found


def find_layer(source, http) -> str:
    """The first candidate that is a queryable layer, else a directory walk."""
    timeout, retries = source.timeout, source.retries
    tried = []
    for url in list(source.candidates) + ([source.url] if source.url else []):
        try:
            info = http.get(f"{url.rstrip('/')}?f=json", timeout=timeout, retries=retries).json()
        except Exception as exc:
            tried.append(f"{url} -> {type(exc).__name__}")
            continue
        if _is_layer(info):
            print(f"        layer: {url}")
            return url
        if isinstance(info, dict) and info.get("layers"):
            first = info["layers"][0]["id"]
            print(f"        layer: {url}/{first}")
            return f"{url.rstrip('/')}/{first}"
        tried.append(f"{url} -> {info.get('error', {}).get('message', 'not a layer')}"
                     if isinstance(info, dict) else f"{url} -> unexpected response")
    for root in DIRECTORIES:
        for url in _walk_directory(http, root, timeout, retries):
            try:
                info = http.get(f"{url}?f=json", timeout=timeout, retries=retries).json()
            except Exception:
                continue
            if _is_layer(info):
                print(f"        layer (found by walking {root}): {url}")
                return url
    raise RuntimeError(
        f"{source.id}: no calls-for-service layer found. Tried: " + "; ".join(tried)
        + ". Services seen are listed in config/tps-calls-catalogue.md - send it to Claude."
    )


def fetch_calls(source, http, areas) -> tuple[list[dict], int]:
    layer = find_layer(source, http)
    minx, miny, maxx, maxy = arcgis.bbox_of(areas)
    params = {
        "where": "1=1",
        "outFields": "*",
        "geometry": f"{minx},{miny},{maxx},{maxy}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "outSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "returnGeometry": "true",
        "resultRecordCount": 2000,
        "f": "json",
    }
    resp = http.get(arcgis.query_url(layer), params=params, timeout=source.timeout,
                    retries=source.retries)
    resp.raise_for_status()
    stats: dict = {}
    items = parse_calls(resp.text, source, areas, stats=stats)
    if stats.get("features"):
        sample = json.loads(resp.text)["features"][0].get("attributes") or {}
        resolved = {name: fields.pick(sample, **spec)[0]
                    for name, spec in (("type", TYPE), ("when", WHEN), ("where", WHERE),
                                       ("division", DIVISION), ("id", ID))}
        print("        columns: " + ", ".join(f"{k}={v}" for k, v in resolved.items()))
    print(f"        {stats.get('features', 0)} calls in the box, {len(items)} in your areas"
          + (f", {stats['no_geometry']} with no location" if stats.get("no_geometry") else ""))
    return items, resp.status_code
