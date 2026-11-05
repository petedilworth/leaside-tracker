"""The topic tabs: building permits, restaurant inspections, Committee of Adjustment.

Each has its own page, built from one template (templates/topic.html). The
page draws everything in the browser from a list of rows, so the cards, the
list and the year table follow the same filters. A row:

    t    the date that orders it, YYYY-MM-DD
    c    its group, an index into the page's groups
    a    our area key
    h    headline;  s  one line under it;  x  longer text
    f    [[label, value], ...] details, shown when opened
    g    small tags, e.g. "Appealed"
    lat, lon, u   map point and link, when the record has them

These records are kept in the log and the downloads as before; they are left
out of the News list because each has a page of its own.
"""
from __future__ import annotations

import json
import re

from . import db, mapdata
from .fetchers import ckan, coa

TOPIC_CATEGORIES = ("permit", "inspection", "coa", "police_call")
CLIP = 320


def _rows(conn, category: str):
    for r in conn.execute(
            f"SELECT * FROM items WHERE category = ? AND {db.SHOWN}"
            " ORDER BY COALESCE(published_at, first_seen_at) DESC", (category,)):
        try:
            raw = json.loads(r["raw"]) if r["raw"] else {}
        except ValueError:
            raw = {}
        yield r, raw


def _clip(text, n: int = CLIP) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text if len(text) <= n else text[: n - 1].rsplit(" ", 1)[0] + "…"


def _fields(*pairs) -> list[list[str]]:
    return [[k, str(v)] for k, v in pairs if v not in (None, "", "None", " ")]


def _base(key, title, areas, groups, rows, **extra) -> dict:
    rows.sort(key=lambda r: r["t"] or "", reverse=True)
    used = {r["a"] for r in rows}
    return {
        "key": key, "title": title, "groups": groups, "rows": rows,
        "areas": [{"key": k, "name": areas.name(k)} for k in areas.keys() if k in used],
        "first": min((r["t"] for r in rows if r["t"]), default=None),
        "generated": db.utcnow(), **extra,
    }


# ---------------------------------------------------------------- permits

PERMIT_GROUPS = ["New buildings", "Demolitions", "Additions and renovations",
                 "Plumbing, heating and drains", "Other"]


def permit_group(raw: dict) -> int:
    kind = str(raw.get("PERMIT_TYPE") or "").lower()
    work = str(raw.get("WORK") or "").lower()
    if "new house" in kind or kind == "new building" or work.startswith("new building"):
        return 0
    if "demolition" in kind or work.startswith("demolition"):
        return 1
    if any(k in kind for k in ("small residential", "additions/alterations", "residential building",
                               "non-residential building", "multiple use")):
        return 2
    if any(k in kind for k in ("plumbing", "mechanical", "drain")):
        return 3
    return 4


def _money(value) -> str | None:
    try:
        n = float(str(value).replace(",", "").replace("$", ""))
    except ValueError:
        return None
    return f"${n:,.0f}" if n > 0 else None


def permits(conn, areas) -> dict:
    rows = []
    for r, raw in _rows(conn, "permit"):
        address = ckan.permit_address(raw) or r["title"].split(": ", 1)[-1]
        use_from, use_to = raw.get("CURRENT_USE"), raw.get("PROPOSED_USE")
        uses = (f"{use_from} to {use_to}" if use_from and use_to and use_from != use_to
                else use_to or use_from)
        units = ", ".join(x for x in (
            f"{raw['DWELLING_UNITS_CREATED']} created" if raw.get("DWELLING_UNITS_CREATED") else "",
            f"{raw['DWELLING_UNITS_LOST']} lost" if raw.get("DWELLING_UNITS_LOST") else "") if x)
        num = " ".join(x for x in (raw.get("PERMIT_NUM"), f"rev {raw['REVISION_NUM']}"
                                   if raw.get("REVISION_NUM") not in (None, "", "00") else "") if x)
        rows.append({
            "t": (r["published_at"] or r["first_seen_at"] or "")[:10],
            "c": permit_group(raw), "a": r["area"],
            "h": address, "s": " · ".join(x for x in (str(raw.get("WORK") or "").strip(),
                                                    str(raw.get("STATUS") or "").strip()) if x),
            "x": _clip(raw.get("DESCRIPTION") or r["summary"]),
            "f": _fields(("Permit", num), ("Type", raw.get("PERMIT_TYPE")),
                         ("Building", raw.get("STRUCTURE_TYPE")), ("Use", uses), ("Units", units),
                         ("Applied", raw.get("APPLICATION_DATE")), ("Issued", raw.get("ISSUED_DATE")),
                         ("Completed", raw.get("COMPLETED_DATE")), ("Builder", raw.get("BUILDER_NAME")),
                         ("Estimated cost", _money(raw.get("EST_CONST_COST")))),
        })
    return _base("permits", "Building permits", areas, PERMIT_GROUPS, rows,
                 hero="permits issued in the last 30 days", card_days=30, since=90,
                 intro="Building permits the City issued or is reviewing, newest first.",
                 caveat="Dated by the day the permit was issued, or applied for if not yet issued. "
                        "One project often has several permits: the building, then plumbing, "
                        "heating and drains.",
                 search="Address, builder or permit number")


# ---------------------------------------------------------------- restaurants

INSPECTION_GROUPS = ["Pass", "Conditional pass", "Closed"]


