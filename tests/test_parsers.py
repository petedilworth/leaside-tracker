"""Parser tests run entirely offline against fixtures. No network, ever."""
import json
import os
import pathlib
import sys

import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from leaside import db, geo, sources  # noqa: E402
from leaside.fetchers import arcgis, notices, rss_feed  # noqa: E402

FIX = Path(__file__).parent / "fixtures"
AREAS = geo.Areas.load("config/areas.geojson")
CFG = sources.load("config/sources.yaml")


def test_rss_parses_and_dates():
    src = CFG.by_id("ra_leaside")
    items = rss_feed.parse((FIX / "ra_feed.xml").read_text(encoding="utf-8"), src)
    assert len(items) == 2
    assert items[0]["title"].startswith("September general meeting")
    assert items[0]["published_at"] == "2025-09-03T14:00:00+00:00"
    assert items[0]["url"] == "https://example.invalid/sept-agenda"


def test_notices_keeps_only_local():
    src = CFG.by_id("city_public_notices")
    items = notices.parse((FIX / "notices.json").read_text(encoding="utf-8"), src)
    assert len(items) == 2
    local = [
        i for i in items
        if AREAS.match_text(i["title"], i["summary"], json.dumps(i["raw"]))
    ]
    assert len(local) == 1
    assert "Millwood" in local[0]["title"]


def test_notices_handles_wrapped_payload():
    src = CFG.by_id("city_public_notices")
    wrapped = json.dumps({"Notices": json.loads((FIX / "notices.json").read_text(encoding="utf-8"))})
    assert len(notices.parse(wrapped, src)) == 2


def test_arcgis_filters_by_area():
    src = CFG.by_id("tps_reported_crime")
    items = arcgis.parse_features((FIX / "arcgis_features.json").read_text(encoding="utf-8"), src, AREAS)
    assert len(items) == 1, "the downtown incident must be dropped"
    assert items[0]["title"] == "Break and Enter"
    assert items[0]["area"] == "leaside"
    assert items[0]["published_at"].startswith("2024-") or items[0]["published_at"].startswith("2025-")


def test_layer_discovery():
    entries = arcgis.catalogue_entries((FIX / "hub_dcat.json").read_text(encoding="utf-8"))
    url = arcgis.find_layer(entries, "major crime indicators")
    assert url and url.endswith("FeatureServer/0")
    assert arcgis.find_layer(entries, "shootings") is None


def test_bbox_covers_all_areas():
    minx, miny, maxx, maxy = arcgis.bbox_of(AREAS)
    assert minx < -79.40 and maxx > -79.35
    assert miny < 43.67 and maxy > 43.73


def test_status_values_are_from_the_documented_set():
    allowed = {"verified", "documented", "guess", "manual", "blocked"}
    bad = [(s.id, s.status) for s in CFG.sources if s.status not in allowed]
    assert not bad, bad


def test_every_source_has_a_known_kind():
    allowed = sources.RUNNABLE_KINDS | {"manual", "blocked"}
    bad = [s.id for s in CFG.sources if s.kind not in allowed]
    assert not bad, bad


def test_blocked_sources_are_never_runnable():
    assert not any(s.runnable for s in CFG.sources if s.status in {"blocked", "manual"})


def test_date_parsing_handles_every_shape_a_source_gives_us():
    from leaside import dates

    assert dates.parse("2025-09-03T14:00:00+00:00").year == 2025
    assert dates.parse("2025-09-03").month == 9
    assert dates.parse(1725235200000).year == 2024      # ArcGIS epoch milliseconds
    assert dates.parse(1725235200).year == 2024          # epoch seconds
    assert dates.parse("") is None
    assert dates.parse("not a date") is None


def test_unknown_dates_are_kept_not_dropped():
    from leaside import dates

    assert dates.within_days(None, 30) is True
    assert dates.within_days("nonsense", 30) is True
    assert dates.within_days("2001-01-01", 30) is False


def test_late_arriving_sources_are_not_age_capped():
    """Collision and crime records arrive months or years late. Keep them all.

    Capping them at ingest is what made them invisible: a 90-day cap on collisions
    discarded all 960 records in the area, twice. The page decides what is shown.
    """
    for sid in ("tps_reported_crime", "tps_traffic_collisions", "city_ksi_collisions"):
        assert CFG.by_id(sid).max_age_days is None, f"{sid} must keep its history"
    # The notices feed is a live stream, so a window there is still right.
    assert CFG.by_id("city_public_notices").max_age_days == 120


def test_crime_gathers_every_offence_layer_because_there_is_no_single_one():
    """TPS publish no "Major Crime Indicators" layer. Each offence is its own dataset."""
    from leaside.fetchers import arcgis as a

    entries = [
        {"title": t, "distribution": [{"accessURL": f"https://x/{i}/FeatureServer/0"}]}
        for i, t in enumerate([
            "Break and Enter Open Data", "Assault Open Data", "Auto Theft Open Data",
            "Budget 2026", "Homicides Open Data (ASR-RC-TBL-002)",
        ])
    ]
    src = CFG.by_id("tps_reported_crime")
    found = a.find_layers(entries, src.discover_match)
    titles = [t for t, _ in found]
    assert "Break and Enter Open Data" in titles and "Assault Open Data" in titles
    assert "Budget 2026" not in titles
    assert "Homicides Open Data (ASR-RC-TBL-002)" not in titles, "deliberately excluded"
    assert a.offence_label("Break and Enter Open Data") == "Break and Enter"
    assert len({u for _, u in found}) == len(found), "no layer fetched twice"


def test_crime_items_are_labelled_with_their_offence():
    from leaside.fetchers import arcgis as a

    src = CFG.by_id("tps_reported_crime")
    raw = json.dumps({"features": [
        {"attributes": {"EVENT_UNIQUE_ID": "GO-9", "OCC_DATE": 1780000000000},
         "geometry": {"x": -79.365, "y": 43.705}}]})
    items = a.parse_features(raw, src, AREAS, label="Break and Enter")
    assert items[0]["title"] == "Break and Enter", "no offence field, so use the layer name"


def test_layer_discovery_survives_a_renamed_dataset():
    """Publishers rename things. Discovery must not be brittle about it."""
    entries = [
        {"title": "Major_Crime_Indicators_Open_Data",
         "distribution": [{"accessURL": "https://x.invalid/MCI/FeatureServer/0"}]},
    ]
    from leaside.fetchers import arcgis as a

    assert a.find_layer(entries, "major crime indicators")
    assert a.find_layer(entries, ["shootings", "major crime indicators"])
    assert a.find_layer(entries, "homicides") is None


def test_queryable_titles_skips_download_only_datasets():
    from leaside.fetchers import arcgis as a

    entries = [
        {"title": "Queryable", "distribution": [{"accessURL": "https://x/FeatureServer/0"}]},
        {"title": "CSV only", "distribution": [{"downloadURL": "https://x/f.csv"}]},
    ]
    assert a.queryable_titles(entries) == ["Queryable"]


def test_unicode_survives_the_whole_pipeline(tmp_path):
    """Regression: Windows defaults files to cp1252 and a single arrow killed the build.

    Real neighbourhood headlines contain arrows, curly quotes, dashes and accents.
    """
    from leaside import db, render

    dbfile = tmp_path / "t.db"
    conn = db.connect(dbfile)
    db.upsert_item(conn, {
        "source_id": "ra_leaside",
        "category": "ra_news",
        "title": "Bayview → Laird detour – café owners’ “concerns”",
        "url": "https://example.invalid/x",
        "summary": "Accented and typographic characters: éèê — ‘quoted’",
        "published_at": "2026-09-01",
        "area": "leaside",
    })
    conn.commit()

    out = render.run(db_path=dbfile)
    written = out.read_text(encoding="utf-8")
    assert "→" in written
    assert "café" in written


def test_directory_scan_keeps_associations_and_drops_the_furniture():
    from leaside import discover

    html = (FIX / "directory.html").read_text(encoding="utf-8")
    links = discover.extract_links(html, "https://fontra.com/member-associations/")
    hosts = sorted(u.split("//")[1].rstrip("/") for _, u in links)

    assert hosts == ["lyttonparkro.ca", "moorepark.org", "sedratoronto.ca"]
    assert all("facebook" not in u for _, u in links)          # social links dropped
    assert all("fontra.com" not in u for _, u in links)        # self links dropped
    names = [n for n, _ in links]
    assert "Moore Park Residents Association" in names


def test_directory_links_are_reduced_to_site_roots():
    from leaside import discover

    html = (FIX / "directory.html").read_text(encoding="utf-8")
    links = dict((u, n) for n, u in discover.extract_links(html, "https://fontra.com/x/"))
    # The SEDRA link pointed at /about/ but must come back as the site root.
    assert "https://sedratoronto.ca/" in links


def test_slug_is_a_usable_source_id():
    from leaside import discover

    assert discover.slug("Moore Park Residents Association") == "ra_moore_park_residents_association"
    assert discover.slug("St. Andrew's Ratepayers' Assn.") == "ra_st_andrew_s_ratepayers_assn"
    assert len(discover.slug("A" * 200)) <= 43


def test_a_named_neighbourhood_beats_the_source_default():
    """The Bulldog covers four neighbourhoods. A Moore Park story must not read Leaside.

    Order is: real coordinates, then a neighbourhood named in the text, then the
    source's own default.
    """
    src = CFG.by_id("media_south_bayview_bulldog")
    assert src.area == "leaside"

    story = {"title": "Moore Park ravine works begin", "summary": None}
    assert AREAS.match_text(story["title"], story["summary"]) == "moore_park"

    generic = {"title": "New bakery opens this week", "summary": None}
    assert AREAS.match_text(generic["title"], generic["summary"]) is None
    # ingest falls back to src.area for that one


def test_fetchers_no_longer_stamp_an_area_themselves():
    """Area assignment lives in ingest only. Two places doing it caused mislabelling."""
    import inspect

    from leaside.fetchers import html_list, rss_feed

    for module in (rss_feed, html_list):
        assert '"area": source.area' not in inspect.getsource(module)


def _area_box(key):
    f = next(f for f in AREAS.features if f["properties"]["key"] == key)
    ring = f["geometry"]["coordinates"][0]
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return min(xs), min(ys), max(xs), max(ys)


# Known and not yet fixed. The areas are hand-drawn rectangles, so several overlap,
# and match_point returns the first hit in file order - which makes Leaside win most
# ties. Replacing them with the City's official boundaries is a pending decision,
# because the City merges the two Rosedales and Moore Park into one neighbourhood.
# This test pins the current damage so it cannot quietly grow.
KNOWN_OVERLAPS = {
    ("bennington", "leaside"),
    ("bennington", "north_rosedale"),
    ("davisville", "leaside"),
    ("davisville", "moore_park"),
    ("leaside", "moore_park"),
    ("moore_park", "north_rosedale"),
    ("north_rosedale", "south_rosedale"),
}


def test_area_overlaps_are_the_known_set_and_no_worse():
    import itertools

    boxes = [(k, _area_box(k)) for k in AREAS.keys()]
    found = set()
    for (ka, a), (kb, b) in itertools.combinations(boxes, 2):
        if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
            found.add(tuple(sorted((ka, kb))))
    assert found == KNOWN_OVERLAPS, (
        f"area overlaps changed. new: {found - KNOWN_OVERLAPS}, "
        f"gone: {KNOWN_OVERLAPS - found}"
    )


# ---------------------------------------------------------------- the four review fixes

def _item(**over):
    base = {"source_id": "ra_leaside", "category": "ra_news", "title": "T",
            "url": "https://example.invalid/a", "published_at": None}
    base.update(over)
    return base


def test_fix1_dates_are_stored_in_one_shape_so_sorting_works(tmp_path):
    """Four publisher date formats must sort by real date, not by first character."""
    from leaside import db

    conn = db.connect(tmp_path / "t.db")
    rows = [
        ("newest", "2026/03/01"),                      # slash form
        ("middle", "Wed, 03 Sep 2025 14:00:00 +0000"),  # RSS form
        ("older", "2025-09-02"),                       # plain date
        ("oldest", 1725235200000),                     # ArcGIS epoch milliseconds
    ]
    for title, when in rows:
        db.upsert_item(conn, _item(title=title, url=f"https://x/{title}", published_at=when))
    order = [r[0] for r in conn.execute(
        "SELECT title FROM items ORDER BY published_at DESC").fetchall()]
    assert order == ["newest", "middle", "older", "oldest"]
    stored = conn.execute("SELECT published_at FROM items WHERE title='newest'").fetchone()[0]
    assert stored == "2026-03-01T00:00:00+00:00"


def test_fix2_html_in_summaries_becomes_plain_text(tmp_path):
    from leaside import db

    conn = db.connect(tmp_path / "t.db")
    db.upsert_item(conn, _item(
        title="<b>Bold</b> headline",
        summary='<p>Meeting at <a href="x">Trace Manes</a>.&nbsp;See&amp;hear</p>\n\n<br>',
    ))
    row = conn.execute("SELECT title, summary FROM items").fetchone()
    assert row["title"] == "Bold headline"
    assert row["summary"] == "Meeting at Trace Manes . See&hear"
    assert "<" not in row["summary"]


