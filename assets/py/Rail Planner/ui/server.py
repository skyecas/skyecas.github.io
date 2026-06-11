#!/usr/bin/env python3
from __future__ import annotations
import sys
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from datetime import timedelta
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn


_script_dir = Path(__file__).parent.resolve()
_project_root = _script_dir
for parent in [_script_dir, *_script_dir.parents]:
    if (parent / "_posts").is_dir():
        _project_root = parent
        break

sys.path.insert(0, str(_script_dir.parent))
sys.path.insert(0, str(_script_dir))

from rail_planner import TransitClient, DURATION, TRANSFERS, EMISSIONS  # noqa: E402
from emissions import OperatorEmissionsModel  # noqa: E402
from post_parser import (  # noqa: E402
    parse_post,
    write_post_cache,
    save_route_cache,
    list_sprint_posts,
)
from railway_db import RailwayDB, detect_region, find_country  # noqa: E402

log = logging.getLogger(__name__)
if not log.handlers:
    log.addHandler(logging.StreamHandler())
    log.setLevel(
        getattr(logging, os.environ.get("LOGLEVEL", "INFO").upper(), logging.INFO)
    )

app = FastAPI(title="Sprint Blog Generator")

client = TransitClient(itineraries=8, search_window=7200)
emissions_model = OperatorEmissionsModel()


class _EmissionLeg:
    def __init__(
        self,
        *,
        mode: str,
        operator: str = "",
        distance_km: float = 0.0,
        has_geometry: bool = False,
    ):
        self.mode = mode
        self.operator = operator
        self._distance_km = distance_km
        self.geometry = [object()] if has_geometry else []

    def distance(self) -> float:
        return self._distance_km


def _emissions_detail(
    *,
    mode: str,
    operator: str = "",
    distance_km: float = 0.0,
    distance_source: str = "scheduled",
    countries: list[str] | None = None,
    traction_hint: str | None = None,
) -> dict:
    estimate = emissions_model.estimate_leg_detail(
        _EmissionLeg(
            mode=mode,
            operator=operator,
            distance_km=distance_km,
            has_geometry=distance_source in {"osm", "transitous"},
        ),
        distance_km=distance_km,
        distance_source=distance_source,
        countries=countries or [],
        traction_hint=traction_hint,
    ).to_dict()
    return estimate


def _planner_leg_countries(leg) -> list[str]:
    countries = []
    points = [leg.origin, *getattr(leg, "stops", []), leg.destination]
    for point in points:
        pos = getattr(point, "position", None)
        if not pos:
            continue
        country = find_country(pos.lat.degrees, pos.lon.degrees)
        if country and country not in countries:
            countries.append(country)
    return countries


# Legacy CRS→coords map — used only as lat/lon fallback when MOTIS text search
# fails. Station ID is always sourced from live MOTIS search, never hardcoded.
STATION_COORDS: dict[str, tuple[float, float]] = {
    "CCH": (50.83188, -0.78185),
    "BAA": (50.83128, -0.64006),
    "VIC": (51.4952, -0.1441),
    "GAT": (51.1565, -0.1611),
    "EBN": (51.3754, -0.0928),
    "PBY": (50.8461, -0.1553),
    "BTN": (50.8289, -0.1411),
    "WAT": (51.5033, -0.1131),
    "PAD": (51.5166, -0.1762),
    "EUS": (51.5284, -0.1338),
    "KGX": (51.5309, -0.1233),
    "STP": (51.5301, -0.1253),
    "MYB": (51.5222, -0.1631),
    "LBG": (51.5054, -0.0864),
    "CST": (51.5113, -0.0904),
    "CHX": (51.5084, -0.1248),
    "FST": (51.5116, -0.0788),
    "LST": (51.5181, -0.0821),
    "HVT": (50.8546, -0.9815),
    "PMH": (50.7970, -1.1090),
    "SOU": (50.9073, -1.4147),
    "BOU": (50.7275, -1.8657),
    "RDG": (51.4593, -0.9726),
    "OXF": (51.7535, -1.2709),
    "CBG": (52.1947, 0.1372),
    "MAN": (53.4774, -2.2302),
    "LIV": (53.4076, -2.9778),
    "BHM": (52.4779, -1.8999),
    "GLC": (55.8588, -4.2590),
    "EDB": (55.9524, -3.1892),
}


@app.get("/api/search-stations")
async def search_stations(q: str = Query("")):
    if not q or len(q) < 2:
        return []
    # Check legacy CRS codes (lat/lon fallback)
    code = q.strip().upper()
    if code in STATION_COORDS:
        lat, lon = STATION_COORDS[code]
        return [{"id": code, "name": code, "lat": lat, "lon": lon}]
    # Fall back to Transitous search
    import asyncio

    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, client.search_stations, q)

    # Sort: exact name match first, then National Rail (910-912), then others.
    # Keep Underground/DLR/etc visible because they are valid interchange targets.
    q_lower = q.strip().lower()

    def _sort_key(r):
        rid = r.id or ""
        code = rid.split("_").pop()[:3] if "_" in rid else ""
        exact = 0 if r.name.lower() == q_lower else 1
        nr = 0 if code in ("910", "911", "912") else 1
        return (exact, nr, r.name)

    results.sort(key=_sort_key)
    return [
        {
            "id": r.id,
            "name": r.name,
            "lat": r.position.lat.degrees,
            "lon": r.position.lon.degrees,
        }
        for r in results
    ]


