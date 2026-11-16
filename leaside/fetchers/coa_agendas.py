"""Committee of Adjustment hearing agendas, for the City's own link to each file.

The open data (fetchers/coa.py) has every file but no owner, applicant or agent
names, no itemised variances and no documents. Those are on each file's page in
the City's Application Information Centre, which refuses automated requests, so
this tracker does not read them. It does not need to: the City's hearing
agendas, plain PDFs on toronto.ca, link every file on the agenda to that page.
This module reads the agendas and keeps, for each file, its place on the agenda
and the City's link, so a reader is one tap from the names, plans, staff
reports, notice and decision.

What is kept: one row per agenda, and one row per file on it in Don Valley
West, the ward Leaside and Bennington Heights are in. Nothing behind the link
is fetched.

The City takes a file down about 90 days after its final decision, and the
link stops working then. The agenda itself stays.

Agendas change shape from one hearing to the next - "1 A0082/26NY", "2.
A0244/26NY", three file numbers under one item, the ward as "Don Valley West
(15)" or just "15" - so nothing here depends on a line's wording. It works from
where the text sits on the page: a file number, the item number to its left,
the ward to its right, and the link drawn over the address on the same line.
"""
from __future__ import annotations

import io
import re
from datetime import date, datetime, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup

REF = re.compile(r"\b([AB]\d{3,4}/\d{2}[A-Z]{2,3})\b")
SLOT = re.compile(r"heard at\s+(\d{1,2}:\d{2}\s*[ap]\.?m\.?)", re.I)
HEARING = re.compile(r"Hearing Date:\s*([A-Za-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})")
LINK_DATE = re.compile(r"([A-Za-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})")
OUR_WARDS = {"15"}            # Don Valley West
REREAD_DAYS = 3               # agendas are revised until the hearing; re-read near ones
LEFT_COLUMN = 115             # item numbers sit left of this
WARD_COLUMN = 400             # wards sit right of this
SAME_ITEM = 16                # points between the lines of one agenda item