def test_fix3_demo_never_touches_the_real_database(tmp_path, monkeypatch):
    from leaside import db, demo

    real = tmp_path / "real.db"
    fake = tmp_path / "demo.db"
    monkeypatch.setattr(db, "DEFAULT_DB", real)
    monkeypatch.setattr(db, "DEMO_DB", fake)
    assert demo.run(db_path=fake) > 0
    assert fake.exists()
    assert not real.exists(), "demo wrote to the real database"


def test_fix3b_ingest_purges_demo_rows_that_got_in_earlier(tmp_path):
    from leaside import db, geo, sources

    conn = db.connect(tmp_path / "t.db")
    db.upsert_item(conn, _item(title="[demo] fake thing", url="https://x/demo"))
    db.upsert_item(conn, _item(title="real thing", url="https://x/real"))
    counts = db.refresh_all(conn, geo.Areas.load(), sources.load())
    assert counts["demo_removed"] == 1
    titles = [r[0] for r in conn.execute("SELECT title FROM items")]
    assert titles == ["real thing"]


def test_fix4_existing_rows_get_relabelled_when_logic_improves(tmp_path):
    """A row stored under an old, wrong label must be corrected without refetching."""
    from leaside import db, geo, sources

    conn = db.connect(tmp_path / "t.db")
    db.upsert_item(conn, _item(title="Moore Park ravine works begin", url="https://x/mp",
                               area="leaside", summary="<p>old &amp; ugly</p>",
                               published_at="2025/06/01"))
    # Simulate the bad old state directly: wrong area, raw html, odd date.
    conn.execute("UPDATE items SET area='leaside', summary='<p>old &amp; ugly</p>',"
                 " published_at='2025/06/01'")
    conn.commit()

    counts = db.refresh_all(conn, geo.Areas.load(), sources.load())
    assert counts["changed"] == 1
    row = conn.execute("SELECT area, summary, published_at FROM items").fetchone()
    assert row["area"] == "moore_park"
    assert row["summary"] == "old & ugly"
    assert row["published_at"] == "2025-06-01T00:00:00+00:00"


def test_fix4b_upsert_refreshes_derived_fields_but_never_first_seen(tmp_path):
    from leaside import db

    conn = db.connect(tmp_path / "t.db")
    db.upsert_item(conn, _item(area="leaside", summary="v1"))
    first = conn.execute("SELECT first_seen_at FROM items").fetchone()[0]
    assert db.upsert_item(conn, _item(area="moore_park", summary="v2")) is False
    row = conn.execute("SELECT first_seen_at, area, summary FROM items").fetchone()
    assert row["first_seen_at"] == first
    assert (row["area"], row["summary"]) == ("moore_park", "v2")


# ---------------------------------------------------------------- duplicate accumulation

def test_stable_collision_key_survives_a_dataset_reload():
    """_id is the datastore row number and shifts on reload. ACCNUM does not."""
    from leaside.fetchers.ckan import _stable_id

    before = {"_id": 41, "ACCNUM": "9912345", "DATE": "2025-06-01", "STREET1": "BAYVIEW AVE"}
    after = {"_id": 907, "ACCNUM": "9912345", "DATE": "2025-06-01", "STREET1": "BAYVIEW AVE"}
    assert _stable_id(before) == _stable_id(after)

    # One crash, several people: the City publishes a row each. They collapse to one item.
    person_a = {"_id": 1, "ACCNUM": "9912345", "INVTYPE": "DRIVER"}
    person_b = {"_id": 2, "ACCNUM": "9912345", "INVTYPE": "PASSENGER"}
    assert _stable_id(person_a) == _stable_id(person_b)

    # No collision number: fall back to something reproducible, not the row number.
    bare = {"_id": 5, "DATE": "2025-06-01", "STREET1": "LAIRD DR", "LATITUDE": "43.70"}
    assert _stable_id(bare) == _stable_id({**bare, "_id": 999})


def test_a_record_that_leaves_its_dataset_stays_in_the_log(tmp_path):
    """Datasets used to be treated as photographs: whatever was missing from the
    latest fetch was deleted. That threw away every crime record older than the
    newest 4,000 per offence, on every run. Now nothing is deleted."""
    import time

    from leaside import db, geo, ingest, sources

    conn = db.connect(tmp_path / "t.db")
    db.upsert_item(conn, _item(source_id="tps_reported_crime", category="crime",
                               title="old break-in", url=None, external_id="E1",
                               area="leaside", published_at="2014-01-01"))
    conn.commit()
    time.sleep(1.1)
    db.upsert_item(conn, _item(source_id="tps_reported_crime", category="crime",
                               title="new break-in", url=None, external_id="E2",
                               area="leaside", published_at="2026-06-01"))
    db.refresh_all(conn, geo.Areas.load(), sources.load())
    titles = sorted(r[0] for r in conn.execute(f"SELECT title FROM items WHERE {db.SHOWN}"))
    assert titles == ["new break-in", "old break-in"]
    assert not hasattr(db, "drop_unseen")
    assert "drop_unseen" not in Path(ingest.__file__).read_text(encoding="utf-8")


def test_no_source_is_configured_to_discard_what_it_collects():
    """`snapshot` meant "delete what is missing from the latest fetch". It is gone."""
    raw = (Path(__file__).resolve().parents[1] / "config" / "sources.yaml").read_text(encoding="utf-8")
    assert "snapshot: true" not in raw
    assert not hasattr(CFG.sources[0], "snapshot")

def test_doctor_reports_duplicates_it_is_given(tmp_path):
    from leaside import db, doctor, geo, sources

    conn = db.connect(tmp_path / "t.db")
    for i in (1, 2):
        conn.execute(
            "INSERT INTO items (id, source_id, category, title, url, published_at,"
            " first_seen_at, last_seen_at) VALUES (?,?,?,?,?,?,?,?)",
            (f"row{i}", "city_ksi_collisions", "collision", "Fatal",
             "https://x/same", "2025-06-01T00:00:00+00:00", "2026-09-01", "2026-09-01"),
        )
    conn.commit()
    data = doctor.gather(conn, geo.Areas.load(), sources.load())
    assert data["total"] == 2
    assert data["dup_links"][0]["n"] == 2
    assert "duplicate links: **1**" in doctor.render(data)


# ---------------------------------------------------------------- the reader page

def _seed_reader_db(tmp_path):
    from datetime import datetime, timedelta, timezone

    from leaside import db

    conn = db.connect(tmp_path / "t.db")
    now = datetime.now(timezone.utc)
    run1 = db.start_run(conn)
    db.upsert_item(conn, _item(title="old post", url="https://x/old",
                               published_at=(now - timedelta(days=200)).isoformat()))
    db.upsert_item(conn, _item(title="last week", url="https://x/week",
                               published_at=(now - timedelta(days=7)).isoformat()))
    db.finish_run(conn, run1, {"new": 2, "seen": 2, "failed": 0})
    import time; time.sleep(1.1)
    run2 = db.start_run(conn)
    db.upsert_item(conn, _item(title="brand new", url="https://x/new",
                               summary="<b>fresh</b>", published_at=now.isoformat()))
    db.finish_run(conn, run2, {"new": 1, "seen": 3, "failed": 0})
    conn.commit()
    return conn


def test_page_carries_old_items_but_counts_only_the_window(tmp_path):
    """Late data has to be in the file to be reachable, and out of the default counts."""
    from leaside import geo, render, sources

    conn = _seed_reader_db(tmp_path)
    data = render.collect(conn, geo.Areas.load(), sources.load())
    titles = [it["title"] for it in data["items"]]
    assert titles == ["brand new", "last week", "old post"], "all of it, newest first"
    assert data["in_window"] == 2, "the 200-day-old item is outside the default window"
    assert data["total_stored"] == 3
    assert sum(data["counts"].values()) == 2, "chip counts match the default view"


def test_page_knows_what_arrived_in_the_latest_run(tmp_path):
    from leaside import geo, render, sources

    conn = _seed_reader_db(tmp_path)
    data = render.collect(conn, geo.Areas.load(), sources.load())
    assert data["new_this_run"] == 1
    assert data["latest_run"] > data["previous_run"]


def test_page_carries_what_the_browser_needs(tmp_path):
    from leaside import render

    _seed_reader_db(tmp_path)
    html = render.run(db_path=tmp_path / "t.db", out_name="t.html").read_text(encoding="utf-8")
    assert 'data-when="' in html and 'data-seen="' in html and 'data-id="' in html
    assert 'target="_blank"' in html and 'rel="noopener"' in html
    assert "Leaside Residents Association" in html, "source name, not source id"
    assert "fresh" in html and "<b>fresh</b>" not in html, "summary html was stripped"
    assert "Mark all read" in html


def test_probe_is_skipped_when_checked_this_week(tmp_path, monkeypatch, capsys):
    """Must never reach the network. It once did, for two minutes, and still passed."""
    from leaside import http, probe

    def no_network(*a, **k):
        raise AssertionError("the probe should not have run")

    monkeypatch.setattr(http.Fetcher, "get", no_network)

    report = tmp_path / "probe-report.md"
    report.write_text("recent", encoding="utf-8")
    monkeypatch.setattr(probe, "REPORT", report)

    assert probe.run() == []
    assert "Skipping" in capsys.readouterr().out
    assert probe.is_fresh() is not None, "must read the patched path, not a bound default"
    assert probe.is_fresh(tmp_path / "missing.md") is None

    old = tmp_path / "old-report.md"
    old.write_text("stale", encoding="utf-8")
    os.utime(old, (0, 0))
    assert probe.is_fresh(old) is None, "a report from 1970 is not fresh"


# ---------------------------------------------------------------- field matching

def test_notices_survive_key_names_nobody_told_us():
    """The real feed used names that matched none of the guesses. Match, don't guess."""
    from leaside.fetchers import notices

    src = CFG.by_id("city_public_notices")
    shapes = [
        # camelCase with unfamiliar names
        [{"noticeTitle": "CofA hearing 123 Millwood Rd", "publishDate": "2026-09-01",
          "noticeLink": "/notice/9911.do", "noticeId": 9911, "fullText": "Minor variance"}],
        # nested under a wrapper key, snake_case, absolute url
        {"notices": [{"notice": {"title": "CofA hearing 123 Millwood Rd",
                                 "date_published": "2026-09-01T10:00:00",
                                 "detail_url": "https://secure.toronto.ca/notice/9911.do",
                                 "reference_number": "N-9911",
                                 "description": "Minor variance"}}]},
        # decoys that must lose: an end date, an image link
        [{"title": "CofA hearing 123 Millwood Rd", "endDate": "2099-01-01",
          "publishedOn": "2026-09-01", "imageUrl": "/img/x.png", "url": "/notice/9911.do",
          "id": 9911, "body": "Minor variance"}],
    ]
    for shape in shapes:
        items = notices.parse(json.dumps(shape), src)
        assert len(items) == 1, shape
        it = items[0]
        assert it["title"].startswith("CofA hearing")
        assert it["published_at"] and it["published_at"].startswith("2026-09-01"), shape
        assert it["url"] == "https://secure.toronto.ca/notice/9911.do", shape
        assert "9911" in it["external_id"], shape
        assert it["summary"] == "Minor variance"


def test_collision_rows_survive_renamed_columns():
    from leaside.fetchers import ckan

    src = CFG.by_id("city_ksi_collisions")
    inside = {"lat": 43.705, "lon": -79.365}     # inside the Leaside box
    shapes = [
        {"_id": 1, "ACCNUM": "5001", "DATE": "2026-06-01", "LATITUDE": inside["lat"],
         "LONGITUDE": inside["lon"], "STREET1": "BAYVIEW AVE", "INJURY": "Major"},
        {"_id": 2, "accnum": "5001", "occ_date": "2026-06-01T04:00:00", "lat_wgs84": inside["lat"],
         "long_wgs84": inside["lon"], "street1": "BAYVIEW AVE", "injury": "Major"},
        {"_id": 3, "COLLISION_ID": "5001", "Date": "2026/06/01", "Latitude": str(inside["lat"]),
         "Longitude": str(inside["lon"]), "Street_1": "BAYVIEW AVE", "ACCLASS": "Fatal"},
    ]
    ids = set()
    for row in shapes:
        items = ckan.rows_to_items([row], src, AREAS)
        assert len(items) == 1, row
        it = items[0]
        assert it["area"] == "leaside" and it["lat"] == inside["lat"], row
        from leaside import dates
        assert dates.to_iso(it["published_at"]).startswith("2026-06-01"), row
        assert "5001" in it["external_id"], row
        ids.add(it["external_id"].split(":")[-1])
    assert ids == {"5001"}, "same collision, three column styles, one key"


