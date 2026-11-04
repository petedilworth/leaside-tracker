"""Toronto Police yearly counts of calls attended, by City neighbourhood.

The live map shows each call for four hours, so our own log only starts on
3 October 2026. For the long view, the police publish one number per
neighbourhood per year (Annual Statistical Report table ASR-CS-TBL-003): every
call officers attended, all types together, back to 2015. No months, no types.

The police split each neighbourhood's count by which division answered, so the
query sums those rows into one number per neighbourhood and year.

Each number is kept in the log like everything else, so a revised count shows
up as a change. The rows are marked routine: they feed the Police calls page,
not the news list or the email.
"""
from __future__ import annotations

import json

from . import arcgis

LAYER = ("https://services.arcgis.com/S9th0jAJ7bqgIRjw/arcgis/rest/services/"
         "Calls_for_Service_Attended_(ASR_CS_TBL_003)/FeatureServer/0")


def our_neighbourhoods(areas) -> list[str]:
    """The City neighbourhood names our areas sit in, in config order, once each."""
    names = [n for f in areas.features for n in f["properties"].get("official", [])]
    return list(dict.fromkeys(names))


def parse_yearly(text: str, source, areas) -> list[dict]:
    data = json.loads(text)
    if "error" in data:
        raise RuntimeError(f"police layer said: {data['error']}")
    items = []
    for feat in data.get("features", []):
        a = feat.get("attributes") or {}
        hood, year, n = a.get("NEIGHBOURHOOD_158"), a.get("EVENT_YEAR"), a.get("calls")
        if not hood or not year or n is None or not areas.is_official_ours(hood):
            continue
        year, n = int(year), int(n)
        items.append({
            "source_id": source.id,
            "category": source.category,
            "external_id": f"{hood}|{year}",
            "title": f"Police calls attended in {hood}, {year}: {n:,}",
            "summary": "Every call Toronto Police officers attended in the neighbourhood that "
                       "year, all types together.",
            "published_at": f"{year}-12-31T12:00:00+00:00",
            "url": source.home_url,
            # No area here: ingest names it from the title, the same way every
            # later refresh does, so the two never disagree.
            "raw": {"neighbourhood": hood, "year": year, "calls": n},
            "routine": True,
        })
    return items


def fetch_calls_yearly(source, http, areas) -> tuple[list[dict], int]:
    names = our_neighbourhoods(areas)
    quoted = ", ".join("'" + n.replace("'", "''") + "'" for n in names)
    params = {
        "where": f"NEIGHBOURHOOD_158 IN ({quoted})",
        "groupByFieldsForStatistics": "NEIGHBOURHOOD_158,EVENT_YEAR",
        "outStatistics": json.dumps([{"statisticType": "sum", "onStatisticField": "EVENT_COUNT",
                                      "outStatisticFieldName": "calls"}]),
        "orderByFields": "NEIGHBOURHOOD_158,EVENT_YEAR",
        "f": "json",
    }
    resp = http.get(arcgis.query_url(source.url or LAYER), params=params,
                    timeout=source.timeout, retries=source.retries)
    resp.raise_for_status()
    items = parse_yearly(resp.text, source, areas)
    years = sorted({it["raw"]["year"] for it in items})
    if years:
        print(f"        {len({it['raw']['neighbourhood'] for it in items})} neighbourhoods, "
              f"{years[0]}-{years[-1]}")
    return items, resp.status_code
