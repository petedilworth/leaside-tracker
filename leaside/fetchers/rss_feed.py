"""RSS and Atom feeds: residents' associations, Leaside Life, police releases."""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse

import feedparser


def _to_iso(entry) -> str | None:
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            return datetime(*parsed[:6], tzinfo=timezone.utc).isoformat(timespec="seconds")
    return None


def _best_text(entry) -> str:
    """Feeds carry their text in several places and the short one is not always first.

    `summary` is often a one-line teaser while `content` holds the real body. Take
    whichever is longest; the stored length cap does the trimming.
    """
    candidates = [entry.get("summary") or "", entry.get("subtitle") or ""]
    for block in entry.get("content") or []:
        if isinstance(block, dict) and block.get("value"):
            candidates.append(block["value"])
    return max(candidates, key=len).strip()


def _google_news(entry, title: str) -> str:
    """"Headline (globalnews.ca)" for a Google News item.

    Google appends the outlet to every headline but spells it two ways from one
    fetch to the next - "globalnews.ca", then "Global News" - so the same story
    logged a change on every run. The outlet's web address does not vary.
    """
    src = entry.get("source") or {}
    host = urlparse(src.get("href") or "").netloc
    host = host[4:] if host.startswith("www.") else host
    if " - " in title:
        title = title.rsplit(" - ", 1)[0].strip()
    return f"{title} ({host})" if host else title


def parse(text: str, source) -> list[dict]:
    feed = feedparser.parse(text)
    items = []
    for e in feed.entries:
        title = (e.get("title") or "").strip()
        if not title:
            continue
        summary = _best_text(e)
        if "news.google." in (source.url or ""):
            title = _google_news(e, title)
            summary = None      # Google's description is the headline again, nothing more
        items.append(
            {
                "source_id": source.id,
                "category": source.category,
                "title": title,
                "url": e.get("link"),
                "summary": summary,
                "published_at": _to_iso(e),
                "external_id": e.get("id") or e.get("link"),
            }
        )
    return items


def fetch(source, http, areas) -> tuple[list[dict], int]:
    resp = http.get(source.url, timeout=source.timeout, retries=source.retries)
    resp.raise_for_status()
    return parse(resp.text, source), resp.status_code
