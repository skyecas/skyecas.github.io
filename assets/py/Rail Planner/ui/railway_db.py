"""Local OSM railway database for geometry enrichment.

Downloads a Geofabrik PBF once, extracts railway ways via osmium,
caches as compressed JSON, and queries locally with a grid spatial index.
"""

from __future__ import annotations
import json
import gzip
import time
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
}

LAT_MIN = -90
LAT_MAX = 90
LON_MIN = -180
LON_MAX = 180

# Country boundary data for dynamic region detection
_COUNTRY_INDEX: dict | None = None
_COUNTRY_INDEX_LOCK = threading.Lock()
_COUNTRY_GEOJSON_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    "master/geojson/ne_110m_admin_0_countries.geojson"
)
_COUNTRY_INDEX_PATH = DATA_DIR / "country_index.json"

# Known exceptions to the "lowercase-hyphenated name" Geofabrik slug pattern
_GEOFABRIK_SLUG_OVERRIDES: dict[str, str] = {
    "United Kingdom": "great-britain",
    "Ireland": "ireland-and-northern-ireland",
    "Bosnia and Herzegovina": "bosnia-herzegovina",
    "Czech Republic": "czech-republic",
    "North Macedonia": "north-macedonia",
    "Moldova": "moldova",
}


def _point_in_polygon(lat: float, lon: float, poly: list[tuple[float, float]]) -> bool:
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        yi, xi = poly[i]
        yj, xj = poly[j]
        if ((xi > lon) != (xj > lon)) and (
            lat < (yj - yi) * (lon - xi) / (xj - xi) + yi
        ):
            inside = not inside
        j = i
    return inside


def _ensure_country_index() -> dict | None:
    """Download Natural Earth country boundaries and build a grid spatial index."""
    global _COUNTRY_INDEX
    if _COUNTRY_INDEX is not None:
        return _COUNTRY_INDEX

    with _COUNTRY_INDEX_LOCK:
        if _COUNTRY_INDEX is not None:
            return _COUNTRY_INDEX

        if _COUNTRY_INDEX_PATH.exists():
            try:
                with open(_COUNTRY_INDEX_PATH) as f:
                    _COUNTRY_INDEX = json.load(f)
                    return _COUNTRY_INDEX
            except Exception:
                _COUNTRY_INDEX_PATH.unlink(missing_ok=True)

        try:
            log.info("Downloading country boundary data for region detection...")
            resp = requests.get(_COUNTRY_GEOJSON_URL, timeout=120)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            log.warning("Failed to download country boundaries: %s", exc)
            return None

        index: dict[str, dict] = {}
        grid: dict[tuple[int, int], list[str]] = {}
        cell_deg = 2.0

        for feat in data["features"]:
            props = feat["properties"]
            name: str = props.get("NAME", "")
            iso: str = props.get("ISO_A2", "")
            if not name or not iso:
                continue
            geom = feat["geometry"]
            rings: list[list[list[float]]] = []
            if geom["type"] == "Polygon":
                rings = geom["coordinates"]
            elif geom["type"] == "MultiPolygon":
                for poly in geom["coordinates"]:
                    rings.extend(poly)
            else:
                continue
            coords = max(rings, key=lambda r: len(r))
            pts = [(c[1], c[0]) for c in coords]
            min_la = min(p[0] for p in pts)
            max_la = max(p[0] for p in pts)
            min_lo = min(p[1] for p in pts)
            max_lo = max(p[1] for p in pts)
            key = f"{name}|{iso}"
            index[key] = {"name": name, "iso": iso, "coords": pts}
            for r in range(
                max(0, int((min_la - LAT_MIN) / cell_deg)),
                int((max_la - LAT_MIN) / cell_deg) + 1,
            ):
                for c in range(
                    max(0, int((min_lo - LON_MIN) / cell_deg)),
                    int((max_lo - LON_MIN) / cell_deg) + 1,
                ):
                    grid.setdefault((r, c), []).append(key)

        index["_grid"] = {str(k): v for k, v in grid.items()}
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with open(_COUNTRY_INDEX_PATH, "w") as f:
                json.dump(index, f)
        except Exception:
            pass
        _COUNTRY_INDEX = index
        log.info("Country index built: %d countries", len(index) - 1)
        return index


