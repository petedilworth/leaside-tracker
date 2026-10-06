"""Toronto Police open data, served from an ArcGIS Hub.

Layer URLs are discovered from the Hub's DCAT-US catalogue rather than hard-coded,
because TPS has already moved this portal between domains once.
"""
from __future__ import annotations

import json

from .. import fields

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
    """"Bicycle Thefts Open Data" -> "Bicycle Theft". One record, so singular."""
    label = dataset_title
    for noise in (" Open Data", " open data"):
        label = label.replace(noise, "")
    label = label.split("(")[0].strip()
    if label.endswith("s") and not label.endswith("ss"):
        label = label[:-1]
    return label or dataset_title


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
        title, summary = _where_and_what(attrs, label)
        occ = attrs.get("OCC_DATE") or attrs.get("REPORT_DATE") or attrs.get("OCC_YEAR")
        items.append(
            {
                "source_id": source.id,
                "category": source.category,
                "title": title,
                "url": None,
                "summary": summary,
                "published_at": _epoch_to_iso(occ),
                "external_id": feature_key(attrs),
                "area": area,
                "lat": lat,
                "lon": lon,
                "raw": attrs,
            }
        )
    return items


STREET_SKIP = ("class", "cond", "user", "type", "surface", "rdsf")


def streets_of(attrs: dict) -> str | None:
    """Whatever a layer calls its location: an intersection, or the first two streets.

    Only the fields numbered 1 and 2 are taken. The City's collision data puts a
    qualifier in the third - "10 m West of" - which read as a street name and
    produced "95 REDPATH AVE & 10 m West of".
    """
    flat = fields.flatten(attrs)
    for key in ("INTERSECTION", "LOCATION_DESC", "ADDRESS", "LOCATION"):
        for k, v in flat.items():
            if k.upper() == key and isinstance(v, str) and v.strip():
                return v.strip()
    named = []
    for key, value in flat.items():
        lk = key.lower()
        is_street = ("street" in lk or "stname" in lk or "st_name" in lk
                     or lk.startswith("road"))
        if not is_street or any(skip in lk for skip in STREET_SKIP):
            continue
        if not lk.rstrip("_").endswith(("1", "2")):
            continue
        if isinstance(value, str) and value.strip() and value.strip().lower() != "none":
            named.append((lk, value.strip()))
    named.sort()
    picked = [v for _, v in named][:2]
    return " & ".join(picked) or None


def _yes(value) -> bool:
    return str(value).strip().upper() in {"YES", "Y", "TRUE", "1"}


def _collision_phrase(flat: dict) -> tuple[str, list[str]] | None:
    """Describe a collision from its flags, for layers with no offence field.

    The traffic collisions layer carries no description at all: just FATALITIES,
    INJURY_COLLISIONS, PD_COLLISIONS, FTR_COLLISIONS and one flag per road user.
    Without reading those, every record on the page said "Incident".
    """
    markers = ("FATALITIES", "INJURY_COLLISIONS", "PD_COLLISIONS", "FTR_COLLISIONS")
    if not any(k in flat for k in markers):
        return None
    try:
        deaths = int(float(flat.get("FATALITIES") or 0))
    except (TypeError, ValueError):
        deaths = 0
    if deaths:
        base = "Fatal collision" if deaths == 1 else f"Collision, {deaths} killed"
    elif _yes(flat.get("INJURY_COLLISIONS")):
        base = "Collision with injuries"
    else:
        base = "Collision"

    for flag, phrase in (("PEDESTRIAN", "involving a pedestrian"),
                         ("BICYCLE", "involving a cyclist"),
                         ("MOTORCYCLE", "involving a motorcycle")):
        if _yes(flat.get(flag)):
            base = f"{base} {phrase}"
            break

    notes = []
    if _yes(flat.get("FTR_COLLISIONS")):
        notes.append("driver failed to remain")
    if _yes(flat.get("PD_COLLISIONS")) and deaths == 0 \
            and not _yes(flat.get("INJURY_COLLISIONS")):
        notes.append("property damage only")
    return base, notes


