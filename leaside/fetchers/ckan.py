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
import re

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


# ---------------------------------------------------------------- shared helpers
# The two sources below are big tables - every active building permit in the city,
# every restaurant inspection - so the filter has to run on the City's side. The
# datastore accepts SQL. When it refuses (the feature is switchable), the fallback
# pages through the whole table and filters here, slower but no less correct.

PAGE = 32000   # the City's datastore caps a single page at this
MAX_SCAN = 400_000


def datastore_fields(http, resource_id: str, **kw) -> list[str]:
    """Column names, from the datastore itself, before any row is read."""
    resp = http.get(f"{API}/datastore_search", params={"id": resource_id, "limit": 0}, **kw)
    resp.raise_for_status()
    return [f["id"] for f in resp.json()["result"].get("fields", [])]


def datastore_sql(http, sql: str, **kw) -> list[dict] | None:
    """Rows for a SQL query, or None when the datastore will not run SQL."""
    resp = http.get(f"{API}/datastore_search_sql", params={"sql": sql}, **kw)
    if resp.status_code in (403, 404, 409, 500):
        print(f"        SQL refused (HTTP {resp.status_code}); scanning the table instead")
        return None
    resp.raise_for_status()
    body = resp.json()
    if not body.get("success"):
        print("        SQL refused; scanning the table instead")
        return None
    return body["result"]["records"]


def scan_rows(http, resource_id: str, keep, limit: int = MAX_SCAN, **kw) -> list[dict]:
    """Page through a resource newest-first, keeping rows that pass `keep`."""
    out, offset = [], 0
    while offset < limit:
        result = datastore_search(http, resource_id, limit=PAGE, offset=offset, **kw)
        rows = result.get("records", [])
        out += [r for r in rows if keep(r)]
        if len(rows) < PAGE:
            break
        offset += len(rows)
    return out


def pick_resource(package: dict, prefer: str | None = None) -> dict:
    resources = datastore_resources(package)
    if not resources:
        raise RuntimeError(f"dataset '{package.get('name')}' has no datastore-backed resource")
    if prefer:
        for r in resources:
            if prefer.lower() in (r.get("name") or "").lower():
                return r
    return resources[0]


def column(names: list[str], **spec) -> str | None:
    """Resolve a role to a column name using the same matcher the rows use."""
    key, _ = fields.pick({n: n for n in names}, **spec)
    return key


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _money(value) -> str | None:
    try:
        n = float(str(value).replace(",", "").replace("$", ""))
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    if n >= 1_000_000:
        return f"${n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"${n / 1_000:.0f}K"
    return f"${n:.0f}"


def _day(value) -> str | None:
    from .. import dates
    dt = dates.parse(value)
    return f"{dt.day} {dt:%b %Y}" if dt else None


# ---------------------------------------------------------------- building permits

P_POSTAL = dict(exact=("POSTAL", "POSTAL_CODE"), contains=("postal",), exclude=())
P_NUM = dict(exact=("STREET_NUM", "STREET_NUMBER", "ST_NUM", "HOUSE_NUMBER"),
             contains=("street_num", "st_num", "house_num"), exclude=("permit",))
P_STREET = dict(exact=("STREET_NAME", "ST_NAME"),
                contains=("street_name", "st_name", "stname"), exclude=())
P_STYPE = dict(exact=("STREET_TYPE", "ST_TYPE"), contains=("street_type", "st_type", "suffix"),
               exclude=())
P_SDIR = dict(exact=("STREET_DIRECTION", "STREET_DIR"), contains=("street_dir", "direction"),
              exclude=())
P_DESC = dict(exact=("DESCRIPTION",), contains=("description", "desc"), exclude=("work",))
P_WORK = dict(exact=("WORK", "WORK_TYPE"), contains=("work",), exclude=("description",))
P_PTYPE = dict(exact=("PERMIT_TYPE",), contains=("permit_type",), exclude=())
P_STRUCT = dict(exact=("STRUCTURE_TYPE",), contains=("structure",), exclude=())
P_STATUS = dict(exact=("STATUS",), contains=("status",), exclude=())
P_COST = dict(exact=("EST_CONST_COST", "ESTIMATED_COST", "CONSTRUCTION_VALUE"),
              contains=("cost", "value"), exclude=("date",))
P_APPLIED = dict(exact=("APPLICATION_DATE", "APPLIED_DATE"),
                 contains=("application_date", "applied", "app_date"), exclude=())
P_ISSUED = dict(exact=("ISSUED_DATE",), contains=("issued", "issue_date"), exclude=())
P_COMPLETED = dict(exact=("COMPLETED_DATE",), contains=("completed", "close"), exclude=())
P_PERMIT = dict(exact=("PERMIT_NUM", "PERMIT_NO", "PERMIT_NUMBER"),
                contains=("permit_num", "permit_no"), exclude=("type",))
