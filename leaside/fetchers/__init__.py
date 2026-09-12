"""Per-kind fetchers. Each returns a list of normalised item dicts."""
from . import arcgis, ckan, notices, rss_feed, html_list  # noqa: F401

REGISTRY = {
    "rss": rss_feed.fetch,
    "html_list": html_list.fetch,
    "json_api": notices.fetch,
    "arcgis_dcat": arcgis.fetch_catalogue,
    "arcgis_feature": arcgis.fetch_features,
    "arcgis_multi": arcgis.fetch_features,   # ingest drives this one per layer
    "ckan_dataset": ckan.fetch_dataset,
}
