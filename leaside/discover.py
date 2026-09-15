"""Read a directory page of residents' associations and test each one for a news feed.

Written because this project's authoring environment cannot reach fontra.com, but the
machine you run it on can. It turns a page of links into a scored table plus ready-made
YAML you can paste into config/sources.yaml.
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import feedparser
from bs4 import BeautifulSoup

from . import http, sources

REPORT = Path("config/associations-report.md")

# Links that are never a residents' association's own website.
SKIP_HOSTS = {
    "facebook.com", "www.facebook.com", "twitter.com", "x.com", "instagram.com",
    "www.instagram.com", "linkedin.com", "youtube.com", "www.youtube.com",
    "toronto.ca", "www.toronto.ca", "en.wikipedia.org", "docs.google.com",
    "wordpress.org", "wordpress.com",
}
SKIP_WORDS = ("privacy", "contact us", "home", "about", "login", "sign in", "donate",
              "membership", "subscribe", "read more", "click here", "next", "previous")

FEED_PATHS = ("/feed/", "/rss/", "/feed/atom/", "/index.xml", "/blog/feed/")


def extract_links(html: str, base_url: str) -> list[tuple[str, str]]:
    """Return (name, url) for every plausible association link on a directory page."""
    soup = BeautifulSoup(html, "html.parser")
    base_host = urlparse(base_url).netloc.lower()
    found: dict[str, str] = {}

    for a in soup.select("a[href]"):
        name = " ".join(a.get_text(" ", strip=True).split())
        href = (a.get("href") or "").strip()
        if not name or not href or href.startswith(("mailto:", "tel:", "#", "javascript:")):
            continue
        if len(name) < 4 or name.lower() in SKIP_WORDS:
            continue
        url = urljoin(base_url, href)
        host = urlparse(url).netloc.lower()
        if not host or host in SKIP_HOSTS or host == base_host:
            continue
        root = f"{urlparse(url).scheme}://{host}/"
        # Keep the longest, most descriptive name seen for each site.
        if root not in found or len(name) > len(found[root]):
            found[root] = name
    return sorted((name, root) for root, name in found.items())


def slug(name: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return f"ra_{text[:40]}"


def test_feed(root: str, fetcher) -> tuple[str | None, int, str]:
    """Try the usual feed paths. Return (feed_url, entry_count, note)."""
    for path in FEED_PATHS:
        candidate = urljoin(root, path)
        try:
            resp = fetcher.get(candidate, timeout=30, retries=0)
        except Exception as exc:
            return None, 0, f"{type(exc).__name__}"
        if resp.status_code != 200:
            continue
        entries = feedparser.parse(resp.text).entries
        if entries:
            return candidate, len(entries), "ok"
    return None, 0, "no feed at any usual path"


def run(config_path="config/sources.yaml") -> Path:
    cfg = sources.load(config_path)
    fetcher = http.Fetcher(cfg.user_agent, cfg.timeout, cfg.delay)
    rows, seen = [], set()

    for directory in cfg.directories:
        print(f"Reading {directory}")
        try:
            resp = fetcher.get(directory, timeout=60, retries=2)
            resp.raise_for_status()
        except Exception as exc:
            print(f"  could not read it: {type(exc).__name__}: {exc}")
            continue
        for name, root in extract_links(resp.text, directory):
            if root in seen:
                continue
            seen.add(root)
            feed, count, note = test_feed(root, fetcher)
            rows.append({"name": name, "root": root, "feed": feed,
                         "count": count, "note": note})
            mark = f"{count} entries" if feed else note
            print(f"  {'FEED' if feed else '  - '}  {name[:45]:<45} {mark}")

    write_report(rows, cfg)
    return REPORT


def write_report(rows: list[dict], cfg) -> None:
    known = {s.url for s in cfg.sources if s.url}
    working = [r for r in rows if r["feed"]]
    new = [r for r in working if r["feed"] not in known]

    lines = [
        "# Residents' associations found",
        "",
        f"Scanned {len(cfg.directories)} directory page(s) and tested {len(rows)} websites.",
        f"**{len(working)} have a working news feed. {len(new)} of those are not yet "
        "in this project.**",
        "",
        "| Association | Website | Feed |",
        "| --- | --- | --- |",
    ]
    for r in sorted(rows, key=lambda x: (not x["feed"], x["name"].lower())):
        state = f"{r['count']} entries" if r["feed"] else r["note"]
        lines.append(f"| {r['name']} | {r['root']} | {state} |")

    if new:
        lines += [
            "",
            "## Ready to add",
            "",
            "These have working feeds and are not in the project yet. Send this whole",
            "file to Claude, who will decide which are close enough to Leaside to keep.",
            "",
            "```yaml",
        ]
        for r in new:
            lines += [
                f"  - id: {slug(r['name'])}",
                f"    name: {r['name']}",
                "    category: ra_news",
                "    area: null          # set to a neighbourhood key, or leave for keyword matching",
                "    kind: rss",
                f"    url: {r['feed']}",
                "    status: verified",
                f"    notes: Found via directory scan. Feed returned {r['count']} entries.",
                "",
            ]
        lines.append("```")

    lines += [
        "",
        "Associations with no feed are not useless. Most still publish news on the page",
        "itself, and several send an email newsletter, which is the better route anyway.",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {REPORT}")
