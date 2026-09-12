"""City of Toronto Open Data, a standard CKAN 3 instance.

Two steps: package_show tells you which resources a dataset has; datastore_search
returns rows for the ones that are loaded into the datastore.

Column names are discovered from the datastore's own field list, not assumed. The
first version assumed DATE, LATITUDE and ACCNUM; none matched, so every collision row
arrived undated and unlocated, and once keyed on a composite of missing fields they
all collapsed into a single item.
"""
from __future__ import annotations

import json

from .. import fields
from . import arcgis

API = "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action"

DATE = dict(exact=("DATE", "OCC_DATE", "date"),
            contains=("occ_date", "date"), exclude=("update", "modif", "load"))
LAT = dict(exact=("LATITUDE", "LAT", "latitude"),
           contains=("latitude", "lat"), exclude=("relat", "plat", "flat"))
LON = dict(exact=("LONGITUDE", "LONG", "LON", "longitude"),
           contains=("longitude", "long", "lon"), exclude=("along", "belong"))
ID = dict(exact=("ACCNUM", "accnum", "COLLISION_ID", "collision_id",
                 "ACCIDENT_NO", "EVENT_UNIQUE_ID", "event_unique_id"),
          contains=("accnum", "collision_id", "accident_no", "event_unique"),
          exclude=())
KIND = dict(exact=("IMPACTYPE", "impactype", "ACCLASS", "acclass", "MCI_CATEGORY"),
            contains=("impactype", "acclass", "category"), exclude=("road", "class"))
SEVERITY = dict(exact=("ACCLASS", "acclass", "INJURY", "injury"),
                contains=("acclass", "injury"), exclude=())
HOOD = dict(exact=("NEIGHBOURHOOD_158", "neighbourhood", "NEIGHBOURHOOD"),
            contains=("neighbourhood",), exclude=("140",))


def package_show(http, dataset: str, **kw) -> dict:
    resp = http.get(f"{API}/package_show", params={"id": dataset}, **kw)
    resp.raise_for_status()
    return resp.json()["result"]


def datastore_resources(package: dict) -> list[dict]:
    return [r for r in package.get("resources", []) if r.get("datastore_active")]


def datastore_search(http, resource_id: str, limit: int = 5000, offset: int = 0, **kw) -> dict:
    """Newest first. Rows are appended in load order, so descending _id is recent-first."""
    resp = http.get(
        f"{API}/datastore_search",
        params={"id": resource_id, "limit": limit, "offset": offset, "sort": "_id desc"},
        **kw,
    )
    resp.raise_for_status()
    return resp.json()["result"]


def _coords(row: dict):
    _, lat = fields.pick(row, **LAT)
    _, lon = fields.pick(row, **LON)
    try:
        return (float(lat), float(lon)) if lat and lon else (None, None)
    except ValueError:
        return None, None


def _clean(value) -> str | None:
    """Strip the City's internal annotations, e.g. "Pedestrian Collision (internal code)"."""
    if value in (None, "", "None"):
        return None
    text = str(value).replace("(internal code)", "").strip(" -·,")
    return text or None


def describe(row: dict) -> tuple[str, str | None]:
    """A readable headline and detail line for one collision record."""
    _, kind = fields.pick(row, **KIND)
    _, severity = fields.pick(row, **SEVERITY)
    _, hood = fields.pick(row, **HOOD)
    road_user = _clean(fields.flatten(row).get("road_user"))

    title = _clean(kind) or (f"{road_user.capitalize()} collision" if road_user
                             else "Collision")
    where = arcgis.streets_of(row)
    if where:
        title = f"{title} at {where}"

    flat = fields.flatten(row)
    detail = [_clean(severity), _clean(flat.get("injury")) and
              f"{_clean(flat.get('injury'))} injury", _clean(flat.get("light")),
              _clean(flat.get("rdsfcond")), _clean(hood)]
    seen, out = set(), []
    for part in detail:
        if part and part.lower() not in seen and part.lower() not in title.lower():
            seen.add(part.lower())
            out.append(part)
    return title, " · ".join(out) or None


