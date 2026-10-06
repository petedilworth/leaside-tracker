"""Build and send the weekly email.

The project was pull-only: nothing arrived unless the owner remembered to run it.
This is the push side. It reports what has been collected since the last successful
digest, so a missed week is folded into the next one rather than lost.

Sent through Resend. On its free tier, without a verified domain, the only permitted
sender is onboarding@resend.dev and the only permitted recipient is the account
owner's own address - which is exactly the arrangement here.
"""
from __future__ import annotations

import html
import json
import os
from datetime import datetime, timedelta, timezone

import requests

from . import db, geo, sources, version

API = "https://api.resend.com/emails"
SENDER = "Leaside Tracker <onboarding@resend.dev>"
MAX_ITEMS = 60
FIRST_EMAIL_DAYS = 14


def site_url() -> str:
    """The published page, when there is one. The workflow sets SITE_URL once
    GitHub Pages is on; until then the email carries no link, so it never
    carries a dead one. Always ends in a slash so trends.html can be appended."""
    url = os.environ.get("SITE_URL", "").strip()
    return url.rstrip("/") + "/" if url else ""
# Order the sections so the things that need a response come before the record-keeping.
SECTION_ORDER = ["city_notice", "planning", "permit", "ra_news", "media", "police_news",
                 "inspection", "business", "community", "councillor", "transit", "crime",
                 "collision"]
# Police calls arrive by the dozen and would crowd out everything else, so the
# email carries a count and the top call types, not the list. The page has the list.
COUNTED_ONLY = {"police_call"}
SECTION_NAMES = {
    "city_notice": "City notices",
    "planning": "Planning",
    "ra_news": "Residents' associations",
    "media": "Local news",
    "business": "Business",
    "community": "Community",
    "councillor": "Councillor",
    "transit": "Transit and construction",
    "crime": "Reported crime",
    "collision": "Collisions",
    "permit": "Building permits",
    "inspection": "Restaurant inspections",
    "police_news": "Police news",
    "police_call": "Police calls",
}


def gather(conn, areas, cfg, since: str | None = None, limit: int = MAX_ITEMS) -> dict:
    """Items first seen after the last digest, newest first, grouped for reading."""
    # After a digest, report only what is strictly newer than it. Timestamps are
    # second-resolution, and an item stored in the same second as the send was
    # already in that email, so an inclusive comparison would repeat it forever.
    inclusive = False
    if since is None:
        since = db.last_digest(conn)
    if since is None:
        # Never sent. Report what the latest run brought in, so the first email is
        # a week of news rather than the entire back catalogue. Inclusive here,
        # because items are first seen at or after the moment the run began.
        runs = db.recent_runs(conn, 1)
        since = runs[0] if runs else (
            datetime.now(timezone.utc) - timedelta(days=7)
        ).isoformat(timespec="seconds")
        inclusive = True
        first_ever = True
    else:
        first_ever = False

    sql = (f"SELECT * FROM items WHERE category != 'registry' AND {db.SHOWN}"
           f" AND first_seen_at {'>=' if inclusive else '>'} ?")
    params: list = [since]
    if first_ever:
        # On a fresh database every stored row is "first seen now", including
        # years of collision history. The first real run reported 9,910 new items.
        # Confine the first email to things actually published recently; undated
        # items are kept because their age is unknown, not because it is old.
        recent = (datetime.now(timezone.utc) - timedelta(days=FIRST_EMAIL_DAYS)
                  ).isoformat(timespec="seconds")
        sql += " AND (published_at IS NULL OR published_at >= ?)"
        params.append(recent)
    rows = conn.execute(
        sql + " ORDER BY COALESCE(published_at, first_seen_at) DESC", params
    ).fetchall()
    names = {s.id: s.name for s in cfg.sources}
    homes = {s.id: s.home for s in cfg.sources}
    # A source's email window. Everything is stored; an item published long before
    # it was first seen - a backfill, not news - stays out of the email.
    now = datetime.now(timezone.utc)
    windows = {s.id: (now - timedelta(days=s.max_age_days)).isoformat(timespec="seconds")
               for s in cfg.sources if s.max_age_days}

    items = []
    for r in rows:
        if (r["source_id"] in windows and r["published_at"]
                and r["published_at"] < windows[r["source_id"]]):
            continue
        it = dict(r)
        it["area_name"] = areas.name(it["area"])
        it["source_name"] = names.get(it["source_id"], it["source_id"])
        it["link"] = it["url"] or homes.get(it["source_id"])
        items.append(it)

    counted = [it for it in items if it["category"] in COUNTED_ONLY]
    items = [it for it in items if it["category"] not in COUNTED_ONLY]
    shown, overflow = items[:limit], max(0, len(items) - limit)
    sections: dict[str, list] = {}
    for it in shown:
        sections.setdefault(it["category"], []).append(it)
    ordered = [(SECTION_NAMES.get(k, k.replace("_", " ").title()), sections[k])
               for k in SECTION_ORDER if k in sections]
    ordered += [(SECTION_NAMES.get(k, k.replace("_", " ").title()), v)
                for k, v in sections.items() if k not in SECTION_ORDER]
    cited = {s.id: s for s in cfg.sources}
    used = list(dict.fromkeys(it["source_id"] for it in shown + counted))
    licences = list({cfg.licence_of(cited[sid]).key: cfg.licence_of(cited[sid])
                     for sid in used if sid in cited and cfg.licence_of(cited[sid])}.values())
    return {"since": since, "total": len(items), "shown": len(shown),
            "overflow": overflow, "sections": ordered,
            "calls": summarise_calls(counted, areas),
            "licences": [(l.statement, l.url) for l in licences]}


