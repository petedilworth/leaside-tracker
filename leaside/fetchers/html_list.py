"""Last resort: pull anchor text off a page that has no feed."""
from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup


def parse(html: str, source, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    selector = source.selector or "article a, h2 a, h3 a"
    seen, items = set(), []
    for a in soup.select(selector):
        title = a.get_text(strip=True)
        href = a.get("href")
        if not title or not href or len(title) < 8:
            continue
        url = urljoin(base_url, href)
        if url in seen:
            continue
        seen.add(url)
        items.append(
            {
                "source_id": source.id,
                "category": source.category,
                "title": title,
                "url": url,
                "summary": None,
                "published_at": None,
                "external_id": url,
            }
        )
    return items


def fetch(source, http, areas) -> tuple[list[dict], int]:
    url = source.url or source.fallback_html
    resp = http.get(url, timeout=source.timeout, retries=source.retries)
    resp.raise_for_status()
    return parse(resp.text, source, url), resp.status_code
