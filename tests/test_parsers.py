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
