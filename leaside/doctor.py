"""A single health report you can copy in one go, instead of hunting through the page.

Everything here is read-only. It answers the questions that keep coming up: how much
is stored, where did it come from, is any of it duplicated, and is the text clean.
"""
from __future__ import annotations

from pathlib import Path

from . import db, geo, sources

REPORT = Path("config/health-report.md")


def gather(conn, areas, cfg) -> dict:
    q = conn.execute
    total = q("SELECT COUNT(*) FROM items").fetchone()[0]
    on_page = q("SELECT COUNT(*) FROM items WHERE category != 'registry'").fetchone()[0]

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

    stale = [dict(r) for r in q("""
        SELECT source_id, COUNT(*) n, MAX(last_seen_at) last_seen FROM items
        WHERE last_seen_at < (SELECT MAX(last_seen_at) FROM items)
        GROUP BY source_id ORDER BY n DESC""").fetchall()]

    by_area = [dict(r) for r in q("""
        SELECT COALESCE(area,'(none)') area, COUNT(*) n FROM items
        WHERE category != 'registry' GROUP BY area ORDER BY n DESC""").fetchall()]

    runs = [dict(r) for r in q("""
        SELECT source_id, ok, item_count, error, ran_at FROM fetch_log
        WHERE ran_at = (SELECT MAX(ran_at) FROM fetch_log f2 WHERE f2.source_id = fetch_log.source_id)
        ORDER BY ok, source_id""").fetchall()]

    return {"total": total, "on_page": on_page, "per_source": per_source,
            "dup_links": dup_links, "dup_titles": dup_titles, "stale": stale,
            "by_area": by_area, "runs": runs, "areas": areas, "cfg": cfg}


def render(d: dict) -> str:
    L = ["# Health report", "",
         f"- rows stored: **{d['total']}**",
         f"- rows the page can show: **{d['on_page']}**",
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

    L += ["", "## Rows not seen in the most recent run", ""]
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

    failed = [r for r in d["runs"] if not r["ok"]]
    L += ["", "## Last result per source", "",
          f"{len(d['runs']) - len(failed)} succeeded, {len(failed)} failed.", ""]
    if failed:
        L.append("| source | error |")
        L.append("| --- | --- |")
        for r in failed:
            L.append(f"| `{r['source_id']}` | {str(r['error'])[:110].replace('|', '/')} |")
    return "\n".join(L) + "\n"


def run(db_path=db.DEFAULT_DB, config_path="config/sources.yaml") -> Path:
    conn = db.connect(db_path)
    d = gather(conn, geo.Areas.load(), sources.load(config_path))
    REPORT.write_text(render(d), encoding="utf-8")
    return REPORT
