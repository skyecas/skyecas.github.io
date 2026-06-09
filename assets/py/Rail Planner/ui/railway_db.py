"""Local OSM railway database for geometry enrichment.

Downloads a Geofabrik PBF once, extracts railway ways via osmium,
caches as compressed JSON, and queries locally with a grid spatial index.
"""

from __future__ import annotations
import json
import gzip
import time
import shutil
import logging
import threading
import os
import math
from pathlib import Path

import requests
import osmium

log = logging.getLogger(__name__)
if not log.handlers:
    log.addHandler(logging.StreamHandler())
    log.setLevel(
        getattr(logging, os.environ.get("LOGLEVEL", "INFO").upper(), logging.INFO)
    )

RAILWAY_TAGS = frozenset(
    {
        "rail",
        "light_rail",
        "narrow_gauge",
        "subway",
        "tram",
        "crossover",
        "siding",
        "spur",
        "disused",
    }
)
DATA_DIR = Path(__file__).parent / "data"

REGIONS: dict[str, dict] = {
    "gb": {
        "url": "https://download.geofabrik.de/europe/great-britain-latest.osm.pbf",
        "pbf": "great-britain-latest.osm.pbf",
        "cache": "railways.gb.json.gz",
        "size_mb": 2200,
    },
    "ie": {
        "url": "https://download.geofabrik.de/europe/ireland-and-northern-ireland-latest.osm.pbf",
        "pbf": "ireland-and-northern-ireland-latest.osm.pbf",
        "cache": "railways.ie.json.gz",
        "size_mb": 200,
    },
}

REGION_BBOXES: dict[str, tuple[float, float, float, float]] = {
    "gb": (49.8, -8.7, 60.9, 1.8),
    "ie": (51.3, -10.5, 55.4, -5.3),
}

LAT_MIN = -90
LAT_MAX = 90
LON_MIN = -180
LON_MAX = 180


def detect_region(lat: float, lon: float) -> str | None:
    for name, (min_lat, min_lon, max_lat, max_lon) in REGION_BBOXES.items():
        if min_lat <= lat <= max_lat and min_lon <= lon <= max_lon:
            return name
    return None


class _RailwayExtractor(osmium.SimpleHandler):
    """Parses OSM PBF and collects railway way/platform coordinates and route relations."""

    CACHE_VERSION = 3

    def __init__(self):
        super().__init__()
        self.ways: list[dict] = []
        self.platforms: list[dict] = []
        self.relations: dict[int, dict] = {}
        self.way_routes: dict[int, list[int]] = {}

    def way(self, w):
        tag = w.tags.get("railway")
        wid = w.id
        if tag in RAILWAY_TAGS:
            coords = [(n.lat, n.lon) for n in w.nodes if n.location.valid()]
            if len(coords) >= 2:
                self.ways.append({"id": wid, "coords": coords})
        elif tag == "platform":
            coords = [(n.lat, n.lon) for n in w.nodes if n.location.valid()]
            if len(coords) >= 2:
                ref = w.tags.get("ref", "")
                self.platforms.append({"ref": ref, "coords": coords})

    def relation(self, r):
        if r.tags.get("route") in ("train", "railway"):
            name = r.tags.get("name", "") or ""
            ref = r.tags.get("ref", "") or ""
            way_ids = [m.ref for m in r.members if m.type == "w"]
            if len(way_ids) >= 2:
                rid = r.id
                self.relations[rid] = {"name": name, "ref": ref, "way_ids": way_ids}
                for wid in way_ids:
                    self.way_routes.setdefault(wid, []).append(rid)


def _polyline_sample(
    poly: list[tuple[float, float]], frac: float
) -> tuple[float, float]:
    """Return (lat, lon) at fraction 0-1 along cumulative length of poly."""
    if frac <= 0 or len(poly) < 2:
        return poly[0]
    if frac >= 1:
        return poly[-1]
    total = sum(
        math.hypot(poly[k][0] - poly[k - 1][0], poly[k][1] - poly[k - 1][1])
        for k in range(1, len(poly))
    )
    target = total * frac
    accum = 0.0
    for k in range(1, len(poly)):
        seg_len = math.hypot(poly[k][0] - poly[k - 1][0], poly[k][1] - poly[k - 1][1])
        if accum + seg_len >= target or k == len(poly) - 1:
            t = (target - accum) / seg_len if seg_len > 0 else 0
            return (
                poly[k - 1][0] + t * (poly[k][0] - poly[k - 1][0]),
                poly[k - 1][1] + t * (poly[k][1] - poly[k - 1][1]),
            )
        accum += seg_len
    return poly[-1]