def find_country(lat: float, lon: float) -> str | None:
    """Return the country name for a lat/lon using Natural Earth boundaries."""
    idx = _ensure_country_index()
    if idx is None:
        return None
    cell_deg = 2.0
    row = max(
        0, min(int((lat - LAT_MIN) / cell_deg), int((LAT_MAX - LAT_MIN) / cell_deg) - 1)
    )
    col = max(
        0, min(int((lon - LON_MIN) / cell_deg), int((LON_MAX - LON_MIN) / cell_deg) - 1)
    )
    candidates = list(idx.get("_grid", {}).get(f"({row}, {col})", []))
    if not candidates:
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                nr, nc = row + dr, col + dc
                candidates.extend(idx.get("_grid", {}).get(f"({nr}, {nc})", []))
    seen: set[str] = set()
    for ck in candidates:
        if ck in seen:
            continue
        seen.add(ck)
        entry = idx.get(ck)
        if entry and _point_in_polygon(lat, lon, entry["coords"]):
            return entry["name"]
    return None


def country_to_geofabrik(country_name: str) -> tuple[str, str] | None:
    """Convert a country name to a Geofabrik region slug and download URL.

    Returns (slug, url) or None if no Geofabrik URL can be constructed.
    Only European countries are supported (Geofabrik /europe/ subdirectory).
    """
    slug = _GEOFABRIK_SLUG_OVERRIDES.get(country_name)
    if slug is None:
        slug = country_name.lower().replace(" ", "-").replace("'", "")
    url = f"https://download.geofabrik.de/europe/{slug}-latest.osm.pbf"
    return slug, url


def detect_region(lat: float, lon: float) -> str | None:
    """Detect the Geofabrik region slug for a coordinate.

    First checks the static REGION_BBOXES (GB is pre-defined), then falls
    back to dynamic country detection using Natural Earth boundaries.
    """
    for name, (min_lat, min_lon, max_lat, max_lon) in REGION_BBOXES.items():
        if min_lat <= lat <= max_lat and min_lon <= lon <= max_lon:
            return name
    country = find_country(lat, lon)
    if country:
        result = country_to_geofabrik(country)
        if result:
            slug, url = result
            if slug not in REGIONS and slug not in REGION_BBOXES:
                log.info("Discovered new region: %s (%s)", slug, country)
                REGIONS[slug] = {
                    "url": url,
                    "pbf": f"{slug}-latest.osm.pbf",
                    "cache": f"railways.{slug}.json.gz",
                    "size_mb": 0,
                }
            return slug
    return None


