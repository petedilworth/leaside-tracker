"""The front page: what happened this week, what is coming up, what to look at.

The old front page was the whole log, 3,000 items in a list, which took eight
seconds to open on a phone and told a reader nothing until they scrolled. This
is the briefing a neighbour wants first: this week against last, dated things
coming up, the stories, and what is being built. Everything links into the full
reader, the map and the trends page for more.
"""
from __future__ import annotations

import calendar
import json
import re
from datetime import date, datetime, timedelta, timezone

from . import db

STORY_CATEGORIES = ("media", "ra_news", "councillor", "community", "business",
                    "planning", "city_notice", "police_news", "transit")
WEEK = 7
LOOKAHEAD_DAYS = 60
_MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
_MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
_MONTHS["sept"] = 9
_DATE = re.compile(
    r"\b(?:(?:mon|tues?|wed(?:nes)?|thu(?:rs)?|fri|sat(?:ur)?|sun)(?:day)?\.?,?\s+)?"
    r"(january|february|march|april|may|june|july|august|september|october|november|december|"
    r"jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec)\.?\s+(\d{1,2})(?!\d)(?:st|nd|rd|th)?"
    r"(?:,?\s+(\d{4}))?", re.I)
_TIME = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?\b", re.I)


def _now(now):
    return now or datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def upcoming(items, now=None, lookahead: int = LOOKAHEAD_DAYS) -> list[dict]:
    """Dated things in the next `lookahead` days, read from recent items' text.

    Deliberately strict. A month and day are needed; a bare "May 2026" is not a
    date. Without a year, the year is the item's own, rolled forward only when
    the date fell before the item was written. Anything already past, or more
    than `lookahead` days out, is dropped. Each item contributes one date: the
    nearest.
    """
    today = _now(now).date()
    horizon = today + timedelta(days=lookahead)
    out = []
    for it in items:
        text = f"{it.get('title') or ''}. {it.get('summary') or ''}"
        written = (it.get("published_at") or it.get("first_seen_at") or "")[:10]
        try:
            wrote = date.fromisoformat(written) if written else today
        except ValueError:
            wrote = today
        best = None
        for m in _DATE.finditer(text):
            month = _MONTHS.get(m.group(1).lower())
            day = int(m.group(2))
            if not month or not 1 <= day <= 31:
                continue
            year = int(m.group(3)) if m.group(3) else wrote.year
            try:
                when = date(year, month, day)
            except ValueError:
                continue
            if not m.group(3) and when < wrote:
                try:
                    when = date(year + 1, month, day)
                except ValueError:
                    continue
            if not today <= when <= horizon:
                continue
            tail = text[m.end():m.end() + 40]
            tm = _TIME.search(tail)
            clock = None
            if tm:
                h, mins, ap = int(tm.group(1)), tm.group(2) or "00", tm.group(3).lower()
                if 1 <= h <= 12:
                    h = h % 12 + (12 if ap == "p" else 0)
                    clock = f"{h:02d}:{mins}"
            snippet = text[max(0, m.start() - 60):m.end() + 60].strip()
            if best is None or when < best["date"]:
                best = {"date": when, "clock": clock, "snippet": snippet}
        if best:
            out.append({**best, "date": best["date"].isoformat(), "title": it["title"],
                        "url": it.get("url"), "source_id": it["source_id"],
                        "source_name": it.get("source_name"), "category": it["category"],
                        "area_name": it.get("area_name"), "id": it["id"]})
    out.sort(key=lambda e: (e["date"], e["clock"] or "99"))
    return out


