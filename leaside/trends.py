"""Monthly counts that answer "is it up this year?", honestly.

Three things make a naive count misleading here, and each is handled:

- Police records arrive roughly three months late, so the most recent months are
  always low. The last month with any data is found per category, and the months
  after it are reported as unknown rather than zero. The comparison with last year
  uses the same months in both years, cut at that point, so it is fair.
- The crime source keeps the newest 4000 records per offence. If an offence's
  oldest kept record is younger than the comparison window, last year's count is
  incomplete, and the delta is withheld rather than shown as a fall.
- The neighbourhood areas are hand-drawn and overlap. Counts are for the collected
  area as a whole; the per-area breakdown is labelled approximate.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone

# Layout order. Not a colour order: every facet is one series in the same hue.
OFFENCE_ORDER = ["Break and Enter", "Auto Theft", "Theft From Motor Vehicle",
                 "Robbery", "Assault", "Bicycle Theft", "Theft Over"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _offence(title: str, raw: str | None) -> str:
    if raw:
        try:
            cat = json.loads(raw).get("CSI_CATEGORY")
            if cat:
                return _tidy(cat)
        except (ValueError, AttributeError):
            pass
    head = title.split(" at ")[0].split(" - ")[0].strip()
    return _tidy(head)


def _tidy(name: str) -> str:
    name = name.strip()
    fixes = {"Theft From Motor Vehicle Under": "Theft From Motor Vehicle",
             "Theft From Motor Vehicle Over": "Theft From Motor Vehicle",
             "Bicycle Thefts": "Bicycle Theft", "B&E": "Break and Enter"}
    return fixes.get(name, name)


def _month(iso: str | None) -> str | None:
    return iso[:7] if iso and len(iso) >= 7 else None


def _ym(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def counts_by_month(conn, category: str, key_fn) -> dict[str, dict[str, int]]:
    """{group: {"YYYY-MM": n}} for every row of a category, grouped by key_fn(row)."""
    out: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in conn.execute(
        "SELECT title, raw, published_at, area, source_id FROM items"
        " WHERE category = ? AND published_at IS NOT NULL AND hidden_at IS NULL",
        (category,)
    ):
        m = _month(row["published_at"])
        if not m:
            continue
        out[key_fn(row)][m] += 1
        out["__all__"][m] += 1
    return out


def _series(months: dict[str, int], year: int, upto: int | None) -> list[int | None]:
    """Twelve values for a calendar year; None past the last month with data."""
    return [months.get(_ym(year, m), 0) if (upto is None or m <= upto) else None
            for m in range(1, 13)]


def summarise(months: dict[str, int], now: datetime) -> dict:
    """One offence, one source, or the total: the numbers a tile and a facet need."""
    have = sorted(k for k in months if k)
    if not have:
        return {"empty": True}
    newest = have[-1]
    oldest = have[0]
    ny, nm = int(newest[:4]), int(newest[5:])
    this_year = now.year
    # Fair window: January to the newest month with data, in both years. If the
    # newest data is from an earlier year, this year has nothing to compare yet.
    if ny == this_year:
        upto = nm
    elif ny < this_year:
        upto = 0
    else:
        upto = 12
    window = [_ym(this_year, m) for m in range(1, upto + 1)]
    prior = [_ym(this_year - 1, m) for m in range(1, upto + 1)]
    ytd = sum(months.get(k, 0) for k in window)
    ytd_prior = sum(months.get(k, 0) for k in prior)
    # Last year's window is complete only if data reaches back before it started.
    prior_start = _ym(this_year - 1, 1)
    complete = oldest <= prior_start and upto > 0
    lag_months = (now.year - ny) * 12 + (now.month - nm)
    return {
        "empty": False,
        "newest": newest,
        "newest_label": f"{MONTHS[nm - 1]} {ny}",
        "oldest": oldest,
        "lag_months": lag_months,
        "upto": upto,
        "window_label": (f"Jan to {MONTHS[upto - 1]}" if upto else "no data yet this year"),
        "ytd": ytd if upto else None,
        "ytd_prior": ytd_prior if (upto and complete) else None,
        "delta": (ytd - ytd_prior) if (upto and complete) else None,
        "complete": complete,
        "this_year": _series(months, this_year, upto),
        "last_year": _series(months, this_year - 1, None),
        "year": this_year,
    }


def _order(names: list[str]) -> list[str]:
    known = [n for n in OFFENCE_ORDER if n in names]
    return known + sorted(n for n in names if n not in OFFENCE_ORDER)


def build(conn, areas, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)

    crime = counts_by_month(conn, "crime", lambda r: _offence(r["title"], r["raw"]))
    crime_by_area = counts_by_month(conn, "crime", lambda r: r["area"] or "none")
    coll = counts_by_month(conn, "collision", lambda r: r["source_id"])
    coll_by_area = counts_by_month(conn, "collision", lambda r: r["area"] or "none")

    def facets(table: dict, names: list[str], label_fn) -> list[dict]:
        out = []
        for name in names:
            s = summarise(table[name], now)
            if not s["empty"]:
                s["name"] = label_fn(name)
                s["key"] = name
                out.append(s)
        return out

    def by_area(table: dict) -> list[dict]:
        rows = []
        for key in areas.keys():
            if key in table:
                s = summarise(table[key], now)
                if not s["empty"]:
                    rows.append({"area": areas.name(key), **s})
        return rows

    offence_names = _order([k for k in crime if k != "__all__"])
    source_labels = {"tps_traffic_collisions": "All collisions (Toronto Police)",
                     "city_ksi_collisions": "Killed or seriously injured (City)"}
    coll_names = [k for k in ("tps_traffic_collisions", "city_ksi_collisions") if k in coll]

    return {
        "generated": now.isoformat(timespec="seconds"),
        "year": now.year,
        "months": MONTHS,
        "crime": {
            "total": summarise(crime["__all__"], now) if "__all__" in crime else {"empty": True},
            "facets": facets(crime, offence_names, lambda n: n),
            "by_area": by_area(crime_by_area),
        },
        "collisions": {
            "facets": facets(coll, coll_names, lambda n: source_labels.get(n, n)),
            "by_area": by_area(coll_by_area),
        },
    }


# ---------------------------------------------------------------- drawing helpers

# Every candidate above 1 is even, so the midpoint tick is a whole number and the
# axis reads 0 / 8 / 16 rather than 0 / 7 / 15.
NICE = (1, 2, 4, 6, 8, 10, 12, 16, 20, 30, 40, 50, 60, 80, 100, 120, 160, 200,
        300, 400, 500, 600, 800, 1000, 1200, 1600, 2000)


def nice_max(values: list[int | None]) -> int:
    top = max((v for v in values if v is not None), default=0)
    if top <= 0:
        return 1
    for n in NICE:
        if top <= n:
            return n
    return ((top + 999) // 1000) * 1000


def path(values: list[int | None], ymax: int, w: int, h: int, pad: int) -> str:
    """An SVG path through the twelve months; a gap where the value is unknown."""
    inner_w, inner_h = w - 2 * pad, h - 2 * pad
    out, pen_down = [], False
    for i, v in enumerate(values):
        if v is None:
            pen_down = False
            continue
        x = pad + inner_w * i / 11
        y = pad + inner_h * (1 - v / ymax)
        out.append(f"{'L' if pen_down else 'M'}{x:.1f},{y:.1f}")
        pen_down = True
    return " ".join(out)


def points(values: list[int | None], ymax: int, w: int, h: int, pad: int) -> list[dict]:
    inner_w, inner_h = w - 2 * pad, h - 2 * pad
    return [
        {"x": round(pad + inner_w * i / 11, 1),
         "y": None if v is None else round(pad + inner_h * (1 - v / ymax), 1),
         "v": v}
        for i, v in enumerate(values)
    ]


GUTTER = 26   # room on the right for tick labels; they were being clipped at the edge


def decorate(facet: dict, w: int = 320, h: int = 130, pad: int = 10) -> dict:
    """Attach everything the template needs to draw one facet.

    `w` is the plot width; the SVG is `w + GUTTER` wide so tick labels sit outside
    the plot. The end label is clamped so it never leaves the top of the box.
    """
    ymax = nice_max(facet["this_year"] + facet["last_year"])
    facet["ymax"] = ymax
    facet["w"], facet["h"], facet["pad"] = w, h, pad
    facet["svg_w"] = w + GUTTER
    facet["path_this"] = path(facet["this_year"], ymax, w, h, pad)
    facet["path_last"] = path(facet["last_year"], ymax, w, h, pad)
    facet["pts_this"] = points(facet["this_year"], ymax, w, h, pad)
    facet["pts_last"] = points(facet["last_year"], ymax, w, h, pad)
    # Shade from the newest month with data to December: unknown, not zero.
    upto = facet["upto"]
    inner_w = w - 2 * pad
    facet["unknown_x"] = round(pad + inner_w * max(upto - 1, 0) / 11, 1) if upto < 12 else None
    facet["ticks"] = [0, ymax // 2, ymax] if ymax >= 2 else [0, ymax]
    last_idx = max((i for i, v in enumerate(facet["this_year"]) if v is not None), default=None)
    facet["end_label"] = (facet["this_year"][last_idx] if last_idx is not None else None)
    facet["end_idx"] = last_idx
    if last_idx is not None:
        ep = facet["pts_this"][last_idx]
        # Above the dot by default; below it when that would leave the box.
        facet["end_y"] = ep["y"] - 7 if ep["y"] - 7 >= 9 else ep["y"] + 14
    return facet