class _RailwayExtractor(osmium.SimpleHandler):
    """Parses OSM PBF and collects railway way/platform coordinates and route relations."""

    CACHE_VERSION = 4

    def __init__(self, progress_cb=None, progress_log_cb=None):
        super().__init__()
        self.ways: list[dict] = []
        self.platforms: list[dict] = []
        self.relations: dict[int, dict] = {}
        self.way_routes: dict[int, list[int]] = {}
        self._progress_cb = progress_cb
        self._progress_log_cb = progress_log_cb
        self._ways_seen = 0
        self._relations_seen = 0
        self._last_progress_at = 0.0
        self._last_progress_log_at = 0.0

    def _report_progress(self, *, force: bool = False) -> None:
        if self._progress_cb is None:
            return
        now = time.time()
        if not force and now - self._last_progress_at < 1.0:
            return
        self._last_progress_at = now
        values = {
            "parse_ways_seen": self._ways_seen,
            "parse_relations_seen": self._relations_seen,
            "parse_railway_ways": len(self.ways),
            "parse_platforms": len(self.platforms),
            "parse_route_relations": len(self.relations),
        }
        self._progress_cb(values)
        if self._progress_log_cb is not None and (
            force or now - self._last_progress_log_at >= 15.0
        ):
            self._last_progress_log_at = now
            self._progress_log_cb(values)

    def way(self, w):
        self._ways_seen += 1
        tag = w.tags.get("railway")
        wid = w.id
        if tag in RAILWAY_TAGS:
            coords = [(n.lat, n.lon) for n in w.nodes if n.location.valid()]
            if len(coords) >= 2:
                self.ways.append(
                    {
                        "id": wid,
                        "coords": coords,
                        "tags": {
                            "electrified": w.tags.get("electrified", ""),
                            "voltage": w.tags.get("voltage", ""),
                            "frequency": w.tags.get("frequency", ""),
                            "railway": tag,
                        },
                    }
                )
        elif tag == "platform":
            coords = [(n.lat, n.lon) for n in w.nodes if n.location.valid()]
            if len(coords) >= 2:
                ref = w.tags.get("ref", "")
                self.platforms.append({"ref": ref, "coords": coords})
        self._report_progress()

    def relation(self, r):
        self._relations_seen += 1
        if r.tags.get("route") in ("train", "railway"):
            name = r.tags.get("name", "") or ""
            ref = r.tags.get("ref", "") or ""
            way_ids = [m.ref for m in r.members if m.type == "w"]
            if len(way_ids) >= 2:
                rid = r.id
                self.relations[rid] = {"name": name, "ref": ref, "way_ids": way_ids}
                for wid in way_ids:
                    self.way_routes.setdefault(wid, []).append(rid)
        self._report_progress()


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
        self._region_way_tags: dict[str, dict[int, dict[str, str]]] = {}
        self._region_way_idx: dict[str, dict[int, int]] = {}
        self._bg_threads: dict[str, threading.Thread] = {}
        self._rel_cache: dict[int, dict] = {}
        self._region_dl_progress: dict[str, tuple[int, int]] = {}
        self._region_started_at: dict[str, float] = {}
        self._region_phase_started_at: dict[str, float] = {}
        self._region_status: dict[str, dict] = {}

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
        now = time.time()
        for key in set(self._region_ready.keys()) | set(self._region_loading.keys()):
            info = REGIONS.get(key, {})
            phase = self._region_phase.get(
                key, "queued" if self._region_loading.get(key) else "idle"
            )
            if self._region_ready.get(key):
                phase = "ready"
            dl_downloaded, dl_total = self._region_dl_progress.get(key, (0, 0))
            phase_started_at = self._region_phase_started_at.get(key, now)
            status = self._region_status.get(key, {})
            dl_started_at = status.get("download_started_at", phase_started_at)
            dl_elapsed = max(0.001, now - dl_started_at)
            dl_rate = dl_downloaded / dl_elapsed if dl_downloaded else 0
            dl_eta = (
                (dl_total - dl_downloaded) / dl_rate
                if dl_total and dl_rate and dl_total > dl_downloaded
                else 0
            )
            region_status = {
                "ready": self._region_ready.get(key, False),
                "loading": self._region_loading.get(key, False),
                "phase": phase,
                "phase_detail": status.get("phase_detail", ""),
                "elapsed_sec": round(now - self._region_started_at.get(key, now), 1),
                "phase_elapsed_sec": round(now - phase_started_at, 1),
                "ways": len(self._region_cache.get(key, [])),
                "platforms": len(self._region_platforms.get(key, [])),
                "pbf_size_mb": info.get("size_mb", 0),
                "dl_downloaded": dl_downloaded,
                "dl_total": dl_total,
                "dl_rate_bps": round(dl_rate, 1),
                "dl_eta_sec": round(dl_eta, 1),
            }
            region_status.update(status)
            regions[key] = region_status
        return {"regions": regions}

    def _set_phase(self, region: str, phase: str, detail: str = "") -> None:
        self._region_phase[region] = phase
        self._region_phase_started_at[region] = time.time()
        self._region_status.setdefault(region, {})["phase_detail"] = detail
        log.info("Railway DB %s: %s%s", region, phase, f" - {detail}" if detail else "")

    def _update_status(self, region: str, **values) -> None:
        self._region_status.setdefault(region, {}).update(values)

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
            self._region_started_at[region] = time.time()
            self._set_phase(region, "loading_cache", "Reading compressed railway cache")
            result = self._load_cache(cache_path)
            if result is not None:
                if len(result) == 6:
                    ways, platforms, relations, way_routes, way_ids, way_tags = result
                else:
                    ways, platforms, relations, way_routes, way_ids = result
                    way_tags = {}
                self._set_region_ready(
                    region, ways, platforms, relations, way_routes, way_ids, way_tags
                )
                return

        # No cache; start background download + parse
        with self._lock:
            if self._region_ready.get(region) or self._region_loading.get(region):
                return
            self._region_loading[region] = True
            self._region_started_at[region] = time.time()
            self._set_phase(region, "queued", "Waiting for background loader")
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
        if not pbf_path.exists():
            self._set_phase(region, "downloading", f"Downloading {info['url']}")
            try:
                self._download_pbf(info["url"], pbf_path, info["size_mb"], region)
            except Exception as e:
                log.error("PBF download failed: %s", e)
                self._region_ready[region] = False
                self._set_phase(region, "failed", str(e))
                return
        else:
            self._region_dl_progress[region] = (
                pbf_path.stat().st_size,
                pbf_path.stat().st_size,
            )

        self._set_phase(
            region, "parsing", "Extracting railway ways, platforms, and route relations"
        )
        ways, platforms, relations, way_routes = self._parse_pbf(pbf_path, region)
        if ways:
            self._set_phase(region, "saving_cache", "Writing compressed railway cache")
            self._save_cache(cache_path, ways, platforms, relations, way_routes)
            # Convert new extractor format to old flat format for region_cache
            way_coords = [w["coords"] for w in ways]
            way_ids = [w["id"] for w in ways]
            way_tags = {w["id"]: w.get("tags", {}) for w in ways}
            self._set_phase(
                region, "building_index", "Building spatial index for route lookup"
            )
            self._set_region_ready(
                region, way_coords, platforms, relations, way_routes, way_ids, way_tags
            )
        else:
            log.warning("No railway ways found in %s PBF", region)
            self._region_ready[region] = False
            self._set_phase(region, "failed", "No railway ways extracted from PBF")

    def _set_region_ready(
        self,
        region: str,
        ways: list,
        platforms: list | None = None,
        relations: dict | None = None,
        way_routes: dict | None = None,
        way_ids: list[int] | None = None,
        way_tags: dict[int, dict[str, str]] | None = None,
    ) -> None:
        self._region_cache[region] = ways
        if platforms is None:
            platforms = []
        self._region_platforms[region] = platforms
        self._region_relations[region] = relations or {}
        self._region_way_routes[region] = way_routes or {}
        self._region_way_ids[region] = way_ids or []
        self._region_way_tags[region] = way_tags or {}
        if way_ids:
            self._region_way_idx[region] = {wid: i for i, wid in enumerate(way_ids)}
        self._region_index[region] = _GridIndex(ways)
        self._region_ready[region] = True
        self._region_loading[region] = False
        self._set_phase(region, "ready", "Railway DB ready")
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
                way_tags = {
                    int(w["id"]): w.get("tags", {})
                    for w in ways_data
                    if w.get("id") is not None
                }
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
                return ways, platforms, relations, way_routes, way_ids, way_tags
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
                ways_data = [
                    {"id": w["id"], "coords": w["coords"], "tags": w.get("tags", {})}
                    for w in ways
                ]
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

    def _download_pbf(
        self, url: str, path: Path, size_mb: int, region: str = ""
    ) -> None:
        log.info("Downloading PBF %s (%.1f GB)...", url, size_mb / 1000)
        try:
            resp = requests.get(url, stream=True, timeout=600)
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            total = total or size_mb * 1_000_000
            self._region_dl_progress[region] = (0, total)
            self._update_status(
                region,
                download_started_at=time.time(),
                download_url=url,
                download_path=str(path),
            )
            tmp = path.with_suffix(".pbf.downloading")
            with open(tmp, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if downloaded % (1024 * 256) < 65536 or downloaded == total:
                            self._region_dl_progress[region] = (downloaded, total)
                            self._update_status(
                                region,
                                download_file_mb=round(downloaded / 1_000_000, 1),
                                download_total_mb=round(total / 1_000_000, 1),
                                download_pct=round(downloaded / total * 100, 1)
                                if total
                                else 0,
                            )
            tmp.rename(path)
            self._region_dl_progress[region] = (downloaded, total)
            log.info("PBF downloaded to %s", path)
        except Exception as e:
            log.error("PBF download failed: %s", e)
            raise

    def _parse_pbf(
        self, pbf_path: Path, region: str = ""
    ) -> tuple[list, list, dict, dict]:
        log.info("Parsing PBF %s...", pbf_path)
        start = time.time()
        try:

            def _progress(values: dict) -> None:
                self._update_status(region, **values)

            def _progress_log(values: dict) -> None:
                elapsed = time.time() - start
                log.info(
                    "Parsing PBF %s: %.0fs, scanned %d ways + %d relations, "
                    "extracted %d railway ways + %d platforms + %d route relations",
                    region or pbf_path.name,
                    elapsed,
                    values.get("parse_ways_seen", 0),
                    values.get("parse_relations_seen", 0),
                    values.get("parse_railway_ways", 0),
                    values.get("parse_platforms", 0),
                    values.get("parse_route_relations", 0),
                )

            extractor = _RailwayExtractor(
                progress_cb=_progress, progress_log_cb=_progress_log
            )
            extractor.apply_file(str(pbf_path), locations=True)
            extractor._report_progress(force=True)
            elapsed = time.time() - start
            self._update_status(
                region,
                parse_elapsed_sec=round(elapsed, 1),
                parse_railway_ways=len(extractor.ways),
                parse_platforms=len(extractor.platforms),
                parse_route_relations=len(extractor.relations),
            )
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

    def traction_hint_for_geometry(
        self, geometry: list[dict[str, float]]
    ) -> str | None:
        if not geometry:
            return None
        counts = {"electric": 0, "diesel": 0, "unknown": 0}
        # Sample up to 48 points for better coverage on long segments.
        sample_count = min(48, len(geometry))
        if sample_count <= 0:
            return None
        for si in range(sample_count):
            pt = geometry[
                min(
                    len(geometry) - 1,
                    int(si * (len(geometry) - 1) / max(1, sample_count - 1)),
                )
            ]
            region = detect_region(pt["lat"], pt["lon"])
            if not region or not self.is_ready(region):
                continue
            idx = self._region_index.get(region)
            way_ids = self._region_way_ids.get(region, [])
            way_tags = self._region_way_tags.get(region, {})
            if not idx:
                continue
            # Slightly larger bbox improves matching on curves and older caches.
            candidates = idx.query_bbox(
                max(LAT_MIN, pt["lat"] - 0.003),
                max(LON_MIN, pt["lon"] - 0.003),
                min(LAT_MAX, pt["lat"] + 0.003),
                min(LON_MAX, pt["lon"] + 0.003),
            )
            for wi in candidates[:20]:
                wid = way_ids[wi] if wi < len(way_ids) else 0
                tags = way_tags.get(wid, {})
                electrified = (tags.get("electrified") or "").lower()
                voltage = tags.get("voltage") or ""
                if (
                    electrified in {"contact_line", "rail", "yes", "4th_rail"}
                    or voltage
                ):
                    counts["electric"] += 1
                elif electrified in {"no", "none"}:
                    counts["diesel"] += 1
                else:
                    counts["unknown"] += 1
        known = counts["electric"] + counts["diesel"]
        if known == 0:
            return None
        # Allow more permissive thresholds to handle mixed tagging; if
        # neither dominates, report bi-mode.
        if counts["electric"] / known >= 0.7:
            return "electric"
        if counts["diesel"] / known >= 0.7:
            return "diesel"
        return "bi-mode"

    def query_corridor(
        self,
        anchor_points: list[dict],
        ref_geos: list[list[tuple[float, float]]] | None = None,
        regions: list[str] | None = None,
    ) -> list[tuple[float, float]] | None:
        """Build geometry using route relations, with cross-station coverage fallback."""
        if len(anchor_points) < 2:
            return None

        if regions is None:
            mid = (len(anchor_points) - 1) // 2
            region = detect_region(anchor_points[0]["lat"], anchor_points[0]["lon"])
            if not region:
                region = detect_region(
                    anchor_points[mid]["lat"], anchor_points[mid]["lon"]
                )
            if not region or not self.is_ready(region):
                return None
            regions = [region]

        regions_ready = [r for r in regions if self.is_ready(r)]
        if not regions_ready:
            return None

        log.debug(
            "query_corridor: %d anchor points for %s",
            len(anchor_points),
            ", ".join(regions_ready),
        )

        # Phase 0: try to find a single route covering all anchor points
        # Only attempt for single-region queries (cross-border routes never share a route)
        prefer_rid: int | None = None
        prefer_rid_region: str | None = None
        if len(anchor_points) >= 3 and len(regions_ready) == 1:
            _region = regions_ready[0]
            _ways = self._region_cache[_region]
            _idx = self._region_index[_region]
            _way_ids = self._region_way_ids.get(_region, [])
            _relations = self._region_relations.get(_region, {})
            _way_routes = self._region_way_routes.get(_region, {})
            _way_idx = self._region_way_idx.get(_region, {})

            TARGET_D2 = 0.0004
            routes_per_anchor: list[set[int]] = []
            for ap in anchor_points:
                rids: set[int] = set()
                inds = _idx.query_bbox(
                    max(LAT_MIN, ap["lat"] - 0.01),
                    max(LON_MIN, ap["lon"] - 0.01),
                    min(LAT_MAX, ap["lat"] + 0.01),
                    min(LON_MAX, ap["lon"] + 0.01),
                )
                for wi in inds:
                    wid = _way_ids[wi] if wi < len(_way_ids) else 0
                    for rid in _way_routes.get(wid, []):
                        rel = _relations.get(rid)
                        if rel is None:
                            continue
                        for w in rel["way_ids"]:
                            wii = _way_idx.get(w)
                            if wii is None or not _ways[wii]:
                                continue
                            for pt in (_ways[wii][0], _ways[wii][-1]):
                                if (pt[0] - ap["lat"]) ** 2 + (
                                    pt[1] - ap["lon"]
                                ) ** 2 < TARGET_D2:
                                    rids.add(rid)
                                    break
                            if rid in rids:
                                break
                routes_per_anchor.append(rids)
            if routes_per_anchor:
                shared_rids = (
                    set.intersection(*routes_per_anchor) if routes_per_anchor else set()
                )
                if shared_rids:
                    prefer_rid = max(
                        shared_rids,
                        key=lambda r: len(_relations.get(r, {}).get("way_ids", [])),
                    )
                    prefer_rid_region = _region
                    log.debug(
                        "  full-route candidate: %d (%s) covers all %d anchors",
                        prefer_rid,
                        _relations.get(prefer_rid, {}).get("name", "")[:40],
                        len(anchor_points),
                    )

        all_coords: list[tuple[float, float]] = []
        prev_route_by_region: dict[str, int] = {}
        for i in range(len(anchor_points) - 1):
            a = anchor_points[i]
            b = anchor_points[i + 1]
            ref_geo = ref_geos[i] if ref_geos and i < len(ref_geos) else None

            seg = None
            for _region in regions_ready:
                _ways = self._region_cache[_region]
                _idx = self._region_index[_region]
                _way_ids = self._region_way_ids.get(_region, [])
                _relations = self._region_relations.get(_region, {})
                _way_routes = self._region_way_routes.get(_region, {})
                _way_idx = self._region_way_idx.get(_region, {})

                _prefer = prefer_rid if prefer_rid_region == _region else None
                _route_bias = prev_route_by_region.get(_region)
                route_result = self._route_segment(
                    a,
                    b,
                    _ways,
                    _way_ids,
                    _relations,
                    _way_routes,
                    _idx,
                    _way_idx,
                    ref_geo=ref_geo,
                    region=_region,
                    _prefer_rid=_prefer,
                    _route_bias_rid=_route_bias,
                )
                if route_result is not None:
                    seg, selected_rid = route_result
                    if selected_rid is not None:
                        prev_route_by_region[_region] = selected_rid
                    break

            if seg is None:
                log.debug(
                    "query_corridor: seg %d (%s->%s) returned None across %s",
                    i,
                    a.get("name", f"{a['lat']:.4f},{a['lon']:.4f}"),
                    b.get("name", f"{b['lat']:.4f},{b['lon']:.4f}"),
                    ", ".join(regions_ready),
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
                # Join at the shared anchor point (station), not at last coord.
                anchor = a  # current segment start is the previous segment's end.
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
        _prefer_rid: int | None = None,
        _route_bias_rid: int | None = None,
    ) -> tuple[list, int | None] | None:
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

        # Compute platform-adjacent way indices before the preferred-route fast path.
        # Otherwise a through route can pick the nearest parallel approach track,
        # then clip across platforms and duplicate the station throat.
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

        def _platform_way_for_route(
            rid: int,
            plat_ways: set[int] | None,
            lat: float,
            lon: float,
        ) -> int | None:
            if not plat_ways:
                return None
            best_wi, best_d = None, float("inf")
            for wi in plat_ways:
                wid = way_ids[wi] if wi < len(way_ids) else 0
                if rid not in way_routes.get(wid, []):
                    continue
                d = min((c[0] - lat) ** 2 + (c[1] - lon) ** 2 for c in ways[wi])
                if d < best_d:
                    best_wi, best_d = wi, d
            return best_wi

        for rid in list(shared):
            pwi_a = _platform_way_for_route(rid, plat_ways_a, a["lat"], a["lon"])
            pwi_b = _platform_way_for_route(rid, plat_ways_b, b["lat"], b["lon"])
            if pwi_a is not None:
                routes_a[rid] = pwi_a
            if pwi_b is not None:
                routes_b[rid] = pwi_b
            if pwi_a is not None or pwi_b is not None:
                log.debug(
                    "  route %d: platform way override A=%s B=%s",
                    rid,
                    pwi_a if pwi_a is not None else "nearest",
                    pwi_b if pwi_b is not None else "nearest",
                )

        def _clip_between_points(coords_list, a_pt: dict, b_pt: dict):
            if len(coords_list) < 2:
                return coords_list

            def _project(lat: float, lon: float):
                best = (0, coords_list[0], 0.0, float("inf"))
                for i in range(len(coords_list) - 1):
                    p0 = coords_list[i]
                    p1 = coords_list[i + 1]
                    vx = p1[0] - p0[0]
                    vy = p1[1] - p0[1]
                    seg2 = vx * vx + vy * vy
                    if seg2 == 0:
                        t = 0.0
                    else:
                        t = ((lat - p0[0]) * vx + (lon - p0[1]) * vy) / seg2
                        t = max(0.0, min(1.0, t))
                    proj = (p0[0] + vx * t, p0[1] + vy * t)
                    d = (proj[0] - lat) ** 2 + (proj[1] - lon) ** 2
                    if d < best[3]:
                        best = (i, proj, t, d)
                return best

            ia, pa, ta, _ = _project(a_pt["lat"], a_pt["lon"])
            ib, pb, tb, _ = _project(b_pt["lat"], b_pt["lon"])
            pos_a = ia + ta
            pos_b = ib + tb
            if pos_a <= pos_b:
                clipped = [pa]
                clipped.extend(coords_list[ia + 1 : ib + 1])
                clipped.append(pb)
            else:
                clipped = [pb]
                clipped.extend(coords_list[ib + 1 : ia + 1])
                clipped.append(pa)
                clipped.reverse()

            deduped = []
            for pt in clipped:
                if (
                    not deduped
                    or (pt[0] - deduped[-1][0]) ** 2 + (pt[1] - deduped[-1][1]) ** 2
                    > 1e-12
                ):
                    deduped.append(pt)
            return deduped

        def _trim_endpoint_overshoot(coords_list):
            if len(coords_list) < 4:
                return coords_list
            direct = math.hypot(a["lat"] - b["lat"], a["lon"] - b["lon"])
            if direct <= 0:
                return coords_list
            limit = min(0.0012, max(0.00025, direct * 0.2))
            coords_list = list(coords_list)

            def _dist_to(pt, target):
                return math.hypot(pt[0] - target["lat"], pt[1] - target["lon"])

            while len(coords_list) > 3:
                d0 = _dist_to(coords_list[0], a)
                d1 = _dist_to(coords_list[1], a)
                if d0 <= limit and d1 < d0:
                    coords_list.pop(0)
                else:
                    break
            while len(coords_list) > 3:
                d0 = _dist_to(coords_list[-1], b)
                d1 = _dist_to(coords_list[-2], b)
                if d0 <= limit and d1 < d0:
                    coords_list.pop()
                else:
                    break
            return coords_list

        # Fast path: if a preferred route was supplied and covers both endpoints, use it directly
        if _prefer_rid is not None and _prefer_rid in shared:
            _rel = relations.get(_prefer_rid)
            if _rel is not None:
                rnam = _rel.get("name", "")[:50]
                _wi_a = routes_a.get(_prefer_rid)
                _wi_b = routes_b.get(_prefer_rid)
                if _wi_a is not None and _wi_b is not None:
                    _wid_a = way_ids[_wi_a] if _wi_a < len(way_ids) else 0
                    _wid_b = way_ids[_wi_b] if _wi_b < len(way_ids) else 0
                    _cached = self._rel_cache.get(_prefer_rid)
                    if (
                        _cached is not None
                        and _wid_a in _cached["avail"]
                        and _wid_b in _cached["avail"]
                    ):
                        _avail = _cached["avail"]
                        _adj = _cached["adj"]
                    else:
                        _avail = {}
                        for _wid in _rel["way_ids"]:
                            _wi = (way_idx or {}).get(_wid)
                            if _wi is not None:
                                _avail[_wid] = _wi
                        _adj: dict[int, list[int]] = {}
                        CONN_D2 = 1e-6
                        _avail_ids = list(_avail.keys())
                        for ii in range(len(_avail_ids)):
                            _wg = ways[_avail[_avail_ids[ii]]]
                            _e0, _e1 = _wg[0], _wg[-1]
                            for jj in range(ii + 1, len(_avail_ids)):
                                _wgj = ways[_avail[_avail_ids[jj]]]
                                for _ep in (_wgj[0], _wgj[-1]):
                                    if (_e0[0] - _ep[0]) ** 2 + (
                                        _e0[1] - _ep[1]
                                    ) ** 2 < CONN_D2 or (_e1[0] - _ep[0]) ** 2 + (
                                        _e1[1] - _ep[1]
                                    ) ** 2 < CONN_D2:
                                        _adj.setdefault(_avail_ids[ii], []).append(
                                            _avail_ids[jj]
                                        )
                                        _adj.setdefault(_avail_ids[jj], []).append(
                                            _avail_ids[ii]
                                        )
                                        break
                        if _prefer_rid not in self._rel_cache:
                            self._rel_cache[_prefer_rid] = {
                                "avail": _avail,
                                "adj": _adj,
                                "name": rnam,
                            }
                    if _wid_a in _avail and _wid_b in _avail:
                        _queue = [(_wid_a, [_wid_a])]
                        _visited = {_wid_a}
                        _path_wids = None
                        while _queue and _path_wids is None:
                            _cur, _path = _queue.pop(0)
                            if _cur == _wid_b:
                                _path_wids = _path
                                break
                            for _nbr in _adj.get(_cur, []):
                                if _nbr not in _visited:
                                    _visited.add(_nbr)
                                    _queue.append((_nbr, _path + [_nbr]))
                        if _path_wids and len(_path_wids) >= 2:
                            coords = []
                            for _wid in _path_wids:
                                _wi = _avail[_wid]
                                _wg = ways[_wi]
                                if not coords:
                                    coords.extend(_wg)
                                else:
                                    _last = coords[-1]
                                    _d0 = (_last[0] - _wg[0][0]) ** 2 + (
                                        _last[1] - _wg[0][1]
                                    ) ** 2
                                    _d1 = (_last[0] - _wg[-1][0]) ** 2 + (
                                        _last[1] - _wg[-1][1]
                                    ) ** 2
                                    if _d0 < _d1:
                                        coords.extend(_wg[1:])
                                    else:
                                        coords.extend(reversed(_wg[:-1]))
                            if len(coords) >= 2:
                                coords = _clip_between_points(coords, a, b)
                                coords = _trim_endpoint_overshoot(coords)
                            if len(coords) >= 2:
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
                                            _filled.append(
                                                (
                                                    _lat0 + (_lat1 - _lat0) * _si / _n,
                                                    _lon0 + (_lon1 - _lon0) * _si / _n,
                                                )
                                            )
                                    _filled.append(coords[_ci])
                                coords = _filled
                                log.debug(
                                    "  => FAST PATH route %d (%s): %d coords",
                                    _prefer_rid,
                                    rnam,
                                    len(coords),
                                )
                                return coords, _prefer_rid
                        log.debug(
                            "  route %d: prefer path not found, falling through",
                            _prefer_rid,
                        )

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
            wid_a = way_ids[wi_a] if wi_a < len(way_ids) else 0
            wid_b = way_ids[wi_b] if wi_b < len(way_ids) else 0
            _new_graph = True
            _cached = self._rel_cache.get(rid)
            if (
                _cached is not None
                and wid_a in _cached["avail"]
                and wid_b in _cached["avail"]
            ):
                _avail = _cached["avail"]
                _adj = _cached["adj"]
                _new_graph = False
                log.debug("  route %d: using cached graph", rid)
            elif _cached is not None:
                log.debug(
                    "  route %d: cached graph but endpoints not in avail",
                    rid,
                )
            else:
                _avail = {}
                for _wid in ordered_ids:
                    _wi = (way_idx or {}).get(_wid)
                    if _wi is not None:
                        _avail[_wid] = _wi
                _adj: dict[int, list[int]] = {}
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
                                _adj.setdefault(_avail_ids[ii], []).append(
                                    _avail_ids[jj]
                                )
                                _adj.setdefault(_avail_ids[jj], []).append(
                                    _avail_ids[ii]
                                )
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
                coords = _clip_between_points(coords, a, b)
                coords = _trim_endpoint_overshoot(coords)
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
                            coords = _clip_between_points(coords, a, b)
                            coords = _trim_endpoint_overshoot(coords)
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
                                            f"{si * 5}% OSM={rf[0]:.4f},{rf[1]:.4f} "
                                            f"REF={gf[0]:.4f},{gf[1]:.4f} Δ={dd:.6f}°"
                                        )
                                    log.info(
                                        "  seg %s->%s %s PD=%s: %s",
                                        a_name,
                                        b_name,
                                        rel.get("name", "")[:40],
                                        rel.get("name", "(full relation)")[:40],
                                        " ; ".join(div_samps),
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
                if _route_bias_rid is not None and rid == _route_bias_rid:
                    cost *= 0.6
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
                    if _new_graph and rid not in self._rel_cache:
                        self._rel_cache[rid] = {
                            "avail": _avail,
                            "adj": _adj,
                            "name": rel.get("name", ""),
                        }

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
            return coords, rid
        log.debug("  => NO ROUTE SURVIVED VERIFICATION")
        return None
