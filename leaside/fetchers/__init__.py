"""Per-kind fetchers. Each returns a list of normalised item dicts."""
from . import arcgis, c4s, ckan, notices, rss_feed, html_list  # noqa: F401

REGISTRY = {
    "rss": rss_feed.fetch,
    "html_list": html_list.fetch,
    "json_api": notices.fetch,
    "arcgis_dcat": arcgis.fetch_catalogue,
    "arcgis_feature": arcgis.fetch_features,
    "arcgis_multi": arcgis.fetch_features,   # ingest drives this one per layer
    "ckan_dataset": ckan.fetch_dataset,
    "ckan_permits": ckan.fetch_permits,
    "ckan_dinesafe": ckan.fetch_dinesafe,
    "tps_calls": c4s.fetch_calls,
}