class _GridIndex:
    """Simple grid-based spatial index over railway ways."""

    def __init__(self, ways: list[list[tuple[float, float]]], cell_deg: float = 0.1):
        self.cell_deg = cell_deg
        self.ways = ways
        self.cells: dict[tuple[int, int], list[int]] = {}

        for i, coords in enumerate(ways):
            min_lat = min(c[0] for c in coords)
            max_lat = max(c[0] for c in coords)
            min_lon = min(c[1] for c in coords)
            max_lon = max(c[1] for c in coords)
            for r in range(self._row(min_lat), self._row(max_lat) + 1):
                for c in range(self._col(min_lon), self._col(max_lon) + 1):
                    self.cells.setdefault((r, c), []).append(i)

    def _row(self, lat: float) -> int:
        return max(
            0,
            min(
                int((lat - LAT_MIN) / self.cell_deg),
                int((LAT_MAX - LAT_MIN) / self.cell_deg) - 1,
            ),
        )

    def _col(self, lon: float) -> int:
        return max(
            0,
            min(
                int((lon - LON_MIN) / self.cell_deg),
                int((LON_MAX - LON_MIN) / self.cell_deg) - 1,
            ),
        )

    def query_bbox(
        self, min_lat: float, min_lon: float, max_lat: float, max_lon: float
    ) -> list[int]:
        seen: set[int] = set()
        for r in range(self._row(min_lat), self._row(max_lat) + 1):
            for c in range(self._col(min_lon), self._col(max_lon) + 1):
                for idx in self.cells.get((r, c), []):
                    seen.add(idx)
        return sorted(seen)


