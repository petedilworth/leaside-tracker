"""City of Toronto Open Data, a standard CKAN 3 instance.

Two steps: package_show tells you which resources a dataset has; datastore_search
returns rows for the ones that are loaded into the datastore.
"""
from __future__ import annotations

import json

API = "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action"


def package_show(http, dataset: str, **kw) -> dict:
    resp = http.get(f"{API}/package_show", params={"id": dataset}, **kw)
    resp.raise_for_status()
    return resp.json()["result"]


def datastore_resources(package: dict) -> list[dict]:
    return [r for r in package.get("resources", []) if r.get("datastore_active")]


def datastore_search(http, resource_id: str, limit: int = 5000, offset: int = 0, **kw) -> dict:
    """Newest first. Rows are appended in load order, so descending _id is recent-first.

    Without this the first page of a dataset that starts in 2006 is all 2006 data.
    """
    resp = http.get(
        f"{API}/datastore_search",
        params={"id": resource_id, "limit": limit, "offset": offset, "sort": "_id desc"},
        **kw,
    )
    resp.raise_for_status()
    return resp.json()["result"]


def _coords(row: dict):
    for lat_key, lon_key in (("LATITUDE", "LONGITUDE"), ("Latitude", "Longitude"), ("lat", "long")):
        if lat_key in row and lon_key in row:
            try:
                return float(row[lat_key]), float(row[lon_key])
            except (TypeError, ValueError):
                return None, None
    return None, None


def rows_to_items(rows: list[dict], source, areas) -> list[dict]:
    items = []
    for row in rows:
        lat, lon = _coords(row)
        area = areas.match_point(lat, lon) or areas.match_text(json.dumps(row, default=str))
        if not area:
            continue
        title = row.get("INJURY") or row.get("ACCLASS") or row.get("IMPACTYPE") or "Collision"
        items.append(
            {
                "source_id": source.id,
                "category": source.category,
                "title": str(title),
                "url": None,
                "summary": " ".join(
                    str(row[k]) for k in ("STREET1", "STREET2", "DISTRICT") if row.get(k)
                )
                or None,
                "published_at": row.get("DATE") or row.get("OCC_DATE"),
                "external_id": str(row.get("_id") or row.get("ACCNUM")),
                "area": area,
                "lat": lat,
                "lon": lon,
                "raw": row,
            }
        )
    return items


def fetch_dataset(source, http, areas) -> tuple[list[dict], int]:
    package = package_show(
        http, source.dataset, timeout=source.timeout, retries=source.retries
    )
    resources = datastore_resources(package)
    if not resources:
        raise RuntimeError(
            f"{source.id}: dataset '{source.dataset}' has no datastore-backed resource. "
            "It is file-download only; add a CSV/GeoJSON download step."
        )
    result = datastore_search(
        http, resources[0]["id"], timeout=source.timeout, retries=source.retries
    )
    return rows_to_items(result.get("records", []), source, areas), 200
