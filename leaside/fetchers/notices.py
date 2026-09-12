"""City Clerk public notices: https://secure.toronto.ca/nm/notices.json

The single most useful municipal feed for this project. It carries Committee of
Adjustment hearing notices, road closures and public meetings, published in real time.

Field names are matched, not guessed - see leaside/fields.py. The first version
guessed, and the title guess happened to land while the date and link guesses did
not, which put 136 undated, unlinked notices on the page without any error.
"""
from __future__ import annotations

import json
from urllib.parse import urljoin

from .. import fields

BASE = "https://secure.toronto.ca/nm/"
# The feed carries no link field at all. The public detail page is built from the
# notice id; this pattern is confirmed against pages the City has published.
DETAIL = "https://secure.toronto.ca/nm/api/individual/notice/{}.do"

TITLE = dict(exact=("noticeTitle", "title", "subject"),
             contains=("title", "subject", "heading"), exclude=("file", "type", "sub"))
URL = dict(exact=("noticeUrl", "url", "link", "detailUrl", "href"),
           contains=("url", "link", "href", "path"),
           exclude=("image", "img", "icon", "logo", "attach"), accept=fields.looks_like_url)
DATE = dict(exact=("publicationDate", "publishedDate", "publishDate", "postedDate"),
            contains=("publish", "posted", "created", "issued", "start", "date"),
            exclude=("end", "expir", "modif", "updat", "close", "deadline"))
BODY = dict(exact=("description", "noticeDescription", "summary"),
            contains=("description", "summary", "body", "content", "text", "detail"),
            exclude=("short", "meta"))
ID = dict(exact=("noticeId", "id", "referenceNumber", "noticeNumber"),
          contains=("noticeid", "_id", "number"), exclude=("phone", "file"))


def _records(payload):
    """The endpoint may return a bare list or wrap it in one key. Handle both."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for value in payload.values():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return value
    return []


def _coords(rec: dict):
    """Notices carry an address list with coordinates. Use them, not keyword guessing."""
    for entry in rec.get("addressList") or []:
        if not isinstance(entry, dict):
            continue
        _, lat = fields.pick(entry, contains=("latitude",), exclude=())
        _, lon = fields.pick(entry, contains=("longitude",), exclude=())
        try:
            if lat and lon:
                return float(lat), float(lon)
        except ValueError:
            continue
    return None, None


def parse(text: str, source) -> list[dict]:
    payload = json.loads(text)
    items = []
    for rec in _records(payload):
        _, title = fields.pick(rec, **TITLE)
        if not title:
            continue
        _, url = fields.pick(rec, **URL)
        if url and url.startswith("/"):
            url = urljoin(BASE, url)
        _, when = fields.pick(rec, **DATE)
        _, body = fields.pick(rec, **BODY)
        _, ext = fields.pick(rec, **ID)
        notice_id = rec.get("noticeId") or ext
        if not url and notice_id:
            url = DETAIL.format(notice_id)
        lat, lon = _coords(rec)
        items.append(
            {
                "source_id": source.id,
                "category": source.category,
                "title": title,
                "url": url,
                "summary": (body or "")[:1500] or None,
                "published_at": when,
                "external_id": ext or url or title,
                "lat": lat,
                "lon": lon,
                "raw": rec,
            }
        )
    return items


def field_report(text: str) -> dict:
    """Which key each field resolved to, on the first record. Printed by ingest."""
    recs = _records(json.loads(text))
    if not recs:
        return {}
    rec = recs[0]
    return {
        name: fields.pick(rec, **spec)[0]
        for name, spec in (("title", TITLE), ("url", URL), ("date", DATE),
                           ("body", BODY), ("id", ID))
    }


def fetch(source, http, areas) -> tuple[list[dict], int]:
    resp = http.get(source.url, timeout=source.timeout, retries=source.retries)
    resp.raise_for_status()
    resolved = field_report(resp.text)
    missing = [k for k, v in resolved.items() if v is None]
    print(f"        fields: " + ", ".join(f"{k}={v}" for k, v in resolved.items()))
    if missing:
        print(f"        WARNING: could not find {', '.join(missing)} - see health report")
    items = parse(resp.text, source)
    kept = []
    for it in items:
        # Coordinates first; only fall back to reading street names out of the text.
        area = areas.match_point(it.get("lat"), it.get("lon"))
        if not area:
            blob = json.dumps(it.get("raw", {}), default=str)
            area = areas.match_text(it["title"], it.get("summary"), blob)
        if area:
            it["area"] = area
            kept.append(it)
    located = sum(1 for it in kept if it.get("lat"))
    print(f"        kept {len(kept)} of {len(items)} notices, {located} placed by coordinates")
    return kept, resp.status_code