P_REV = dict(exact=("REVISION_NUM",), contains=("revision",), exclude=())
P_UNITS_UP = dict(exact=("DWELLING_UNITS_CREATED",), contains=("units_created",), exclude=())
P_UNITS_DOWN = dict(exact=("DWELLING_UNITS_LOST",), contains=("units_lost",), exclude=())
P_USE_NOW = dict(exact=("CURRENT_USE",), contains=("current_use",), exclude=())
P_USE_NEXT = dict(exact=("PROPOSED_USE",), contains=("proposed_use",), exclude=())

PERMIT_ROLES = {"postal": P_POSTAL, "num": P_NUM, "street": P_STREET, "stype": P_STYPE,
                "desc": P_DESC, "work": P_WORK, "status": P_STATUS, "cost": P_COST,
                "applied": P_APPLIED, "issued": P_ISSUED, "permit": P_PERMIT}


def permit_address(row: dict) -> str | None:
    parts = [fields.pick(row, **spec)[1] for spec in (P_NUM, P_STREET, P_STYPE, P_SDIR)]
    text = " ".join(p for p in parts if p and p.lower() != "none").strip()
    return _clean(text.title()) if text else None


def describe_permit(row: dict) -> tuple[str, str | None]:
    work = _clean(fields.pick(row, **P_WORK)[1])
    ptype = _clean(fields.pick(row, **P_PTYPE)[1])
    structure = _clean(fields.pick(row, **P_STRUCT)[1])
    addr = permit_address(row) or "address not given"
    head = work or ptype or "Building permit"
    title = f"{head.capitalize() if head.isupper() else head}: {addr}"

    desc = _clean(fields.pick(row, **P_DESC)[1])
    status = _clean(fields.pick(row, **P_STATUS)[1])
    cost = _money(fields.pick(row, **P_COST)[1])
    applied = _day(fields.pick(row, **P_APPLIED)[1])
    issued = _day(fields.pick(row, **P_ISSUED)[1])
    completed = _day(fields.pick(row, **P_COMPLETED)[1])
    up = _clean(fields.pick(row, **P_UNITS_UP)[1])
    down = _clean(fields.pick(row, **P_UNITS_DOWN)[1])
    use_now = _clean(fields.pick(row, **P_USE_NOW)[1])
    use_next = _clean(fields.pick(row, **P_USE_NEXT)[1])
    units = None
    try:
        if up and float(up) > 0:
            units = f"{int(float(up))} new unit{'s' if float(up) != 1 else ''}"
        if down and float(down) > 0:
            units = (units + ", " if units else "") + f"{int(float(down))} lost"
    except ValueError:
        pass
    bits = [desc,
            f"Estimated {cost}" if cost else None,
            units,
            f"{use_now} → {use_next}" if use_now and use_next and use_now != use_next else None,
            structure if structure and structure.lower() not in title.lower() else None,
            ptype if ptype and ptype.lower() not in title.lower() else None,
            f"Status: {status}" if status else None,
            f"Applied {applied}" if applied else None,
            f"Issued {issued}" if issued else None,
            f"Completed {completed}" if completed else None,
            f"Permit {fields.pick(row, **P_PERMIT)[1]}" if fields.pick(row, **P_PERMIT)[1] else None]
    return title, " · ".join(b for b in bits if b) or None


def permit_rows_to_items(rows: list[dict], source, areas, stats: dict | None = None) -> list[dict]:
    tally = stats if stats is not None else {}
    for key in ("rows", "outside_areas", "kept"):
        tally.setdefault(key, 0)
    items, seen = [], set()
    for row in rows:
        tally["rows"] += 1
        addr = permit_address(row)
        _, postal = fields.pick(row, **P_POSTAL)
        area = areas.match_text(addr) or areas.match_postal(postal)
        if not area:
            tally["outside_areas"] += 1
            continue
        _, permit = fields.pick(row, **P_PERMIT)
        key = f"permit:{permit}" if permit else f"composite:{addr}|{fields.pick(row, **P_APPLIED)[1]}"
        if key in seen:                       # one row per revision; keep the newest
            continue
        seen.add(key)
        tally["kept"] += 1
        title, summary = describe_permit(row)
        _, applied = fields.pick(row, **P_APPLIED)
        _, issued = fields.pick(row, **P_ISSUED)
        # The newest milestone is the news: an application shows up when filed and
        # climbs the page again when the permit is issued.
        when = max((d for d in (applied, issued) if d), default=None, key=lambda d: str(d))
        items.append({
            "source_id": source.id, "category": source.category, "title": title,
            "url": None, "summary": summary, "published_at": when, "external_id": key,
            "area": area, "lat": None, "lon": None, "raw": row,
        })
    return items