def summarise_calls(calls: list[dict], areas) -> dict | None:
    """How many police calls, where, and of what kind, for the email's one-liner."""
    if not calls:
        return None
    kinds: dict[str, int] = {}
    where: dict[str, int] = {}
    for it in calls:
        kind = it["title"].split(" near ")[0]
        kinds[kind] = kinds.get(kind, 0) + 1
        name = it.get("area_name") or areas.name(it.get("area"))
        where[name] = where.get(name, 0) + 1
    top = sorted(kinds.items(), key=lambda x: (-x[1], x[0]))[:4]
    return {"total": len(calls),
            "kinds": top,
            "areas": sorted(where.items(), key=lambda x: (-x[1], x[0]))}


def _day(value: str | None) -> str:
    if not value:
        return ""
    try:
        d = datetime.fromisoformat(value)
        # The day is formatted by hand. The usual no-padding strftime flag is a glibc
        # extension and raises ValueError on Windows.
        return f"{d:%a} {d.day} {d:%b}"
    except (ValueError, TypeError):
        return str(value)[:10]


def render_text(data: dict) -> str:
    lines = [f"Leaside Tracker - {data['total']} new since {_day(data['since'])}"]
    if site_url():
        lines.append(f"The full page, with trends: {site_url()}")
    lines.append("")
    if data.get("calls"):
        c = data["calls"]
        kinds = ", ".join(f"{k} ({n})" for k, n in c["kinds"])
        lines.append(f"POLICE CALLS: {c['total']} attended in your areas"
                     + (f" - {kinds}" if kinds else ""))
        lines.append("    " + ", ".join(f"{a} {n}" for a, n in c["areas"]))
        lines.append("")
    for name, items in data["sections"]:
        lines.append(f"{name.upper()} ({len(items)})")
        for it in items:
            lines.append(f"  {it['title']}")
            meta = " · ".join(x for x in (it["area_name"], it["source_name"],
                                          _day(it["published_at"])) if x)
            lines.append(f"    {meta}")
            if it["summary"]:
                text = it["summary"]
                lines.append(f"    {text[:300]}{'…' if len(text) > 300 else ''}")
            if it["link"]:
                lines.append(f"    {it['link']}")
            lines.append("")
        lines.append("")
    if data["overflow"]:
        lines.append(f"And {data['overflow']} more, not listed. Open the page for all of it.")
    if data.get("licences"):
        lines += ["", "Each item names its source."]
        lines += [f"{st}{' ' + url if url else ''}" for st, url in data["licences"]]
        lines.append(INDEPENDENT)
    return "\n".join(lines)