class RailwayDB:
    """Singleton local railway database. Downloads + parses in background on first use."""

    _instance: RailwayDB | None = None
    _lock = threading.Lock()

    def __init__(self):
        self._region_cache: dict[str, list[list[tuple[float, float]]]] = {}
        self._region_platforms: dict[str, list[list[tuple[float, float]]]] = {}
        self._region_index: dict[str, _GridIndex] = {}
        self._region_ready: dict[str, bool] = {}
        self._region_loading: dict[str, bool] = {}
        self._region_phase: dict[str, str] = {}
        self._region_relations: dict[str, dict] = {}
        self._region_way_routes: dict[str, dict[int, list[int]]] = {}
        self._region_way_ids: dict[str, list[int]] = {}
        self._region_way_idx: dict[str, dict[int, int]] = {}
        self._bg_threads: dict[str, threading.Thread] = {}

    @classmethod
    def get_instance(cls) -> RailwayDB:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = RailwayDB()
        return cls._instance

    def is_ready(self, region: str) -> bool:
        return self._region_ready.get(region, False)

    def get_status(self) -> dict:
        regions = {}
        for key in set(self._region_ready.keys()) | set(self._region_loading.keys()):
            info = REGIONS.get(key, {})
            phase = self._region_phase.get(
                key, "queued" if self._region_loading.get(key) else "idle"
            )
            if self._region_ready.get(key):
                phase = "ready"
            regions[key] = {
                "ready": self._region_ready.get(key, False),
                "loading": self._region_loading.get(key, False),
                "phase": phase,
                "ways": len(self._region_cache.get(key, [])),
                "platforms": len(self._region_platforms.get(key, [])),
                "pbf_size_mb": info.get("size_mb", 0),
            }
        return {"regions": regions}

    def ensure_region(self, region: str) -> None:
        """Load cache synchronously if available, otherwise start background download."""
        if self._region_ready.get(region) or self._region_loading.get(region):
            return

        info = REGIONS.get(region)
        if not info:
            self._region_ready[region] = False
            return

        cache_path = DATA_DIR / info["cache"]

        # Try loading from cache synchronously
        if cache_path.exists():
            self._region_phase[region] = "loading_cache"
            result = self._load_cache(cache_path)
            if result is not None:
                ways, platforms, relations, way_routes, way_ids = result
                self._set_region_ready(
                    region, ways, platforms, relations, way_routes, way_ids
                )
                return

        # No cache; start background download + parse
        with self._lock:
            if self._region_ready.get(region) or self._region_loading.get(region):
                return
            self._region_loading[region] = True
            self._region_phase[region] = "queued"
        t = threading.Thread(target=self._load_region_bg, args=(region,), daemon=True)
        self._bg_threads[region] = t
        t.start()

    def _load_region_bg(self, region: str) -> None:
        info = REGIONS.get(region)
        if not info:
            self._region_ready[region] = False
            return

        pbf_path = DATA_DIR / info["pbf"]
        cache_path = DATA_DIR / info["cache"]

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._region_phase[region] = "downloading"
        if not pbf_path.exists():
            try:
                self._download_pbf(info["url"], pbf_path, info["size_mb"])
            except Exception as e:
                log.error("PBF download failed: %s", e)
                self._region_ready[region] = False
                self._region_phase[region] = "failed"
                return

        self._region_phase[region] = "parsing"
        ways, platforms, relations, way_routes = self._parse_pbf(pbf_path)
        if ways:
            self._save_cache(cache_path, ways, platforms, relations, way_routes)
            # Convert new extractor format to old flat format for region_cache
            way_coords = [w["coords"] for w in ways]
            way_ids = [w["id"] for w in ways]
            self._set_region_ready(
                region, way_coords, platforms, relations, way_routes, way_ids
            )
        else:
            log.warning("No railway ways found in %s PBF", region)
            self._region_ready[region] = False
            self._region_phase[region] = "failed"

    def _set_region_ready(
        self,
        region: str,
        ways: list,
        platforms: list | None = None,
        relations: dict | None = None,
        way_routes: dict | None = None,
        way_ids: list[int] | None = None,
    ) -> None:
        self._region_cache[region] = ways
        if platforms is None:
            platforms = []
        self._region_platforms[region] = platforms
        self._region_relations[region] = relations or {}
        self._region_way_routes[region] = way_routes or {}
        self._region_way_ids[region] = way_ids or []
        if way_ids:
            self._region_way_idx[region] = {wid: i for i, wid in enumerate(way_ids)}
        self._region_index[region] = _GridIndex(ways)
        self._region_ready[region] = True
        self._region_loading[region] = False
        self._region_phase[region] = "ready"
        n_rel = len(relations) if relations else 0
        log.info(
            "Railway DB ready for %s (%d ways, %d platforms, %d relations)",
            region,
            len(ways),
            len(platforms),
            n_rel,
        )

    def _load_cache(self, path: Path) -> tuple | None:
        try:
            with gzip.open(path, "rt") as f:
                raw = json.load(f)
            ver = raw.get("version", 1) if isinstance(raw, dict) else 1
            if ver == 1:
                if isinstance(raw, list):
                    ways = [list(c) for c in raw]
                else:
                    ways = [list(c) for c in raw.get("railways", [])]
                platforms_raw = (
                    raw.get("platforms", []) if isinstance(raw, dict) else []
                )
                platforms = []
                for p in platforms_raw:
                    if isinstance(p, dict):
                        platforms.append(
                            {
                                "ref": p.get("ref", ""),
                                "coords": [list(c) for c in p.get("coords", [])],
                            }
                        )
                    elif isinstance(p, list):
                        platforms.append({"ref": "", "coords": [list(c) for c in p]})
                return ways, platforms, {}, {}, []
            else:
                # v3: ways with IDs, relations, way_routes
                ways_data = raw.get("ways", [])
                way_ids = [w["id"] for w in ways_data]
                ways = [list(c) for c in (w["coords"] for w in ways_data)]
                platforms_raw = raw.get("platforms", [])
                platforms = []
                for p in platforms_raw:
                    if isinstance(p, dict):
                        platforms.append(
                            {
                                "ref": p.get("ref", ""),
                                "coords": [list(c) for c in p.get("coords", [])],
                            }
                        )
                    elif isinstance(p, list):
                        platforms.append({"ref": "", "coords": [list(c) for c in p]})
                relations = raw.get("relations", {})
                way_routes = raw.get("way_routes", {})
                # Convert all JSON string keys to ints
                relations = {int(k): v for k, v in relations.items()}
                way_routes = {int(k): v for k, v in way_routes.items()}
                # Convert way_ids to ints
                way_ids = [int(w) for w in way_ids]
                return ways, platforms, relations, way_routes, way_ids
        except Exception as e:
            log.warning("Failed to load cache %s: %s", path, e)
            return None

    def _save_cache(
        self,
        path: Path,
        ways: list,
        platforms: list,
        relations: dict | None = None,
        way_routes: dict | None = None,
    ) -> None:
        try:
            # ways from _parse_pbf are dicts {"id", "coords"}; _load_cache returns flat list
            if ways and isinstance(ways[0], dict):
                ways_data = [{"id": w["id"], "coords": w["coords"]} for w in ways]
            else:
                ways_data = [{"id": 0, "coords": w} for w in ways]
            data = {
                "version": _RailwayExtractor.CACHE_VERSION,
                "ways": ways_data,
                "platforms": platforms,
                "relations": {str(k): v for k, v in (relations or {}).items()},
                "way_routes": {str(k): v for k, v in (way_routes or {}).items()},
            }
            with gzip.open(path, "wt") as f:
                json.dump(data, f)
            log.info(
                "Saved railway cache %s (%d ways, %d platforms, %d relations, %d MB)",
                path,
                len(ways),
                len(platforms),
                len(relations or {}),
                path.stat().st_size // 1_000_000,
            )
        except Exception as e:
            log.warning("Failed to save cache %s: %s", path, e)

    def _download_pbf(self, url: str, path: Path, size_mb: int) -> None:
        log.info("Downloading PBF %s (%.1f GB)...", url, size_mb / 1000)
        try:
            resp = requests.get(url, stream=True, timeout=600)
            resp.raise_for_status()
            tmp = path.with_suffix(".pbf.downloading")
            with open(tmp, "wb") as f:
                shutil.copyfileobj(resp.raw, f)
            tmp.rename(path)
            log.info("PBF downloaded to %s", path)
        except Exception as e:
            log.error("PBF download failed: %s", e)
            raise

    def _parse_pbf(self, pbf_path: Path) -> tuple[list, list, dict, dict]:
        log.info("Parsing PBF %s...", pbf_path)
        start = time.time()
        try:
            extractor = _RailwayExtractor()
            extractor.apply_file(str(pbf_path), locations=True)
            elapsed = time.time() - start
            log.info(
                "Parsed %d railway ways + %d platforms + %d relations in %.1fs",
                len(extractor.ways),
                len(extractor.platforms),
                len(extractor.relations),
                elapsed,
            )
            return (
                extractor.ways,
                extractor.platforms,
                extractor.relations,
                extractor.way_routes,
            )
        except Exception as e:
            log.error("PBF parsing failed: %s", e)
            return [], [], {}, {}

    def _platform_ways(
        self,
        lat: float,
        lon: float,
        *,
        region: str | None = None,
        platform: str | None = None,
    ) -> set[int]:
        """Return indices of railway ways adjacent to platforms near (lat, lon).

        If `platform` is given, match against platform `ref` tags first, then
        fall back to proximity matching within ~20m (0.0002 deg).
        Returns empty set if no platform data found.
        """
        if not region or region not in self._region_platforms:
            return set()
        all_platforms = self._region_platforms[region]
        if not all_platforms:
            return set()

        ways = self._region_cache.get(region, [])
        if not ways:
            return set()

        # Filter to platforms near the station coordinate
        NEAR_DEG = 0.01  # ~1km — station node can be far from platforms
        nearby = []
        for p in all_platforms:
            if any(
                abs(pn[0] - lat) < NEAR_DEG and abs(pn[1] - lon) < NEAR_DEG
                for pn in p["coords"]
            ):
                nearby.append(p)

        if not nearby:
            return set()

        THRESH = 0.0002  # ~20m

        def _adjacent(p_coords):
            found: set[int] = set()
            for pn in p_coords:
                for wi, way in enumerate(ways):
                    for wn in way:
                        if abs(wn[0] - pn[0]) < THRESH and abs(wn[1] - pn[1]) < THRESH:
                            found.add(wi)
                            break
                    else:
                        continue
                    break
            return found

        # If a specific platform ref is known, try to match it
        if platform:
            for p in nearby:
                if p.get("ref", "") == platform:
                    matched = _adjacent(p["coords"])
                    if matched:
                        return matched
            # Platform ref not matched; fall through to proximity match

        # Proximity match: any platform near the station
        result: set[int] = set()
        for p in nearby:
            result |= _adjacent(p["coords"])
        return result

    def _nearest_on_way(self, lat: float, lon: float, way: list) -> tuple[int, float]:
        """Return (index_of_nearest_point, squared_distance) on way."""
        best_i, best_d = 0, float("inf")
        for i, (wl, wn) in enumerate(way):
            d = (wl - lat) ** 2 + (wn - lon) ** 2
            if d < best_d:
                best_d, best_i = d, i
        return best_i, best_d

    def _ways_in_bbox(
        self,
        ways: list,
        idx: _GridIndex,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> list:
        """Get candidate ways in a padded bbox around two points."""
        span = max(abs(lat1 - lat2), abs(lon1 - lon2))
        pad = max(0.03, span * 0.3)
        min_lat = max(LAT_MIN, min(lat1, lat2) - pad)
        max_lat = min(LAT_MAX, max(lat1, lat2) + pad)
        min_lon = max(LON_MIN, min(lon1, lon2) - pad)
        max_lon = min(LON_MAX, max(lon1, lon2) + pad)
        return [ways[i] for i in idx.query_bbox(min_lat, min_lon, max_lat, max_lon)]

    def query_corridor(
        self,
        anchor_points: list[dict],
        ref_geos: list[list[tuple[float, float]]] | None = None,
    ) -> list[tuple[float, float]] | None:
        """Build geometry using route relations, with cross-station coverage fallback."""
        if len(anchor_points) < 2:
            return None

        mid = (len(anchor_points) - 1) // 2
        region = detect_region(anchor_points[0]["lat"], anchor_points[0]["lon"])
        if not region:
            region = detect_region(anchor_points[mid]["lat"], anchor_points[mid]["lon"])
        if not region or not self.is_ready(region):
            return None

        ways = self._region_cache[region]
        idx = self._region_index[region]
        way_ids = self._region_way_ids.get(region, [])
        relations = self._region_relations.get(region, {})
        way_routes = self._region_way_routes.get(region, {})

        all_coords: list[tuple[float, float]] = []

        log.debug(
            "query_corridor: %d anchor points for %s region", len(anchor_points), region
        )
        for i in range(len(anchor_points) - 1):
            a = anchor_points[i]
            b = anchor_points[i + 1]
            ref_geo = ref_geos[i] if ref_geos and i < len(ref_geos) else None

            way_idx = self._region_way_idx.get(region, {})
            seg = self._route_segment(
                a,
                b,
                ways,
                way_ids,
                relations,
                way_routes,
                idx,
                way_idx,
                ref_geo=ref_geo,
                region=region,
            )

            if seg is None:
                log.debug(
                    "query_corridor: seg %d (%s->%s) returned None",
                    i,
                    a.get("name", f"{a['lat']:.4f},{a['lon']:.4f}"),
                    b.get("name", f"{b['lat']:.4f},{b['lon']:.4f}"),
                )
                return None
            seg_km = (
                sum(
                    math.hypot(
                        (seg[j][0] - seg[j - 1][0]) * 111000,
                        (seg[j][1] - seg[j - 1][1]) * 70000,
                    )
                    for j in range(1, len(seg))
                )
                / 1000
            )
            log.debug(
                "query_corridor: seg %d -> %d coords, %.1fkm", i, len(seg), seg_km
            )
            # Per-segment sample coordinates for debugging
            if len(seg) >= 2:
                ns = len(seg)
                a_name = a.get("name", "").replace(" ", "_")
                b_name = b.get("name", "").replace(" ", "_")
                samples = []
                for frac in (0, 0.25, 0.5, 0.75, 1):
                    si = min(int(frac * (ns - 1)), ns - 1)
                    samples.append(f"{seg[si][0]:.4f},{seg[si][1]:.4f}")
                log.info(
                    "  seg %d OSM %s->%s: %s",
                    i,
                    a_name,
                    b_name,
                    " | ".join(samples),
                )
                if ref_geo and len(ref_geo) >= 2:
                    nr = len(ref_geo)
                    ref_samps = []
                    for frac in (0, 0.25, 0.5, 0.75, 1):
                        si = min(int(frac * (nr - 1)), nr - 1)
                        ref_samps.append(f"{ref_geo[si][0]:.4f},{ref_geo[si][1]:.4f}")
                    log.info(
                        "  seg %d REF %s->%s: %s",
                        i,
                        a_name,
                        b_name,
                        " | ".join(ref_samps),
                    )
            if all_coords:
                # Join at the shared anchor point (station), not at last coord
                anchor = b  # b is the shared anchor between this seg and prev
                gap = abs(all_coords[-1][0] - seg[0][0]) + abs(
                    all_coords[-1][1] - seg[0][1]
                )
                if gap < 0.001:
                    all_coords.extend(seg[1:])
                else:
                    best_i = 0
                    best_d = float("inf")
                    for si, sp in enumerate(seg):
                        d = (sp[0] - anchor["lat"]) ** 2 + (sp[1] - anchor["lon"]) ** 2
                        if d < best_d:
                            best_d, best_i = d, si
                    all_coords.extend(seg[best_i:])
            else:
                all_coords.extend(seg)

        if all_coords and len(all_coords) >= 2:
            all_coords[0] = (anchor_points[0]["lat"], anchor_points[0]["lon"])
            all_coords[-1] = (anchor_points[-1]["lat"], anchor_points[-1]["lon"])
        return all_coords

    def _route_segment(
        self,
        a: dict,
        b: dict,
        ways: list,
        way_ids: list[int],
        relations: dict,
        way_routes: dict,
        idx: _GridIndex,
        way_idx: dict[int, int] | None = None,
        ref_geo: list[tuple[float, float]] | None = None,
        region: str | None = None,
    ) -> list | None:
        """Find a path between two anchor points using OSM railway route relations."""
        if not relations or not way_ids:
            return None

        def _candidates_in_radius(lat, lon, deg):
            min_lat = max(LAT_MIN, lat - deg)
            max_lat = min(LAT_MAX, lat + deg)
            min_lon = max(LON_MIN, lon - deg)
            max_lon = min(LON_MAX, lon + deg)
            return idx.query_bbox(min_lat, min_lon, max_lat, max_lon)

        def _routes_at(lat, lon, deg=0.01):
            inds = _candidates_in_radius(lat, lon, deg)
            rv: dict[int, int] = {}
            rv_dist: dict[int, float] = {}
            for wi in inds:
                wid = way_ids[wi] if wi < len(way_ids) else 0
                for rid in way_routes.get(wid, []):
                    d = min((c[0] - lat) ** 2 + (c[1] - lon) ** 2 for c in ways[wi])
                    if rid not in rv or d < rv_dist[rid]:
                        rv[rid] = wi
                        rv_dist[rid] = d
            return rv, len(inds)

        # Try expanding search radius if no shared route found initially
        aname = a.get("name", f"{a['lat']:.4f},{a['lon']:.4f}")
        bname = b.get("name", f"{b['lat']:.4f},{b['lon']:.4f}")
        log.debug(
            "_route_segment: %s (%s) -> %s (%s)",
            aname,
            f"{a['lat']:.4f},{a['lon']:.4f}",
            bname,
            f"{b['lat']:.4f},{b['lon']:.4f}",
        )
        routes_a, n_a = _routes_at(a["lat"], a["lon"])
        routes_b, n_b = _routes_at(b["lat"], b["lon"])
        shared = set(routes_a.keys()) & set(routes_b.keys())
        log.debug(
            "  routes near A: %d ways, %d routes; near B: %d ways, %d routes; shared: %d",
            n_a,
            len(routes_a),
            n_b,
            len(routes_b),
            len(shared),
        )

        # Expand search radius up to 0.05° to capture main-line ways near stations
        if not shared:
            for radius in (0.02, 0.03, 0.05):
                routes_a, n_a = _routes_at(a["lat"], a["lon"], radius)
                routes_b, n_b = _routes_at(b["lat"], b["lon"], radius)
                shared = set(routes_a.keys()) & set(routes_b.keys())
                log.debug(
                    "  radius=%.2f: A=%d ways/%d routes, B=%d ways/%d routes, shared=%d",
                    radius,
                    n_a,
                    len(routes_a),
                    n_b,
                    len(routes_b),
                    len(shared),
                )
                if shared:
                    break

        if not shared:
            # No shared route. Check if any route near A extends close enough to B
            # (or vice versa). Station platform ways often differ from main-line ways.
            TARGET_D2 = 0.0004  # 0.02° squared (~2.2km) — tight to avoid false matches
            log.debug(
                "  fallback: checking routes near A that extend toward B (TARGET_D2=%.4f)",
                TARGET_D2,
            )
            for rid, wi_a in list(routes_a.items()):
                if rid in routes_b:
                    shared.add(rid)
                    continue
                rel = relations.get(rid)
                if not rel:
                    continue
                for wid in rel["way_ids"]:
                    wi = (way_idx or {}).get(wid)
                    if wi is None:
                        continue
                    for pt in (ways[wi][0], ways[wi][-1]):
                        if (pt[0] - b["lat"]) ** 2 + (
                            pt[1] - b["lon"]
                        ) ** 2 < TARGET_D2:
                            log.debug(
                                "  fallback A->B matched route %d (%s)",
                                rid,
                                rel.get("name", ""),
                            )
                            routes_b[rid] = wi
                            shared.add(rid)
                            break
                    if rid in shared:
                        break
            if not shared:
                log.debug("  fallback A->B found nothing, trying B->A")
                for rid, wi_b in list(routes_b.items()):
                    if rid in routes_a:
                        shared.add(rid)
                        continue
                    rel = relations.get(rid)
                    if not rel:
                        continue
                    for wid in rel["way_ids"]:
                        wi = (way_idx or {}).get(wid)
                        if wi is None:
                            continue
                        for pt in (ways[wi][0], ways[wi][-1]):
                            if (pt[0] - a["lat"]) ** 2 + (
                                pt[1] - a["lon"]
                            ) ** 2 < TARGET_D2:
                                log.debug(
                                    "  fallback B->A matched route %d (%s)",
                                    rid,
                                    rel.get("name", ""),
                                )
                                routes_a[rid] = wi
                                shared.add(rid)
                                break
                        if rid in shared:
                            break

        if not shared:
            log.debug("  => NO ROUTE FOUND")
            return None
        else:
            log.debug("  candidates: %d routes", len(shared))

        # Compute platform-adjacent way indices for ranking
        plat_ways_a: set[int] | None = None
        plat_ways_b: set[int] | None = None
        platform_a = a.get("platform") or a.get("track")
        platform_b = b.get("platform") or b.get("track")
        if platform_a and region:
            plat_ways_a = self._platform_ways(
                a["lat"], a["lon"], region=region, platform=str(platform_a)
            )
        if platform_b and region:
            plat_ways_b = self._platform_ways(
                b["lat"], b["lon"], region=region, platform=str(platform_b)
            )

        def _nearest_on_path(lat, lon, coords_list):
            best_i, best_d = 0, float("inf")
            for i, pt in enumerate(coords_list):
                d = (pt[0] - lat) ** 2 + (pt[1] - lon) ** 2
                if d < best_d:
                    best_d, best_i = d, i
            return best_i

        best_path = None
        best_cost = float("inf")

        for rid in shared:
            rel = relations.get(rid)
            if not rel:
                continue
            ordered_ids = rel["way_ids"]
            wi_a = routes_a.get(rid)
            wi_b = routes_b.get(rid)
            if wi_a is None or wi_b is None:
                continue

            # Find positions in ordered way list
            try:
                pos_a = ordered_ids.index(way_ids[wi_a] if wi_a < len(way_ids) else 0)
            except ValueError:
                continue
            try:
                pos_b = ordered_ids.index(way_ids[wi_b] if wi_b < len(way_ids) else 0)
            except ValueError:
                continue

            # Build graph from all relation ways connected by endpoint proximity.
            # This naturally follows one track without interleaving parallel lines,
            # because parallel-track ways don't share nearby endpoints.
            wid_a = way_ids[wi_a] if wi_a < len(way_ids) else 0
            wid_b = way_ids[wi_b] if wi_b < len(way_ids) else 0
            _avail = {}
            for _wid in ordered_ids:
                _wi = (way_idx or {}).get(_wid)
                if _wi is not None:
                    _avail[_wid] = _wi
            _adj: dict[int, list[int]] = {}
            # Build adjacency from endpoint proximity
            CONN_D2 = 1e-6  # 0.001 deg squared (~110m)
            _avail_ids = list(_avail.keys())
            for ii in range(len(_avail_ids)):
                _wg = ways[_avail[_avail_ids[ii]]]
                _e0 = _wg[0]
                _e1 = _wg[-1]
                for jj in range(ii + 1, len(_avail_ids)):
                    _wgj = ways[_avail[_avail_ids[jj]]]
                    for _ep in (_wgj[0], _wgj[-1]):
                        if (_e0[0] - _ep[0]) ** 2 + (
                            _e0[1] - _ep[1]
                        ) ** 2 < CONN_D2 or (_e1[0] - _ep[0]) ** 2 + (
                            _e1[1] - _ep[1]
                        ) ** 2 < CONN_D2:
                            _adj.setdefault(_avail_ids[ii], []).append(_avail_ids[jj])
                            _adj.setdefault(_avail_ids[jj], []).append(_avail_ids[ii])
                            break
            # BFS shortest path
            _queue: list[tuple[int, list[int]]] = [(wid_a, [wid_a])]
            _visited = {wid_a}
            _path_wids: list[int] | None = None
            while _queue and _path_wids is None:
                _cur, _path = _queue.pop(0)
                if _cur == wid_b:
                    _path_wids = _path
                    break
                for _nbr in _adj.get(_cur, []):
                    if _nbr not in _visited:
                        _visited.add(_nbr)
                        _queue.append((_nbr, _path + [_nbr]))
            if _path_wids is None or len(_path_wids) < 2:
                log.debug(
                    "  route %d (%s): graph path not found (%d avail, %d edges), "
                    "trying full relation",
                    rid,
                    rel.get("name", "")[:40],
                    len(_avail),
                    sum(len(v) for v in _adj.values()) // 2,
                )
                coords = []
                for wid in ordered_ids:
                    _wi = (way_idx or {}).get(wid)
                    if _wi is None:
                        continue
                    wg = ways[_wi]
                    if not coords:
                        coords.extend(wg)
                    else:
                        last = coords[-1]
                        _wgd = ways[_wi]
                        _d0 = (last[0] - _wgd[0][0]) ** 2 + (last[1] - _wgd[0][1]) ** 2
                        _d1 = (last[0] - _wgd[-1][0]) ** 2 + (
                            last[1] - _wgd[-1][1]
                        ) ** 2
                        if _d0 < _d1:
                            coords.extend(_wgd[1:])
                        else:
                            coords.extend(reversed(_wgd[:-1]))
            else:
                # Concatenate along graph path
                coords = []
                for _wid in _path_wids:
                    _wi = _avail[_wid]
                    _wg = ways[_wi]
                    if not coords:
                        coords.extend(_wg)
                    else:
                        _last = coords[-1]
                        _d0 = (_last[0] - _wg[0][0]) ** 2 + (_last[1] - _wg[0][1]) ** 2
                        _d1 = (_last[0] - _wg[-1][0]) ** 2 + (
                            _last[1] - _wg[-1][1]
                        ) ** 2
                        if _d0 < _d1:
                            coords.extend(_wg[1:])
                        else:
                            coords.extend(reversed(_wg[:-1]))

            if coords and len(coords) >= 2:
                # Clip to nearest approach to A and B (fixes station jump)
                i_a = _nearest_on_path(a["lat"], a["lon"], coords)
                i_b = _nearest_on_path(b["lat"], b["lon"], coords)
                if i_a <= i_b:
                    coords = coords[i_a : i_b + 1]
                else:
                    coords = coords[i_b : i_a + 1][::-1]
                # Verify clipped path isn't absurdly long (bad pos_a/pos_b extraction
                # causes sub-ids to span beyond the intended segment)
                if len(coords) >= 2:
                    path_len = sum(
                        math.hypot(
                            coords[i + 1][0] - coords[i][0],
                            coords[i + 1][1] - coords[i][1],
                        )
                        for i in range(len(coords) - 1)
                    )
                    direct_d = math.hypot(a["lat"] - b["lat"], a["lon"] - b["lon"])
                    if path_len > 100 * direct_d:
                        log.debug(
                            "  %d (%s): sub-ids path %.4f deg vs direct %.4f deg (%.1fx), "
                            "trying full relation",
                            rid,
                            rel.get("name", "")[:40],
                            path_len,
                            direct_d,
                            path_len / direct_d,
                        )
                        # Fall back — use all relation ways in OSM member order
                        coords = []
                        for wid in ordered_ids:
                            _wi = (way_idx or {}).get(wid)
                            if _wi is None:
                                continue
                            wg = ways[_wi]
                            if not coords:
                                coords.extend(wg)
                            else:
                                last = coords[-1]
                                best_wi = 0
                                best_d = (last[0] - wg[0][0]) ** 2 + (
                                    last[1] - wg[0][1]
                                ) ** 2
                                for pi in range(1, len(wg)):
                                    pd = (last[0] - wg[pi][0]) ** 2 + (
                                        last[1] - wg[pi][1]
                                    ) ** 2
                                    if pd < best_d:
                                        best_d, best_wi = pd, pi
                                d0 = (last[0] - wg[0][0]) ** 2 + (
                                    last[1] - wg[0][1]
                                ) ** 2
                                d1 = (last[0] - wg[-1][0]) ** 2 + (
                                    last[1] - wg[-1][1]
                                ) ** 2
                                if (
                                    best_wi > 1
                                    and best_wi < len(wg) - 2
                                    and best_d > 0.0001
                                ):
                                    if d0 < d1:
                                        coords.extend(wg[best_wi:])
                                    else:
                                        coords.extend(reversed(wg[: best_wi + 1]))
                                elif d0 < d1:
                                    coords.extend(wg[1:])
                                else:
                                    coords.extend(reversed(wg[:-1]))
                        # Same inter-track gap cleanup as primary path
                        if coords and len(coords) >= 3:
                            _best_start, _best_end = 0, 0
                            _seg_start = 0
                            for ci in range(1, len(coords)):
                                _gap = math.hypot(
                                    coords[ci][0] - coords[ci - 1][0],
                                    coords[ci][1] - coords[ci - 1][1],
                                )
                                if _gap > 0.001:
                                    if ci - _seg_start > _best_end - _best_start:
                                        _best_start, _best_end = _seg_start, ci
                                    _seg_start = ci
                            if len(coords) - _seg_start > _best_end - _best_start:
                                _best_start, _best_end = _seg_start, len(coords)
                            if len(coords) - (_best_end - _best_start) > 0:
                                coords = coords[_best_start:_best_end]
                        if coords and len(coords) >= 2:
                            i_a = _nearest_on_path(a["lat"], a["lon"], coords)
                            i_b = _nearest_on_path(b["lat"], b["lon"], coords)
                            if i_a <= i_b:
                                coords = coords[i_a : i_b + 1]
                            else:
                                coords = coords[i_b : i_a + 1][::-1]
                            if len(coords) >= 2:
                                path_len = sum(
                                    math.hypot(
                                        coords[i + 1][0] - coords[i][0],
                                        coords[i + 1][1] - coords[i][1],
                                    )
                                    for i in range(len(coords) - 1)
                                )
                                # Log 21-sample OSM+REF comparison for debugging
                                if ref_geo and len(ref_geo) >= 3:
                                    _ns = 20
                                    a_name = a.get("name", "").replace(" ", "_")
                                    b_name = b.get("name", "").replace(" ", "_")
                                    div_samps = []
                                    for si in range(_ns + 1):
                                        frac = si / _ns
                                        gf = _polyline_sample(ref_geo, frac)
                                        rf = _polyline_sample(coords, frac)
                                        dd = math.hypot(gf[0] - rf[0], gf[1] - rf[1])
                                        div_samps.append(
                                            f"{si * 5:3d}% OSM=({rf[0]:.4f},{rf[1]:.4f}) "
                                            f"REF=({gf[0]:.4f},{gf[1]:.4f}) "
                                            f"Δ={dd:.6f}°"
                                        )
                                    log.info(
                                        "  seg %s->%s %s PD=%s\n    %s",
                                        a_name,
                                        b_name,
                                        rel.get("name", "")[:40],
                                        rel.get("name", "(full relation)")[:40],
                                        "\n    ".join(div_samps),
                                    )

            if coords and len(coords) >= 2:
                # Verify route actually passes near both stations
                dist_a = min(
                    (c[0] - a["lat"]) ** 2 + (c[1] - a["lon"]) ** 2 for c in coords
                )
                dist_b = min(
                    (c[0] - b["lat"]) ** 2 + (c[1] - b["lon"]) ** 2 for c in coords
                )
                if dist_a > 0.0001 or dist_b > 0.0001:
                    continue
                # Rank by divergence from Transitous ref_geo (>=3 pts for meaningful shape), fall back to path length
                using_div = False
                if ref_geo and len(ref_geo) >= 3:
                    using_div = True
                    n_samp = 20
                    avg_div = 0.0
                    for si in range(n_samp + 1):
                        frac = si / n_samp
                        gf = _polyline_sample(ref_geo, frac)
                        rf = _polyline_sample(coords, frac)
                        avg_div += math.hypot(gf[0] - rf[0], gf[1] - rf[1])
                    avg_div /= n_samp + 1
                    cost = avg_div
                    # When divergence is very low (all routes closely match a sparse reference),
                    # prefer routes with more coordinate detail (denser railway geometry). This
                    # prevents sparse/collinear Transitous references from selecting collinear routes.
                    if avg_div < 0.02:
                        cost -= 0.00001 * len(coords)
                else:
                    # Normalized step distance: prefer denser (more detailed) routes
                    step = max(1, len(coords) // 200)
                    sampled_path = (
                        sum(
                            abs(coords[ci][0] - coords[ci - 1][0])
                            + abs(coords[ci][1] - coords[ci - 1][1])
                            for ci in range(1, len(coords), step)
                        )
                        * step
                    )
                    cost = sampled_path / len(coords)
                # Prefer routes whose way at each station is adjacent to the Transitous platform
                if plat_ways_a and wi_a in plat_ways_a:
                    cost *= 0.9
                if plat_ways_b and wi_b in plat_ways_b:
                    cost *= 0.9
                # Penalise reversed routes (slightly; way concatenation is handled below)
                if pos_a > pos_b:
                    cost *= 1.1
                rname = rel.get("name", "")[:50]
                log.debug(
                    "  try %d (%-50s): OK %d coords cost=%.4f%s%s%s",
                    rid,
                    rname,
                    len(coords),
                    cost,
                    " (div)" if using_div else "",
                    " rev" if pos_a > pos_b else "",
                    " plat"
                    if wi_a in (plat_ways_a or set()) or wi_b in (plat_ways_b or set())
                    else "",
                )
                if cost < best_cost:
                    best_cost = cost
                    best_path = (rid, rel.get("name", ""), coords)

        if best_path:
            rid, rnam, coords = best_path
            # Fill gaps > 0.001 deg with interpolated points
            _raw_n = len(coords)
            _filled = [coords[0]]
            for _ci in range(1, len(coords)):
                _g = math.hypot(
                    coords[_ci][0] - coords[_ci - 1][0],
                    coords[_ci][1] - coords[_ci - 1][1],
                )
                if _g > 0.001:
                    _n = max(2, int(_g / 0.0002))
                    _lat0, _lon0 = coords[_ci - 1]
                    _lat1, _lon1 = coords[_ci]
                    for _si in range(1, _n):
                        _frac = _si / _n
                        _filled.append(
                            (
                                _lat0 + (_lat1 - _lat0) * _frac,
                                _lon0 + (_lon1 - _lon0) * _frac,
                            )
                        )
                _filled.append(coords[_ci])
            coords = _filled
            log.debug(
                "  => SELECTED route %d (%s): %d coords (%d raw), cost=%.4f",
                rid,
                rnam,
                len(coords),
                _raw_n,
                best_cost,
            )
            return coords
        log.debug("  => NO ROUTE SURVIVED VERIFICATION")
        return None