def _where_and_what(attrs: dict, label: str | None) -> tuple[str, str | None]:
    """A readable title and a one-line description of where it happened.

    Collision layers carry no offence field, so without this every record read
    "Incident" with a division code under it.
    """
    flat = fields.flatten(attrs)
    # What happened, in the publisher's words. Injury severity is not a headline,
    # so it belongs in the line underneath. A collision layer has no such words at
    # all, only flags, so those are read instead.
    collision = _collision_phrase(flat)
    extra: list[str] = []
    if collision:
        title, extra = collision
    else:
        title = (flat.get("OFFENCE") or flat.get("MCI_CATEGORY")
                 or flat.get("CSI_CATEGORY") or flat.get("Category")
                 or flat.get("IMPACTYPE") or label or "Incident")
    where = streets_of(attrs)
    if where:
        title = f"{title} at {where}"
    parts = [
        *extra,
        flat.get("OFFENCE") if flat.get("OFFENCE") != title else None,
        flat.get("PREMISES_TYPE") or flat.get("LOCATION_TYPE"),
        flat.get("INJURY"),
        flat.get("INVTYPE"),
        flat.get("NEIGHBOURHOOD_158") or flat.get("NEIGHBOURHOOD_140")
        or flat.get("DIVISION"),
    ]
    seen, out = set(), []
    for part in parts:
        text = str(part).strip() if part else ""
        if text and text.lower() not in seen and text.lower() not in title.lower():
            seen.add(text.lower())
            out.append(text)
    return str(title), " · ".join(out) or None


def feature_key(attrs: dict) -> str:
    """One police record's identity.

    An event number alone is not enough: one break-in can be recorded as both
    "B&E" and "Unlawfully In Dwelling-House" under the same event. Keyed on the
    event alone, the two collapsed into one item, the second overwrote the first,
    and the stored record flipped between them on every run. The offence code
    (UCR_CODE, UCR_EXT) separates them. Layers without offence codes, such as
    traffic collisions, keep the plain event number, so their keys do not move.
    """
    event = attrs.get("EVENT_UNIQUE_ID") or attrs.get("OBJECTID")
    code, ext = attrs.get("UCR_CODE"), attrs.get("UCR_EXT")
    if code is not None:
        return f"{event}|{code}.{ext}"
    return str(event)


def _epoch_to_iso(value):
    from datetime import datetime, timezone

    if value is None:
        return None
    if isinstance(value, (int, float)) and value > 1e11:  # ArcGIS uses epoch milliseconds
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat(timespec="seconds")
    return str(value)


PAGE_SIZE = 2000
DATE_ORDER = "OCC_DATE DESC"


def query_url(url: str) -> str:
    query = url.rstrip("/")
    if query.endswith("/query"):
        return query
    return f"{query}/0/query" if query.endswith("Server") else f"{query}/query"


def fetch_features(source, http, areas, layer_url: str | None = None,
                   label: str | None = None, max_records: int = 4000):
    """Query one layer, newest first, in pages.

    Two failures this fixes. Without an ordering the service returns records in
    internal id order, so a 2000-record cap gave the OLDEST 2000: every traffic
    collision came back from the first half of 2014. And without paging, anything
    past the cap was simply invisible.

    Not every layer has OCC_DATE, and ArcGIS rejects an unknown sort field, so the
    first page decides whether ordering is available and the rest follow suit.
    """
    url = layer_url or source.url
    if not url:
        raise RuntimeError(
            f"{source.id}: no layer URL. Run the probe so it can be discovered "
            f"from {source.discover_from}."
        )
    minx, miny, maxx, maxy = bbox_of(areas)
    base = {
        "where": "1=1",
        "outFields": "*",
        "geometry": f"{minx},{miny},{maxx},{maxy}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "outSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "returnGeometry": "true",
        "resultRecordCount": PAGE_SIZE,
        "f": "json",
    }
    query = query_url(url)
    items: list[dict] = []
    stats: dict = {}
    order = DATE_ORDER
    offset = 0
    status = 200

    while offset < max_records:
        params = dict(base, resultOffset=offset)
        if order:
            params["orderByFields"] = order
        resp = http.get(query, params=params, timeout=source.timeout,
                        retries=source.retries)
        resp.raise_for_status()
        status = resp.status_code
        payload = json.loads(resp.text)
        if payload.get("error"):
            if order:                      # the layer has no such field; sort by nothing
                order = None
                continue
            raise RuntimeError(
                f"{source.id}: {payload['error'].get('message', 'query rejected')}"
            )
        page = payload.get("features", [])
        items += parse_features(resp.text, source, areas, label=label, stats=stats)
        # Servers cap a page at their own maxRecordCount, often 1000, regardless of
        # what was asked for. Judging "last page" by our requested size would stop
        # after the first page on any such server. The response says whether more
        # exist; trust that, and fall back to the size test only if it is absent.
        more = payload.get("exceededTransferLimit")
        if more is None:
            more = len(page) >= PAGE_SIZE
        if not more or not page:
            break
        offset += len(page)

    fetched = stats.get("features", 0)
    if fetched:
        note = "newest first" if order else "in table order (no date field to sort on)"
        print(f"        {fetched} records read {note}, {len(items)} in your areas"
              + (f", {stats['other_neighbourhood']} in other neighbourhoods"
                 if stats.get("other_neighbourhood") else ""))
    return items, status
