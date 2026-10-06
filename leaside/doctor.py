"""A single health report you can copy in one go, instead of hunting through the page.

Everything here is read-only. It answers the questions that keep coming up: how much
is stored, where did it come from, is any of it duplicated, and is the text clean.
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path

from . import db, fields, geo, sources, version

REPORT = Path("config/health-report.md")


def gather(conn, areas, cfg) -> dict:
    q = conn.execute
    total = q("SELECT COUNT(*) FROM items").fetchone()[0]
    on_page = q("SELECT COUNT(*) FROM items WHERE category != 'registry'"
                f" AND {db.SHOWN}").fetchone()[0]
    log = dict(q("""SELECT COALESCE(SUM(routine = 1 AND hidden_at IS NULL), 0) routine,
                           COALESCE(SUM(hidden_at IS NOT NULL), 0) hidden
                    FROM items""").fetchone())
    events = {r[0]: r[1] for r in q("SELECT event, COUNT(*) FROM item_log GROUP BY event")}
    hidden_why = [dict(r) for r in q("""SELECT hidden_reason reason, COUNT(*) n FROM items
        WHERE hidden_at IS NOT NULL GROUP BY hidden_reason ORDER BY n DESC""").fetchall()]

    per_source = [dict(r) for r in q("""
        SELECT source_id,
               COUNT(*)                                            AS rows,
               COALESCE(SUM(published_at IS NULL), 0)               AS undated,
               COALESCE(SUM(summary LIKE '%<%'), 0)                 AS html_left,
               COALESCE(SUM(url IS NULL OR url = ''), 0)            AS no_link,
               MIN(published_at)                                   AS oldest,
               MAX(published_at)                                   AS newest,
               MAX(last_seen_at)                                   AS last_seen
        FROM items GROUP BY source_id ORDER BY rows DESC""").fetchall()]

    # Same source, same link, more than one row: an unambiguous duplicate.
    dup_links = [dict(r) for r in q("""
        SELECT source_id, url, COUNT(*) n FROM items
        WHERE url IS NOT NULL AND url != ''
        GROUP BY source_id, url HAVING n > 1 ORDER BY n DESC LIMIT 20""").fetchall()]

    # Same source, same headline and date: near-certainly the same thing stored twice.
    dup_titles = [dict(r) for r in q("""
        SELECT source_id, title, COALESCE(published_at,'') pub, COUNT(*) n FROM items
        GROUP BY source_id, title, pub HAVING n > 1 ORDER BY n DESC LIMIT 20""").fetchall()]

    runs = db.recent_runs(conn, 1)
    latest_run = runs[0] if runs else "0"
    stale = [dict(r) for r in q("""
        SELECT source_id, COUNT(*) n, MAX(last_seen_at) last_seen FROM items
        WHERE last_seen_at < ? GROUP BY source_id ORDER BY n DESC""", (latest_run,)).fetchall()]

    # A feed whose newest item is over a year old is a feed nobody is writing.
    dormant = [dict(r) for r in q("""
        SELECT source_id, MAX(published_at) newest FROM items
        WHERE category != 'registry' GROUP BY source_id
        HAVING newest < date('now', '-365 days') ORDER BY newest""").fetchall()]

    # For sources that mostly lack a date or a link, show what the raw record holds,
    # so the parser can be corrected from evidence rather than from another guess.
    shapes = []
    linkless_by_design = {s.id for s in cfg.sources
                          if s.category in ("crime", "collision", "police_call",
                                            "permit", "inspection")}
    # A source whose address or columns were guessed shows one raw record every
    # time, until its status is promoted. That record is how the guess gets fixed.
    unverified = {s.id for s in cfg.sources if s.status == "guess"}
    for r in per_source:
        missing_links = (r["no_link"] > r["rows"] / 2
                         and r["source_id"] not in linkless_by_design)
        if r["rows"] and (r["undated"] > r["rows"] / 2 or missing_links
                          or r["source_id"] in unverified):
            raw = q("SELECT raw FROM items WHERE source_id = ? AND raw IS NOT NULL LIMIT 1",
                    (r["source_id"],)).fetchone()
            if raw:
                try:
                    shapes.append((r["source_id"], fields.keys_with_samples(json.loads(raw[0]))))
                except (ValueError, TypeError):
                    pass

    by_area = [dict(r) for r in q("""
        SELECT COALESCE(area,'(none)') area, COUNT(*) n FROM items
        WHERE category != 'registry' GROUP BY area ORDER BY n DESC""").fetchall()]

    runnable = {s.id for s in cfg.sources if s.runnable}
    results = [dict(r) for r in q("""
        SELECT source_id, ok, item_count, error, ran_at FROM fetch_log
        WHERE ran_at = (SELECT MAX(ran_at) FROM fetch_log f2 WHERE f2.source_id = fetch_log.source_id)
        ORDER BY ok, source_id""").fetchall() if r["source_id"] in runnable]

    return {"total": total, "on_page": on_page, "log": log, "events": events,
            "hidden_why": hidden_why, "per_source": per_source,
            "dup_links": dup_links, "dup_titles": dup_titles, "stale": stale,
            "dormant": dormant, "shapes": shapes, "latest_run": latest_run,
            "by_area": by_area, "runs": results, "areas": areas, "cfg": cfg}


def render(d: dict) -> str:
    L = ["# Health report", "",
         f"Produced by code **{version.label()}**.", ""]
    stale = version.warn_if_stale()
    if stale:
        L += [f"> {stale}", ""]
    L += [
         f"- rows stored: **{d['total']}** (nothing is ever deleted)",
         f"- rows the page can show: **{d['on_page']}**",
         f"- routine rows, logged but not shown: **{d['log']['routine']}**",
         f"- hidden rows, kept in the log: **{d['log']['hidden']}**",
         f"- changes recorded: **{d['events'].get('changed', 0)}**",
         f"- duplicate links: **{sum(r['n'] - 1 for r in d['dup_links'])}**",
         f"- duplicate headlines: **{sum(r['n'] - 1 for r in d['dup_titles'])}**",
         "",
         "## Per source", "",
         "| source | rows | no date | html left | no link | oldest | newest |",
         "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in d["per_source"]:
        L.append(f"| `{r['source_id']}` | {r['rows']} | {r['undated']} | {r['html_left']} "
                 f"| {r['no_link']} | {str(r['oldest'])[:10]} | {str(r['newest'])[:10]} |")

    L += ["", "## Duplicates", ""]
    if d["dup_links"] or d["dup_titles"]:
        L.append("| source | what | copies |")
        L.append("| --- | --- | --- |")
        for r in d["dup_links"]:
            L.append(f"| `{r['source_id']}` | link {str(r['url'])[:70]} | {r['n']} |")
        for r in d["dup_titles"]:
            L.append(f"| `{r['source_id']}` | headline {str(r['title'])[:70]} | {r['n']} |")
        L += ["",
              "Duplicate links are always a fault. Repeated headlines are not always:",
              "crime and collision records reuse short labels like `Assault`, so several",
              "genuine incidents on one day share a headline. Judge those by the link column."]
    else:
        L.append("None found.")

    if d["shapes"]:
        L += ["", "## What the raw records look like", "",
              "Listed for sources where most rows lack a date or a link, and for every",
              "source still marked guess. These are the actual keys and",
              "sample values, so the parser can be matched to them.", ""]
        for sid, kv in d["shapes"]:
            L.append(f"### `{sid}`")
            L.append("")
            L.append("| key | sample |")
            L.append("| --- | --- |")
            for k, v in kv[:40]:
                L.append(f"| `{k}` | {v.replace('|', '/')} |")
            L.append("")

    if d["dormant"]:
        L += ["", "## Feeds with nothing new in over a year", "",
              "Still fetched every run, never on the page. Candidates to drop.", "",
              "| source | newest item |", "| --- | --- |"]
        for r in d["dormant"]:
            L.append(f"| `{r['source_id']}` | {str(r['newest'])[:10]} |")

    L += ["", f"## Rows not seen in the most recent run (started {str(d['latest_run'])[:16]})", ""]
    if d["stale"]:
        L.append("| source | rows | last seen |")
        L.append("| --- | --- | --- |")
        for r in d["stale"]:
            L.append(f"| `{r['source_id']}` | {r['n']} | {str(r['last_seen'])[:16]} |")
    else:
        L.append("None. Everything stored was seen in the last run.")

    L += ["", "## By neighbourhood", "", "| area | items |", "| --- | --- |"]
    for r in d["by_area"]:
        L.append(f"| {d['areas'].name(None if r['area'] == '(none)' else r['area'])} | {r['n']} |")

    if d["hidden_why"]:
        L += ["", "## Hidden from the page, kept in the log", "", "| why | rows |", "| --- | --- |"]
        for r in d["hidden_why"]:
            L.append(f"| {r['reason']} | {r['n']} |")

    if d.get("size"):
        raw_mb, gz_mb = d["size"]
        L += ["", "## Size of the log", "",
              f"The database is **{raw_mb:.1f} MB**, about **{gz_mb:.1f} MB** compressed, which is "
              "how it is stored on GitHub. GitHub refuses a single file over 100 MB."]
        if gz_mb > 60:
            L += ["", f"> **Act soon.** At {gz_mb:.0f} MB compressed the log is over halfway to "
                  "GitHub's limit. Ask Claude to split it by year."]

    failed = [r for r in d["runs"] if not r["ok"]]
    L += ["", "## Last result per source", "",
          f"{len(d['runs']) - len(failed)} succeeded, {len(failed)} failed.", ""]
    if failed:
        L.append("| source | error |")
        L.append("| --- | --- |")
        for r in failed:
            L.append(f"| `{r['source_id']}` | {str(r['error'])[:110].replace('|', '/')} |")
    return "\n".join(L) + "\n"


def file_size(path) -> tuple[float, float] | None:
    """(megabytes on disk, megabytes compressed). The compressed size is what
    GitHub stores, so it is the one that matters for the 100 MB limit."""
    path = Path(path)
    if not path.exists():
        return None
    data = path.read_bytes()
    return len(data) / 1e6, len(gzip.compress(data, 6)) / 1e6


def run(db_path=db.DEFAULT_DB, config_path="config/sources.yaml") -> Path:
    conn = db.connect(db_path)
    d = gather(conn, geo.Areas.load(), sources.load(config_path))
    d["size"] = file_size(db_path)
    REPORT.write_text(render(d), encoding="utf-8")
    return REPORT
