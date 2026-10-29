"""Area matching: by coordinate when a source gives one, by keyword when it does not."""
from __future__ import annotations

import json
import re
from pathlib import Path

DEFAULT_AREAS = Path("config/areas.geojson")


class Areas:
    def __init__(self, features: list[dict], official: dict | None = None):
        self.features = features
        # {normalised City neighbourhood name: [rings]} - the City's own
        # boundaries, when a run has fetched them. See official_gate().
        self.official = official or {}

    @classmethod
    def load(cls, path: Path | str = DEFAULT_AREAS, conn=None) -> "Areas":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        areas = cls(data["features"])
        if conn is not None:
            areas.attach_official(conn)
        return areas

    def attach_official(self, conn) -> int:
        """Load the City's neighbourhood polygons saved by the boundaries source.

        The hand-drawn rectangles overshoot. The South Rosedale box reached across
        Bloor into Yorkville and St James Town, so Bloor Street towers were
        "Rosedale" and Rosedale subway station was the busiest place on the map.
        With the City's polygons loaded, a point must fall inside one of our
        official neighbourhoods before a rectangle is allowed to name the sub-area.
        """
        try:
            rows = conn.execute("SELECT name, geojson FROM boundaries").fetchall()
        except Exception:               # an older database, before the table existed
            return 0
        wanted = self.official_names()
        loaded = {}
        for name, geojson in rows:
            key = self._norm(name)
            if key not in wanted:
                continue
            try:
                geom = json.loads(geojson)
            except ValueError:
                continue
            loaded[key] = list(_rings(geom))
        self.official = loaded
        return len(loaded)

    @property
    def official_gate(self) -> bool:
        """True when every one of our official neighbourhoods has a City polygon."""
        return bool(self.official) and self.official_names() <= set(self.official)

    def official_at(self, lat: float, lon: float) -> str | None:
        """The City neighbourhood (normalised) containing a point, among ours."""
        for key, rings in self.official.items():
            if any(_point_in_ring(lon, lat, ring) for ring in rings):
                return key
        return None

    def match_point(self, lat: float | None, lon: float | None) -> str | None:
        if lat is None or lon is None:
            return None
        if self.official_gate:
            hood = self.official_at(lat, lon)
            if hood is None:
                return None
            for f in self.features:          # the sub-area, by rectangle, within the hood
                if hood in {self._norm(n) for n in f["properties"].get("official", [])}:
                    if any(_point_in_ring(lon, lat, ring) for ring in f["geometry"]["coordinates"]):
                        return f["properties"]["key"]
            return self.match_official(hood)   # inside the hood, outside every rectangle
        for f in self.features:
            for ring in f["geometry"]["coordinates"]:
                if _point_in_ring(lon, lat, ring):
                    return f["properties"]["key"]
        return None

    @staticmethod
    def _norm(name: str) -> str:
        """"North St.James Town (74)" -> "northstjamestown". Drops the id and punctuation."""
        name = re.sub(r"\(\s*\d+\s*\)\s*$", "", str(name)).strip()
        return re.sub(r"[^a-z0-9]", "", name.lower())

    def official_names(self) -> set[str]:
        """Normalised City neighbourhood names that fall inside our areas."""
        return {self._norm(n) for f in self.features
                for n in f["properties"].get("official", [])}

    def is_official_ours(self, name: str | None) -> bool:
        """True when a publisher's own neighbourhood label is one of ours."""
        return bool(name) and self._norm(name) in self.official_names()

    def match_official(self, name: str | None) -> str | None:
        """Map a City neighbourhood name to one of our areas.

        Several of our areas share one City neighbourhood - Rosedale-Moore Park
        covers three - so this is a fallback for when coordinates are missing, not
        a replacement for them.
        """
        if not name:
            return None
        target = self._norm(name)
        for f in self.features:
            if target in {self._norm(n) for n in f["properties"].get("official", [])}:
                return f["properties"]["key"]
        return None

    def match_postal(self, postal: str | None, street: str | None = None) -> str | None:
        """Map a postal code to an area by its first three characters (the FSA).

        The City's permit records carry a postal code but no coordinates. M4G is
        Leaside almost exactly. M4W is not Rosedale: it runs along Bloor into
        Yorkville, and 833 Bloor Street permits were filed under Rosedale before
        this was caught. An area can mark an FSA `loose`, and then the street must
        also be one the area lists. Coordinates and street keywords are tried
        first; this is the fallback.
        """
        if not postal:
            return None
        fsa = re.sub(r"[^A-Z0-9]", "", str(postal).upper())[:3]
        if len(fsa) != 3:
            return None
        street_key = _street_key(street)
        for f in self.features:
            props = f["properties"]
            if fsa not in [x.upper() for x in props.get("fsa", [])]:
                continue
            if fsa in [x.upper() for x in props.get("loose_fsa", [])]:
                known = {_street_key(x) for x in props.get("streets", [])}
                if street_key not in known:
                    continue
            return props["key"]
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


_SUFFIX = re.compile(r"\s+(avenue|ave|road|rd|street|st|drive|dr|boulevard|blvd|crescent|cres|"
                     r"lane|ln|place|pl|court|ct|gardens|gdns|terrace|terr|way|trail|trl|"
                     r"square|sq|circle|cir|path)\.?$")
_DIRECTION = re.compile(r"\s+(east|west|north|south|e|w|n|s)\.?$")


def _street_key(street: str | None) -> str:
    """"Roxborough Dr E" -> "roxborough": the name alone, for matching lists."""
    text = re.sub(r"[^a-z0-9 ]", " ", str(street or "").lower()).strip()
    text = re.sub(r"\s+", " ", text)
    text = _DIRECTION.sub("", text)
    text = _SUFFIX.sub("", text)
    return _DIRECTION.sub("", text).strip()


def _rings(geom: dict):
    """Every outer ring in a Polygon or MultiPolygon, as [lon, lat] lists."""
    t = geom.get("type")
    if t == "Polygon":
        yield geom["coordinates"][0]
    elif t == "MultiPolygon":
        for poly in geom["coordinates"]:
            yield poly[0]
    elif t == "Feature":
        yield from _rings(geom.get("geometry") or {})
    elif t == "FeatureCollection":
        for f in geom.get("features", []):
            yield from _rings(f)


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