_STATION_ALIAS_CACHE: dict[str, dict] = {}


def _station_alias_key(name: str) -> str:
    return " ".join(name.lower().strip().split())


def _station_alias_fallback(name: str) -> str:
    key = _station_alias_key(name)
    for old, new in (
        ("bruxelles-zuid", "bruxelles midi"),
        ("bruxelles zuid", "bruxelles midi"),
        ("brussel zuid", "bruxelles midi"),
        ("brussels south", "bruxelles midi"),
        ("s+u berlin hauptbahnhof", "berlin hauptbahnhof"),
        ("st pancras international", "st pancras"),
        ("london st pancras international", "st pancras"),
    ):
        if key == old:
            return new
    return key


def _resolve_station_alias_sync(name: str) -> dict:
    cache_key = _station_alias_key(name)
    if cache_key in _STATION_ALIAS_CACHE:
        return _STATION_ALIAS_CACHE[cache_key]
    fallback = _station_alias_fallback(name)
    try:
        results = client.search_stations(name)
    except Exception:
        results = []
    if results:
        q = cache_key

        def _sort_key(r):
            exact = 0 if r.name.lower() == q else 1
            return (exact, r.name)

        results.sort(key=_sort_key)
        best = results[0]
        # Prefer stable Transitous/MOTIS IDs; nearby aliases are clustered client-side.
        resolved = {
            "input": name,
            "key": best.id or fallback,
            "name": best.name,
            "lat": best.position.lat.degrees,
            "lon": best.position.lon.degrees,
        }
    else:
        resolved = {
            "input": name,
            "key": fallback,
            "name": name,
            "lat": None,
            "lon": None,
        }
    _STATION_ALIAS_CACHE[cache_key] = resolved
    return resolved


@app.post("/api/resolve-station-aliases")
async def resolve_station_aliases(body: dict):
    import asyncio

    names = [str(n).strip() for n in body.get("names", []) if str(n).strip()]
    names = sorted(set(names))
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(
        None, lambda: [_resolve_station_alias_sync(n) for n in names]
    )
    return {"stations": results}


@app.get("/api/sprint-dirs")
async def sprint_dirs():
    img_dir = _project_root / "assets/img"
    dirs = sorted(
        d.name for d in img_dir.iterdir() if d.is_dir() and d.name.startswith("sprint")
    )
    return dirs


@app.get("/api/photos")
async def photos(sprint: str = "", direction: str = "", exclude: str = ""):
    sprint_dir = _project_root / "assets/img" / sprint
    if not sprint_dir.is_dir():
        return []

    excluded = set(f.strip() for f in exclude.split(",") if f.strip())
    results = []
    for f in sorted(sprint_dir.iterdir()):
        if f.suffix.lower() not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
            continue
        if f.name in excluded:
            continue
        name_lower = f.name.lower()
        if direction == "outbound" and not name_lower.startswith("outbound"):
            continue
        if direction == "inbound" and not name_lower.startswith("inbound"):
            continue

        url = f"assets/img/{sprint}/{f.name}"
        results.append(
            {
                "filename": f.name,
                "path": url,
                "size": f.stat().st_size,
            }
        )

    return results