def _stable_id(row: dict) -> str:
    """A key that survives the City reloading the dataset.

    `_id` is the datastore row number and changes on every reload. A collision
    number is stable, and keying on it collapses the several rows the City publishes
    for one crash - one per person involved - into one item.
    """
    key, value = fields.pick(row, **ID)
    if value:
        return f"{key}:{value}"
    _, when = fields.pick(row, **DATE)
    streets = [v for k, v in fields.flatten(row).items()
               if "street" in k.lower() and isinstance(v, str) and v.strip()]
    _, lat = fields.pick(row, **LAT)
    return "composite:" + "|".join([when or "", *streets[:2], lat or ""])


def resolved_fields(row: dict) -> dict:
    """Which column each role resolved to. Printed once per run so wrong guesses show."""
    return {name: fields.pick(row, **spec)[0]
            for name, spec in (("date", DATE), ("lat", LAT), ("lon", LON),
                               ("id", ID), ("kind", KIND))}


def rows_to_items(rows: list[dict], source, areas, stats: dict | None = None) -> list[dict]:
    items = []
    tally = stats if stats is not None else {}
    for key in ("rows", "no_coords", "outside_areas", "kept"):
        tally.setdefault(key, 0)
    for row in rows:
        tally["rows"] += 1
        lat, lon = _coords(row)
        if lat is None:
            tally["no_coords"] += 1
        # The City names the neighbourhood on each record. Trust it over the
        # rectangles, the same way the police records are handled.
        _, hood = fields.pick(row, **HOOD)
        if hood and not areas.is_official_ours(hood):
            tally["other_neighbourhood"] = tally.get("other_neighbourhood", 0) + 1
            continue
        area = (areas.match_point(lat, lon) or areas.match_official(hood)
                or areas.match_text(json.dumps(row, default=str)))
        if not area:
            tally["outside_areas"] += 1
            continue
        tally["kept"] += 1
        _, when = fields.pick(row, **DATE)
        title, summary = describe(row)
        items.append(
            {
                "source_id": source.id,
                "category": source.category,
                "title": title,
                "url": None,
                "summary": summary,
                "published_at": when,
                "external_id": _stable_id(row),
                "area": area,
                "lat": lat,
                "lon": lon,
                "raw": row,
            }
        )
    return items


def fetch_dataset(source, http, areas) -> tuple[list[dict], int]:
    package = package_show(http, source.dataset, timeout=source.timeout, retries=source.retries)
    resources = datastore_resources(package)
    if not resources:
        raise RuntimeError(
            f"{source.id}: dataset '{source.dataset}' has no datastore-backed resource. "
            "It is file-download only; add a CSV/GeoJSON download step."
        )
    result = datastore_search(http, resources[0]["id"], timeout=source.timeout,
                              retries=source.retries)
    rows = result.get("records", [])
    total = result.get("total")
    if rows:
        resolved = resolved_fields(rows[0])
        print("        columns: " + ", ".join(f"{k}={v}" for k, v in resolved.items()))
        missing = [k for k in ("date", "lat", "lon") if resolved[k] is None]
        if missing:
            names = [f["id"] for f in result.get("fields", [])][:40]
            print(f"        WARNING: no column for {', '.join(missing)}. "
                  f"Columns are: {', '.join(names)}")
    stats: dict = {}
    items = rows_to_items(rows, source, areas, stats=stats)
    print(f"        {len(rows)} of {total} rows read, {stats.get('kept', 0)} in your areas"
          + (f", {stats['other_neighbourhood']} in other neighbourhoods"
             if stats.get("other_neighbourhood") else "")
          + (f", {stats['no_coords']} with no coordinates" if stats.get("no_coords") else ""))
    return items, 200
