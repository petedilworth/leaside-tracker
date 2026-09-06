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