@app.post("/api/find-routes")
async def find_routes(body: dict):
    origin_name = body.get("origin", "")
    dest_name = body.get("destination", "")
    origin_id = body.get("origin_id", "")
    dest_id = body.get("dest_id", "")
    via = body.get("via", [])
    dep_date = body.get("date", "")
    dep_time = body.get("time", "08:00")
    mode = body.get("mode", "")

    from datetime import datetime
    from zoneinfo import ZoneInfo

    def _best_station(name: str) -> Any | None:
        """Search MOTIS, filter out non-rail, return best National Rail result."""
        from rail_planner import Location

        try:
            results = client.search_stations(name)
        except Exception:
            return None

        # Same filter as search_stations endpoint
        def _keep(r) -> bool:
            rid = r.id or ""
            prefix = rid.split("_").pop()[:3] if "_" in rid else ""
            return prefix not in ("940", "930", "700")

        filtered = [r for r in results if _keep(r)]
        if not filtered:
            return None
        # Exact name match first, then National Rail prefix
        q_lower = name.lower()

        def _sort_key(r):
            rid = r.id or ""
            code = rid.split("_").pop()[:3] if "_" in rid else ""
            exact = 0 if r.name.lower() == q_lower else 1
            nr = 0 if code in ("910", "911", "912") else 1
            return (exact, nr)

        filtered.sort(key=_sort_key)
        best = filtered[0]
        return Location(
            position=best.position,
            timezone=ZoneInfo("Europe/London"),
            id=best.id,
            name=best.name,
            address=best.name,
        )

    def resolve_station(name, station_id="", station_lat=None, station_lon=None):
        if station_id:
            from geo import Position
            from rail_planner import Location

            if station_lat is not None and station_lon is not None:
                pos = Position(station_lat, station_lon)
            else:
                try:
                    results = client.search_stations(name)
                    match = next((r for r in results if r.id == station_id), results[0])
                    pos = match.position
                except Exception:
                    pos = Position(0, 0)
            return Location(
                position=pos,
                timezone=ZoneInfo("Europe/London"),
                id=station_id,
                name=name,
                address=name,
            )
        # Check legacy CRS codes (lat/lon fallback only)
        code = name.strip().upper()
        if code in STATION_COORDS:
            from geo import Position
            from rail_planner import Location

            try:
                match = _best_station(code)
                if match:
                    return match
            except Exception:
                pass
            lat, lon = STATION_COORDS[code]
            return Location(
                position=Position(lat, lon),
                timezone=ZoneInfo("Europe/London"),
                id=code,
                name=code,
                address=code,
            )
        match = _best_station(name)
        if match:
            return match
        raise ValueError(f"Could not find station: {name}")

    try:
        origin = resolve_station(origin_name, origin_id)
        dest = resolve_station(dest_name, dest_id)
    except (IndexError, ValueError):
        return JSONResponse({"error": "Could not find station"}, status_code=400)

    via_locs = []
    for v in via:
        try:
            match = _best_station(v)
            if match:
                via_locs.append(match)
        except (IndexError, ValueError):
            pass

    if dep_date:
        depart_after = datetime.strptime(f"{dep_date} {dep_time}", "%Y-%m-%d %H:%M")
        depart_after -= timedelta(hours=1)
        # Auto-adjust dates more than 3 months old to current week (same weekday)
        now = datetime.now()
        if (now - depart_after).days > 90:
            target_weekday = depart_after.weekday()
            days_ahead = target_weekday - now.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            adj = now.replace(
                hour=depart_after.hour,
                minute=depart_after.minute,
                second=0,
                microsecond=0,
            ) + timedelta(days=days_ahead)
            print(f"Adjusted date {depart_after.date()} -> {adj.date()}")
            depart_after = adj
    else:
        depart_after = datetime.now() + timedelta(hours=1)

    # Default: all UK/EU rail (train, regional, high speed, subway, tram, light rail, ferry, walk)
    # This is the recommended mode — includes everything a rail journey might use.
    ALL_RAIL = TransitClient.TRAVEL_SKYE  # "RAIL,REGIONAL_RAIL,...,WALK"

    if mode == "walking":
        modes = "WALK"
    elif mode in ("bus", "plane", "coach"):
        modes = TransitClient.TRAVEL_SKYE_BUSINESS
    elif mode == "ferry":
        modes = ALL_RAIL + ",FERRY"
    elif mode == "car":
        modes = "CAR,RIDE_SHARING"
    elif mode == "high_speed":
        modes = "HIGHSPEED_RAIL,REGIONAL_FAST_RAIL,NIGHT_RAIL"
    elif mode == "regional":
        modes = "REGIONAL_RAIL,SUBURBAN"
    elif mode == "light_rail":
        modes = "TRAM,SUBWAY,METRO,SUBURBAN"
    elif mode == "train" or not mode:
        modes = ALL_RAIL
    else:
        modes = ALL_RAIL

    # Build list of dates to try: initial + fallback same-weekday probes
    user_dt = depart_after
    dates_to_try = [(depart_after, body.get("date", ""), 0)]
    if dep_date:
        target_weekday = user_dt.weekday()
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        days_ahead = target_weekday - today.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        first_match = today + timedelta(days=days_ahead)
        for week_offset in (-2, -1, 0, 1, 2, 3, 4):
            alt_date = first_match + timedelta(weeks=week_offset)
            alt_dt = alt_date.replace(hour=user_dt.hour, minute=user_dt.minute)
            user_min = user_dt.hour * 60 + user_dt.minute
            alt_min = alt_dt.hour * 60 + alt_dt.minute
            offset_min = user_min - alt_min
            alt_body = dict(body, date=alt_dt.strftime("%Y-%m-%d"))
            dates_to_try.append((alt_dt, alt_dt.strftime("%Y-%m-%d"), offset_min))

    import concurrent.futures

    def _query_one(
        dt: datetime, date_str: str, offset_min: int
    ) -> tuple[list | None, str | None]:
        """Returns (routes, None) on success or (None, error_msg) on failure."""
        try:
            alt_routes = client.routes_between(
                origin,
                dest,
                depart_after=dt,
                via=via_locs or None,
                modes=modes,
                sort=EMISSIONS + TRANSFERS + DURATION,
                model=emissions_model,
            )
            return (alt_routes, None)
        except Exception as ex:
            err = str(ex) or type(ex).__name__
            print(f"Transitous query failed ({modes}): {err}")
            return (None, err)

    warning = None
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(len(dates_to_try), 5)
    ) as pool:
        fut_map = {
            pool.submit(_query_one, dt, ds, om): (ds, om) for dt, ds, om in dates_to_try
        }
        done, pending = concurrent.futures.wait(
            fut_map,
            timeout=110,
            return_when=concurrent.futures.FIRST_COMPLETED,
        )
        for f in done:
            routes, err = f.result()
            if routes:
                date_str, offset_min = fut_map[f]
                if offset_min:
                    alt_body = dict(body, date=date_str)
                    return _route_response(routes, alt_body, offset_min, date_str)
                return _route_response(routes, body)
        # Collect first error for warning if nothing succeeded
        for f in done:
            _, err = f.result()
            if err and warning is None:
                warning = err

    resp = _route_response([], body)
    mode_label = body.get("mode", "train")
    resp["_warning"] = (
        warning
        or f"No routes found for {origin_name} → {dest_name} using mode={mode_label}"
    )
    return resp


