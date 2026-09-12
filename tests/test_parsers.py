"""Parser tests run entirely offline against fixtures. No network, ever."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from leaside import geo, sources  # noqa: E402
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


def test_snapshot_sources_drop_rows_that_left_the_dataset(tmp_path):
    """A dataset is a photograph. What is not in the latest one is not on the page."""
    import time

    from leaside import db

    conn = db.connect(tmp_path / "t.db")
    db.upsert_item(conn, _item(source_id="city_ksi_collisions", title="old crash",
                               url="https://x/old"))
    db.upsert_item(conn, _item(source_id="ra_leaside", title="old post", url="https://x/post"))
    conn.commit()

    time.sleep(1.1)                       # timestamps are second-resolution
    started = db.utcnow()
    db.upsert_item(conn, _item(source_id="city_ksi_collisions", title="new crash",
                               url="https://x/new"))
    removed = db.drop_unseen(conn, "city_ksi_collisions", started)
    conn.commit()

    assert removed == 1
    kept = sorted(r[0] for r in conn.execute("SELECT title FROM items"))
    assert kept == ["new crash", "old post"], "a feed source must not be touched"


def test_only_datasets_are_marked_as_snapshots():
    """Feeds are streams. Marking one a snapshot would delete your reading history."""
    snapshots = {s.id for s in CFG.sources if s.snapshot}
    assert snapshots == {
        "tps_hub_dcat", "tps_reported_crime",
        "tps_traffic_collisions", "city_ksi_collisions",
    }
    assert not any(s.snapshot for s in CFG.sources if s.kind == "rss")


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
    from leaside import probe

    report = tmp_path / "probe-report.md"
    report.write_text("recent", encoding="utf-8")
    monkeypatch.setattr(probe, "REPORT", report)
    assert probe.run() == []
    assert "Skipping" in capsys.readouterr().out
    assert probe.is_fresh(report) is not None
    assert probe.is_fresh(tmp_path / "missing.md") is None


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


def test_retired_dataset_rows_are_swept_but_feed_history_is_kept(tmp_path):
    """What gets swept: a source no longer configured, and a retired dataset or listing.

    What survives: anything a live source still collects, and the back catalogue of a
    feed that has been retired, because a post that was true stays true.
    """
    from leaside import db, geo, sources

    conn = db.connect(tmp_path / "t.db")
    rows = [
        ("fontra_directory", "a scraped link", "registry"),       # retired listing
        ("no_such_source", "ghost from an old config", "other"),  # not configured at all
        ("tps_hub_dcat", "a police dataset", "registry"),         # listing, still live
        ("ra_north_rosedale", "old newsletter", "ra_news"),       # retired feed
    ]
    for i, (sid, title, cat) in enumerate(rows):
        db.upsert_item(conn, _item(source_id=sid, title=title, category=cat,
                                   url=f"https://x/{i}"))
    conn.commit()

    counts = db.refresh_all(conn, geo.Areas.load(), sources.load())
    left = sorted(r[0] for r in conn.execute("SELECT title FROM items"))
    assert left == ["a police dataset", "old newsletter"]
    assert counts["orphans_removed"] == 2


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
    assert "Robbery - Business" in kept[0]["summary"]
    assert "Commercial" in kept[0]["summary"]


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