def inspections(conn, areas) -> dict:
    rows, crucial = [], 0
    for r, raw in _rows(conn, "inspection"):
        status = str(raw.get("inspectionStatus") or "").lower()
        group = 2 if "closed" in status else 1 if "conditional" in status else 0
        parts = (r["summary"] or "").split(" · ")
        address = raw.get("address") or (parts[0] if parts else "")
        found = " · ".join(parts[1:])
        name = raw.get("estName") or r["title"].split(": ", 1)[-1]
        tags = []
        if "crucial" in found.lower():
            tags.append("Crucial infraction")
        rows.append({
            "t": (r["published_at"] or r["first_seen_at"] or "")[:10],
            "c": group, "a": r["area"],
            "h": " ".join(w.capitalize() if w.isupper() else w for w in str(name).split()),
            "s": address, "x": _clip(found or "No infractions recorded.", 600), "g": tags,
            "f": _fields(("Result", raw.get("inspectionStatus")), ("Inspected", raw.get("inspectionDate")),
                         ("Fine", _money(raw.get("amountFined"))),
                         ("Court outcome", raw.get("OutcomeDesc") if raw.get("OutcomeDesc") != "None" else None)),
            "lat": None if r["lat"] is None else round(r["lat"], 5),
            "lon": None if r["lon"] is None else round(r["lon"], 5),
        })
    return _base("restaurants", "Restaurant inspections", areas, INSPECTION_GROUPS, rows,
                 hero="inspections in the last 30 days", card_days=30, since=90,
                 intro="Toronto Public Health food safety inspections (DineSafe), newest first.",
                 caveat="A conditional pass means the inspector found a significant or crucial "
                        "problem and will come back. A closure means the place had to shut until "
                        "it was fixed.",
                 search="Restaurant or street", near=True)


# ---------------------------------------------------------------- Committee of Adjustment

COA_GROUPS = ["Waiting for a decision", "Approved", "Partly approved", "Refused", "Deferred",
              "Withdrawn or cancelled", "No decision recorded"]


def coa_outcome(n: dict) -> int:
    d, s = (n["decision"] or "").lower(), (n["status"] or "").lower()
    if "withdr" in d or "withdr" in s or s == "cancelled":
        return 5
    if "partial" in d:
        return 2
    if "refus" in d or d.startswith("not "):
        return 3
    if any(w in d for w in ("approv", "grant", "conditional")):
        return 1
    if "defer" in d:
        return 4
    if not d and s not in ("closed", ""):
        return 0
    return 6


def coa_files(conn, areas) -> dict:
    rows = []
    for r, raw in _rows(conn, "coa"):
        n = coa.normalise(raw)
        outcome = coa_outcome(n)
        tribunal = n["tribunal_decision"] or ("Appealed" if "appeal" in (n["status"] or "").lower() else None)
        tags = []
        if tribunal:
            tags.append("Appealed")
        if (n["objections"] or "").lower() == "yes":
            tags.append("Objections at hearing")
        hearing = " ".join(x for x in (n["hearing"], n["time"]) if x)
        rows.append({
            "t": n["hearing"] or n["received"] or "",
            "c": outcome, "a": r["area"],
            "h": n["address"] or "No address",
            "s": " · ".join(x for x in (n["kind"], n["work_type"], n["ref"]) if x),
            "x": _clip(n["description"], 900), "g": tags,
            "f": _fields(("File", n["ref"]), ("Application", n["kind"]), ("Work", n["work_type"]),
                         ("Project", n["sub_type"]), ("Zoning", n["zoning"]),
                         ("Received", n["received"]), ("Hearing", hearing), ("Where", n["location"]),
                         ("Decision", n["decision"]), ("Objections at hearing", n["objections"]),
                         ("Appeal deadline", n["appeal_expiry"]),
                         ("Tribunal decision", tribunal), ("Tribunal date", n["tribunal_date"]),
                         ("Lots created", n["lots_created"]),
                         ("Conditions expire", n["condition_expiry"]), ("Status", n["status"]),
                         ("Closed", n["final"])),
            "u": n["url"],
        })
    decided = [r for r in rows if r["c"] in (1, 2, 3)]
    approved = sum(1 for r in decided if r["c"] in (1, 2))
    appealed = sum(1 for r in rows if "Appealed" in r["g"])
    years = sorted(r["t"][:4] for r in rows if r["t"])
    facts = []
    if decided:
        facts.append(["Approved", f"{round(100 * approved / len(decided))}%",
                      f"{approved:,} of {len(decided):,} decided since {years[0]}, fully or in part"])
    facts.append(["Appealed to a tribunal", f"{appealed:,}", "Ontario Municipal Board, then the "
                  "Toronto Local Appeal Body"])
    return _base("variances", "Committee of Adjustment", areas, COA_GROUPS, rows,
                 hero="files heard in the last 12 months", card_days=365, since=0,
                 upcoming=True, years=True, facts=facts,
                 intro="Minor variance and consent applications in Leaside and Bennington Heights, "
                       "heard by the North York panel every two weeks. Newest first, with hearings back "
                       "to January 2000.",
                 caveat="The City's open data has no owner, applicant or agent names and no "
                        "itemised list of variances. Those are only on each file's page in the "
                        "City's Application Information Centre. Search it by file number at "
                        "secure.toronto.ca/AIC.",
                 search="Street, house number or file number",
                 aic="https://secure.toronto.ca/AIC/index.do")


BUILDERS = {"permits": permits, "restaurants": inspections, "variances": coa_files}
SOURCES = {"permits": ("permit",), "restaurants": ("inspection",), "variances": ("coa",)}


def payload(data: dict) -> str:
    return mapdata.payload(data)
