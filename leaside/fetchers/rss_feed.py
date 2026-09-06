"""RSS and Atom feeds: residents' associations, Leaside Life, police releases."""
from __future__ import annotations

from datetime import datetime, timezone

import feedparser


def _to_iso(entry) -> str | None:
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            return datetime(*parsed[:6], tzinfo=timezone.utc).isoformat(timespec="seconds")
    return None


def parse(text: str, source) -> list[dict]:
    feed = feedparser.parse(text)
    items = []
    for e in feed.entries:
        title = (e.get("title") or "").strip()
        if not title:
            continue
        summary = (e.get("summary") or "").strip()
        items.append(
            {
                "source_id": source.id,
                "category": source.category,
                "title": title,
                "url": e.get("link"),
                "summary": summary[:1500],
                "published_at": _to_iso(e),
                "external_id": e.get("id") or e.get("link"),
                "area": source.area,
            }
        )
    return items


def fetch(source, http, areas) -> tuple[list[dict], int]:
    resp = http.get(source.url, timeout=source.timeout, retries=source.retries)
    resp.raise_for_status()
    items = parse(resp.text, source)
    for it in items:
        if not it.get("area"):
            it["area"] = areas.match_text(it["title"], it.get("summary"))
    return items, resp.status_code
