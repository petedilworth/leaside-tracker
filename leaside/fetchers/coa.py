"""Committee of Adjustment applications in Leaside and Bennington Heights, 2000 on.

The City publishes every application as open data (dataset
committee-of-adjustment-applications), refreshed daily:

- Active applications, in the City's datastore.
- Closed applications by year, 2001 to 2016, in the datastore. The 2001 table
  already holds hearings from January 2000.
- Closed applications since 2017, as one CSV file of about 15 MB. Its datastore
  copy refuses queries, so the file is read whole and filtered here.

Leaside and Bennington Heights both sit in postal area M4G and both go to the
North York panel. A file counts as ours when its postal area is M4G, or when it
has no postal area but sits in Don Valley West (ward 26 before 2018, ward 15
after) on a street our areas list. Bennington Heights is told apart from
Leaside by its street names.

What the open data does not have: the names of owners, applicants or agents,
and the itemised list of variances. Those are in the City's Application
Information Centre, which refuses automated requests (HTTP 403), so they are
not collected. The description, decision, objections and appeals are.
"""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime

from . import ckan

DATASET = "committee-of-adjustment-applications"
WARDS = ["15", "26"]          # Don Valley West: ward 15 since 2018, ward 26 before
FSA = "M4G"
OURS = ("leaside", "bennington")
KINDS = {"MV": "Minor variance", "CO": "Consent"}


def day(value) -> str | None:
    """'2019-02-21', '2018-12-20T00:00:00' or 'Jan 11, 2000' -> '2019-02-21'."""
    text = str(value or "").strip()
    if not text:
        return None
    if re.match(r"\d{4}-\d{2}-\d{2}", text):
        return text[:10]
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%d-%b-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _clean(value) -> str | None:
    text = re.sub(r"\s+", " ", str(value if value is not None else "")).strip()
    return text or None


def _title(text: str | None) -> str | None:
    """'MCRAE DR' -> 'Mcrae Dr', leaving short codes like 'NY' alone."""
    if not text:
        return None
    return " ".join(w if len(w) <= 1 else w[0] + w[1:].lower() for w in text.split())


def normalise(row: dict) -> dict:
    """One shape for every table's row, in plain field names."""
    street = _title(" ".join(x for x in (_clean(row.get("STREET_NAME")), _clean(row.get("STREET_TYPE")),
                                          _clean(row.get("STREET_DIRECTION"))) if x))
    num = _clean(row.get("STREET_NUM"))
    ref = _clean(row.get("REFERENCE_FILE#") or row.get("REFERENCE_FILE"))
    return {
        "ref": ref.upper() if ref else None,
        "kind": KINDS.get(_clean(row.get("APPLICATION_TYPE")) or "", _clean(row.get("APPLICATION_TYPE"))),
        "address": " ".join(x for x in (num, street) if x) or None,
        "street": street,
        "postal": (_clean(row.get("POSTAL")) or "").upper()[:3] or None,
        "ward": (_clean(row.get("WARD") or row.get("WARD_NUMBER")) or "").lstrip("0") or None,
        "district": _clean(row.get("PLANNING_DISTRICT")),
        "received": day(row.get("IN_DATE")),
        "hearing": day(row.get("HEARING_DATE")),
        "time": _clean(row.get("TIME_OF_MEETING")),
        "location": _clean(row.get("MEETING_LOCATION")),
        "description": _clean(row.get("DESCRIPTION")),
        "sub_type": _clean(row.get("SUB_TYPE")),
        "work_type": _clean(row.get("WORK_TYPE")),
        "zoning": _clean(row.get("ZONING_DESIGNATION")),
        "decision": _clean(row.get("C_OF_A_DESCISION")),
        "objections": _clean(row.get("ANYONE_OBJECT_AT_MEETING")),
        "appeal_expiry": day(row.get("APPEAL_EXPIRY_DATE")),
        "tribunal_date": day(row.get("OMB_ORDER_DATE")),
        "tribunal_decision": _clean(row.get("OMB_DESCISION")),
        "lots_created": _clean(row.get("NUMBER_OF_LOTS_CREATED")),
        "condition_expiry": day(row.get("CONDITION_EXPIRY_DATE")),
        "status": _clean(row.get("STATUSDESC")),
        "final": day(row.get("FINALDATE")),
        "url": _clean(row.get("APPLICATION_URL")),
    }