def _route_response(routes, query_body, offset_minutes=None, fallback_date=None):
    from truth.snapshot import TruthSnapshot

    total_emissions_g = sum(emissions_model.estimate_route(r) for r in routes)
    snapshot = TruthSnapshot.from_routes(
        routes, query=query_body, emissions=total_emissions_g
    )

    resp = {
        "snapshot_id": snapshot.snapshot_id,
        "routes": [
            {
                "route_id": r.route_id,
                "origin": r.origin_name,
                "destination": r.destination_name,
                "departure": r.departure,
                "arrival": r.arrival,
                "duration_seconds": r.duration_seconds,
                "duration_str": f"{r.duration_seconds // 3600}h{(r.duration_seconds % 3600) // 60:02d}m",
                "total_distance_km": r.total_distance_km,
                "rail_distance_km": r.rail_distance_km,
                "walk_distance_km": r.walk_distance_km,
                "transfers": r.transfers,
                "average_speed_kmh": r.average_speed_kmh,
                "max_speed_kmh": r.max_speed_kmh,
                "tortuosity_pct": r.tortuosity_pct,
                "operators": r.operators,
                "legs": [
                    {
                        "mode": leg.mode,
                        "display_name": leg.display_name,
                        "operator": leg.operator,
                        "origin": leg.origin_name,
                        "destination": leg.destination_name,
                        "origin_lat": leg.origin_lat,
                        "origin_lon": leg.origin_lon,
                        "dest_lat": leg.dest_lat,
                        "dest_lon": leg.dest_lon,
                        "departure": leg.departure,
                        "arrival": leg.arrival,
                        "duration_seconds": leg.duration_seconds,
                        "distance_km": leg.distance_km,
                        "max_speed_kmh": leg.max_speed_kmh,
                        "stops": leg.intermediate_stops,
                        "geometry": leg.geometry,
                        "leg_type": leg.leg_type,
                        "origin_platform": leg.origin_platform,
                        "destination_platform": leg.destination_platform,
                    }
                    for leg in r.legs
                ],
            }
            for r in snapshot.routes
        ],
    }
    # Add per-leg and per-route emissions
    for route_idx, route in enumerate(routes):
        rt = resp["routes"][route_idx]
        total_kg = 0.0
        for leg_idx, leg in enumerate(route.legs):
            detail = emissions_model.estimate_leg_detail(
                leg,
                countries=_planner_leg_countries(leg),
            )
            em_kg = detail.kg
            rate = round(detail.rate_g_per_km, 1)
            rt["legs"][leg_idx]["emissions_kg"] = em_kg
            rt["legs"][leg_idx]["emissions_rate_g_per_km"] = rate
            rt["legs"][leg_idx]["emissions_min_kg"] = detail.min_kg
            rt["legs"][leg_idx]["emissions_max_kg"] = detail.max_kg
            rt["legs"][leg_idx]["emissions_operational_kg"] = detail.operational_kg
            rt["legs"][leg_idx]["emissions_lifecycle_kg"] = detail.lifecycle_kg
            rt["legs"][leg_idx]["emissions_radiative_forcing_kg"] = (
                detail.radiative_forcing_kg
            )
            rt["legs"][leg_idx]["emissions_rate_min_g_per_km"] = (
                detail.rate_min_g_per_km
            )
            rt["legs"][leg_idx]["emissions_rate_max_g_per_km"] = (
                detail.rate_max_g_per_km
            )
            rt["legs"][leg_idx]["emissions_confidence"] = detail.confidence
            rt["legs"][leg_idx]["emissions_distance_source"] = detail.distance_source
            rt["legs"][leg_idx]["emissions_traction"] = detail.traction
            rt["legs"][leg_idx]["emissions_traction_source"] = detail.traction_source
            rt["legs"][leg_idx]["emissions_countries"] = detail.countries
            rt["legs"][leg_idx]["emissions_grid_intensity_g_per_kwh"] = (
                detail.grid_intensity_g_per_kwh
            )
            rt["legs"][leg_idx]["emissions_lifecycle_uplift_pct"] = (
                detail.lifecycle_uplift_pct
            )
            rt["legs"][leg_idx]["emissions_radiative_forcing_multiplier"] = (
                detail.radiative_forcing_multiplier
            )
            rt["legs"][leg_idx]["emissions_assumptions"] = detail.assumptions
            total_kg += em_kg
        rt["total_emissions_kg"] = round(total_kg, 3)

    if offset_minutes is not None:
        resp["_offset_minutes"] = offset_minutes
        resp["_fallback_date"] = fallback_date
    return resp


# ---- Geometry enrichment (local OSM railway DB) ----

_ENRICH_CACHE: dict[str, tuple[list[dict[str, float]] | None, str | None]] = {}


