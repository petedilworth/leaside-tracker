"""Load and validate config/sources.yaml."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG = Path("config/sources.yaml")

RUNNABLE_KINDS = {"rss", "json_api", "arcgis_dcat", "arcgis_feature",
                  "arcgis_multi", "ckan_dataset", "ckan_permits", "ckan_dinesafe",
                  "html_list", "tps_calls"}


@dataclass
class Source:
    id: str
    name: str
    kind: str
    status: str
    category: str = "other"
    area: str | None = None
    url: str | None = None
    fallback_html: str | None = None
    home_url: str | None = None
    alt_url: str | None = None
    dataset: str | None = None
    selector: str | None = None
    discover_from: str | None = None
    discover_match: str | None = None
    # Alternative addresses for one endpoint, tried in order until one answers.
    # For publishers whose exact URL is unconfirmed but whose host is known.
    candidates: list = field(default_factory=list)
    timeout: int | None = None
    retries: int | None = None
    max_age_days: int | None = None
    snapshot: bool = False
    notes: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def runnable(self) -> bool:
        """True when the ingester can pull this source without a human step."""
        if self.status in {"manual", "blocked"}:
            return False
        return self.kind in RUNNABLE_KINDS and bool(
            self.url or self.dataset or self.discover_from or self.candidates
        )

    @property
    def home(self) -> str | None:
        """A page a person can actually read, for items that carry no link of their own.

        A feed URL is not it, so strip the feed path off and use the site root.
        """
        if self.home_url:
            return self.home_url
        if self.fallback_html:
            return self.fallback_html
        if not self.url:
            return None
        for suffix in ("/feed/", "/feed", "/rss/", "/rss", "/index.xml", "/blog/feed/"):
            if self.url.endswith(suffix):
                return self.url[: -len(suffix)] + "/"
        return self.url

    @property
    def probeable(self) -> bool:
        """True when there is a URL worth checking, even if we expect it to fail."""
        return bool(self.url or self.fallback_html or self.alt_url or self.candidates)


@dataclass
class Config:
    user_agent: str
    timeout: int
    delay: float
    sources: list[Source]
    directories: list[str] = field(default_factory=list)

    def by_id(self, sid: str) -> Source | None:
        return next((s for s in self.sources if s.id == sid), None)


def load(path: Path | str = DEFAULT_CONFIG) -> Config:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    d = raw.get("defaults", {})
    known = {f for f in Source.__dataclass_fields__ if f != "extra"}
    sources = []
    for entry in raw["sources"]:
        kwargs = {k: v for k, v in entry.items() if k in known}
        kwargs["extra"] = {k: v for k, v in entry.items() if k not in known}
        sources.append(Source(**kwargs))
    return Config(
        user_agent=d.get("user_agent", "leaside-tracker/0.1"),
        timeout=int(d.get("timeout", 30)),
        delay=float(d.get("request_delay_seconds", 2)),
        sources=sources,
        directories=list(raw.get("directories") or []),
    )