def fetch_permits(source, http, areas) -> tuple[list[dict], int]:
    kw = dict(timeout=source.timeout, retries=source.retries)
    package = package_show(http, source.dataset, **kw)
    resource = pick_resource(package, source.extra.get("resource_match"))
    names = datastore_fields(http, resource["id"], **kw)
    cols = {role: column(names, **spec) for role, spec in PERMIT_ROLES.items()}
    print("        columns: " + ", ".join(f"{k}={v}" for k, v in cols.items()))
    fsas = sorted({f.upper() for feat in areas.features for f in feat["properties"].get("fsa", [])})
    rows = None
    if cols["postal"] and fsas:
        where = " OR ".join(f"UPPER({_q(cols['postal'])}) LIKE '{f}%'" for f in fsas)
        sql = (f"SELECT * FROM {_q(resource['id'])} WHERE {where} "
               f"ORDER BY _id DESC LIMIT 20000")
        rows = datastore_sql(http, sql, **kw)
    if rows is None:
        def keep(r):
            _, postal = fields.pick(r, **P_POSTAL)
            return bool(areas.match_postal(postal) or areas.match_text(permit_address(r)))
        rows = scan_rows(http, resource["id"], keep, **kw)
    stats: dict = {}
    items = permit_rows_to_items(rows, source, areas, stats=stats)
    print(f"        {stats['rows']} rows for your postal areas, {stats['kept']} permits kept")
    return items, 200


# ---------------------------------------------------------------- DineSafe

D_EST_ID = dict(exact=("Establishment ID", "ESTABLISHMENT_ID", "establishment_id"),
                contains=("establishment id", "establishment_id", "establishmentid"), exclude=())
D_INSP_ID = dict(exact=("Inspection ID", "INSPECTION_ID", "inspection_id"),
                 contains=("inspection id", "inspection_id", "inspectionid"), exclude=())
D_NAME = dict(exact=("Establishment Name", "ESTABLISHMENT_NAME"),
              contains=("establishment name", "establishment_name", "name"), exclude=("type",))
D_TYPE = dict(exact=("Establishment Type", "ESTABLISHMENT_TYPE"),
              contains=("establishment type", "establishment_type"), exclude=())
D_ADDR = dict(exact=("Establishment Address", "ESTABLISHMENT_ADDRESS"),
              contains=("address",), exclude=())
D_STATUS = dict(exact=("Establishment Status", "ESTABLISHMENT_STATUS"),
                contains=("status",), exclude=())
D_DETAIL = dict(exact=("Infraction Details", "INFRACTION_DETAILS"),
                contains=("infraction", "details"), exclude=())
D_DATE = dict(exact=("Inspection Date", "INSPECTION_DATE"),
              contains=("inspection date", "inspection_date", "date"), exclude=())
D_SEV = dict(exact=("Severity", "SEVERITY"), contains=("severity",), exclude=())
D_ACTION = dict(exact=("Action", "ACTION"), contains=("action",), exclude=())
D_OUTCOME = dict(exact=("Outcome", "OUTCOME"), contains=("outcome",), exclude=())
D_FINE = dict(exact=("Amount Fined", "AMOUNT_FINED"), contains=("fined", "fine"), exclude=())
D_LAT = dict(exact=("Latitude", "LATITUDE", "lat"), contains=("latitude", "lat"),
             exclude=("relat",))
D_LON = dict(exact=("Longitude", "LONGITUDE", "lon"), contains=("longitude", "long", "lon"),
             exclude=())

DINESAFE_ROLES = {"inspection": D_INSP_ID, "name": D_NAME, "address": D_ADDR,
                  "status": D_STATUS, "date": D_DATE, "severity": D_SEV, "lat": D_LAT,
                  "lon": D_LON}


def _dine_coords(row):
    _, lat = fields.pick(row, **D_LAT)
    _, lon = fields.pick(row, **D_LON)
    try:
        return (float(lat), float(lon)) if lat and lon else (None, None)
    except ValueError:
        return None, None


def group_inspections(rows: list[dict]) -> dict[str, list[dict]]:
    """One row per infraction; one item per inspection."""
    groups: dict[str, list[dict]] = {}
    for row in rows:
        _, iid = fields.pick(row, **D_INSP_ID)
        if not iid:
            _, est = fields.pick(row, **D_EST_ID)
            _, when = fields.pick(row, **D_DATE)
            iid = f"{est}|{when}"
        groups.setdefault(str(iid), []).append(row)
    return groups


