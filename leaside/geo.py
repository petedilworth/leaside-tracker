"""Area matching: by coordinate when a source gives one, by keyword when it does not."""
from __future__ import annotations

import json
import re
from pathlib import Path

DEFAULT_AREAS = Path("config/areas.geojson")


class Areas:
    def __init__(self, features: list[dict]):
        self.features = features

    @classmethod
    def load(cls, path: Path | str = DEFAULT_AREAS) -> "Areas":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(data["features"])

    def match_point(self, lat: float | None, lon: float | None) -> str | None:
        if lat is None or lon is None:
            return None
        for f in self.features:
            for ring in f["geometry"]["coordinates"]:
                if _point_in_ring(lon, lat, ring):
                    return f["properties"]["key"]
        return None

    def match_text(self, *texts: str | None) -> str | None:
        """Return the area whose keyword appears earliest in the joined text."""
        blob = " ".join(t for t in texts if t).lower()
        if not blob:
            return None
        best_key, best_pos = None, len(blob) + 1
        for f in self.features:
            for kw in f["properties"].get("keywords", []):
                m = re.search(r"\b" + re.escape(kw.lower()), blob)
                if m and m.start() < best_pos:
                    best_key, best_pos = f["properties"]["key"], m.start()
        return best_key

    def name(self, key: str | None) -> str:
        for f in self.features:
            if f["properties"]["key"] == key:
                return f["properties"]["name"]
        return "Unmatched"

    def default_off(self) -> set[str]:
        """Areas kept in the data but not shown until the reader asks for them."""
        return {f["properties"]["key"] for f in self.features
                if f["properties"].get("default_off")}

    def keys(self) -> list[str]:
        return [f["properties"]["key"] for f in self.features]


def _point_in_ring(x: float, y: float, ring: list[list[float]]) -> bool:
    """Ray casting. Ring is a GeoJSON linear ring of [lon, lat] pairs."""
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if (y1 > y) != (y2 > y):
            xint = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < xint:
                inside = not inside
    return inside