def _rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def build(conn, areas, cfg, now=None) -> dict:
    now = _now(now)
    week_ago = _iso(now - timedelta(days=WEEK))
    two_weeks = _iso(now - timedelta(days=2 * WEEK))
    month_ago = _iso(now - timedelta(days=30))
    names = {s.id: s.name for s in cfg.sources}
    homes = {s.id: s.home for s in cfg.sources}

    def decorate(rows):
        for it in rows:
            it["area_name"] = areas.name(it["area"])
            it["source_name"] = names.get(it["source_id"], it["source_id"])
            it["source_home"] = homes.get(it["source_id"])
            it["when"] = it["published_at"] or it["first_seen_at"]
        return rows

    def count(category, since, until=None):
        # "New this week" means first seen by the tracker. The City dates a permit
        # by its application day and publishes it days later; counting by that
        # date showed zero permits in a week that brought 21.
        sql = f"SELECT COUNT(*) FROM items WHERE category = ? AND {db.SHOWN} AND first_seen_at >= ?"
        params = [category, since]
        if until:
            sql += " AND first_seen_at < ?"
            params.append(until)
        return conn.execute(sql, params).fetchone()[0]

    tiles = []
    # A rise in police calls or failed inspections is bad news and is coloured;
    # more permits or more stories is neither, so those deltas stay grey.
    for cat, label, note, bad_up in (("police_call", "Police calls", "attended in your areas", True),
                                     ("permit", "Building permits", "new to the tracker", False),
                                     ("inspection", "Restaurant inspections", "with something found", True),
                                     ("media", "Stories", "from local and city press", False)):
        this, last = count(cat, week_ago), count(cat, two_weeks, week_ago)
        tiles.append({"category": cat, "label": label, "note": note, "this": this, "last": last,
                      "delta": this - last, "bad_up": bad_up})

    calls = decorate(_rows(conn, f"""SELECT * FROM items WHERE category = 'police_call' AND {db.SHOWN}
        AND COALESCE(published_at, first_seen_at) >= ? ORDER BY COALESCE(published_at, first_seen_at) DESC""",
        (week_ago,)))
    kinds: dict[str, int] = {}
    for it in calls:
        k = it["title"].split(" near ")[0]
        kinds[k] = kinds.get(k, 0) + 1
    call_kinds = sorted(kinds.items(), key=lambda x: (-x[1], x[0]))[:6]

    marks = ",".join("?" * len(STORY_CATEGORIES))
    stories = decorate(_rows(conn, f"""SELECT * FROM items WHERE category IN ({marks}) AND {db.SHOWN}
        AND COALESCE(published_at, first_seen_at) >= ?
        ORDER BY COALESCE(published_at, first_seen_at) DESC LIMIT 40""",
        (*STORY_CATEGORIES, two_weeks)))
    # Google News repeats a story the local papers already carry; keep the first of each headline.
    seen, unique = set(), []
    for it in stories:
        key = re.sub(r"\s*\([^)]*\)\s*$", "", it["title"]).lower()[:70]
        if key in seen:
            continue
        seen.add(key)
        unique.append(it)
    stories = unique[:14]

    permits = decorate(_rows(conn, f"""SELECT * FROM items WHERE category = 'permit' AND {db.SHOWN}
        AND first_seen_at >= ? ORDER BY COALESCE(published_at, first_seen_at) DESC""", (week_ago,)))
    big = sorted(permits, key=lambda p: -_cost(p["summary"]))[:8]

    inspections = decorate(_rows(conn, f"""SELECT * FROM items WHERE category = 'inspection' AND {db.SHOWN}
        AND first_seen_at >= ? ORDER BY COALESCE(published_at, first_seen_at) DESC LIMIT 8""", (month_ago,)))

    recent_text = decorate(_rows(conn, f"""SELECT * FROM items WHERE category IN ({marks}) AND {db.SHOWN}
        AND COALESCE(published_at, first_seen_at) >= ?""", (*STORY_CATEGORIES, month_ago)))
    events = upcoming(recent_text, now)[:12]

    # Late data: say when the newest crime and collision records are from.
    lag = {}
    for cat in ("crime", "collision"):
        newest = conn.execute(f"SELECT MAX(published_at) FROM items WHERE category = ? AND {db.SHOWN}",
                              (cat,)).fetchone()[0]
        lag[cat] = (newest or "")[:10]

    # For "near home": the last 30 days of located records, compact, for the browser.
    near = _rows(conn, f"""SELECT id, category, title, published_at, first_seen_at, lat, lon, area, url
        FROM items WHERE {db.SHOWN} AND lat IS NOT NULL AND lon IS NOT NULL
        AND COALESCE(published_at, first_seen_at) >= ?
        ORDER BY COALESCE(published_at, first_seen_at) DESC LIMIT 1500""", (month_ago,))
    near_payload = [[r["id"], r["category"], r["title"][:90], (r["published_at"] or r["first_seen_at"])[:10],
                     round(r["lat"], 5), round(r["lon"], 5), areas.name(r["area"]), r["url"] or ""]
                    for r in near]

    runs = db.recent_runs(conn, 1)
    return {
        "now": _iso(now), "week_start": (now - timedelta(days=WEEK)).date().isoformat(),
        "tiles": tiles, "calls": calls[:12], "calls_total": len(calls), "call_kinds": call_kinds,
        "stories": stories, "permits": big, "permits_total": len(permits),
        "inspections": inspections, "events": events, "lag": lag,
        "latest_run": runs[0] if runs else None,
        "near_json": json.dumps(near_payload, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/"),
    }


def _cost(summary: str | None) -> float:
    m = re.search(r"Estimated \$([\d.]+)([MK])?", summary or "")
    if not m:
        return 0.0
    n = float(m.group(1))
    return n * {"M": 1e6, "K": 1e3}.get(m.group(2) or "", 1)