def test_column_report_names_what_it_could_not_find():
    from leaside.fetchers import ckan

    resolved = ckan.resolved_fields({"_id": 1, "Foo": "bar"})
    assert resolved["date"] is None and resolved["lat"] is None


def test_rows_from_a_retired_source_are_hidden_not_deleted(tmp_path):
    """A source taken out of the config used to have its rows deleted. Now they are
    hidden from the page, kept in the log with the reason, and come back if the
    source does."""
    from leaside import db, geo, sources

    conn = db.connect(tmp_path / "t.db")
    rows = [
        ("no_such_source", "ghost from an old config", "other"),  # not configured at all
        ("fontra_directory", "a scraped link", "registry"),       # configured, manual
        ("ra_north_rosedale", "old newsletter", "ra_news"),       # configured, manual feed
    ]
    for i, (sid, title, cat) in enumerate(rows):
        db.upsert_item(conn, _item(source_id=sid, title=title, category=cat,
                                   url=f"https://x/{i}"))
    conn.commit()

    counts = db.refresh_all(conn, geo.Areas.load(), sources.load())
    assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 3
    shown = sorted(r[0] for r in conn.execute(f"SELECT title FROM items WHERE {db.SHOWN}"))
    assert shown == ["a scraped link", "old newsletter"]
    assert counts["retired_hidden"] == 1
    reason = conn.execute("SELECT hidden_reason FROM items WHERE source_id='no_such_source'").fetchone()[0]
    assert reason == "source no longer configured"
    assert conn.execute("SELECT event, note FROM item_log WHERE event='hidden'").fetchone()[1] == reason
    # Running it again does not hide it twice.
    assert db.refresh_all(conn, geo.Areas.load(), sources.load())["retired_hidden"] == 0

    # The source returns: the row is seen again and comes back.
    db.upsert_item(conn, _item(source_id="no_such_source", title="ghost from an old config",
                               category="other", url="https://x/0"))
    assert conn.execute("SELECT hidden_at FROM items WHERE source_id='no_such_source'").fetchone()[0] is None
    assert [r[0] for r in conn.execute("SELECT event FROM item_log ORDER BY id")][-1] == "back"


def test_doctor_shows_raw_shape_when_dates_or_links_are_missing(tmp_path):
    from leaside import db, doctor, geo, sources

    conn = db.connect(tmp_path / "t.db")
    for i in range(3):
        db.upsert_item(conn, _item(source_id="city_public_notices", title=f"n{i}",
                                   url=None, published_at=None,
                                   raw={"noticeTitle": f"n{i}", "publishDate": "2026-09-01",
                                        "noticeLink": "/notice/1.do"}))
    conn.commit()
    d = doctor.gather(conn, geo.Areas.load(), sources.load())
    out = doctor.render(d)
    assert "What the raw records look like" in out
    assert "`publishDate`" in out and "`noticeLink`" in out


def test_areas_are_only_the_seven_that_were_asked_for():
    """Deer Park, Lytton Park and Bedford Park were dropped: they border, not belong."""
    assert set(AREAS.keys()) == {
        "leaside", "bennington", "north_rosedale", "south_rosedale",
        "moore_park", "davisville", "lawrence_park",
    }
    gone = {"ra_deer_park", "ra_lytton_park", "ra_bedford_park"}
    assert not [s.id for s in CFG.sources if s.id in gone]
    assert not [s.id for s in CFG.sources if s.area and s.area not in AREAS.keys()]