def describe_inspection(rows: list[dict]) -> tuple[str, str | None, bool]:
    """Headline, detail, and whether this is worth a reader's time.

    A clean pass is the normal outcome and would bury everything else, so only an
    inspection with a conditional pass, a closure, or at least one infraction is
    kept. The rest stay in the City's dataset, where anyone can look them up.
    """
    first = rows[0]
    name = _clean(fields.pick(first, **D_NAME)[1]) or "Unnamed establishment"
    status = _clean(fields.pick(first, **D_STATUS)[1]) or "Inspected"
    kind = _clean(fields.pick(first, **D_TYPE)[1])
    addr = _clean(fields.pick(first, **D_ADDR)[1])
    infractions = [r for r in rows if _clean(fields.pick(r, **D_DETAIL)[1])]
    by_sev: dict[str, int] = {}
    for r in infractions:
        sev = _clean(fields.pick(r, **D_SEV)[1]) or "unspecified"
        sev = re.sub(r"^[A-Z]\s*-\s*", "", sev)     # "S - Significant" -> "Significant"
        by_sev[sev] = by_sev.get(sev, 0) + 1
    n = len(infractions)
    notable = status.lower() != "pass" or n > 0
    if status.lower() == "pass" and n:
        head = f"Pass with {n} infraction{'s' if n != 1 else ''}"
    else:
        head = status
    title = f"{head}: {name}"
    sev_text = ", ".join(f"{c} {s.lower()}" for s, c in sorted(by_sev.items(), key=lambda x: -x[1]))
    actions = sorted({_clean(fields.pick(r, **D_ACTION)[1]) for r in rows} - {None})
    fines = [_money(fields.pick(r, **D_FINE)[1]) for r in rows]
    fines = [f for f in fines if f]
    details = [_clean(fields.pick(r, **D_DETAIL)[1]) for r in infractions][:4]
    bits = [addr, kind,
            f"Infractions: {sev_text}" if sev_text else None,
            "; ".join(d for d in details if d) if details else None,
            "Action: " + ", ".join(actions) if actions and actions != ["Notice to Comply"] else None,
            "Fined " + ", ".join(fines) if fines else None]
    return title, " · ".join(b for b in bits if b) or None, notable


def inspection_rows_to_items(rows: list[dict], source, areas, stats: dict | None = None) -> list[dict]:
    tally = stats if stats is not None else {}
    for key in ("rows", "inspections", "outside_areas", "routine", "kept"):
        tally.setdefault(key, 0)
    tally["rows"] = len(rows)
    items = []
    for iid, group in group_inspections(rows).items():
        tally["inspections"] += 1
        first = group[0]
        lat, lon = _dine_coords(first)
        _, addr = fields.pick(first, **D_ADDR)
        area = areas.match_point(lat, lon) or areas.match_text(addr)
        if not area:
            tally["outside_areas"] += 1
            continue
        title, summary, notable = describe_inspection(group)
        if not notable:
            tally["routine"] += 1
            continue
        tally["kept"] += 1
        _, when = fields.pick(first, **D_DATE)
        items.append({
            "source_id": source.id, "category": source.category, "title": title,
            "url": None, "summary": summary, "published_at": when,
            "external_id": f"inspection:{iid}", "area": area, "lat": lat, "lon": lon,
            "raw": first,
        })
    return items


def fetch_dinesafe(source, http, areas) -> tuple[list[dict], int]:
    kw = dict(timeout=source.timeout, retries=source.retries)
    package = package_show(http, source.dataset, **kw)
    resource = pick_resource(package, source.extra.get("resource_match"))
    names = datastore_fields(http, resource["id"], **kw)
    cols = {role: column(names, **spec) for role, spec in DINESAFE_ROLES.items()}
    print("        columns: " + ", ".join(f"{k}={v}" for k, v in cols.items()))
    rows = None
    if cols["lat"] and cols["lon"]:
        minx, miny, maxx, maxy = arcgis.bbox_of(areas)
        sql = (f"SELECT * FROM {_q(resource['id'])} "
               f"WHERE CAST({_q(cols['lat'])} AS DOUBLE PRECISION) BETWEEN {miny} AND {maxy} "
               f"AND CAST({_q(cols['lon'])} AS DOUBLE PRECISION) BETWEEN {minx} AND {maxx} "
               f"ORDER BY _id DESC LIMIT 20000")
        rows = datastore_sql(http, sql, **kw)
    if rows is None:
        def keep(r):
            lat, lon = _dine_coords(r)
            return bool(areas.match_point(lat, lon)
                        or areas.match_text(fields.pick(r, **D_ADDR)[1]))
        rows = scan_rows(http, resource["id"], keep, **kw)
    stats: dict = {}
    items = inspection_rows_to_items(rows, source, areas, stats=stats)
    print(f"        {stats['rows']} rows, {stats['inspections']} inspections in your areas, "
          f"{stats['routine']} clean passes left out, {stats['kept']} kept")
    return items, 200
