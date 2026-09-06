"""Toronto Police open data, served from an ArcGIS Hub.

Layer URLs are discovered from the Hub's DCAT-US catalogue rather than hard-coded,
because TPS has already moved this portal between domains once.
"""
from __future__ import annotations

import json

FEATURE_HINTS = ("FeatureServer", "MapServer")


def catalogue_entries(text: str) -> list[dict]:
    data = json.loads(text)
    return data.get("dataset", []) if isinstance(data, dict) else []


def find_layer(entries: list[dict], match: str) -> str | None:
    """Return the first FeatureServer/MapServer URL whose title contains `match`."""
    needle = match.lower()
    for ds in entries:
        if needle not in (ds.get("title") or "").lower():
            continue
        for dist in ds.get("distribution", []):
            url = dist.get("accessURL") or dist.get("downloadURL") or ""
            if any(h in url for h in FEATURE_HINTS):
                return url
    return None


def fetch_catalogue(source, http, areas) -> tuple[list[dict], int]:
    """Not a news source. Ingesting it just records what layers exist today."""
    resp = http.get(source.url, timeout=source.timeout, retries=source.retries)
    resp.raise_for_status()
    items = [
        {
            "source_id": source.id,
            "category": "registry",
            "title": ds.get("title", "untitled dataset"),
            "url": ds.get("landingPage"),
            "summary": (ds.get("description") or "")[:500] or None,
            "published_at": ds.get("modified"),
            "external_id": ds.get("identifier") or ds.get("title"),
            "raw": ds,
        }
        for ds in catalogue_entries(resp.text)
    ]
    return items, resp.status_code


def bbox_of(areas) -> tuple[float, float, float, float]:
    xs, ys = [], []
    for f in areas.features:
        for ring in f["geometry"]["coordinates"]:
            for lon, lat in ring:
                xs.append(lon)
                ys.append(lat)
    return min(xs), min(ys), max(xs), max(ys)


def parse_features(text: str, source, areas) -> list[dict]:
    data = json.loads(text)
    items = []
    for feat in data.get("features", []):
        attrs = feat.get("attributes") or feat.get("properties") or {}
        geom = feat.get("geometry") or {}
        lon, lat = geom.get("x"), geom.get("y")
        if lon is None and isinstance(geom.get("coordinates"), list):
            lon, lat = geom["coordinates"][0], geom["coordinates"][1]
        area = areas.match_point(lat, lon)
        if not area:
            continue
        title = (
            attrs.get("MCI_CATEGORY")
            or attrs.get("OFFENCE")
            or attrs.get("Category")
            or "Incident"
        )
        occ = attrs.get("OCC_DATE") or attrs.get("REPORT_DATE") or attrs.get("OCC_YEAR")
        items.append(
            {
                "source_id": source.id,
                "category": source.category,
                "title": str(title),
                "url": None,
                "summary": attrs.get("NEIGHBOURHOOD_158") or attrs.get("DIVISION"),
                "published_at": _epoch_to_iso(occ),
                "external_id": str(attrs.get("EVENT_UNIQUE_ID") or attrs.get("OBJECTID")),
                "area": area,
                "lat": lat,
                "lon": lon,
                "raw": attrs,
            }
        )
    return items


def _epoch_to_iso(value):
    from datetime import datetime, timezone

    if value is None:
        return None
    if isinstance(value, (int, float)) and value > 1e11:  # ArcGIS uses epoch milliseconds
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat(timespec="seconds")
    return str(value)


def fetch_features(source, http, areas, layer_url: str | None = None):
    url = layer_url or source.url
    if not url:
        raise RuntimeError(
            f"{source.id}: no layer URL. Run the probe so it can be discovered "
            f"from {source.discover_from}."
        )
    minx, miny, maxx, maxy = bbox_of(areas)
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
    query = url.rstrip("/")
    if not query.endswith("/query"):
        query = f"{query}/0/query" if query.endswith("Server") else f"{query}/query"
    resp = http.get(query, params=params, timeout=source.timeout,
                    retries=source.retries)
    resp.raise_for_status()
    return parse_features(resp.text, source, areas), resp.status_code