def _enrich_leg_geometry(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    stops: list[dict],
    geometry: list[dict[str, float]] | None = None,
    origin_platform: str | None = None,
    dest_platform: str | None = None,
) -> tuple[list[dict[str, float]] | None, str | None]:
    import hashlib

    def rnd(x):
        return round(x, 4)

    geo_sig = ""
    if geometry and len(geometry) >= 2:
        sample_idxs = sorted({0, len(geometry) // 2, len(geometry) - 1})
        geo_sig = ";".join(
            f"{rnd(geometry[i]['lat'])},{rnd(geometry[i]['lon'])}" for i in sample_idxs
        )
    cache_key = hashlib.sha256(
        (
            f"{rnd(origin_lat)},{rnd(origin_lon)}-{rnd(dest_lat)},{rnd(dest_lon)}"
            f"|{origin_platform or ''}|{dest_platform or ''}|{geo_sig}"
        ).encode()
    ).hexdigest()[:16]
    if cache_key in _ENRICH_CACHE:
        cached_result, cached_source = _ENRICH_CACHE[cache_key]
        # Only cache-hit for stable railway_db results; re-run for arc/loading in
        # case RailwayDB is now ready or a code fix changed the outcome.
        if cached_source == "railway_db":
            if cached_result and len(cached_result) >= 2:
                log.info("  enrich cache: %d coords", len(cached_result))
            return cached_result, cached_source

    # Build anchor points from station stops only (no Transitous geometry waypoints).
    # Only include stops that lie on the route segment between origin and destination,
    # determined by their position in the Transitous geometry ordering.
    anchor_points: list[dict] = [
        {"lat": origin_lat, "lon": origin_lon, "name": "origin"}
    ]
    if origin_platform:
        anchor_points[0]["platform"] = origin_platform

    def _dedup(pt: dict) -> bool:
        return any(
            abs(pt["lat"] - p["lat"]) < 0.001 and abs(pt["lon"] - p["lon"]) < 0.001
            for p in anchor_points
        )

    if stops and len(stops) > 1:
        # Find stops array indices for origin and destination by nearest neighbor.
        # Transitous stops are ordered along the route; keep only stops that lie
        # between origin and dest in this ordering.
        si_orig = min(
            range(len(stops)),
            key=lambda i: (
                (stops[i].get("lat", 0) - origin_lat) ** 2
                + (stops[i].get("lon", 0) - origin_lon) ** 2
            ),
        )
        si_dest = min(
            range(len(stops)),
            key=lambda i: (
                (stops[i].get("lat", 0) - dest_lat) ** 2
                + (stops[i].get("lon", 0) - dest_lon) ** 2
            ),
        )
        lo_s, hi_s = (si_orig, si_dest) if si_orig <= si_dest else (si_dest, si_orig)
        for s in stops[lo_s : hi_s + 1]:
            if s.get("lat") is None:
                continue
            if _dedup(s):
                continue
            ap = {"lat": s["lat"], "lon": s["lon"], "name": s.get("name", "")}
            if s.get("track"):
                ap["platform"] = s["track"]
            anchor_points.append(ap)
    elif stops:
        for s in stops:
            if s.get("lat") is None:
                continue
            if _dedup(s):
                continue
            ap = {"lat": s["lat"], "lon": s["lon"], "name": s.get("name", "")}
            if s.get("track"):
                ap["platform"] = s["track"]
            anchor_points.append(ap)

    if (
        abs(anchor_points[-1]["lat"] - dest_lat) > 0.0001
        or abs(anchor_points[-1]["lon"] - dest_lon) > 0.0001
    ):
        ap = {"lat": dest_lat, "lon": dest_lon, "name": "destination"}
        if dest_platform:
            ap["platform"] = dest_platform
        anchor_points.append(ap)
    else:
        if dest_platform:
            anchor_points[-1]["platform"] = dest_platform

    def _project_anchor_to_geometry(ap: dict, raw_geo: list[dict[str, float]]) -> None:
        if not raw_geo or len(raw_geo) < 2:
            return
        best = None
        for i in range(len(raw_geo) - 1):
            p0 = raw_geo[i]
            p1 = raw_geo[i + 1]
            vx = p1["lat"] - p0["lat"]
            vy = p1["lon"] - p0["lon"]
            seg2 = vx * vx + vy * vy
            if seg2 == 0:
                t = 0.0
            else:
                t = ((ap["lat"] - p0["lat"]) * vx + (ap["lon"] - p0["lon"]) * vy) / seg2
                t = max(0.0, min(1.0, t))
            lat = p0["lat"] + vx * t
            lon = p0["lon"] + vy * t
            d2 = (lat - ap["lat"]) ** 2 + (lon - ap["lon"]) ** 2
            if best is None or d2 < best[0]:
                best = (d2, lat, lon)
        if best and best[0] < 0.0001:
            ap["station_lat"] = ap["lat"]
            ap["station_lon"] = ap["lon"]
            ap["lat"] = best[1]
            ap["lon"] = best[2]

    if geometry and len(geometry) >= 2:
        for ap in anchor_points:
            _project_anchor_to_geometry(ap, geometry)

    if geometry and len(geometry) >= 3:

        def _geo_index(pt: dict) -> int:
            return min(
                range(len(geometry)),
                key=lambda i: (
                    (geometry[i]["lat"] - pt["lat"]) ** 2
                    + (geometry[i]["lon"] - pt["lon"]) ** 2
                ),
            )

        split_anchors = []
        last_region = detect_region(geometry[0]["lat"], geometry[0]["lon"])
        for gi, gp in enumerate(geometry[1:-1], start=1):
            region = detect_region(gp["lat"], gp["lon"])
            if region and last_region and region != last_region:
                prev = geometry[gi - 1]
                split_anchors.append(
                    {
                        "idx": gi,
                        "lat": (prev["lat"] + gp["lat"]) / 2,
                        "lon": (prev["lon"] + gp["lon"]) / 2,
                        "name": f"region:{last_region}->{region}",
                    }
                )
            if region:
                last_region = region

        if split_anchors:
            new_anchors = []
            inserted = 0
            for ai in range(len(anchor_points) - 1):
                a = anchor_points[ai]
                b = anchor_points[ai + 1]
                new_anchors.append(a)
                ia = _geo_index(a)
                ib = _geo_index(b)
                lo, hi = sorted((ia, ib))
                candidates = [s for s in split_anchors if lo < s["idx"] <= hi]
                candidates.sort(key=lambda s: s["idx"], reverse=ia > ib)
                for split in candidates:
                    if (
                        abs(split["lat"] - a["lat"]) < 0.0001
                        and abs(split["lon"] - a["lon"]) < 0.0001
                    ) or (
                        abs(split["lat"] - b["lat"]) < 0.0001
                        and abs(split["lon"] - b["lon"]) < 0.0001
                    ):
                        continue
                    new_anchors.append(
                        {
                            "lat": split["lat"],
                            "lon": split["lon"],
                            "name": split["name"],
                        }
                    )
                    inserted += 1
            new_anchors.append(anchor_points[-1])
            anchor_points = new_anchors
            log.info(
                "  inserted %d region split anchors for cross-border enrichment",
                inserted,
            )

    # Phase 1: local railway database corridor query
    db = RailwayDB.get_instance()

    # Detect all regions from all anchor points for cross-border support
    regions_needed: set[str] = set()
    for ap in anchor_points:
        r = detect_region(ap["lat"], ap["lon"])
        if r:
            regions_needed.add(r)
    if not regions_needed:
        regions_needed.add(detect_region(origin_lat, origin_lon) or "")
    regions_needed.discard("")

    if regions_needed:
        for r in list(regions_needed):
            db.ensure_region(r)

        loading_regions = [r for r in regions_needed if db._region_loading.get(r)]
        if loading_regions:
            log.debug(
                "_enrich_leg_geometry: regions %s loading, returning None",
                loading_regions,
            )
            return None, "loading"

        ready_regions = [r for r in regions_needed if db.is_ready(r)]
        if ready_regions:

            def _clip_ref_geo(
                raw: list[dict], a: dict, b: dict
            ) -> list[tuple[float, float]]:
                if len(raw) < 2:
                    return [(p["lat"], p["lon"]) for p in raw]
                pts = [(p["lat"], p["lon"]) for p in raw]
                ia = min(
                    range(len(pts)),
                    key=lambda i: (
                        (pts[i][0] - a["lat"]) ** 2 + (pts[i][1] - a["lon"]) ** 2
                    ),
                )
                ib = min(
                    range(len(pts)),
                    key=lambda i: (
                        (pts[i][0] - b["lat"]) ** 2 + (pts[i][1] - b["lon"]) ** 2
                    ),
                )
                if ia <= ib:
                    clipped = pts[ia : ib + 1]
                else:
                    clipped = pts[ib : ia + 1][::-1]
                return clipped

            ref_geos: list[list[tuple[float, float]] | None] = []
            for ai in range(len(anchor_points) - 1):
                a, b = anchor_points[ai], anchor_points[ai + 1]
                if geometry and len(geometry) > 2:
                    best_ai = best_bi = 0
                    best_da = best_db = float("inf")
                    for gi, gp in enumerate(geometry):
                        da = (gp["lat"] - a["lat"]) ** 2 + (gp["lon"] - a["lon"]) ** 2
                        db2 = (gp["lat"] - b["lat"]) ** 2 + (gp["lon"] - b["lon"]) ** 2
                        if da < best_da:
                            best_da, best_ai = da, gi
                        if db2 < best_db:
                            best_db, best_bi = db2, gi
                    if best_ai <= best_bi:
                        sub = geometry[best_ai : best_bi + 1]
                    else:
                        sub = geometry[best_bi : best_ai + 1][::-1]
                    ref_geos.append(_clip_ref_geo(sub, a, b))
                else:
                    ref_geos.append(None)

            all_coords = db.query_corridor(
                anchor_points, ref_geos=ref_geos, regions=ready_regions
            )
            if all_coords:
                if len(all_coords) >= 2:
                    orig_name = anchor_points[0].get("name", "origin").replace(" ", "_")
                    dest_name = (
                        anchor_points[-1].get("name", "destination").replace(" ", "_")
                    )
                    lats = [c[0] for c in all_coords]
                    lons = [c[1] for c in all_coords]
                    log.info(
                        "  enriched %s->%s: %d coords, bbox=(%.4f-%.4f, %.4f-%.4f)",
                        orig_name,
                        dest_name,
                        len(all_coords),
                        min(lats),
                        max(lats),
                        min(lons),
                        max(lons),
                    )
                    n = len(all_coords)
                    osm_samps = []
                    ref_samps = []
                    for frac_int in range(0, 101, 5):
                        frac = frac_int / 100.0
                        si = min(int(frac * (n - 1)), n - 1)
                        osm_samps.append(
                            f"{frac_int}%={all_coords[si][0]:.4f},{all_coords[si][1]:.4f}"
                        )
                    if geometry and len(geometry) >= 2:
                        gn = len(geometry)
                        for frac_int in range(0, 101, 5):
                            frac = frac_int / 100.0
                            si = min(int(frac * (gn - 1)), gn - 1)
                            gp = geometry[si]
                            ref_samps.append(
                                f"{frac_int}%={gp['lat']:.4f},{gp['lon']:.4f}"
                            )
                        log.info(
                            "  enriched %s->%s OSM: %s | REF: %s",
                            orig_name,
                            dest_name,
                            " ; ".join(osm_samps),
                            " ; ".join(ref_samps),
                        )
                    else:
                        log.info(
                            "  enriched %s->%s OSM: %s",
                            orig_name,
                            dest_name,
                            " ; ".join(osm_samps),
                        )
                result = [{"lat": c[0], "lon": c[1]} for c in all_coords]
                _ENRICH_CACHE[cache_key] = (result, "railway_db")
                return result, "railway_db"
            else:
                log.debug("  query_corridor returned None")

    log.warning(
        "OSM enrichment failed: %.5f,%.5f -> %.5f,%.5f via %d anchors",
        origin_lat,
        origin_lon,
        dest_lat,
        dest_lon,
        len(anchor_points),
    )
    return None, "osm_failed"


@app.get("/api/railway-status")
async def railway_status():
    db = RailwayDB.get_instance()
    return db.get_status()


@app.post("/api/enrich-geometry")
async def enrich_geometry(body: dict):
    legs_in = body.get("legs", [])
    import asyncio

    loop = asyncio.get_event_loop()
    results = await asyncio.gather(
        *[loop.run_in_executor(None, _enrich_one_leg, leg_in) for leg_in in legs_in]
    )
    return {"legs": results}


@app.post("/api/estimate-emissions")
async def estimate_emissions(body: dict):
    legs = []
    for i, leg in enumerate(body.get("legs", [])):
        detail = _emissions_detail(
            mode=leg.get("mode", "RAIL"),
            operator=leg.get("operator", ""),
            distance_km=float(leg.get("distance_km") or 0),
            distance_source=leg.get("distance_source", "scheduled"),
            countries=leg.get("countries") or [],
            traction_hint=leg.get("traction_hint"),
        )
        detail["index"] = leg.get("index", i)
        legs.append(detail)
    return {"legs": legs}


def _enrich_one_leg(leg_in: dict) -> dict:
    if leg_in.get("leg_type", "transit") not in {"transit", "unincluded"}:
        return {"index": leg_in.get("index"), "geometry": None, "source": None}
    geom, source = _enrich_leg_geometry(
        leg_in.get("origin_lat", 0),
        leg_in.get("origin_lon", 0),
        leg_in.get("dest_lat", 0),
        leg_in.get("dest_lon", 0),
        leg_in.get("stops", []),
        leg_in.get("geometry"),
        leg_in.get("origin_platform"),
        leg_in.get("dest_platform"),
    )
    traction_hint = None
    if geom and source == "railway_db":
        try:
            traction_hint = RailwayDB.get_instance().traction_hint_for_geometry(geom)
        except Exception:
            traction_hint = None
    return {
        "index": leg_in.get("index"),
        "geometry": geom,
        "source": source,
        "traction_hint": traction_hint,
    }


@app.post("/api/generate-blog")
async def generate_blog(body: dict):
    from narrative.blog import generate_blog_post

    route_data = body.get("route", {})
    curation_data = body.get("curation", {})

    snapshot = _build_snapshot(route_data)
    curation = _build_curation(curation_data, route_data)

    post = generate_blog_post(snapshot, curation)

    if body.get("write_file", False):
        out_path = _project_root / f"_posts/{curation.trip_date}-sprint.md"
        out_path.parent.mkdir(exist_ok=True)
        out_path.write_text(post)
        save_route_cache(out_path, route_data, curation_data)
        return {"post": post, "path": str(out_path)}

    return {"post": post}


def _build_snapshot(route_data: dict) -> Any:
    from truth.snapshot import TruthSnapshot, TruthRoute, TruthLeg

    legs = [
        TruthLeg(
            mode=leg.get("mode", "REGIONAL_RAIL"),
            display_name=leg.get("display_name", ""),
            operator=leg.get("operator", ""),
            origin_name=leg.get("origin", ""),
            destination_name=leg.get("destination", ""),
            departure=leg.get("departure", ""),
            arrival=leg.get("arrival", ""),
            duration_seconds=leg.get("duration_seconds", 0),
            distance_km=leg.get("distance_km", 0),
            max_speed_kmh=leg.get("max_speed_kmh", 0),
            tortuosity_pct=leg.get("tortuosity_pct", 100),
            intermediate_stops=leg.get("stops", []),
            origin_lat=leg.get("origin_lat", 0.0),
            origin_lon=leg.get("origin_lon", 0.0),
            dest_lat=leg.get("dest_lat", 0.0),
            dest_lon=leg.get("dest_lon", 0.0),
            geometry=leg.get("geometry"),
            leg_type=leg.get("leg_type", "transit"),
            emissions_kg=leg.get("emissions_kg", 0.0),
            emissions_min_kg=leg.get("emissions_min_kg", 0.0),
            emissions_max_kg=leg.get("emissions_max_kg", 0.0),
            emissions_operational_kg=leg.get("emissions_operational_kg", 0.0),
            emissions_lifecycle_kg=leg.get("emissions_lifecycle_kg", 0.0),
            emissions_radiative_forcing_kg=leg.get(
                "emissions_radiative_forcing_kg", 0.0
            ),
            emissions_rate_g_per_km=leg.get("emissions_rate_g_per_km", 0.0),
            emissions_confidence=leg.get("emissions_confidence", ""),
            emissions_distance_source=leg.get("emissions_distance_source", ""),
            emissions_traction=leg.get("emissions_traction", ""),
            emissions_traction_source=leg.get("emissions_traction_source", ""),
            emissions_assumptions=leg.get("emissions_assumptions", []),
        )
        for leg in route_data.get("legs", [])
    ]
    route = TruthRoute(
        route_id=route_data.get("route_id", ""),
        origin_name=route_data.get("origin", ""),
        destination_name=route_data.get("destination", ""),
        departure=route_data.get("departure", ""),
        arrival=route_data.get("arrival", ""),
        duration_seconds=route_data.get("duration_seconds", 0),
        total_distance_km=route_data.get("total_distance_km", 0),
        rail_distance_km=route_data.get("rail_distance_km", 0),
        walk_distance_km=route_data.get("walk_distance_km", 0),
        transfers=route_data.get("transfers", 0),
        average_speed_kmh=route_data.get("average_speed_kmh", 0),
        max_speed_kmh=route_data.get("max_speed_kmh", 0),
        tortuosity_pct=route_data.get("tortuosity_pct", 100),
        legs=legs,
        operators=route_data.get("operators", []),
        countries=[],
        total_emissions_kg=route_data.get("total_emissions_kg", 0.0),
        emissions_min_kg=route_data.get("emissions_min_kg", 0.0),
        emissions_max_kg=route_data.get("emissions_max_kg", 0.0),
    )
    return TruthSnapshot(
        snapshot_id="manual",
        created_at="",
        query={},
        routes=[route],
    )


def _build_curation(curation_data: dict, route_data: dict) -> Any:
    from curation.state import CurationState, LegCuration

    curation = CurationState(
        snapshot_id="manual",
        selected_route_index=0,
        trip_title=curation_data.get("title", ""),
        trip_date=curation_data.get("date", ""),
        trip_description=curation_data.get("description", ""),
        trip_tags=curation_data.get("tags", ["train", "travel", "canonical"]),
        trip_category=curation_data.get("category", "train-travel"),
        destination_notes=curation_data.get("destination_notes", ""),
        overall_notes=curation_data.get("overall_notes", ""),
        trains_notes=curation_data.get("trains_notes", ""),
        stations_notes=curation_data.get("stations_notes", ""),
        countries=curation_data.get("countries", []),
        outbound_label=curation_data.get("outbound_label", "Outbound"),
        inbound_label=curation_data.get("inbound_label", "Inbound"),
    )
    for lc in curation_data.get("leg_curations", []):
        idx = lc.get("leg_index", 0)
        curation.leg_curations[idx] = LegCuration(
            leg_index=idx,
            highlighted=lc.get("highlighted", False),
            photos=lc.get("photos", []),
            notes=lc.get("notes", ""),
            omit_from_narrative=lc.get("omit", False),
        )
    return curation


@app.get("/")
async def index():
    html_path = _script_dir / "index.html"
    if html_path.exists():
        return HTMLResponse(html_path.read_text())
    return HTMLResponse("<h1>Sprint Blog Generator</h1><p>index.html not found.</p>")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/shutdown")
async def shutdown():
    import asyncio
    import os

    print("Shutdown requested — server stopping in 1s")
    loop = asyncio.get_event_loop()
    loop.call_later(1, os._exit, 0)
    return {"status": "shutting_down"}


@app.get("/api/posts")
async def list_posts():
    return list_sprint_posts(_project_root / "_posts")


@app.get("/api/import-post")
async def import_post(path: str = ""):
    post_path = _project_root / path.lstrip("/")
    data = parse_post(post_path)
    if data is None:
        return JSONResponse({"error": "Could not parse post"}, status_code=400)
    write_post_cache(post_path, data)
    return data


@app.post("/api/delete-cache")
async def delete_cache(body: dict):
    path = body.get("path", "")
    if not path:
        return JSONResponse({"error": "No path provided"}, status_code=400)
    cache_path = _project_root / path.lstrip("/")
    # Find and delete .json cache alongside the .md file
    cache_files = [
        cache_path.with_suffix(".json"),
        cache_path.parent / (cache_path.stem + ".json"),
    ]
    for cf in cache_files:
        if cf.exists():
            cf.unlink()
            print(f"Deleted post cache: {cf}")
            return {"success": True, "deleted": str(cf)}
    return JSONResponse({"error": "No cache file found"}, status_code=404)


@app.post("/api/delete-railway-cache")
async def delete_railway_cache(body: dict):
    region = body.get("region", "gb")
    from ui.railway_db import DATA_DIR, REGIONS

    info = REGIONS.get(region)
    if not info:
        return JSONResponse({"error": f"Unknown region {region}"}, status_code=400)
    cache_path = DATA_DIR / info["cache"]
    if cache_path.exists():
        cache_path.unlink()
        print(f"Deleted railway cache: {cache_path}")
        return {"success": True, "deleted": str(cache_path)}
    return JSONResponse({"error": "No railway cache found"}, status_code=404)


assets_dir = _project_root / "assets"
if assets_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")


if __name__ == "__main__":
    print(f"Project root: {_project_root}")
    print("Starting server at http://localhost:8080")
    uvicorn.run(app, host="0.0.0.0", port=8080)
