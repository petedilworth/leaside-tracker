"""City Clerk public notices: https://secure.toronto.ca/nm/notices.json

The single most useful municipal feed for this project. It carries Committee of
Adjustment hearing notices, road closures and public meetings, published in real time.

The field names below are best guesses drawn from the City's documentation page. The
parser is deliberately tolerant: it looks for the first plausible key in each group and
keeps the whole record in `raw` so nothing is lost when the guess is wrong.
"""
from __future__ import annotations

import json

TITLE_KEYS = ("noticeTitle", "title", "subject", "name")
URL_KEYS = ("noticeUrl", "url", "link", "detailUrl")
DATE_KEYS = ("publicationDate", "publishedDate", "postedDate", "date", "startDate")
BODY_KEYS = ("description", "noticeDescription", "summary", "body", "text")
ID_KEYS = ("noticeId", "id", "referenceNumber")


def _first(record: dict, keys) -> str | None:
    for k in keys:
        v = record.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, (int, float)):
            return str(v)
    return None


def _records(payload):
    """The endpoint may return a bare list or wrap it in one key. Handle both."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for value in payload.values():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return value
    return []


def parse(text: str, source) -> list[dict]:
    payload = json.loads(text)
    items = []
    for rec in _records(payload):
        title = _first(rec, TITLE_KEYS)
        if not title:
            continue
        items.append(
            {
                "source_id": source.id,
                "category": source.category,
                "title": title,
                "url": _first(rec, URL_KEYS),
                "summary": (_first(rec, BODY_KEYS) or "")[:1500] or None,
                "published_at": _first(rec, DATE_KEYS),
                "external_id": _first(rec, ID_KEYS) or title,
                "raw": rec,
            }
        )
    return items


def fetch(source, http, areas) -> tuple[list[dict], int]:
    resp = http.get(source.url)
    resp.raise_for_status()
    items = parse(resp.text, source)
    kept = []
    for it in items:
        blob = json.dumps(it.get("raw", {}), default=str)
        area = areas.match_text(it["title"], it.get("summary"), blob)
        if area:
            it["area"] = area
            kept.append(it)
    return kept, resp.status_code
