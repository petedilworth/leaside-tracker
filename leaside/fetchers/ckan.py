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

API = "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action"

DATE = dict(exact=("DATE", "OCC_DATE", "date"),
            contains=("occ_date", "date"), exclude=("update", "modif", "load"))
LAT = dict(exact=("LATITUDE", "LAT", "latitude"),
           contains=("latitude", "lat"), exclude=("relat", "plat", "flat"))
LON = dict(exact=("LONGITUDE", "LONG", "LON", "longitude"),
           contains=("longitude", "long", "lon"), exclude=("along", "belong"))
ID = dict(exact=("ACCNUM", "ACCIDENT_NO", "COLLISION_ID", "EVENT_UNIQUE_ID"),
          contains=("accnum", "accident", "collision_id", "event_unique", "unique"),
          exclude=("_id",))
KIND = dict(exact=("INJURY", "ACCLASS", "IMPACTYPE", "MCI_CATEGORY"),
            contains=("injury", "acclass", "impactype", "category", "class"), exclude=())
STREET = dict(exact=("STREET1", "STREET2"), contains=("street", "road"), exclude=("class",))


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


def rows_to_items(rows: list[dict], source, areas) -> list[dict]:
    items = []
    for row in rows:
        lat, lon = _coords(row)
        area = areas.match_point(lat, lon) or areas.match_text(json.dumps(row, default=str))
        if not area:
            continue
        _, kind = fields.pick(row, **KIND)
        _, when = fields.pick(row, **DATE)
        streets = [v for k, v in fields.flatten(row).items()
                   if "street" in k.lower() and isinstance(v, str) and v.strip()]
        items.append(
            {
                "source_id": source.id,
                "category": source.category,
                "title": str(kind or "Collision"),
                "url": None,
                "summary": " & ".join(streets[:2]) or None,
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
    if rows:
        resolved = resolved_fields(rows[0])
        print("        columns: " + ", ".join(f"{k}={v}" for k, v in resolved.items()))
        missing = [k for k in ("date", "lat", "lon") if resolved[k] is None]
        if missing:
            names = [f["id"] for f in result.get("fields", [])][:40]
            print(f"        WARNING: no column for {', '.join(missing)}. "
                  f"Columns are: {', '.join(names)}")
    return rows_to_items(rows, source, areas), 200
