"""Render the SQLite contents to a static page in site/.

The page is a reader, not a dump. It carries enough data attributes for the browser
to do the parts that depend on the reader: local time, "since you last looked",
read state. The server only knows dates and when the last two runs happened.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import attribution, db, export, geo, sources, trends, version

OUT = Path("site")

# What the page shows when you open it. Everything collected is in the file, so the
# reader can widen the window without a rebuild - which matters because collision and
# crime records arrive months or years late and would never appear inside 120 days.
WINDOW_DAYS = 120
WINDOW_CHOICES = [(120, "Last 120 days"), (365, "Last year"), (0, "Everything")]
MAX_ROWS = 3000
LIVE_DAYS = 7


def collect(conn, areas, cfg, window_days: int = WINDOW_DAYS) -> dict:
    rows = conn.execute(
        f"SELECT * FROM items WHERE category != 'registry' AND {db.SHOWN}"
        " ORDER BY COALESCE(published_at, first_seen_at) DESC LIMIT ?",
        (MAX_ROWS,),
    ).fetchall()
    names = {s.id: s.name for s in cfg.sources}
    homes = {s.id: s.home for s in cfg.sources}
    credits = {s.id: s.credit for s in cfg.sources}
    items = []
    for r in rows:
        it = dict(r)
        it["area_name"] = areas.name(it["area"])
        it["source_name"] = names.get(it["source_id"], it["source_id"])
        it["source_home"] = homes.get(it["source_id"])
        it["source_credit"] = credits.get(it["source_id"], it["source_name"])
        it["when"] = it["published_at"] or it["first_seen_at"]
        items.append(it)

    runs = db.recent_runs(conn, 2)
    latest_run = runs[0] if runs else None
    new_this_run = sum(1 for it in items if latest_run and it["first_seen_at"] >= latest_run)

    # Counts are for the default window, so the chips match what you first see.
    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat(
        timespec="seconds")
    in_window = [it for it in items if it["when"] >= cutoff]
    counts, area_counts = {}, {}
    for it in in_window:
        counts[it["category"]] = counts.get(it["category"], 0) + 1
        key = it["area"] or "none"
        area_counts[key] = area_counts.get(key, 0) + 1
    area_names = {k: areas.name(None if k == "none" else k) for k in area_counts}

    fetches = [
        dict(r)
        for r in conn.execute(
            "SELECT source_id, MAX(ran_at) ran_at, ok, item_count, error"
            " FROM fetch_log GROUP BY source_id ORDER BY ok, source_id"
        ).fetchall()
    ]
    for f in fetches:
        f["source_name"] = names.get(f["source_id"], f["source_id"])

    # The live lane: police calls from the last week, newest first. They are in
    # the main list too; this is the glance at the top.
    live_cutoff = (datetime.now(timezone.utc) - timedelta(days=LIVE_DAYS)).isoformat(
        timespec="seconds")
    live = [it for it in items if it["category"] == "police_call" and it["when"] >= live_cutoff]
    live_kinds: dict[str, int] = {}
    for it in live:
        k = it["title"].split(" near ")[0]
        live_kinds[k] = live_kinds.get(k, 0) + 1

    log = conn.execute(
        """SELECT COUNT(*) total,
                  COALESCE(SUM(routine = 1 AND hidden_at IS NULL), 0) routine,
                  COALESCE(SUM(hidden_at IS NOT NULL), 0) hidden
           FROM items WHERE category != 'registry'""").fetchone()
    changes = conn.execute("SELECT COUNT(*) FROM item_log WHERE event = 'changed'").fetchone()[0]

    calls_src = cfg.by_id("tps_calls_for_service")
    return {
        "items": items,
        # Only the sources whose records are actually on this page are cited.
        "attrib": attribution.for_sources(conn, cfg, [it["source_id"] for it in items],
                                          where=f"AND {db.SHOWN}"),
        "live_source": {"home": calls_src.home if calls_src else None,
                        "credit": calls_src.credit if calls_src else "Toronto Police Service"},
        "log_total": log["total"],
        "log_routine": log["routine"],
        "log_hidden": log["hidden"],
        "log_changes": changes,
        "live": live[:40],
        "live_total": len(live),
        "live_days": LIVE_DAYS,
        "live_kinds": sorted(live_kinds.items(), key=lambda x: (-x[1], x[0]))[:5],
        "counts": counts,
        "area_counts": area_counts,
        "area_names": area_names,
        "fetches": fetches,
        "latest_run": latest_run,
        "previous_run": runs[1] if len(runs) > 1 else None,
        "new_this_run": new_this_run,
        "window_days": window_days,
        "window_choices": WINDOW_CHOICES,
        "in_window": len(in_window),
        "total_stored": len(items),
        "truncated": len(items) >= MAX_ROWS,
        "area_default_off": sorted(areas.default_off()),
    }


def run(db_path=db.DEFAULT_DB, config_path="config/sources.yaml",
        out_name="index.html") -> Path:
    conn = db.connect(db_path)
    areas = geo.Areas.load()
    cfg = sources.load(config_path)
    env = Environment(
        loader=FileSystemLoader("templates"), autoescape=select_autoescape(["html"])
    )
    data = collect(conn, areas, cfg)
    data["sources"] = cfg.sources
    data["generated_at"] = db.utcnow()
    data["code_version"] = version.label()
    OUT.mkdir(exist_ok=True)
    # GitHub Pages runs Jekyll over the folder unless told not to. Jekyll drops
    # files whose names start with an underscore and rewrites others; the page
    # wants neither. An empty .nojekyll file switches it off.
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    target = OUT / out_name
    target.write_text(env.get_template("index.html").render(**data), encoding="utf-8")
    render_trends(conn, areas, env, out_name)
    if out_name == "index.html":          # never let the demo overwrite the real log
        export.write(conn, areas, cfg, OUT / "log")
    return target


def render_trends(conn, areas, env, out_name: str = "index.html") -> Path:
    """The companion page: monthly counts, this year against last."""
    data = trends.build(conn, areas)
    for group in (data["crime"], data["collisions"]):
        for f in group["facets"]:
            trends.decorate(f)
    name = "trends.html" if out_name == "index.html" else out_name.replace(".html", "-trends.html")
    target = OUT / name
    cfg = sources.load()
    used = [r[0] for r in conn.execute(
        "SELECT DISTINCT source_id FROM items WHERE category IN ('crime', 'collision')"
        " AND hidden_at IS NULL ORDER BY source_id")]
    attrib = attribution.for_sources(conn, cfg, used, where="AND hidden_at IS NULL")
    target.write_text(env.get_template("trends.html").render(
        data=data, attrib=attrib, srcline=source_lines(attrib, cfg)), encoding="utf-8")
    return target


def source_lines(attrib: dict, cfg) -> dict:
    """"Source: ..." under each heading of the trends page, as linked HTML."""
    from markupsafe import escape
    out = {}
    for cat in ("crime", "collision"):
        parts = []
        for s in attrib["sources"]:
            if cfg.by_id(s["id"]).category != cat:
                continue
            name = escape(s["publisher"])
            link = f'<a href="{escape(s["home"])}" target="_blank" rel="noopener">{name}</a>' \
                if s["home"] else str(name)
            newest = f", newest record {escape(s['newest'][:10])}" if s["newest"] else ""
            parts.append(f"{link} ({escape(s['name'])}{newest})")
        out[cat] = "; ".join(parts)
    return out