def test_muting_an_area_still_works_even_though_none_is_muted(tmp_path):
    """The switch stays available for the next area that turns out to be noise."""
    from leaside import geo

    assert AREAS.default_off() == set(), "no area is muted today"
    synthetic = geo.Areas([
        {"type": "Feature",
         "properties": {"key": "somewhere", "name": "Somewhere", "default_off": True,
                        "keywords": []},
         "geometry": {"type": "Polygon",
                      "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}},
    ])
    assert synthetic.default_off() == {"somewhere"}


def test_page_switches_off_a_muted_area(tmp_path, monkeypatch):
    from leaside import db, geo, render

    conn = db.connect(tmp_path / "t.db")
    db.upsert_item(conn, _item(title="an item", url="https://x/k", area="leaside",
                               published_at="2026-09-01"))
    conn.commit()
    real = geo.Areas.load

    def muted(*a, **k):
        areas = real(*a, **k)
        for f in areas.features:
            if f["properties"]["key"] == "leaside":
                f["properties"]["default_off"] = True
        return areas

    monkeypatch.setattr(geo.Areas, "load", staticmethod(muted))
    html = render.run(db_path=tmp_path / "t.db", out_name="t.html").read_text(encoding="utf-8")
    assert 'data-area="leaside"' in html
    assert 'aria-pressed="false"' in html


def test_rss_prefers_the_fullest_text_a_feed_offers():
    from leaside.fetchers import rss_feed

    entry = {"title": "T", "summary": "one line teaser",
             "content": [{"value": "the full body, which is considerably longer than the teaser"}]}
    assert "full body" in rss_feed._best_text(entry)
    assert rss_feed._best_text({"title": "T", "summary": "only this"}) == "only this"
    assert rss_feed._best_text({"title": "T"}) == ""


def test_data_sources_point_at_a_page_a_person_can_read():
    for sid in ("city_public_notices", "city_ksi_collisions"):
        home = CFG.by_id(sid).home
        assert home and not home.endswith(".json"), f"{sid} links to raw data"


def test_version_stamp_survives_a_checkout_with_no_git():
    """Every output carries the code version, with or without git on the machine."""
    from leaside import version

    v = version.describe()
    assert v["date"], "no date from git and no file fallback"
    assert v["age_days"] is not None and v["age_days"] >= 0
    assert version.label() != "version unknown"


def test_stale_code_warning_triggers_on_age():
    from leaside import version

    assert version.warn_if_stale(days=-1), "must warn when the threshold is exceeded"
    assert version.warn_if_stale(days=10_000) is None


def test_health_report_and_page_both_state_their_version(tmp_path):
    from leaside import db, doctor, geo, render, sources, version

    conn = db.connect(tmp_path / "t.db")
    db.upsert_item(conn, _item(title="thing", url="https://x/1", area="leaside",
                               published_at="2026-09-01"))
    conn.commit()
    label = version.label()
    report = doctor.render(doctor.gather(conn, geo.Areas.load(), sources.load()))
    assert label in report
    html = render.run(db_path=tmp_path / "t.db", out_name="t.html").read_text(encoding="utf-8")
    assert label in html


# ---------------------------------------------------------------- evidence from the live run

def test_crime_outside_our_neighbourhoods_is_rejected_whatever_the_rectangle_says():
    """A real robbery in North St.James Town was being filed as South Rosedale.

    The rectangle is wide enough to contain it; Toronto Police state the real
    neighbourhood on every record, so that is what decides.
    """
    from leaside.fetchers import arcgis

    src = CFG.by_id("tps_reported_crime")
    downtown = {"features": [{
        "attributes": {"EVENT_UNIQUE_ID": "GO-20261277447", "OCC_DATE": 1781928000000,
                       "OFFENCE": "Robbery - Business", "PREMISES_TYPE": "Commercial",
                       "NEIGHBOURHOOD_158": "North St.James Town (74)"},
        "geometry": {"x": -79.37575275526954, "y": 43.66966190876556}}]}
    assert AREAS.match_point(43.66966190876556, -79.37575275526954) == "south_rosedale", \
        "the rectangle does contain it, which is the bug this guards"
    assert arcgis.parse_features(json.dumps(downtown), src, AREAS) == []

    ours = json.loads(json.dumps(downtown))
    ours["features"][0]["attributes"]["NEIGHBOURHOOD_158"] = "Leaside-Bennington (56)"
    kept = arcgis.parse_features(json.dumps(ours), src, AREAS)
    assert len(kept) == 1
    assert kept[0]["title"] == "Robbery - Business", "the offence is the headline"
    assert "Commercial" in kept[0]["summary"], "premises type goes underneath"
    assert "Leaside-Bennington" in kept[0]["summary"]


def test_crime_with_no_neighbourhood_field_still_uses_the_rectangle():
    """Older layers may not carry the field. Do not throw those away."""
    from leaside.fetchers import arcgis

    src = CFG.by_id("tps_reported_crime")
    raw = json.dumps({"features": [{
        "attributes": {"EVENT_UNIQUE_ID": "GO-1", "OCC_DATE": 1781928000000},
        "geometry": {"x": -79.365, "y": 43.705}}]})
    assert len(arcgis.parse_features(raw, src, AREAS, label="Assault")) == 1


def test_notices_get_a_link_built_from_their_id_because_the_feed_has_none():
    from leaside.fetchers import notices

    src = CFG.by_id("city_public_notices")
    rec = {"noticeId": 7923, "title": "Notice of Application - 2654 Bayview Ave",
           "noticeDate": 1789099200000,
           "noticeDescription": "<p>NOTICE OF APPLICATION</p>",
           "addressList": [{"city": "Toronto", "latitudeCoordinate": "43.705",
                            "longitudeCoordinate": "-79.365"}]}
    it = notices.parse(json.dumps([rec]), src)[0]
    assert it["url"] == "https://secure.toronto.ca/nm/api/individual/notice/7923.do"
    assert it["published_at"] and it["lat"] == 43.705 and it["lon"] == -79.365
    assert "7923" in it["external_id"]


def test_notice_coordinates_place_it_without_reading_street_names():
    from leaside.fetchers import notices

    src = CFG.by_id("city_public_notices")
    rec = {"noticeId": 1, "title": "Notice of Public Meeting", "noticeDate": 1789099200000,
           "addressList": [{"latitudeCoordinate": 43.705, "longitudeCoordinate": -79.365}]}
    it = notices.parse(json.dumps([rec]), src)[0]
    assert AREAS.match_point(it["lat"], it["lon"]) == "leaside"
    # no address list, no coordinates, and that must not crash
    bare = notices.parse(json.dumps([{"noticeId": 2, "title": "No address here",
                                      "noticeDate": 1789099200000}]), src)[0]
    assert bare["lat"] is None and bare["url"].endswith("/2.do")


def test_official_neighbourhood_names_map_to_our_areas():
    assert AREAS.is_official_ours("Leaside-Bennington (56)")
    assert AREAS.is_official_ours("leaside-bennington")
    assert AREAS.is_official_ours("Mount Pleasant East (99)")
    assert not AREAS.is_official_ours("North St.James Town (74)")
    assert not AREAS.is_official_ours("Thorncliffe Park (55)")
    assert not AREAS.is_official_ours(None)
    assert AREAS.match_official("Lawrence Park North (105)") == "lawrence_park"
    # Rosedale-Moore Park covers three of our areas, so coordinates must win
    assert AREAS.match_official("Rosedale-Moore Park (98)") in {
        "north_rosedale", "south_rosedale", "moore_park"}


def test_page_holds_everything_and_narrows_in_the_browser():
    """The file carries all of it; the Since control picks what you look at."""
    from leaside import render

    days = [d for d, _ in render.WINDOW_CHOICES]
    assert render.WINDOW_DAYS in days
    assert 0 in days, "there must be an Everything option for the late data"
    assert max(days) >= 365


def test_dead_feeds_are_gone_but_their_area_is_not():
    """Lawrence Park kept its area when its association feed was dropped.

    The feed had posted nothing since November 2023. City notices and police
    records there are still matched, by coordinates and by official name.
    """
    ids = {s.id for s in CFG.sources}
    assert "ra_lawrence_park" not in ids
    assert "community_leaside_baseball" not in ids
    assert "lawrence_park" in AREAS.keys()
    assert AREAS.is_official_ours("Lawrence Park South (103)")
    assert AREAS.is_official_ours("Lawrence Park North (105)")


def test_every_runnable_source_earns_its_request():
    """One request per source per run. Each one must be able to reach the page."""
    for s in CFG.sources:
        if not s.runnable:
            continue
        assert s.category, s.id
        assert s.home or s.category == "registry", f"{s.id} has nowhere to link"


def test_collision_records_read_as_a_place_not_a_code():
    """Every collision used to render as "Incident" over a division code."""
    from leaside.fetchers import arcgis

    src = CFG.by_id("tps_traffic_collisions")
    raw = json.dumps({"features": [{
        "attributes": {"OBJECTID": 5, "OCC_DATE": 1781928000000,
                       "STREET1": "BAYVIEW AVE", "STREET2": "MILLWOOD RD",
                       "INJURY": "Major", "DIVISION": "D53",
                       "NEIGHBOURHOOD_158": "Leaside-Bennington (56)"},
        "geometry": {"x": -79.365, "y": 43.705}}]})
    it = arcgis.parse_features(raw, src, AREAS, label="Traffic Collision")[0]
    assert it["title"] == "Traffic Collision at BAYVIEW AVE & MILLWOOD RD"
    assert "Major" in it["summary"]
    assert it["lat"] == 43.705 and it["lon"] == -79.365, "so the map link works"
    assert it["title"] != "Incident"


def test_an_intersection_field_is_preferred_over_two_street_names():
    from leaside.fetchers import arcgis

    raw = json.dumps({"features": [{
        "attributes": {"OBJECTID": 1, "OCC_DATE": 1781928000000,
                       "INTERSECTION": "BAYVIEW AVE & MCRAE DR",
                       "STREET1": "BAYVIEW AVE", "ROAD_CLASS": "Major Arterial",
                       "NEIGHBOURHOOD_158": "Leaside-Bennington (56)"},
        "geometry": {"x": -79.365, "y": 43.705}}]})
    it = arcgis.parse_features(raw, CFG.by_id("tps_traffic_collisions"), AREAS,
                               label="Traffic Collision")[0]
    assert it["title"] == "Traffic Collision at BAYVIEW AVE & MCRAE DR"
    assert "Major Arterial" not in it["title"], "road class is not a street name"


def test_layer_labels_are_singular_because_each_item_is_one_event():
    from leaside.fetchers import arcgis as a

    assert a.offence_label("Traffic Collisions Open Data (ASR-T-TBL-001)") == "Traffic Collision"
    assert a.offence_label("Bicycle Thefts Open Data") == "Bicycle Theft"
    assert a.offence_label("Break and Enter Open Data") == "Break and Enter"
    assert a.offence_label("Assault Open Data") == "Assault"


def test_page_warns_that_police_locations_are_approximate(tmp_path):
    from leaside import db, render

    conn = db.connect(tmp_path / "t.db")
    db.upsert_item(conn, _item(source_id="tps_traffic_collisions", category="collision",
                               title="Traffic Collision at Bayview & Millwood", url=None,
                               area="leaside", lat=43.705, lon=-79.365,
                               published_at="2026-09-01"))
    conn.commit()
    html = render.run(db_path=tmp_path / "t.db", out_name="t.html").read_text(encoding="utf-8")
    assert "openstreetmap.org" in html
    assert "Nearest intersection on a map" in html
    assert "nearest road intersection, not" in html
    assert "data.tps.ca" in html, "collisions have no article, so the source page is the link"


def test_generated_files_are_not_tracked_by_git():
    """Committing a file the program rewrites blocks every future `git pull`.

    config/health-report.md was tracked and rewritten on every run, so git saw a
    local edit each time and refused to update. Five sessions of fixes never
    reached the owner's machine because of it.
    """
    import subprocess

    root = pathlib.Path(__file__).resolve().parents[1]
    tracked = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True,
                             text=True, check=True).stdout.split()
    generated = [f for f in tracked
                 if f.endswith(("-report.md", "-catalogue.md"))
                 or f in {"config/health-report.md", "config/probe-report.md"}]
    assert not generated, f"these are outputs and must not be tracked: {generated}"


# ------------------------------------------- evidence from the 12 Sep 12:46 report

def test_collisions_are_described_from_their_flags():
    """The collision layer has no offence field at all, only flags.

    Every record on the page therefore read "Incident". These are the exact
    attributes of OBJECTID 14 as they appeared in the health report.
    """
    from leaside.fetchers import arcgis

    src = CFG.by_id("tps_traffic_collisions")
    real = {"OBJECTID": 14, "EVENT_UNIQUE_ID": "GO-20148000028",
            "OCC_DATE": 1388552400000, "DIVISION": "D53", "FATALITIES": 0,
            "INJURY_COLLISIONS": "NO", "FTR_COLLISIONS": "YES", "PD_COLLISIONS": "NO",
            "NEIGHBOURHOOD_158": "Mount Pleasant East (99)", "AUTOMOBILE": "YES",
            "MOTORCYCLE": "NO", "PASSENGER": "NO", "BICYCLE": "NO", "PEDESTRIAN": "NO"}

    def parse(attrs):
        raw = json.dumps({"features": [{"attributes": attrs,
                                        "geometry": {"x": -79.3776, "y": 43.7012}}]})
        return arcgis.parse_features(raw, src, AREAS, label="Traffic Collision")[0]

    it = parse(real)
    assert it["title"] == "Collision"
    assert "driver failed to remain" in it["summary"]

    assert parse(dict(real, FATALITIES=1, PEDESTRIAN="YES"))["title"] \
        == "Fatal collision involving a pedestrian"
    assert parse(dict(real, INJURY_COLLISIONS="YES", BICYCLE="YES"))["title"] \
        == "Collision with injuries involving a cyclist"
    assert parse(dict(real, FATALITIES=2))["title"] == "Collision, 2 killed"
    assert parse(dict(real, INTERSECTION="BAYVIEW AVE & MCRAE DR"))["title"] \
        == "Collision at BAYVIEW AVE & MCRAE DR"


def test_a_third_street_field_is_a_qualifier_not_a_street():
    """The City puts "10 m West of" in stname3, which read as a street name."""
    from leaside.fetchers import arcgis

    row = {"stname1": "95 REDPATH AVE", "stname2": None, "stname3": "10 m West of",
           "road_class": "Collector", "road_user": "pedestrian", "rdsfcond": "Wet"}
    assert arcgis.streets_of(row) == "95 REDPATH AVE"


def test_city_collision_records_read_as_events():
    """Exactly the record in the report, which had produced no summary at all."""
    from leaside.fetchers import ckan

    row = {"_id": 20702, "collision_id": "2017:7000148860",
           "accdate": "2017-01-24T16:35:00", "stname1": "95 REDPATH AVE",
           "stname2": None, "stname3": "10 m West of", "acclass": "Non-Fatal Injury",
           "impactype": "Pedestrian Collision (internal code)", "light": "Daylight",
           "rdsfcond": "Wet", "injury": "Major", "road_user": "pedestrian",
           "longitude": -79.39241380710648, "latitude": 43.706873182117896,
           "neighbourhood": "South Eglinton-Davisville"}
    it = ckan.rows_to_items([row], CFG.by_id("city_ksi_collisions"), AREAS)[0]
    assert it["title"] == "Pedestrian Collision at 95 REDPATH AVE"
    assert "internal code" not in it["title"], "the City's annotation is stripped"
    assert "Non-Fatal Injury" in it["summary"] and "Major injury" in it["summary"]
    assert it["area"] == "davisville"


def test_one_crash_with_several_people_becomes_one_item():
    """The City publishes a row per person involved, keyed on collision_id."""
    from leaside.fetchers import ckan

    base = {"collision_id": "2017:7000148860", "accdate": "2017-01-24T16:35:00",
            "latitude": 43.705, "longitude": -79.365, "acclass": "Non-Fatal Injury",
            "neighbourhood": "Leaside-Bennington"}
    src = CFG.by_id("city_ksi_collisions")
    a = ckan.rows_to_items([dict(base, _id=1, per_no=1)], src, AREAS)[0]
    b = ckan.rows_to_items([dict(base, _id=99999, per_no=2)], src, AREAS)[0]
    assert a["external_id"] == b["external_id"] == "collision_id:2017:7000148860"
    # keyed on the collision, not on the datastore row number, which shifts on reload
    assert not a["external_id"].startswith(("_id:", "composite:"))


def test_city_collisions_are_also_gated_on_the_official_neighbourhood():
    from leaside.fetchers import ckan

    row = {"collision_id": "x", "accdate": "2020-01-01", "latitude": 43.6696,
           "longitude": -79.3757, "neighbourhood": "North St.James Town"}
    assert ckan.rows_to_items([row], CFG.by_id("city_ksi_collisions"), AREAS) == []
    ours = dict(row, neighbourhood="Leaside-Bennington")
    assert len(ckan.rows_to_items([ours], CFG.by_id("city_ksi_collisions"), AREAS)) == 1


def test_davisville_covers_both_names_the_city_uses_for_it():
    assert AREAS.is_official_ours("Mount Pleasant East (99)")
    assert AREAS.is_official_ours("South Eglinton-Davisville")
    assert AREAS.match_official("South Eglinton-Davisville") == "davisville"


def test_layer_queries_ask_for_newest_first_and_page_through():
    """Without an ordering, a 2000-record cap returned the oldest 2000: all 2014."""
    from leaside.fetchers import arcgis

    assert arcgis.DATE_ORDER.endswith("DESC")
    assert arcgis.query_url("https://x/FeatureServer").endswith("/0/query")
    assert arcgis.query_url("https://x/FeatureServer/3").endswith("/3/query")
    assert arcgis.query_url("https://x/FeatureServer/3/query").endswith("/3/query")


# ---------------------------------------------------------------- the weekly email

def _digest_db(tmp_path):
    from datetime import datetime, timedelta, timezone

    from leaside import db

    conn = db.connect(tmp_path / "t.db")
    now = datetime.now(timezone.utc)
    run = db.start_run(conn)
    db.upsert_item(conn, _item(source_id="city_public_notices", category="city_notice",
                               title="Committee of Adjustment hearing, 123 Millwood Rd",
                               url="https://secure.toronto.ca/nm/api/individual/notice/1.do",
                               summary="Minor variance <b>application</b>", area="leaside",
                               published_at=now.isoformat()))
    db.upsert_item(conn, _item(source_id="tps_reported_crime", category="crime",
                               title="Break and Enter", url=None, area="leaside",
                               published_at=(now - timedelta(days=5)).isoformat()))
    db.finish_run(conn, run, {"new": 2, "seen": 2, "failed": 0})
    conn.commit()
    return conn


def test_digest_reports_what_arrived_since_the_last_one(tmp_path):
    from leaside import digest, geo, sources

    conn = _digest_db(tmp_path)
    data = digest.gather(conn, geo.Areas.load(), sources.load())
    assert data["total"] == 2
    names = [name for name, _ in data["sections"]]
    assert names.index("City notices") < names.index("Reported crime"), \
        "things needing a response come before the record-keeping"


def test_digest_covers_a_missed_week_rather_than_losing_it(tmp_path):
    from leaside import db, digest, geo, sources

    conn = _digest_db(tmp_path)
    db.record_digest(conn, 2, True, "first")
    data = digest.gather(conn, geo.Areas.load(), sources.load())
    assert data["total"] == 0, "already reported"

    import time
    time.sleep(1.1)                       # timestamps are second-resolution
    db.upsert_item(conn, _item(source_id="ra_leaside", title="something new",
                               url="https://x/new", published_at="2026-09-12T00:00:00+00:00"))
    conn.commit()
    later = digest.gather(conn, geo.Areas.load(), sources.load())
    assert later["total"] == 1, "a week with one new item reports one item"
    assert later["sections"][0][1][0]["title"] == "something new"


def test_digest_caps_a_huge_first_email_but_says_so(tmp_path):
    from leaside import digest, geo, sources

    conn = _digest_db(tmp_path)
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for i in range(digest.MAX_ITEMS + 15):
        db.upsert_item(conn, _item(source_id="tps_reported_crime", category="crime",
                                   title=f"Assault {i}", url=None, area="leaside",
                                   published_at=today))
    conn.commit()
    data = digest.gather(conn, geo.Areas.load(), sources.load())
    assert data["shown"] == digest.MAX_ITEMS
    assert data["overflow"] > 0
    assert f"{data['overflow']} more" in digest.render_text(data)
    assert f"{data['overflow']} more" in digest.render_html(data)


def test_digest_email_is_safe_and_self_contained(tmp_path):
    from leaside import digest, geo, sources

    conn = _digest_db(tmp_path)
    data = digest.gather(conn, geo.Areas.load(), sources.load())
    html_body = digest.render_html(data)
    text_body = digest.render_text(data)

    assert "<b>application</b>" not in html_body, "publisher markup must be escaped"
    assert "Minor variance" in html_body and "Minor variance" in text_body
    assert "secure.toronto.ca" in html_body, "items must be clickable"
    assert "data.tps.ca" in text_body, "a record with no article links to its source"
    assert "nearest intersection" in html_body, "the location caveat travels with the email"
    assert "style=" in html_body and "flex" not in html_body, "email clients need inline styles"
    assert digest.subject(data).startswith("Leaside: 2 new items")


def test_digest_says_so_when_nothing_happened(tmp_path):
    from leaside import digest, geo, sources

    conn = db.connect(tmp_path / "empty.db")
    data = digest.gather(conn, geo.Areas.load(), sources.load())
    assert data["total"] == 0
    assert "nothing new" in digest.subject(data).lower()
    assert "Nothing new this week" in digest.render_html(data)


def test_digest_refuses_to_send_without_credentials(tmp_path, monkeypatch):
    from leaside import digest

    conn = _digest_db(tmp_path)
    conn.commit()
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("DIGEST_TO", raising=False)
    with pytest.raises(RuntimeError, match="RESEND_API_KEY"):
        digest.run(db_path=tmp_path / "t.db")


def test_digest_uses_the_only_sender_the_free_tier_allows():
    """Resend permits onboarding@resend.dev and the account owner's address only."""
    from leaside import digest

    assert "onboarding@resend.dev" in digest.SENDER


# ---------------------------------------------------------------- the bug sweep

def test_paging_stops_on_the_servers_signal_not_on_the_requested_page_size():
    """ArcGIS caps a page at its own maxRecordCount, often 1000, whatever we asked.

    Judging "last page" by our requested 2000 would have stopped after page one on
    every such server, silently returning half the data.
    """
    from leaside.fetchers import arcgis

    calls = []

    class Resp:
        status_code = 200

        def __init__(self, payload):
            self.text = json.dumps(payload)

        def raise_for_status(self):
            pass

    class Http:
        def get(self, url, params=None, **kw):
            calls.append(params["resultOffset"])
            feature = {"attributes": {"EVENT_UNIQUE_ID": f"GO-{len(calls)}",
                                      "OCC_DATE": 1781928000000,
                                      "NEIGHBOURHOOD_158": "Leaside-Bennington (56)"},
                       "geometry": {"x": -79.365, "y": 43.705}}
            # A server that returns 1000 a page and says whether more remain.
            if len(calls) < 3:
                return Resp({"features": [feature] * 1000, "exceededTransferLimit": True})
            return Resp({"features": [feature] * 37, "exceededTransferLimit": False})

    src = CFG.by_id("tps_traffic_collisions")
    items, _ = arcgis.fetch_features(src, Http(), AREAS, layer_url="https://x/FeatureServer/0",
                                     label="Collision")
    assert calls == [0, 1000, 2000], "offsets must advance by what was received"
    assert len(items) == 2037


def test_paging_falls_back_to_table_order_when_the_layer_has_no_date_field():
    from leaside.fetchers import arcgis

    seen = []

    class Resp:
        status_code = 200

        def __init__(self, payload):
            self.text = json.dumps(payload)

        def raise_for_status(self):
            pass

    class Http:
        def get(self, url, params=None, **kw):
            seen.append(params.get("orderByFields"))
            if params.get("orderByFields"):
                return Resp({"error": {"code": 400, "message": "Invalid field: OCC_DATE"}})
            return Resp({"features": [], "exceededTransferLimit": False})

    src = CFG.by_id("tps_traffic_collisions")
    arcgis.fetch_features(src, Http(), AREAS, layer_url="https://x/FeatureServer/0")
    assert seen == [arcgis.DATE_ORDER, None], "one rejected sort, then unsorted"


def test_digest_dates_do_not_use_flags_windows_rejects():
    """strftime("%-d") is a glibc extension; on Windows it raises ValueError."""
    from leaside import digest

    assert digest._day("2026-09-05T14:04:00+00:00") == "Sat 5 Sep"
    assert digest._day("2026-12-25") == "Fri 25 Dec"
    assert digest._day(None) == ""
    import ast
    import inspect
    # Look at real strftime calls in the code, not at comments or strings elsewhere.
    tree = ast.parse(inspect.getsource(digest))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "strftime":
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    assert "%-" not in arg.value, f"glibc-only flag in {arg.value!r}"


def test_probe_does_not_call_an_empty_reply_json():
    from leaside import probe

    class Resp:
        status_code = 200
        text = ""
        content = b""
        headers = {"content-type": "application/json"}

    assert probe._classify(Resp())[0] == "empty"

    class Real(Resp):
        text = '[{"a": 1}]'
        content = text.encode()

    assert probe._classify(Real())[0] == "json"


def test_health_report_does_not_dump_keys_for_sources_that_never_have_links(tmp_path):
    """Crime and collision rows have no article by design. Dumping their raw keys on
    every weekly report was noise that buried the section's real purpose."""
    from leaside import db, doctor, geo, sources

    conn = db.connect(tmp_path / "t.db")
    for i in range(3):
        db.upsert_item(conn, _item(source_id="tps_reported_crime", category="crime",
                                   title=f"Assault {i}", url=None, area="leaside",
                                   published_at="2026-09-01",
                                   raw={"OFFENCE": "Assault", "OCC_DATE": 1}))
    conn.commit()
    out = doctor.render(doctor.gather(conn, geo.Areas.load(), sources.load()))
    assert "What the raw records look like" not in out

    # ...but a source that SHOULD have links and does not still gets its keys shown.
    db.upsert_item(conn, _item(source_id="city_public_notices", category="city_notice",
                               title="n", url=None, published_at="2026-09-01",
                               raw={"noticeId": 1, "title": "n"}))
    conn.commit()
    out = doctor.render(doctor.gather(conn, geo.Areas.load(), sources.load()))
    assert "What the raw records look like" in out and "`noticeId`" in out


def test_undated_sample_is_a_date_that_failed_not_a_date_that_was_missing():
    import inspect

    from leaside import ingest

    src = inspect.getsource(ingest)
    assert 'if it.get("published_at")\n                              and dates.to_iso' in src


def test_launcher_stubs_never_need_to_change():
    """cmd and bash read a script while it runs. If the update step rewrote the file
    being executed, the rest of the run would be garbage. So the double-click file
    only pulls and hands over; the real work lives where an update can replace it."""
    root = pathlib.Path(__file__).resolve().parents[1]
    win = (root / "run-windows.bat").read_text(encoding="utf-8")
    inner = (root / "scripts" / "run-windows-main.bat").read_text(encoding="utf-8")
    assert "git pull" in win and "call" in win and "run-windows-main.bat" in win
    assert "Step 1 of 4" not in win and "Step 1 of 4" in inner
    assert "leaside.cli ingest" not in win and "leaside.cli ingest" in inner
    assert "MUST NEVER CHANGE" in win

    mac = (root / "run-mac.command").read_text(encoding="utf-8")
    mac_inner = (root / "scripts" / "run-mac-main.sh").read_text(encoding="utf-8")
    assert "git pull" in mac and "run-mac-main.sh" in mac
    assert "leaside.cli ingest" not in mac and "leaside.cli ingest" in mac_inner


def test_first_ever_digest_is_the_recent_fortnight_not_the_archive(tmp_path):
    """On a fresh database everything is "first seen now". The first real GitHub
    run counted 9,910 new items, most of them collisions from years ago."""
    from datetime import datetime, timedelta, timezone

    from leaside import db, digest, geo, sources

    conn = db.connect(tmp_path / "t.db")
    now = datetime.now(timezone.utc)
    run = db.start_run(conn)
    db.upsert_item(conn, _item(title="this week", url="https://x/1",
                               published_at=now.isoformat()))
    db.upsert_item(conn, _item(title="2014 collision", url="https://x/2",
                               category="collision", source_id="tps_traffic_collisions",
                               published_at=(now - timedelta(days=4000)).isoformat()))
    db.upsert_item(conn, _item(title="undated", url="https://x/3", published_at=None))
    db.finish_run(conn, run, {"new": 3, "seen": 3, "failed": 0})
    conn.commit()

    first = digest.gather(conn, geo.Areas.load(), sources.load())
    titles = {it["title"] for _, items in first["sections"] for it in items}
    assert titles == {"this week", "undated"}, "the archive stays out of the first email"

    # After a digest has gone out, the boundary is the digest, not the calendar.
    db.record_digest(conn, first["total"], True, "sent")
    import time; time.sleep(1.1)
    db.upsert_item(conn, _item(title="old but newly published", url="https://x/4",
                               published_at=(now - timedelta(days=400)).isoformat()))
    conn.commit()
    later = digest.gather(conn, geo.Areas.load(), sources.load())
    assert {it["title"] for _, items in later["sections"] for it in items} \
        == {"old but newly published"}


def test_workflow_sets_git_identity_where_it_commits():
    """Both scheduled runs failed with 'empty ident name': the identity was set
    in the checkout, then the commit happened in a freshly initialised repo."""
    root = pathlib.Path(__file__).resolve().parents[1]
    wf = (root / ".github/workflows/weekly-digest.yml").read_text(encoding="utf-8")
    # The save step now lives in scripts/state.sh, shared with the daily publish.
    save = (root / "scripts/state.sh").read_text(encoding="utf-8")
    save = save[save.index("save)"):]
    init_at = save.index("git init")
    ident_at = save.index('git config user.name')
    commit_at = save.index("git commit")
    assert init_at < ident_at < commit_at, "identity must be set after init, before commit"
    assert "::error" in wf and "RESEND_API_KEY" in wf, "missing secrets must be an annotation"


# ---------------------------------------------------------------- trends

def _trend_db(tmp_path, now):
    """Break and Enter: 3 a month last year, 5 a month this year, data to June."""
    from datetime import timedelta

    from leaside import db

    conn = db.connect(tmp_path / "t.db")
    n = 0
    for year, per_month, months in ((now.year - 1, 3, range(1, 13)),
                                    (now.year, 5, range(1, 7))):
        for m in months:
            for k in range(per_month):
                n += 1
                db.upsert_item(conn, _item(
                    source_id="tps_reported_crime", category="crime",
                    title="Break and Enter at SOMEWHERE", url=None, area="leaside",
                    published_at=f"{year:04d}-{m:02d}-15T12:00:00+00:00",
                    raw={"CSI_CATEGORY": "Break and Enter"}, external_id=f"be{n}"))
    conn.commit()
    return conn


def test_trends_compare_the_same_months_in_both_years():
    """Data reaches June. Comparing Jan-Jun this year with all of last year would
    make every offence look like it fell. The window is cut at the newest month."""
    from datetime import datetime, timezone

    from leaside import trends

    now = datetime(2026, 9, 29, tzinfo=timezone.utc)
    months = {}
    for m in range(1, 13):
        months[f"2025-{m:02d}"] = 3
    for m in range(1, 7):
        months[f"2026-{m:02d}"] = 5
    s = trends.summarise(months, now)
    assert s["upto"] == 6 and s["window_label"] == "Jan to Jun"
    assert s["ytd"] == 30 and s["ytd_prior"] == 18 and s["delta"] == 12
    assert s["lag_months"] == 3
    assert s["this_year"][:6] == [5] * 6 and s["this_year"][6:] == [None] * 6, \
        "months after the newest data are unknown, not zero"
    assert s["last_year"] == [3] * 12


def test_trends_withhold_a_delta_when_last_year_is_incomplete():
    """The crime source keeps the newest 4000 per offence. If that reaches only
    part-way into last year, a fall is an artefact of the cap."""
    from datetime import datetime, timezone

    from leaside import trends

    now = datetime(2026, 9, 29, tzinfo=timezone.utc)
    months = {f"2025-{m:02d}": 3 for m in range(8, 13)}      # data starts Aug 2025
    months.update({f"2026-{m:02d}": 5 for m in range(1, 7)})
    s = trends.summarise(months, now)
    assert s["complete"] is False
    assert s["ytd"] == 30 and s["ytd_prior"] is None and s["delta"] is None


def test_trends_say_no_data_when_the_newest_record_is_from_a_past_year():
    """The City's serious-injury dataset lagged to April 2024 in September 2026."""
    from datetime import datetime, timezone

    from leaside import trends

    now = datetime(2026, 9, 29, tzinfo=timezone.utc)
    s = trends.summarise({"2024-03": 2, "2024-04": 1}, now)
    assert s["upto"] == 0 and s["ytd"] is None and s["delta"] is None
    assert s["window_label"] == "no data yet this year"
    assert s["newest_label"] == "Apr 2024"
    assert all(v is None for v in s["this_year"])


def test_trends_build_reads_the_offence_from_the_record(tmp_path):
    from datetime import datetime, timezone

    from leaside import geo, trends

    now = datetime(2026, 9, 29, tzinfo=timezone.utc)
    conn = _trend_db(tmp_path, now)
    data = trends.build(conn, geo.Areas.load(), now)
    names = [f["name"] for f in data["crime"]["facets"]]
    assert names == ["Break and Enter"]
    f = data["crime"]["facets"][0]
    assert f["ytd"] == 30 and f["ytd_prior"] == 18
    assert data["crime"]["total"]["ytd"] == 30
    assert data["crime"]["by_area"][0]["area"] == "Leaside"
    assert data["collisions"]["facets"] == []


def test_offence_names_are_tidied_and_ordered():
    from leaside import trends

    assert trends._offence("Robbery - Mugging at X", None) == "Robbery"
    assert trends._offence("Theft From Motor Vehicle Under at X", None) == "Theft From Motor Vehicle"
    assert trends._offence("anything", json.dumps({"CSI_CATEGORY": "Auto Theft"})) == "Auto Theft"
    assert trends._order(["Assault", "Zebra", "Break and Enter"]) == \
        ["Break and Enter", "Assault", "Zebra"]


def test_facet_geometry_leaves_a_gap_for_unknown_months():
    from leaside import trends

    facet = {"this_year": [5] * 6 + [None] * 6, "last_year": [3] * 12, "upto": 6}
    d = trends.decorate(facet)
    assert d["ymax"] == 6, "5 rounds up to an even 6 so the midpoint tick is whole"
    assert d["path_this"].count("M") == 1 and d["path_this"].count("L") == 5
    assert d["path_last"].count("L") == 11
    assert d["unknown_x"] is not None, "the still-arriving band starts at the newest month"
    assert d["end_label"] == 5 and d["end_idx"] == 5
    assert trends.nice_max([0, None]) == 1 and trends.nice_max([37]) == 40
    assert trends.nice_max([15]) == 16, "even, so the midpoint tick is a whole number"
    assert trends.nice_max([5]) == 6 and trends.nice_max([3]) == 4
    assert d["svg_w"] > d["w"], "tick labels need a gutter or they clip"
    top = trends.decorate({"this_year": [10] * 6 + [None] * 6, "last_year": [1] * 12, "upto": 6})
    assert top["end_y"] >= 9, "an end label at the maximum must not leave the box"


# --- Publishing to GitHub Pages ---------------------------------------------

def test_every_published_page_tells_search_engines_not_to_list_it(tmp_path, monkeypatch):
    """Public but not searchable: the page is on the open web, and the owner does
    not want it in search results. The noindex tag is the mechanism that works.
    A robots.txt Disallow would not: a crawler that is told not to fetch the page
    never sees the noindex and can still list the bare address."""
    from leaside import demo, render
    monkeypatch.setattr(render, "OUT", tmp_path)
    demo.run(db_path=tmp_path / "demo.db")
    render.run(db_path=tmp_path / "demo.db", out_name="index.html")
    for name in ("index.html", "trends.html"):
        page = (tmp_path / name).read_text(encoding="utf-8")
        assert '<meta name="robots" content="noindex, nofollow">' in page, name
    # GitHub Pages must serve the folder as-is, not run Jekyll over it.
    assert (tmp_path / ".nojekyll").exists()


def test_digest_links_to_the_live_page_only_when_there_is_one(monkeypatch):
    from leaside import digest
    data = {"total": 1, "since": "2026-09-01T00:00:00Z", "overflow": 0,
            "sections": [("Local news", [{"title": "A", "link": "https://x/a",
                                         "area_name": "Leaside", "source_name": "S",
                                         "published_at": "2026-09-02T00:00:00Z",
                                         "summary": ""}])]}
    monkeypatch.delenv("SITE_URL", raising=False)
    assert "github.io" not in digest.render_html(data)
    assert "full page" not in digest.render_text(data)
    monkeypatch.setenv("SITE_URL", "https://someone.github.io/leaside-tracker")
    html_out = digest.render_html(data)
    assert 'href="https://someone.github.io/leaside-tracker/"' in html_out
    assert 'href="https://someone.github.io/leaside-tracker/trends.html"' in html_out
    assert "https://someone.github.io/leaside-tracker/" in digest.render_text(data)


def test_both_workflows_share_the_state_script_and_one_concurrency_group():
    """Two workflows save the same database to the same branch. If they ever ran
    at once, one would overwrite the other's week of collection."""
    import yaml
    root = Path(__file__).resolve().parents[1]
    wf = {n: yaml.safe_load((root / ".github" / "workflows" / n).read_text(encoding="utf-8"))
          for n in ("weekly-digest.yml", "publish-site.yml")}
    groups = {w["concurrency"]["group"] for w in wf.values()}
    assert len(groups) == 1
    for name, w in wf.items():
        text = (root / ".github" / "workflows" / name).read_text(encoding="utf-8")
        assert "scripts/state.sh restore" in text and "scripts/state.sh save" in text, name
    pub = wf["publish-site.yml"]
    assert pub["permissions"] == {"contents": "write", "pages": "write", "id-token": "write"}
    assert "17 10 * * *" in str(pub[True]["schedule"])  # YAML reads the key `on` as True


# ---------------------------------------------------------------- live and daily sources

def _src(**over):
    base = dict(id="s", name="S", kind="rss", status="guess", category="x", area=None,
                url=None, timeout=None, retries=None, candidates=[], extra={})
    base.update(over)
    return sources.Source(**base)


def test_postal_codes_map_to_areas_as_a_fallback():
    assert AREAS.match_postal("M4G 1A1") == "leaside"
    assert AREAS.match_postal("m4t2k9") == "moore_park"
    assert AREAS.match_postal("M5V 1J1") is None
    assert AREAS.match_postal("") is None and AREAS.match_postal(None) is None


def test_police_calls_parse_from_web_mercator_and_keep_only_our_areas():
    """The live layer answers in metres unless told otherwise, and one call in the
    fixture has no geometry at all. Both must still land in the right area."""
    from leaside.fetchers import c4s
    text = (FIX / "c4s_calls.json").read_text(encoding="utf-8")
    stats = {}
    items = c4s.parse_calls(text, _src(id="tps_calls_for_service", category="police_call"),
                            AREAS, stats=stats)
    assert stats == {"features": 3, "no_geometry": 1, "outside_areas": 1, "kept": 2}
    by_title = {it["title"]: it for it in items}
    assert "Check Address near BAYVIEW AVE & MILLWOOD RD" in by_title
    first = by_title["Check Address near BAYVIEW AVE & MILLWOOD RD"]
    assert first["area"] == "leaside"
    assert abs(first["lat"] - 43.708) < 0.01 and abs(first["lon"] - (-79.364)) < 0.01
    assert first["published_at"].startswith("2025-10-03T11:15")
    assert "Police attended at 07:15" in first["summary"]
    assert "D53 Division" in first["summary"]
    assert first["external_id"] == "event:P26-1001"
    # No geometry: matched by the intersection text, keyed by a composite.
    second = by_title["Collision near EGLINTON AVE E & LAIRD DR"]
    assert second["area"] == "leaside" and second["lat"] is None
    assert second["external_id"].startswith("composite:2025-10-03")


def test_police_call_layer_discovery_tries_candidates_then_walks_the_directory():
    from leaside.fetchers import c4s

    class R:
        def __init__(self, body): self._b = body
        def json(self): return self._b

    calls = []

    class H:
        def get(self, url, **kw):
            calls.append(url)
            if url.startswith("https://bad.example/"):
                raise ConnectionError("nope")
            if url == "https://dir.example/arcgis/rest/services?f=json":
                return R({"folders": ["CADPublic"], "services": []})
            if url == "https://dir.example/arcgis/rest/services/CADPublic?f=json":
                return R({"services": [{"name": "CADPublic/Boundaries", "type": "MapServer"},
                                       {"name": "CADPublic/C4S_Public", "type": "FeatureServer"}]})
            if url.endswith("C4S_Public/FeatureServer/0?f=json"):
                return R({"fields": [{"name": "OBJECTID"}]})
            return R({"error": {"message": "Invalid URL"}})

    src = _src(id="t", kind="tps_calls", candidates=["https://bad.example/x/FeatureServer/0",
                                                   "https://dir.example/arcgis/rest/services/Nope/MapServer/0"])
    orig = c4s.DIRECTORIES
    c4s.DIRECTORIES = ("https://dir.example/arcgis/rest/services",)
    try:
        assert c4s.find_layer(src, H()) == \
            "https://dir.example/arcgis/rest/services/CADPublic/C4S_Public/FeatureServer/0"
    finally:
        c4s.DIRECTORIES = orig
    assert calls[0].startswith("https://bad.example/")


def test_building_permits_become_one_item_per_permit_matched_by_street_or_postal():
    from leaside.fetchers import ckan
    rows = json.loads((FIX / "permits_rows.json").read_text(encoding="utf-8"))
    stats = {}
    items = ckan.permit_rows_to_items(rows, _src(id="city_building_permits", category="permit"),
                                      AREAS, stats=stats)
    assert stats == {"rows": 4, "outside_areas": 1, "kept": 2}
    house, furnace = items
    assert house["title"] == "New Building: 123 Rumsey Rd"
    assert house["area"] == "leaside"                      # Rumsey is a Leaside keyword
    assert house["published_at"] == "2026-09-28"               # issued beats applied
    assert "Estimated $1.9M" in house["summary"]
    assert "1 new unit, 1 lost" in house["summary"]
    assert "Status: Permit Issued" in house["summary"]
    assert "Applied 2 Sep 2026" in house["summary"] and "Issued 28 Sep 2026" in house["summary"]
    assert house["external_id"] == "permit:26 123456 BLD"
    assert furnace["title"] == "Mechanical: 9 Heath St E"
    assert furnace["area"] == "moore_park"                 # heath street keyword; M4T agrees
    assert furnace["published_at"] == "2026-09-30"


def test_permit_columns_are_resolved_from_the_datastore_field_list():
    from leaside.fetchers import ckan
    names = ["_id", "PERMIT_NUM", "REVISION_NUM", "PERMIT_TYPE", "STREET_NUM", "STREET_NAME",
             "STREET_TYPE", "POSTAL", "APPLICATION_DATE", "ISSUED_DATE", "STATUS",
             "DESCRIPTION", "EST_CONST_COST", "WORK"]
    cols = {role: ckan.column(names, **spec) for role, spec in ckan.PERMIT_ROLES.items()}
    assert cols == {"postal": "POSTAL", "num": "STREET_NUM", "street": "STREET_NAME",
                    "stype": "STREET_TYPE", "desc": "DESCRIPTION", "work": "WORK",
                    "status": "STATUS", "cost": "EST_CONST_COST",
                    "applied": "APPLICATION_DATE", "issued": "ISSUED_DATE",
                    "permit": "PERMIT_NUM"}


def test_dinesafe_groups_infractions_per_inspection_and_logs_clean_passes_as_routine():
    from leaside.fetchers import ckan
    rows = json.loads((FIX / "dinesafe_rows.json").read_text(encoding="utf-8"))
    stats = {}
    items = ckan.inspection_rows_to_items(rows, _src(id="city_dinesafe", category="inspection"),
                                          AREAS, stats=stats)
    assert stats == {"rows": 4, "inspections": 3, "outside_areas": 1, "routine": 1, "kept": 1}
    pizza, cafe = items
    assert cafe["title"] == "Pass: LAIRD CAFE" and cafe["routine"] is True
    assert pizza["routine"] is False
    assert pizza["title"] == "Conditional Pass: BAYVIEW PIZZA"
    assert pizza["area"] == "leaside" and pizza["lat"] == 43.7075
    assert "Infractions: 1 significant, 1 minor" in pizza["summary"]
    assert "1600 BAYVIEW AVE" in pizza["summary"]
    assert "free of pests" in pizza["summary"]
    assert "Action:" not in pizza["summary"]              # a notice to comply is routine
    assert pizza["external_id"] == "inspection:105000881"
    assert pizza["published_at"] == "2026-09-29"


def test_dinesafe_pass_with_infractions_is_kept_and_says_so():
    from leaside.fetchers import ckan
    rows = json.loads((FIX / "dinesafe_rows.json").read_text(encoding="utf-8"))
    rows[0]["Establishment Status"] = rows[1]["Establishment Status"] = "Pass"
    title, summary, notable = ckan.describe_inspection(rows[:2])
    assert notable and title == "Pass with 2 infractions: BAYVIEW PIZZA"
    _, _, clean = ckan.describe_inspection([rows[2]])
    assert not clean


def test_digest_counts_police_calls_instead_of_listing_them(tmp_path):
    from leaside import db, digest
    conn = db.connect(tmp_path / "t.db")
    for i in range(30):
        db.upsert_item(conn, _item(source_id="tps_calls_for_service", category="police_call",
                                   title=f"{'Check Address' if i % 3 else 'Theft'} near X & Y",
                                   url=None, area="leaside" if i % 2 else "davisville",
                                   external_id=f"event:{i}", published_at="2026-10-02"))
    db.upsert_item(conn, _item(title="A real story", external_id="story",
                               published_at="2026-10-02"))
    conn.commit()
    data = digest.gather(conn, geo.Areas.load(), sources.load())
    assert data["total"] == 1                              # calls do not count as items
    assert [n for n, _ in data["sections"]] == ["Residents' associations"]
    assert data["calls"]["total"] == 30
    assert data["calls"]["kinds"][0] == ("Check Address", 20)
    assert dict(data["calls"]["areas"]) == {"Leaside": 15, "Davisville": 15}
    html_out = digest.render_html(data)
    assert "Police attended 30 calls" in html_out and "Check Address (20)" in html_out
    assert "POLICE CALLS: 30 attended" in digest.render_text(data)
    assert "Leaside 15" in digest.render_text(data)


def test_digest_subject_when_only_police_calls_are_new():
    from leaside import digest
    data = {"total": 0, "sections": [], "overflow": 0, "since": "2026-09-25T00:00:00+00:00",
            "calls": {"total": 12, "kinds": [("Theft", 5)], "areas": [("Leaside", 12)]}}
    assert digest.subject(data) == "Leaside: police attended 12 calls, nothing else new"
    assert "Nothing new this week" not in digest.render_html(data)


def test_page_shows_a_police_calls_strip_for_the_last_week(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from leaside import db, render
    conn = db.connect(tmp_path / "t.db")
    now = datetime.now(timezone.utc)
    for i, days in enumerate((0, 1, 3, 20)):
        db.upsert_item(conn, _item(source_id="tps_calls_for_service", category="police_call",
                                   title="Check Address near BAYVIEW AVE & MILLWOOD RD",
                                   url=None, area="leaside", external_id=f"event:{i}",
                                   lat=43.708, lon=-79.364,
                                   published_at=(now - timedelta(days=days)).isoformat()))
    conn.commit()
    monkeypatch.setattr(render, "OUT", tmp_path)
    html_out = render.run(db_path=tmp_path / "t.db", out_name="t.html").read_text(encoding="utf-8")
    assert "Police calls, last 7 days" in html_out
    assert "3 attended" in html_out                        # the 20-day-old one is not live
    assert "Check Address 3" in html_out
    assert "Nearest intersection on a map" in html_out


def test_probe_reports_which_candidate_answered():
    from leaside import probe

    class Resp:
        def __init__(self, status, body, ctype="application/json"):
            self.status_code, self.text, self.content = status, body, body.encode()
            self.headers = {"content-type": ctype}

    class H:
        def get(self, url, **kw):
            if "good" in url:
                return Resp(200, '{"fields": []}')
            return Resp(404, "not found", "text/html")

    src = _src(id="t", kind="tps_calls",
               candidates=["https://a.example/bad/0", "https://a.example/good/0"])
    r = probe.probe_one(src, H())
    assert r["ok"] and r["url"] == "https://a.example/good/0"
    assert "tried 2" in r["detail"]


def test_new_sources_are_configured_and_runnable():
    cfg = sources.load()
    ids = {s.id: s for s in cfg.sources}
    for sid, kind in (("tps_calls_for_service", "tps_calls"),
                      ("city_building_permits", "ckan_permits"),
                      ("city_dinesafe", "ckan_dinesafe"),
                      ("news_police_coverage", "rss"),
                      ("news_leaside_coverage", "rss")):
        assert ids[sid].kind == kind and ids[sid].runnable, sid
    assert ids["tps_news_releases"].runnable is False      # 403: never scraped
    assert len(ids["tps_calls_for_service"].candidates) >= 3


# ---------------------------------------------------------------- the complete log

def test_dinesafe_live_columns_keep_restaurants_apart():
    """The City's live dataset names its columns estId, estName, typeDesc. The parser
    only knew "Establishment ID", so every inspection on one date shared the key
    "None|<date>" and different restaurants merged into one item."""
    from leaside.fetchers import ckan
    def row(est, name, status, detail, sev, date="2026-09-01"):
        return {"_id": 1, "unique_id": est + date + (detail or ""), "estId": est,
                "oldEstId": "None", "estName": name, "address": "1600 Bayview Ave None M4G 3B7",
                "inspectionStatus": status, "inspectionDate": date,
                "typeDesc": detail, "deficiencyDesc": "05. MAINTENANCE" if detail else None,
                "severity": sev, "OutcomeDesc": "None", "amountFined": None,
                "latitude": "43.7075", "longitude": "-79.3764"}
    rows = [row("A1", "BAYVIEW PIZZA", "Pass", "FAIL TO PROVIDE SOAP - SEC. 7", "M - Minor"),
            row("A1", "BAYVIEW PIZZA", "Pass", "FAIL TO MAINTAIN THERMOMETER", "M - Minor"),
            row("B2", "LAIRD CAFE", "Pass", None, None)]
    stats = {}
    items = ckan.inspection_rows_to_items(rows, _src(id="city_dinesafe", category="inspection"),
                                          AREAS, stats=stats)
    assert stats["inspections"] == 2
    by_key = {it["external_id"]: it for it in items}
    assert set(by_key) == {"inspection:A1|2026-09-01", "inspection:B2|2026-09-01"}
    pizza = by_key["inspection:A1|2026-09-01"]
    assert pizza["title"] == "Pass with 2 infractions: BAYVIEW PIZZA"
    assert pizza["routine"] is False
    assert "FAIL TO PROVIDE SOAP" in pizza["summary"]
    assert "None" not in pizza["summary"].split(" · ")[0]           # "1600 Bayview Ave M4G 3B7"
    assert by_key["inspection:B2|2026-09-01"]["routine"] is True
    assert ckan.inspection_external_id(rows[0]) == "inspection:A1|2026-09-01"


def test_rows_stored_under_a_broken_key_are_hidden_as_superseded(tmp_path):
    from leaside import db
    from leaside.fetchers import ckan
    conn = db.connect(tmp_path / "t.db")
    raw = {"estId": "A1", "estName": "BAYVIEW PIZZA", "inspectionDate": "2026-09-01"}
    db.upsert_item(conn, _item(source_id="city_dinesafe", category="inspection", url=None,
                               title="Conditional Pass: merged", external_id="inspection:None|2026-09-01",
                               raw=raw))
    db.upsert_item(conn, _item(source_id="city_dinesafe", category="inspection", url=None,
                               title="Conditional Pass: BAYVIEW PIZZA",
                               external_id="inspection:A1|2026-09-01", raw=raw))
    assert db.hide_superseded(conn, "city_dinesafe", ckan.inspection_external_id) == 1
    assert db.hide_superseded(conn, "city_dinesafe", ckan.inspection_external_id) == 0
    shown = [r[0] for r in conn.execute(f"SELECT title FROM items WHERE {db.SHOWN}")]
    assert shown == ["Conditional Pass: BAYVIEW PIZZA"]
    assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 2


def test_a_change_keeps_the_version_it_replaced(tmp_path):
    """A permit's status moves from applied to issued. The page shows the new one;
    the log keeps the old one, so the history of each record is complete."""
    from leaside import db
    conn = db.connect(tmp_path / "t.db")
    first = _item(source_id="city_building_permits", category="permit", url=None,
                  title="New Building: 1 Rumsey Rd", summary="Status: Application Received",
                  external_id="permit:26 1", raw={"_id": 1, "STATUS": "Application Received"})
    assert db.upsert_item(conn, first) is True
    # Same record, reloaded: the datastore row number moved. Not a change.
    db.upsert_item(conn, {**first, "raw": {"_id": 907, "STATUS": "Application Received"}})
    assert conn.execute("SELECT COUNT(*) FROM item_log WHERE event='changed'").fetchone()[0] == 0
    # A real change.
    db.upsert_item(conn, {**first, "summary": "Status: Permit Issued",
                          "raw": {"_id": 908, "STATUS": "Permit Issued"}})
    rows = conn.execute("SELECT event, note, summary, raw FROM item_log ORDER BY id").fetchall()
    assert [r["event"] for r in rows] == ["new", "changed"]
    assert rows[1]["note"] == "summary, record"
    assert rows[1]["summary"] == "Status: Application Received"     # the old version
    assert "Application Received" in rows[1]["raw"]
    now = conn.execute("SELECT summary, raw FROM items").fetchone()
    assert now["summary"] == "Status: Permit Issued" and "Permit Issued" in now["raw"]


def test_rows_from_before_the_log_get_a_fingerprint_without_a_false_change(tmp_path):
    """Databases from before this version have no fingerprints. The first sighting
    after the upgrade records one; it must not be logged as a change."""
    from leaside import db
    conn = db.connect(tmp_path / "t.db")
    it = _item(source_id="ra_leaside", title="A post", url="https://x/1", external_id="p1")
    db.upsert_item(conn, it)
    conn.execute("UPDATE items SET content_hash = NULL")
    db.upsert_item(conn, it)
    db.upsert_item(conn, it)
    assert [r[0] for r in conn.execute("SELECT event FROM item_log")] == ["new"]


def test_an_old_database_is_upgraded_in_place_without_losing_rows(tmp_path):
    import sqlite3
    from leaside import db
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript(db.SCHEMA.split("-- The change log")[0])   # items etc., no log, no new columns
    old.execute("INSERT INTO items (id, source_id, category, title, first_seen_at, last_seen_at)"
                " VALUES ('x', 'ra_leaside', 'ra_news', 'kept', '2026-01-01', '2026-01-01')")
    old.commit(); old.close()
    conn = db.connect(path)
    row = conn.execute("SELECT title, routine, hidden_at, content_hash FROM items").fetchone()
    assert tuple(row) == ("kept", 0, None, None)
    assert conn.execute("SELECT COUNT(*) FROM item_log").fetchone()[0] == 0


def test_raw_records_drop_the_citys_search_index(tmp_path):
    from leaside import db
    conn = db.connect(tmp_path / "t.db")
    db.upsert_item(conn, _item(source_id="city_dinesafe", category="inspection",
                               raw={"estId": "A1", "_full_text": "'a1':1 'pizza':2" * 50}))
    assert "_full_text" not in conn.execute("SELECT raw FROM items").fetchone()[0]


def test_routine_and_hidden_rows_stay_off_the_page_email_and_trends(tmp_path, monkeypatch):
    from leaside import db, digest, render, trends
    conn = db.connect(tmp_path / "t.db")
    db.upsert_item(conn, _item(source_id="city_dinesafe", category="inspection", url=None,
                               title="Pass: LAIRD CAFE", routine=True, published_at="2026-10-01"))
    db.upsert_item(conn, _item(source_id="tps_reported_crime", category="crime", url=None,
                               title="Assault at X", external_id="hid", area="leaside",
                               published_at="2026-10-01", raw={"CSI_CATEGORY": "Assault"}))
    db.upsert_item(conn, _item(source_id="tps_reported_crime", category="crime", url=None,
                               title="Robbery at Y", external_id="ok", area="leaside",
                               published_at="2026-10-01", raw={"CSI_CATEGORY": "Robbery"}))
    iid = db.item_id("tps_reported_crime", "hid")
    db.hide(conn, iid, "tps_reported_crime", "superseded by a corrected record")
    conn.commit()
    monkeypatch.setattr(render, "OUT", tmp_path)
    page = render.run(db_path=tmp_path / "t.db", out_name="t.html").read_text(encoding="utf-8")
    assert "Robbery at Y" in page
    assert "Pass: LAIRD CAFE" not in page and "Assault at X" not in page
    assert "3 records" in page and "1 routine" in page and "1 hidden" in page
    data = digest.gather(conn, geo.Areas.load(), sources.load())
    assert [it["title"] for _, items in data["sections"] for it in items] == ["Robbery at Y"]
    counts = trends.counts_by_month(conn, "crime", lambda r: trends._offence(r["title"], r["raw"]))
    assert "Assault" not in counts and "Robbery" in counts


def test_backfilled_items_are_stored_but_not_emailed(tmp_path):
    """A source's window used to throw older items away before storing them. Now
    they are stored, and the window only keeps them out of the email."""
    from datetime import datetime, timedelta, timezone
    from leaside import db, digest
    conn = db.connect(tmp_path / "t.db")
    now = datetime.now(timezone.utc)
    for title, days in (("fresh notice", 3), ("2019 notice", 2400)):
        db.upsert_item(conn, _item(source_id="city_public_notices", category="city_notice",
                                   title=title, external_id=title,
                                   published_at=(now - timedelta(days=days)).isoformat()))
    conn.commit()
    data = digest.gather(conn, geo.Areas.load(), sources.load(),
                         since=(now - timedelta(days=1)).isoformat(timespec="seconds"))
    assert [it["title"] for _, items in data["sections"] for it in items] == ["fresh notice"]
    assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 2


def test_the_log_downloads_open_cleanly_in_excel(tmp_path, monkeypatch):
    import csv
    from leaside import db, render
    conn = db.connect(tmp_path / "t.db")
    db.upsert_item(conn, _item(title="Café on Bayview", url="https://x/c", external_id="c",
                               area="leaside", published_at="2026-10-01T14:00:00+00:00"))
    db.upsert_item(conn, _item(source_id="city_dinesafe", category="inspection", url=None,
                               title="Pass: LAIRD CAFE", routine=True, external_id="r"))
    db.upsert_item(conn, _item(title="Café on Bayview", url="https://x/c", external_id="c",
                               area="leaside", summary="now with hours",
                               published_at="2026-10-01T14:00:00+00:00"))
    conn.commit()
    monkeypatch.setattr(render, "OUT", tmp_path)
    render.run(db_path=tmp_path / "t.db", out_name="index.html")
    body = (tmp_path / "log" / "everything.csv").read_bytes()
    assert body.startswith(b"\xef\xbb\xbf")                     # Excel's UTF-8 marker
    rows = list(csv.DictReader((tmp_path / "log" / "everything.csv").open(encoding="utf-8-sig")))
    assert {r["Title"] for r in rows} == {"Café on Bayview", "Pass: LAIRD CAFE"}
    cafe = next(r for r in rows if r["Title"] == "Café on Bayview")
    assert cafe["Status"] == "Shown" and cafe["Times changed"] == "1" and cafe["Area"] == "Leaside"
    assert next(r for r in rows if r["Title"] == "Pass: LAIRD CAFE")["Status"] == "Routine, not shown"
    changes = list(csv.DictReader((tmp_path / "log" / "changes.csv").open(encoding="utf-8-sig")))
    assert [c["What happened"] for c in changes] == ["Changed", "First seen", "First seen"]
    assert changes[0]["What changed"] == "summary"
    page = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert 'href="log/everything.csv"' in page and 'href="log/changes.csv"' in page


def test_the_demo_never_overwrites_the_real_log(tmp_path, monkeypatch):
    from leaside import demo, render
    monkeypatch.setattr(render, "OUT", tmp_path)
    demo.run(db_path=tmp_path / "demo.db")
    render.run(db_path=tmp_path / "demo.db", out_name="demo.html")
    assert not (tmp_path / "log").exists()


def test_health_report_states_the_log_size_against_githubs_limit(tmp_path):
    from leaside import db, doctor
    conn = db.connect(tmp_path / "t.db")
    db.upsert_item(conn, _item())
    conn.commit()
    d = doctor.gather(conn, geo.Areas.load(), sources.load())
    d["size"] = doctor.file_size(tmp_path / "t.db")
    out = doctor.render(d)
    assert "## Size of the log" in out and "100 MB" in out
    assert "nothing is ever deleted" in out
    d["size"] = (400.0, 70.0)
    assert "Act soon" in doctor.render(d)


def test_weekly_backup_copies_the_saved_log_to_a_release():
    import yaml
    root = Path(__file__).resolve().parents[1]
    text = (root / ".github" / "workflows" / "weekly-backup.yml").read_text(encoding="utf-8")
    wf = yaml.safe_load(text)
    assert wf["permissions"] == {"contents": "write"}
    assert "origin/state:leaside.db.gz" in text and "gh release upload" in text
    assert "1" == str(wf[True]["schedule"][0]["cron"]).split()[-1]       # Mondays


def test_save_refuses_without_a_finished_restore_and_never_shrinks_the_log():
    root = Path(__file__).resolve().parents[1]
    script = (root / "scripts" / "state.sh").read_text(encoding="utf-8")
    save = script[script.index("  save)"):]
    assert save.index('[ ! -f "$COUNT_FILE" ]') < save.index("git push")
    assert save.index('"$after" -lt "$before"') < save.index("git push")
    assert "gzip" in save and "leaside.db.gz" in script[:script.index("  save)")]


def test_one_police_event_with_two_offences_is_two_records_and_stays_put(tmp_path):
    """Found by the change log on its first day: 503 crime records "changed" in one
    run. One break-in is recorded as both B&E and Unlawfully In Dwelling-House
    under one event number. Keyed on the event alone, the second overwrote the
    first and the record flipped on every run."""
    from leaside import db
    from leaside.fetchers import arcgis
    src = _src(id="tps_reported_crime", category="crime")
    base = {"EVENT_UNIQUE_ID": "GO-2026-1", "OCC_DATE": 1780000000000, "PREMISES_TYPE": "House",
            "NEIGHBOURHOOD_158": "Leaside-Bennington (56)", "LAT_WGS84": 43.708, "LONG_WGS84": -79.364}
    rows = [{**base, "OBJECTID": 1, "OFFENCE": "B&E", "UCR_CODE": 2120, "UCR_EXT": 200},
            {**base, "OBJECTID": 2, "OFFENCE": "Unlawfully In Dwelling-House", "UCR_CODE": 2120, "UCR_EXT": 210}]
    feats = [{"attributes": r, "geometry": {"x": r["LONG_WGS84"], "y": r["LAT_WGS84"]}} for r in rows]
    items = arcgis.parse_features(json.dumps({"features": feats}), src, AREAS, label="Break and Enter")
    assert {it["external_id"] for it in items} == {"GO-2026-1|2120.200", "GO-2026-1|2120.210"}
    # Layers without offence codes keep the bare event number, so their keys do not move.
    assert arcgis.feature_key({"EVENT_UNIQUE_ID": "GO-9", "OBJECTID": 4}) == "GO-9"

    conn = db.connect(tmp_path / "t.db")
    for _ in range(3):
        its, merged = db.collapse_same_key(list(reversed(items)) if _ % 2 else items)
        assert merged == 0
        for it in its:
            db.upsert_item(conn, it)
    assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM item_log WHERE event='changed'").fetchone()[0] == 0


def test_stored_crime_is_renamed_to_its_corrected_key_with_its_history(tmp_path):
    """Records past the newest 4,000 are never fetched again, so hiding the old-key
    rows would hide real history. They are renamed in place instead."""
    from leaside import db
    from leaside.fetchers import arcgis
    conn = db.connect(tmp_path / "t.db")
    raw = {"EVENT_UNIQUE_ID": "GO-2014-7", "UCR_CODE": 1430, "UCR_EXT": 100, "OFFENCE": "Assault"}
    db.upsert_item(conn, _item(source_id="tps_reported_crime", category="crime", url=None,
                               title="Assault at X", external_id="GO-2014-7", raw=raw,
                               published_at="2014-03-01"))
    old_id = db.item_id("tps_reported_crime", "GO-2014-7")
    moved = db.rekey(conn, "tps_reported_crime", arcgis.feature_key)
    assert moved == {"renamed": 1, "superseded": 0}
    new_id = db.item_id("tps_reported_crime", "GO-2014-7|1430.100")
    assert conn.execute("SELECT id FROM items").fetchone()[0] == new_id
    assert conn.execute("SELECT item_id FROM item_log").fetchone()[0] == new_id
    assert db.rekey(conn, "tps_reported_crime", arcgis.feature_key) == {"renamed": 0, "superseded": 0}
    assert new_id != old_id


def test_rows_sharing_a_key_collapse_to_the_same_one_in_any_order():
    """The City lists each person in a serious collision under one collision number."""
    import random
    from leaside import db
    rows = [_item(source_id="city_ksi_collisions", category="collision", url=None,
                  title="Pedestrian collision", external_id="collision_id:5",
                  raw={"_id": n, "collision_id": 5, "per_no": n, "injury": inj})
            for n, inj in enumerate(("Major", "Minor", "None"))]
    picks = set()
    for seed in range(6):
        shuffled = rows[:]
        random.Random(seed).shuffle(shuffled)
        kept, merged = db.collapse_same_key(shuffled)
        assert merged == 2 and len(kept) == 1
        picks.add(kept[0]["raw"]["per_no"])
    assert len(picks) == 1


def test_google_news_headlines_do_not_flip_between_outlet_spellings(tmp_path):
    """Google names the outlet "globalnews.ca" on one fetch and "Global News" on the
    next. 62 false changes in the log's first day came from that alone."""
    from leaside import db
    def feed(name):
        return f"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>Boy facing charges after officer hit - {name}</title>
<link>https://news.google.com/rss/articles/CBMi123?oc=5</link><guid isPermaLink="false">CBMi123</guid>
<pubDate>Mon, 05 Oct 2026 14:00:00 GMT</pubDate>
<description>&lt;a href="x"&gt;Boy facing charges after officer hit&lt;/a&gt; {name}</description>
<source url="https://www.globalnews.ca">Global News</source></item></channel></rss>"""
    src = CFG.by_id("news_police_coverage")
    conn = db.connect(tmp_path / "t.db")
    for name in ("globalnews.ca", "Global News", "globalnews.ca"):
        (it,) = rss_feed.parse(feed(name), src)
        assert it["title"] == "Boy facing charges after officer hit (globalnews.ca)"
        assert it["summary"] is None
        db.upsert_item(conn, it)
    assert conn.execute("SELECT COUNT(*) FROM item_log WHERE event='changed'").fetchone()[0] == 0
    # Other feeds are untouched.
    (plain,) = rss_feed.parse(feed("Global News"), CFG.by_id("ra_leaside"))
    assert plain["title"] == "Boy facing charges after officer hit - Global News"


# ---------------------------------------------------------------- every page names its sources

OGL = "Contains information licensed under the Open Government Licence – Toronto."


def test_every_collected_source_has_a_publisher_page_and_terms():
    for s in CFG.sources:
        if not s.runnable or s.category == "registry":
            continue
        lic = CFG.licence_of(s)
        assert lic and lic.statement, f"{s.id} has no terms of use"
        assert s.home and s.home.startswith("http"), f"{s.id} has no page to cite"
        assert s.credit, s.id
    # The City's data carries the City's exact wording.
    for sid in ("city_public_notices", "city_building_permits", "city_dinesafe",
                "city_ksi_collisions"):
        assert CFG.licence_of(CFG.by_id(sid)).statement == OGL


def _sourced_db(tmp_path):
    from leaside import db
    conn = db.connect(tmp_path / "t.db")
    db.upsert_item(conn, _item(source_id="city_building_permits", category="permit", url=None,
                               title="New Building: 1 Rumsey Rd", external_id="p1",
                               area="leaside", published_at="2026-10-01"))
    db.upsert_item(conn, _item(source_id="ra_leaside", title="Meeting", external_id="m1",
                               area="leaside", published_at="2026-10-02"))
    db.upsert_item(conn, _item(source_id="tps_reported_crime", category="crime", url=None,
                               title="Assault at X", external_id="c1", area="leaside",
                               published_at="2026-05-01", raw={"CSI_CATEGORY": "Assault"}))
    db.upsert_item(conn, _item(source_id="tps_calls_for_service", category="police_call",
                               url=None, title="Theft near A & B", external_id="k1",
                               area="leaside", published_at=__import__("datetime").datetime.now(
                                   __import__("datetime").timezone.utc).isoformat()))
    conn.commit()
    return conn


def test_the_news_page_cites_every_source_it_shows(tmp_path, monkeypatch):
    from leaside import render
    _sourced_db(tmp_path)
    monkeypatch.setattr(render, "OUT", tmp_path)
    page = render.run(db_path=tmp_path / "t.db", out_name="index.html").read_text(encoding="utf-8")
    section = page[page.index('id="sources"'):]
    for sid in ("city_building_permits", "ra_leaside", "tps_reported_crime", "tps_calls_for_service"):
        s = CFG.by_id(sid)
        assert s.name in section and f'href="{s.home}"' in section, sid
    assert "Building permits" in section and "Open Government Licence – Toronto" in section
    assert OGL in section
    assert "Headlines and short excerpts belong to their publishers" in section
    # Sources with nothing on the page are not cited.
    assert CFG.by_id("city_dinesafe").name not in section
    # Each item's source name links to the source.
    assert f'class="src" href="{CFG.by_id("ra_leaside").home}"' in page
    # The police-calls strip names its source.
    strip = page[page.index('class="live"'):page.index("</section>", page.index('class="live"'))]
    assert "Source:" in strip and CFG.by_id("tps_calls_for_service").home in strip


def test_the_trends_page_cites_its_sources_under_each_heading(tmp_path, monkeypatch):
    from leaside import render
    _sourced_db(tmp_path)
    monkeypatch.setattr(render, "OUT", tmp_path)
    render.run(db_path=tmp_path / "t.db", out_name="index.html")
    page = (tmp_path / "trends.html").read_text(encoding="utf-8")
    crime_h = page.index("Reported crime, all offences")
    line = page[crime_h:page.index("</p>", crime_h)]
    assert 'class="srcline">Source:' in line
    assert "Toronto Police Service, Public Safety Data Portal" in line
    assert "newest record 2026-05-01" in line
    section = page[page.index('id="sources"'):]
    assert "Open Government Licence – Ontario" in section
    assert "Contains information licensed under the Open Government Licence – Ontario." in section
    assert "not affiliated with, or endorsed by" in section
    assert CFG.by_id("ra_leaside").name not in section          # not on this page


def test_downloads_carry_the_source_and_terms_of_every_row(tmp_path, monkeypatch):
    import csv
    from leaside import render
    _sourced_db(tmp_path)
    monkeypatch.setattr(render, "OUT", tmp_path)
    render.run(db_path=tmp_path / "t.db", out_name="index.html")
    rows = list(csv.DictReader((tmp_path / "log" / "everything.csv").open(encoding="utf-8-sig")))
    assert all(r["Source page"].startswith("http") and r["Terms of use"] for r in rows)
    permit = next(r for r in rows if r["Type"] == "Building permit")
    assert permit["Terms of use"] == "Open Government Licence – Toronto"
    listed = list(csv.DictReader((tmp_path / "log" / "sources.csv").open(encoding="utf-8-sig")))
    assert {r["Source"] for r in listed} == {CFG.by_id(s).name for s in
        ("city_building_permits", "ra_leaside", "tps_reported_crime", "tps_calls_for_service")}
    assert any(r["Required wording"] == OGL for r in listed)
    page = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert 'href="log/sources.csv"' in page


def test_the_email_credits_the_sources_it_carries(tmp_path):
    from leaside import digest
    conn = _sourced_db(tmp_path)
    data = digest.gather(conn, geo.Areas.load(), sources.load(), since="2000-01-01T00:00:00+00:00")
    html_out, text_out = digest.render_html(data), digest.render_text(data)
    assert "Each item names its source." in html_out and "Each item names its source." in text_out
    assert OGL in html_out and OGL in text_out
    assert "Police calls come from the Toronto Police Service" in html_out    # counted, still credited
    assert "not affiliated with or endorsed by" in html_out and "not affiliated" in text_out
