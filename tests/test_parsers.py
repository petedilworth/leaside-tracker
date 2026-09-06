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
    items = rss_feed.parse((FIX / "ra_feed.xml").read_text(), src)
    assert len(items) == 2
    assert items[0]["title"].startswith("September general meeting")
    assert items[0]["published_at"] == "2025-09-03T14:00:00+00:00"
    assert items[0]["url"] == "https://example.invalid/sept-agenda"


def test_notices_keeps_only_local():
    src = CFG.by_id("city_public_notices")
    items = notices.parse((FIX / "notices.json").read_text(), src)
    assert len(items) == 2
    local = [
        i for i in items
        if AREAS.match_text(i["title"], i["summary"], json.dumps(i["raw"]))
    ]
    assert len(local) == 1
    assert "Millwood" in local[0]["title"]


def test_notices_handles_wrapped_payload():
    src = CFG.by_id("city_public_notices")
    wrapped = json.dumps({"Notices": json.loads((FIX / "notices.json").read_text())})
    assert len(notices.parse(wrapped, src)) == 2


def test_arcgis_filters_by_area():
    src = CFG.by_id("tps_major_crime_indicators")
    items = arcgis.parse_features((FIX / "arcgis_features.json").read_text(), src, AREAS)
    assert len(items) == 1, "the downtown incident must be dropped"
    assert items[0]["title"] == "Break and Enter"
    assert items[0]["area"] == "leaside"
    assert items[0]["published_at"].startswith("2024-") or items[0]["published_at"].startswith("2025-")


def test_layer_discovery():
    entries = arcgis.catalogue_entries((FIX / "hub_dcat.json").read_text())
    url = arcgis.find_layer(entries, "major crime indicators")
    assert url and url.endswith("FeatureServer/0")
    assert arcgis.find_layer(entries, "shootings") is None


def test_bbox_covers_all_areas():
    minx, miny, maxx, maxy = arcgis.bbox_of(AREAS)
    assert minx < -79.40 and maxx > -79.35
    assert miny < 43.67 and maxy > 43.73


def test_every_source_has_a_known_kind():
    allowed = sources.RUNNABLE_KINDS | {"manual", "blocked"}
    bad = [s.id for s in CFG.sources if s.kind not in allowed]
    assert not bad, bad


def test_blocked_sources_are_never_runnable():
    assert not any(s.runnable for s in CFG.sources if s.status in {"blocked", "manual"})
