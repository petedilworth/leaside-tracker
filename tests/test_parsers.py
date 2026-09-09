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
    src = CFG.by_id("tps_major_crime_indicators")
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


def test_high_volume_sources_are_age_capped():
    """Crime and collision history must not bury the neighbourhood news."""
    for sid in ("tps_major_crime_indicators", "tps_traffic_collisions", "city_ksi_collisions"):
        assert CFG.by_id(sid).max_age_days, f"{sid} needs an age cap"


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


def test_new_areas_do_not_overlap_their_neighbours():
    """Overlapping placeholder boxes would make point matching order-dependent."""
    def box(key):
        f = next(f for f in AREAS.features if f["properties"]["key"] == key)
        ring = f["geometry"]["coordinates"][0]
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        return min(xs), min(ys), max(xs), max(ys)

    deer, moore = box("deer_park"), box("moore_park")
    assert deer[2] <= moore[0], "Deer Park must sit west of Moore Park"
    lytton, lawrence = box("lytton_park"), box("lawrence_park")
    assert lytton[2] <= lawrence[0], "Lytton Park must sit west of Lawrence Park"


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
        "tps_hub_dcat", "tps_major_crime_indicators",
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


def test_page_shows_a_time_window_not_a_count_cap(tmp_path):
    from leaside import geo, render, sources

    conn = _seed_reader_db(tmp_path)
    data = render.collect(conn, geo.Areas.load(), sources.load())
    titles = [it["title"] for it in data["items"]]
    assert "old post" not in titles, "200 days old is outside the window"
    assert titles == ["brand new", "last week"], "newest first"


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