def area_of(n: dict, areas) -> str | None:
    """Leaside, Bennington Heights, or not ours."""
    if n["postal"] and n["postal"] != FSA:
        return None
    by_street = areas.match_text(n["street"]) if n["street"] else None
    if by_street == "bennington":
        return "bennington"
    if n["postal"] == FSA:
        return "leaside"
    if n["ward"] in WARDS and by_street == "leaside":
        return "leaside"
    return None


def rows_to_items(rows: list[dict], source, areas) -> list[dict]:
    """Our rows as items, one per file number. A later row for the same file wins,
    so pass active applications first and closed ones after: closing comes later."""
    by_ref: dict[str, dict] = {}
    for row in rows:
        n = normalise(row)
        area = area_of(n, areas)
        if area not in OURS:
            continue
        key = n["ref"] or f"sys:{_clean(row.get('SYS_ID'))}"
        raw = {k: v for k, v in row.items() if k != "_id"}
        by_ref[key] = {
            "source_id": source.id,
            "category": source.category,
            "external_id": key,
            "title": f"{n['address'] or 'No address'}: {n['kind'] or 'application'}",
            "summary": n["description"],
            "published_at": n["hearing"] or n["received"],
            "url": n["url"],
            "area": area,
            "raw": raw,
        }
    return list(by_ref.values())


def _search(http, resource_id: str, filters: dict, **kw) -> list[dict]:
    resp = http.get(f"{ckan.API}/datastore_search",
                    params={"id": resource_id, "filters": json.dumps(filters), "limit": 32000}, **kw)
    resp.raise_for_status()
    return resp.json()["result"]["records"]


def fetch(source, http, areas) -> tuple[list[dict], int]:
    kw = dict(timeout=source.timeout, retries=source.retries)
    package = ckan.package_show(http, source.dataset or DATASET, **kw)
    resources = package.get("resources", [])
    active = [r for r in resources if r.get("datastore_active") and r["name"].strip() == "Active Applications"]
    yearly = sorted((r for r in resources if r.get("datastore_active")
                     and re.fullmatch(r"Closed Applications \d{4}", r["name"].strip())),
                    key=lambda r: r["name"])
    recent = [r for r in resources if r["name"].strip().lower() == "closed applications since 2017.csv"]
    rows: list[dict] = []
    for r in active:
        rows += _search(http, r["id"], {"WARD": WARDS}, **kw)
    n_active = len(rows)
    for r in yearly:
        rows += _search(http, r["id"], {"WARD": WARDS}, **kw)
    n_yearly = len(rows) - n_active
    status = 200
    for r in recent:
        resp = http.get(r["url"], **kw)
        resp.raise_for_status()
        status = resp.status_code
        text = resp.content.decode("utf-8-sig", errors="replace")
        for row in csv.DictReader(io.StringIO(text, newline="")):
            ward = (row.get("WARD_NUMBER") or "").strip().lstrip("0")
            if ward in WARDS or (row.get("POSTAL") or "").strip().upper().startswith(FSA):
                rows.append(row)
    # Active rows came first, so a closed record of the same file replaces them.
    items = rows_to_items(rows, source, areas)
    print(f"        {n_active} active and {n_yearly} closed-by-year rows in Don Valley West, "
          f"{len(rows) - n_active - n_yearly} from the 2017-on file; "
          f"{len(items)} files in Leaside and Bennington")
    return items, status
