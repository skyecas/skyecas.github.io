from __future__ import annotations

import csv
import gzip
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional
import requests
import math
import json
from pathlib import Path as _Path
import importlib.util as _isu
_mod_path = _Path(__file__).parent / 'flight_osm.py'
if _mod_path.exists():
    spec = _isu.spec_from_file_location('flight_osm', str(_mod_path))
    flight_osm = _isu.module_from_spec(spec)
    spec.loader.exec_module(flight_osm)
else:
    flight_osm = None

log = logging.getLogger(__name__)
DATA_DIR = Path(__file__).parent / "data"
FLIGHT_DIR = DATA_DIR / "flight"
AIRPORTS_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat"
ROUTES_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/routes.dat"


class FlightDB:
    _instance: "FlightDB" | None = None

    def __init__(self):
        self._airports: Dict[str, dict] = {}
        self._routes: List[dict] = []
        self._loaded = False

    @classmethod
    def get_instance(cls) -> "FlightDB":
        if cls._instance is None:
            cls._instance = FlightDB()
        return cls._instance

    def ensure_data(self) -> None:
        if self._loaded:
            return
        FLIGHT_DIR.mkdir(parents=True, exist_ok=True)
        a_path = FLIGHT_DIR / "airports.dat"
        r_path = FLIGHT_DIR / "routes.dat"

        try:
            if not a_path.exists():
                log.info("Downloading airports.dat...")
                resp = requests.get(AIRPORTS_URL, timeout=60)
                resp.raise_for_status()
                a_path.write_bytes(resp.content)
            if not r_path.exists():
                log.info("Downloading routes.dat...")
                resp = requests.get(ROUTES_URL, timeout=60)
                resp.raise_for_status()
                r_path.write_bytes(resp.content)
        except Exception as e:
            log.warning("FlightDB: could not download OpenFlights data: %s", e)
            # leave unloaded but continue with empty DB

        # Parse airports
        try:
            with open(a_path, newline='', encoding='utf8') as f:
                reader = csv.reader(f)
                for row in reader:
                    # OpenFlights airports.dat fields: id,name,city,country,iata,icao,lat,lon,...
                    if len(row) < 8:
                        continue
                    iata = row[4].strip('"')
                    if not iata or iata == "\\N":
                        continue
                    try:
                        lat = float(row[6])
                        lon = float(row[7])
                    except Exception:
                        continue
                    icao = row[5].strip('"') if len(row) > 5 and row[5].strip('"') and row[5].strip('"') != "\\N" else ""
                    self._airports[iata.upper()] = {
                        "name": row[1].strip('"'),
                        "city": row[2].strip('"'),
                        "country": row[3].strip('"'),
                        "iata": iata.upper(),
                        "icao": icao.upper(),
                        "lat": lat,
                        "lon": lon,
                    }
        except Exception as e:
            log.debug("FlightDB: no airports parsed: %s", e)

        # Parse routes
        try:
            with open(r_path, newline='', encoding='utf8') as f:
                reader = csv.reader(f)
                for row in reader:
                    # fields: airline,airline_id,source_airport,source_id,dest_airport,dest_id,..
                    if len(row) < 6:
                        continue
                    src = row[2].strip('"').upper()
                    dst = row[4].strip('"').upper()
                    if src == "" or dst == "":
                        continue
                    self._routes.append({"src": src, "dst": dst, "airline": row[0].strip('"')})
        except Exception as e:
            log.debug("FlightDB: no routes parsed: %s", e)

        self._loaded = True

    def find_airport(self, iata: str) -> Optional[dict]:
        self.ensure_data()
        return self._airports.get((iata or '').upper())

    def search_airports(self, query: str) -> List[dict]:
        """Case-insensitive substring search over airport name/city/country.

        Returns a list of airport dicts (same shape as find_airport entries).
        """
        self.ensure_data()
        q = (query or "").strip().lower()
        if not q:
            return []
        out: List[dict] = []
        for a in self._airports.values():
            if q in (a.get("name") or "").lower() or q in (a.get("city") or "").lower() or q in (a.get("country") or "").lower():
                out.append(a)
        # Sort exact name matches first, then city
        out.sort(key=lambda x: (0 if q == (x.get('name') or '').lower() else 1, x.get('name') or ''))
        return out

    def find_routes(self, src_iata: str, dst_iata: str) -> List[dict]:
        self.ensure_data()
        si = (src_iata or '').upper()
        di = (dst_iata or '').upper()
        return [r for r in self._routes if r.get('src') == si and r.get('dst') == di]

    def _haversine_km(self, a_lat, a_lon, b_lat, b_lon) -> float:
        R = 6371.0
        dlat = math.radians(b_lat - a_lat)
        dlon = math.radians(b_lon - a_lon)
        lat1 = math.radians(a_lat)
        lat2 = math.radians(b_lat)
        aa = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
        return R * 2 * math.atan2(math.sqrt(aa), math.sqrt(1-aa))

    def _dest_point(self, lat, lon, bearing_deg, dist_km):
        # returns (lat, lon)
        R = 6371.0
        br = math.radians(bearing_deg)
        lat1 = math.radians(lat)
        lon1 = math.radians(lon)
        d = dist_km / R
        lat2 = math.asin(math.sin(lat1)*math.cos(d) + math.cos(lat1)*math.sin(d)*math.cos(br))
        lon2 = lon1 + math.atan2(math.sin(br)*math.sin(d)*math.cos(lat1), math.cos(d)-math.sin(lat1)*math.sin(lat2))
        return (math.degrees(lat2), math.degrees(lon2))

    def _bearing(self, lat1, lon1, lat2, lon2):
        # initial bearing from 1 -> 2
        lat1r = math.radians(lat1)
        lat2r = math.radians(lat2)
        dlon = math.radians(lon2 - lon1)
        x = math.sin(dlon) * math.cos(lat2r)
        y = math.cos(lat1r) * math.sin(lat2r) - math.sin(lat1r) * math.cos(lat2r) * math.cos(dlon)
        return (math.degrees(math.atan2(x, y)) + 360) % 360

    def search_runways_near(self, lat: float, lon: float, radius: int = 5000) -> List[dict]:
        """Search locally-extracted runway/taxiway ways near a point using cached runway data
        or by extracting from available PBF files in the local data directory.
        """
        # Try cached runways first
        cache_path = DATA_DIR / "flight_runways.json.gz"
        ways = []
        if cache_path.exists():
            try:
                with gzip.open(cache_path, "rt") as f:
                    raw = json.load(f)
                ways = raw.get("ways", [])
            except Exception as e:
                log.debug("Failed to read runway cache: %s", e)

        if not ways:
            # No cache; extract from any local PBFs in DATA_DIR (may be slow first time)
            pbf_files = list(DATA_DIR.glob("*.osm.pbf"))
            # Load any existing per-PBF runway caches. Do not auto-extract large PBFs here to avoid
            # expensive runtime work; extraction should be performed offline and caches placed
            # alongside the PBFs as runways.<pbf_stem>.json.gz
            for pbf in pbf_files:
                try:
                    out_cache = DATA_DIR / f"runways.{pbf.stem}.json.gz"
                    if out_cache.exists():
                        extracted = flight_osm.load_runway_cache(out_cache)
                        if extracted:
                            ways.extend(extracted)
                except Exception as e:
                    log.debug("Failed to load runway cache %s: %s", out_cache, e)
            # Save combined cache
            try:
                with gzip.open(cache_path, "wt") as f:
                    json.dump({"ways": ways}, f)
            except Exception:
                pass

        # Filter ways by distance to any vertex
        out = []
        for w in ways:
            coords = w.get("coords", [])
            for (rlat, rlon) in coords:
                dkm = self._haversine_km(lat, lon, rlat, rlon)
                if dkm * 1000 <= radius:
                    out.append(w)
                    break
        return out

    def estimate_ground_and_departure(self, airport: dict, radius: int = 5000) -> Optional[dict]:
        """Return a best-effort ground path and runway direction for an airport.

        Returns dict with keys: centroid, threshold (lat,lon), runway_heading_deg, ground_path (list of pts from centroid->threshold)
        or None if nothing found.
        """
        self.ensure_data()
        if not airport:
            return None
        lat = airport.get('lat')
        lon = airport.get('lon')
        if lat is None or lon is None:
            return None
        ways = self.search_runways_near(lat, lon, radius=radius)
        if not ways:
            return None
        # Prefer ways tagged as runway
        runway_ways = [w for w in ways if (w.get('tags') or {}).get('aeroway') == 'runway']
        if runway_ways:
            ways = runway_ways
        # Find nearest runway way by distance to its endpoints
        best = None
        best_d = float('inf')
        for w in ways:
            coords = w.get('coords')
            for idx, (rlat, rlon) in enumerate(coords):
                d = self._haversine_km(lat, lon, rlat, rlon)
                if d < best_d:
                    best_d = d
                    best = (w, idx)
        if not best:
            return None
        w, idx = best
        coords = w.get('coords')
        # choose threshold as the closer endpoint (first or last)
        if idx <= len(coords) // 2:
            threshold = coords[0]
            nextpt = coords[1] if len(coords) > 1 else coords[0]
        else:
            threshold = coords[-1]
            nextpt = coords[-2] if len(coords) > 1 else coords[-1]
        runway_heading = self._bearing(threshold[0], threshold[1], nextpt[0], nextpt[1])
        # Build simple straight-line ground path from airport centroid to threshold with interpolation
        dist = self._haversine_km(lat, lon, threshold[0], threshold[1])
        steps = max(2, int(min(10, dist)))
        path = []
        for i in range(steps + 1):
            f = i / steps
            ilat = lat + (threshold[0] - lat) * f
            ilon = lon + (threshold[1] - lon) * f
            path.append({'lat': ilat, 'lon': ilon})
        return {
            'centroid': {'lat': lat, 'lon': lon},
            'threshold': {'lat': threshold[0], 'lon': threshold[1]},
            'runway_heading_deg': runway_heading,
            'ground_path': path,
            'distance_km': dist,
            'runway_coords': coords,
        }

    def build_detailed_departure(self, airport: dict, dest_lat: float, dest_lon: float) -> Optional[dict]:
        """Build a detailed departure path combining ground path, runway rollout,
        a smooth transition turn, and the initial portion of the great-circle arc.

        Returns dict: { path: [pts], metadata: {...} }
        """
        info = self.estimate_ground_and_departure(airport)
        if not info:
            return None
        centroid = info['centroid']
        threshold = info['threshold']
        runway_coords = info['runway_coords']
        runway_heading = info['runway_heading_deg']

        # Decide takeoff end: choose runway end whose heading is best aligned to dest
        # compute bearing from both runway endpoints to dest
        end1 = runway_coords[0]
        end2 = runway_coords[-1]
        b1 = self._bearing(end1[0], end1[1], dest_lat, dest_lon)
        b2 = self._bearing(end2[0], end2[1], dest_lat, dest_lon)
        # compute heading of runway ends: heading from end to next point
        head1 = self._bearing(runway_coords[0][0], runway_coords[0][1], runway_coords[1][0], runway_coords[1][1]) if len(runway_coords) > 1 else runway_heading
        head2 = self._bearing(runway_coords[-1][0], runway_coords[-1][1], runway_coords[-2][0], runway_coords[-2][1]) if len(runway_coords) > 1 else (runway_heading + 180) % 360
        # angle difference between runway heading and bearing to destination
        def ang_diff(a, b):
            d = (a - b + 180) % 360 - 180
            return abs(d)

        diff1 = ang_diff(head1, b1)
        diff2 = ang_diff(head2, b2)
        takeoff_end = end1 if diff1 <= diff2 else end2
        takeoff_heading = head1 if diff1 <= diff2 else head2

        # Ground path from centroid to threshold (approx)
        path = info['ground_path'][:]

        # Rollout: move along runway heading from threshold for a short distance
        rollout_km = 2.0  # default rollout / initial climb segment
        rollout_steps = 6
        for i in range(1, rollout_steps + 1):
            d = rollout_km * (i / rollout_steps)
            lat, lon = self._dest_point(takeoff_end[0], takeoff_end[1], takeoff_heading, d)
            path.append({'lat': lat, 'lon': lon})

        # Transition: smoothly rotate heading towards great-circle initial bearing
        gc_bearing = self._bearing(path[-1]['lat'], path[-1]['lon'], dest_lat, dest_lon)
        # choose shortest angular direction
        angle_a = takeoff_heading
        angle_b = gc_bearing
        ang_delta = ((angle_b - angle_a + 540) % 360) - 180
        trans_len_km = min(40.0, max(5.0, self._haversine_km(path[-1]['lat'], path[-1]['lon'], dest_lat, dest_lon) * 0.07))
        trans_steps = max(4, int(trans_len_km))
        # produce points by rotating heading gradually and stepping out
        cum = 0.0
        for i in range(1, trans_steps + 1):
            frac = i / trans_steps
            heading_i = (angle_a + ang_delta * frac) % 360
            step_dist = trans_len_km / trans_steps
            cum += step_dist
            lat, lon = self._dest_point(path[-1]['lat'], path[-1]['lon'], heading_i, cum)
            path.append({'lat': lat, 'lon': lon})

        # Append a sampled great-circle arc from current end to destination
        # Use slerp based great-circle sampling
        def gc_arc(lat1, lon1, lat2, lon2, steps=48):
            lat1r = math.radians(lat1); lon1r = math.radians(lon1)
            lat2r = math.radians(lat2); lon2r = math.radians(lon2)
            x1 = math.cos(lat1r) * math.cos(lon1r)
            y1 = math.cos(lat1r) * math.sin(lon1r)
            z1 = math.sin(lat1r)
            x2 = math.cos(lat2r) * math.cos(lon2r)
            y2 = math.cos(lat2r) * math.sin(lon2r)
            z2 = math.sin(lat2r)
            dot = max(-1.0, min(1.0, x1 * x2 + y1 * y2 + z1 * z2))
            omega = math.acos(dot)
            if omega == 0:
                return [{'lat': lat1, 'lon': lon1}, {'lat': lat2, 'lon': lon2}]
            pts = []
            for i in range(steps + 1):
                t = i / steps
                s1 = math.sin((1 - t) * omega) / math.sin(omega)
                s2 = math.sin(t * omega) / math.sin(omega)
                x = s1 * x1 + s2 * x2
                y = s1 * y1 + s2 * y2
                z = s1 * z1 + s2 * z2
                lat = math.degrees(math.atan2(z, math.hypot(x, y)))
                lon = math.degrees(math.atan2(y, x))
                pts.append({'lat': lat, 'lon': lon})
            return pts

        gc_pts = gc_arc(path[-1]['lat'], path[-1]['lon'], dest_lat, dest_lon, steps=64)
        # append but avoid duplicating start point
        if gc_pts:
            if abs(gc_pts[0]['lat'] - path[-1]['lat']) < 1e-6 and abs(gc_pts[0]['lon'] - path[-1]['lon']) < 1e-6:
                path.extend(gc_pts[1:])
            else:
                path.extend(gc_pts)

        metadata = {
            'takeoff_end': {'lat': takeoff_end[0], 'lon': takeoff_end[1]},
            'takeoff_heading': takeoff_heading,
            'gc_bearing': gc_bearing,
            'rollout_km': rollout_km,
            'transition_len_km': trans_len_km,
        }
        return {'path': path, 'metadata': metadata}