def _day(month: str, day: str, year: str) -> str | None:
    for fmt in ("%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(f"{month} {day} {year}", fmt).date().isoformat()
        except ValueError:
            continue
    return None


def agenda_links(html: str, base: str) -> list[tuple[str | None, str]]:
    """[(hearing date or None, agenda PDF address)] from a panel's schedule page."""
    out, seen = [], set()
    for a in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        href = urljoin(base, a["href"].strip())
        if not href.lower().endswith(".pdf") or "agenda" not in href.lower() or href in seen:
            continue
        seen.add(href)
        m = LINK_DATE.search(a.get_text(" ", strip=True))
        out.append((_day(*m.groups()) if m else None, href))
    return out


def _page_parts(page) -> tuple[list[tuple[float, float, str]], list[tuple[float, float, str]]]:
    """A page's text as (y, x, text), and its links to City files as (bottom, top, address)."""
    chunks: list[tuple[float, float, str]] = []

    def visit(text, cm, tm, font_dict, font_size):
        if text and text.strip():
            x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            chunks.append((y, x, text.strip()))

    page.extract_text(visitor_text=visit)
    links = []
    for annot in page.get("/Annots") or []:
        annot = annot.get_object()
        uri = str((annot.get("/A") or {}).get("/URI") or "")
        if "/AIC/" in uri and "folderRsn=" in uri and annot.get("/Rect"):
            rect = [float(v) for v in annot["/Rect"]]
            links.append((min(rect[1], rect[3]), max(rect[1], rect[3]), uri))
    return chunks, links


def parse_agenda(pdf: bytes, agenda_url: str, hearing: str | None = None) -> dict:
    """{'hearing': date, 'files': [{ref, item, slot, ward, address, city_file_url}]}."""
    import pypdf
    reader = pypdf.PdfReader(io.BytesIO(pdf))
    files, slot, found_date = [], None, None
    for page in reader.pages:
        chunks, links = _page_parts(page)
        if not found_date:
            m = HEARING.search(re.sub(r"\s+", " ", page.extract_text() or ""))
            found_date = _day(*m.groups()) if m else None
        numbers = [(y, int(m.group(1))) for y, x, t in chunks if x < LEFT_COLUMN
                   for m in [re.match(r"(\d{1,3})\.?(?:\s|$)", t)] if m]
        wards = [(y, m.group(1)) for y, x, t in chunks if x >= WARD_COLUMN
                 for m in [re.search(r"(\d{1,2})\)?\s*$", t)] if m]
        # Top of the page first, so each file takes the sitting named above it.
        for y, x, t in sorted(chunks, key=lambda c: (-c[0], c[1])):
            s = SLOT.search(t)
            if s:
                slot = re.sub(r"\s+", " ", s.group(1)).lower()
            for m in REF.finditer(t):
                near = lambda pairs: min((p for p in pairs if abs(p[0] - y) <= SAME_ITEM),
                                         key=lambda p: abs(p[0] - y), default=(None, None))[1]
                link = next((u for lo, hi, u in links if lo - 4 <= y <= hi + 2), None)
                same_line = " ".join(c[2] for c in sorted(chunks, key=lambda c: c[1])
                                     if abs(c[0] - y) <= 2 and c[1] < WARD_COLUMN)
                address = REF.sub("", re.sub(r"^\s*\d{1,3}\.?\s+", "", same_line))
                address = re.sub(r"\s+", " ", address).strip(" ,-") or None
                files.append({"ref": m.group(1), "item": near(numbers), "slot": slot,
                              "ward": near(wards), "address": address, "city_file_url": link})
    return {"hearing": found_date or hearing, "agenda_url": agenda_url, "files": files}


def to_items(agenda: dict, source, panel: str) -> list[dict]:
    """One row for the agenda, and one per file on it that could be ours."""
    hearing, url = agenda["hearing"], agenda["agenda_url"]
    when = hearing or "an undated hearing"
    items = [{
        "source_id": source.id, "category": source.category, "routine": True,
        "external_id": f"agenda|{url}",
        "title": f"{panel} hearing agenda, {when}",
        "url": url, "published_at": hearing, "summary": None,
        "raw": {"kind": "agenda", "panel": panel, "hearing": hearing, "agenda_url": url,
                "files_listed": len(agenda["files"])},
    }]
    for f in agenda["files"]:
        if f["ward"] and f["ward"] not in OUR_WARDS:
            continue
        items.append({
            "source_id": source.id, "category": source.category, "routine": True,
            "external_id": f"{f['ref']}|{hearing}",
            "title": f"{f['address'] or f['ref']}: on the {when} agenda"
                     + (f", item {f['item']}" if f["item"] else ""),
            "url": url, "published_at": hearing, "summary": None,
            "raw": {"kind": "file", "panel": panel, "hearing": hearing, "agenda_url": url, **f},
        })
    return items


def fetch(source, http, areas) -> tuple[list[dict], int]:
    """Read the schedule page, then each agenda not read before or still to be heard."""
    kw = dict(timeout=source.timeout, retries=source.retries)
    panel = source.extra.get("panel", "North York")
    resp = http.get(source.url, **kw)
    resp.raise_for_status()
    listed = agenda_links(resp.text, source.url)
    if not listed:
        raise RuntimeError(f"{source.id}: no agenda PDFs found on {source.url}")
    known = getattr(source, "_known", set())
    cutoff = (date.today() - timedelta(days=REREAD_DAYS)).isoformat()
    items, read, failed = [], 0, 0
    for hearing, url in listed:
        if url in known and not (hearing and hearing >= cutoff):
            continue
        try:
            got = http.get(url, **kw)
            got.raise_for_status()
            items += to_items(parse_agenda(got.content, url, hearing), source, panel)
            read += 1
        except Exception as exc:           # one unreadable agenda must not lose the rest
            failed += 1
            print(f"        could not read {url}: {type(exc).__name__}: {exc}")
    if failed and not read:
        raise RuntimeError(f"{source.id}: none of {failed} agendas could be read")
    ours = sum(1 for it in items if it["raw"]["kind"] == "file")
    linked = sum(1 for it in items if it["raw"].get("city_file_url"))
    print(f"        {len(listed)} agendas listed, {read} read, {ours} files in Don Valley West, "
          f"{linked} with the City's link")
    return items, resp.status_code
