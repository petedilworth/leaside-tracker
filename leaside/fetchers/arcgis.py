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


def _layer_url(ds: dict) -> str | None:
    for dist in ds.get("distribution", []):
        url = dist.get("accessURL") or dist.get("downloadURL") or ""
        if any(h in url for h in FEATURE_HINTS):
            return url
    return None


def find_layer(entries: list[dict], match) -> str | None:
    """Find a queryable layer by title.

    `match` may be one phrase or several. Publishers rename datasets, so an exact
    substring is tried first and then a looser all-words-present match. "Major Crime
    Indicators" has appeared as "MCI", "Major Crime Indicators Open Data" and
    "Major_Crime_Indicators_Open_Data" at different times.
    """
    candidates = [match] if isinstance(match, str) else list(match)
    titled = [(ds, (ds.get("title") or "").lower()) for ds in entries]

    for phrase in candidates:
        needle = phrase.lower().strip()
        for ds, title in titled:
            if needle in title and (url := _layer_url(ds)):
                return url

    for phrase in candidates:
        words = [w for w in phrase.lower().replace("_", " ").split() if w]
        for ds, title in titled:
            normalised = title.replace("_", " ")
            if all(w in normalised for w in words) and (url := _layer_url(ds)):
                return url
    return None


def find_layers(entries: list[dict], matches) -> list[tuple[str, str]]:
    """Every layer matching any of `matches`, as (title, url).

    Toronto Police do not publish one "Major Crime Indicators" layer. They publish
    each offence separately - Assault Open Data, Break and Enter Open Data and so on -
    so a crime source has to gather several layers rather than pick one.
    """
    wanted = [matches] if isinstance(matches, str) else list(matches)
    found, seen = [], set()
    for phrase in wanted:
        needle = phrase.lower().strip()
        for ds in entries:
            title = (ds.get("title") or "")
            if needle not in title.lower():
                continue
            url = _layer_url(ds)
            if url and url not in seen:
                seen.add(url)
                found.append((title, url))
    return found


def offence_label(dataset_title: str) -> str:
    """"Break and Enter Open Data" -> "Break and Enter"."""
    label = dataset_title
    for noise in (" Open Data", " open data"):
        label = label.replace(noise, "")
    return label.split("(")[0].strip() or dataset_title


def queryable_titles(entries: list[dict]) -> list[str]:
    """Titles of every dataset we could actually query. For when discovery fails."""
    return sorted(ds.get("title", "untitled") for ds in entries if _layer_url(ds))


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


def parse_features(text: str, source, areas, label: str | None = None,
                   stats: dict | None = None) -> list[dict]:
    """Turn an ArcGIS query result into items, counting what was dropped and why.

    A source that returns nothing used to report plain success. The funnel counts
    make the difference between "no records here" and "my filter ate them all".
    """
    data = json.loads(text)
    items = []
    tally = stats if stats is not None else {}
    for key in ("features", "no_geometry", "other_neighbourhood", "outside_areas", "kept"):
        tally.setdefault(key, 0)
    for feat in data.get("features", []):
        tally["features"] += 1
        attrs = feat.get("attributes") or feat.get("properties") or {}
        geom = feat.get("geometry") or {}
        lon, lat = geom.get("x"), geom.get("y")
        if lon is None and isinstance(geom.get("coordinates"), list):
            lon, lat = geom["coordinates"][0], geom["coordinates"][1]
        # Toronto Police state the City neighbourhood on every record. That beats
        # a hand-drawn rectangle: a South Rosedale box was wide enough to claim a
        # robbery in North St.James Town, four kilometres away.
        official = (attrs.get("NEIGHBOURHOOD_158") or attrs.get("NEIGHBOURHOOD_140")
                    or attrs.get("Neighbourhood"))
        if official and not areas.is_official_ours(official):
            tally["other_neighbourhood"] += 1
            continue
        if lat is None or lon is None:
            tally["no_geometry"] += 1
        area = areas.match_point(lat, lon) or areas.match_official(official)
        if not area:
            tally["outside_areas"] += 1
            continue
        tally["kept"] += 1
        title = (
            attrs.get("MCI_CATEGORY")
            or attrs.get("OFFENCE")
            or attrs.get("Category")
            or label
            or "Incident"
        )
        occ = attrs.get("OCC_DATE") or attrs.get("REPORT_DATE") or attrs.get("OCC_YEAR")
        items.append(
            {
                "source_id": source.id,
                "category": source.category,
                "title": str(title),
                "url": None,
                "summary": _crime_summary(attrs),
                "published_at": _epoch_to_iso(occ),
                "external_id": str(attrs.get("EVENT_UNIQUE_ID") or attrs.get("OBJECTID")),
                "area": area,
                "lat": lat,
                "lon": lon,
                "raw": attrs,
            }
        )
    return items


def _crime_summary(attrs: dict) -> str | None:
    """The offence in full, where it happened, and the neighbourhood, if given."""
    parts = [attrs.get("OFFENCE"), attrs.get("PREMISES_TYPE"),
             attrs.get("NEIGHBOURHOOD_158") or attrs.get("DIVISION")]
    seen, out = set(), []
    for part in parts:
        text = str(part).strip() if part else ""
        if text and text.lower() not in seen:
            seen.add(text.lower())
            out.append(text)
    return " · ".join(out) or None


def _epoch_to_iso(value):
    from datetime import datetime, timezone

    if value is None:
        return None
    if isinstance(value, (int, float)) and value > 1e11:  # ArcGIS uses epoch milliseconds
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat(timespec="seconds")
    return str(value)


def fetch_features(source, http, areas, layer_url: str | None = None,
                   label: str | None = None):
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
    stats: dict = {}
    items = parse_features(resp.text, source, areas, label=label, stats=stats)
    if stats.get("features") and not items:
        print(f"        {stats['features']} records fetched, none kept: "
              f"{stats['other_neighbourhood']} in other neighbourhoods, "
              f"{stats['outside_areas']} outside the areas, "
              f"{stats['no_geometry']} with no coordinates")
    return items, resp.status_code