def render_html(data: dict) -> str:
    """Table-based and inline-styled, because email clients ignore most CSS."""
    e = html.escape
    out = [
        '<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        'font-size:15px;line-height:1.5;color:#1c1b19;max-width:640px;margin:0 auto;'
        'padding:20px">',
        '<h1 style="font-size:20px;margin:0 0 2px">Leaside Tracker</h1>',
        f'<p style="color:#6f6a63;font-size:13px;margin:0 0 22px">'
        f'{data["total"]} new item{"s" if data["total"] != 1 else ""} '
        f'since {e(_day(data["since"]))}</p>',
    ]
    if site_url():
        out.append(f'<p style="font-size:13px;margin:-14px 0 22px">'
                   f'<a href="{e(site_url())}" style="color:#8a3b2a">Open the full page</a>'
                   f' &middot; <a href="{e(site_url())}trends.html" style="color:#8a3b2a">'
                   f'Is it up this year?</a></p>')
    if data.get("calls"):
        c = data["calls"]
        kinds = ", ".join(f"{e(k)} ({n})" for k, n in c["kinds"])
        where = ", ".join(f"{e(a)} {n}" for a, n in c["areas"])
        out.append(
            f'<p style="font-size:14px;background:#f6f1ea;border-radius:8px;padding:10px 12px;'
            f'margin:0 0 20px"><strong>Police attended {c["total"]} call'
            f'{"s" if c["total"] != 1 else ""}</strong> in your areas'
            + (f': {kinds}.' if kinds else '.')
            + (f'<br><span style="color:#6f6a63">{where}</span>' if where else '')
            + ' Each is placed at the nearest intersection by the police. '
            + 'The page lists them.</p>')
    if not data["sections"] and not data.get("calls"):
        out.append('<p style="color:#6f6a63">Nothing new this week. '
                   'The sources were checked and had no new items.</p>')
    for name, items in data["sections"]:
        out.append(
            f'<h2 style="font-size:12px;text-transform:uppercase;letter-spacing:.06em;'
            f'color:#6f6a63;border-bottom:1px solid #e4e0d8;padding-bottom:5px;'
            f'margin:26px 0 10px">{e(name)} ({len(items)})</h2>'
        )
        for it in items:
            title = e(it["title"])
            if it["link"]:
                title = (f'<a href="{e(it["link"])}" style="color:#8a3b2a;'
                         f'text-decoration:none">{title}</a>')
            out.append('<div style="margin:0 0 16px">')
            out.append(f'<div style="font-weight:600">{title}</div>')
            meta = " &middot; ".join(
                e(x) for x in (it["area_name"], it["source_name"],
                               _day(it["published_at"])) if x)
            out.append(f'<div style="font-size:12.5px;color:#6f6a63;'
                       f'margin-top:2px">{meta}</div>')
            if it["summary"]:
                text = it["summary"]
                out.append(f'<div style="font-size:14px;color:#4a4641;margin-top:5px">'
                           f'{e(text[:400])}{"…" if len(text) > 400 else ""}</div>')
            out.append('</div>')
    if data["overflow"]:
        out.append(f'<p style="font-size:13px;color:#6f6a63">And {data["overflow"]} more, '
                   f'not listed here.</p>')
    out.append(
        '<p style="font-size:12px;color:#a39d94;border-top:1px solid #e4e0d8;'
        'margin-top:30px;padding-top:12px">'
        + _credits_html(data.get("licences", []))
        + 'Police crime and collision records sit at the nearest intersection, not the '
        'address, and arrive months after the event.<br>'
        f'Collected by code {e(version.label())}.</p>'
    )
    out.append('</div>')
    return "\n".join(out)


# Both open government licences (clause 7) forbid suggesting official status or
# endorsement, so every place that credits them says so.
INDEPENDENT = ("This is an independent project, not affiliated with or endorsed by "
               "any publisher it cites.")


def _credits_html(licences) -> str:
    """"Each item names its source." and the licence wording, each with its link."""
    e = html.escape
    parts = ["Each item names its source."]
    for statement, url in licences:
        link = (f' <a href="{e(url)}" style="color:#a39d94">The licence</a>.' if url else "")
        parts.append(f"{e(statement)}{link}")
    parts.append(e(INDEPENDENT))
    return " ".join(parts) + "<br>"


def subject(data: dict) -> str:
    if not data["total"] and data.get("calls"):
        return f"Leaside: police attended {data['calls']['total']} calls, nothing else new"
    if not data["total"]:
        return "Leaside Tracker: nothing new this week"
    headline = data["sections"][0][1][0]["title"] if data["sections"] else ""
    n = data["total"]
    return f"Leaside: {n} new item{'s' if n != 1 else ''} - {headline}"[:120]


def send(data: dict, to: str, api_key: str, timeout: int = 30) -> dict:
    resp = requests.post(
        API,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        data=json.dumps({"from": SENDER, "to": [to], "subject": subject(data),
                         "html": render_html(data), "text": render_text(data)}),
        timeout=timeout,
    )
    if resp.status_code >= 300:
        raise RuntimeError(f"Resend refused the email: HTTP {resp.status_code} {resp.text[:300]}")
    return resp.json()


def run(db_path=db.DEFAULT_DB, config_path="config/sources.yaml", dry_run: bool = False,
        to: str | None = None, skip_empty: bool = True) -> dict:
    conn = db.connect(db_path)
    data = gather(conn, geo.Areas.load(), sources.load(config_path))
    print(f"{data['total']} new items since {data['since'][:16]}"
          f" ({data['shown']} listed, {data['overflow']} beyond the cap)")

    if dry_run:
        print("\n--- subject ---")
        print(subject(data))
        print("\n--- text ---")
        print(render_text(data))
        return data
    if skip_empty and not data["total"]:
        print("Nothing new, so no email sent.")
        db.record_digest(conn, 0, True, "skipped: nothing new")
        return data

    to = to or os.environ.get("DIGEST_TO")
    api_key = os.environ.get("RESEND_API_KEY")
    missing = [n for n, v in (("DIGEST_TO", to), ("RESEND_API_KEY", api_key)) if not v]
    if missing:
        raise RuntimeError(
            f"cannot send: {' and '.join(missing)} not set. "
            "See docs/EMAIL-DIGEST.md."
        )
    try:
        result = send(data, to, api_key)
    except Exception as exc:
        db.record_digest(conn, data["total"], False, str(exc))
        raise
    db.record_digest(conn, data["total"], True, f"resend id {result.get('id', '?')}")
    print(f"Sent to {to}.")
    return data
