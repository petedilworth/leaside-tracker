"""Where the data on a page came from, and the terms it is used under.

Every page built from the database ends with the same section, listing only the
sources whose records appear on that page. The City's licence asks for its
statement, and a link to the licence, wherever its data is shown; the other
publishers are credited the same way so the reader can always check the original.
"""
from __future__ import annotations

from . import sources as sources_mod


def for_sources(conn, cfg, source_ids, where: str = "") -> dict:
    """{"sources": [...], "licences": [...]} for the given source ids.

    Each source carries its publisher, a page a person can read, what it
    provides, its licence, how many records it has on the page and the newest.
    """
    ids = [sid for sid in dict.fromkeys(source_ids) if cfg.by_id(sid)]
    stats = {}
    if ids:
        marks = ",".join("?" * len(ids))
        for r in conn.execute(
            f"""SELECT source_id, COUNT(*) n, MAX(published_at) newest, MAX(last_seen_at) seen
                FROM items WHERE source_id IN ({marks}) {where} GROUP BY source_id""", ids
        ):
            stats[r[0]] = {"n": r[1], "newest": r[2], "seen": r[3]}
    rows, licences = [], {}
    for sid in ids:
        src = cfg.by_id(sid)
        lic = cfg.licence_of(src)
        if lic:
            licences.setdefault(lic.key, lic)
        rows.append({
            "id": sid,
            "name": src.name,
            "publisher": src.credit,
            "home": src.home,
            "what": sources_mod.CATEGORY_NAMES.get(src.category, src.category),
            "licence": lic,
            **stats.get(sid, {"n": 0, "newest": None, "seen": None}),
        })
    rows.sort(key=lambda r: (r["what"], r["name"].lower()))
    return {"sources": rows, "licences": list(licences.values())}
