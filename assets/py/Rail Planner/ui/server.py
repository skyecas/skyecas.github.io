#!/usr/bin/env python3
from __future__ import annotations
import sys
import logging
import os
from pathlib import Path

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

from rail_planner import TransitClient, DURATION, TRANSFERS, EMISSIONS
from emissions import OperatorEmissionsModel
from post_parser import (
    parse_post,
    write_post_cache,
    save_route_cache,
    list_sprint_posts,
)
from railway_db import RailwayDB, detect_region

log = logging.getLogger(__name__)
if not log.handlers:
    log.addHandler(logging.StreamHandler())
    log.setLevel(
        getattr(logging, os.environ.get("LOGLEVEL", "INFO").upper(), logging.INFO)
    )

app = FastAPI(title="Sprint Blog Generator")

client = TransitClient(itineraries=5, search_window=7200)
emissions_model = OperatorEmissionsModel()

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

    # Filter out Underground (940), DLR (930), Bus/Coach (700)
    def _keep(r) -> bool:
        rid = r.id or ""
        prefix = rid.split("_").pop()[:3] if "_" in rid else ""
        return prefix not in ("940", "930", "700")

    filtered = [r for r in results if _keep(r)]
    # Sort: exact name match first, then National Rail (910-912), then others
    q_lower = q.strip().lower()

    def _sort_key(r):
        rid = r.id or ""
        code = rid.split("_").pop()[:3] if "_" in rid else ""
        exact = 0 if r.name.lower() == q_lower else 1
        nr = 0 if code in ("910", "911", "912") else 1
        return (exact, nr, r.name)

    filtered.sort(key=_sort_key)
    return [
        {
            "id": r.id,
            "name": r.name,
            "lat": r.position.lat.degrees,
            "lon": r.position.lon.degrees,
        }
        for r in filtered
    ]


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
    leg_type = body.get("leg_type", "transit")
    mode = body.get("mode", "")

    from datetime import datetime
    from zoneinfo import ZoneInfo

    def _best_station(name: str) -> Location | None:
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
        depart_after -= timedelta(minutes=15)  # search a bit before so routes show up
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
        for week_offset in range(0, 5):
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
                        "mode": l.mode,
                        "display_name": l.display_name,
                        "operator": l.operator,
                        "origin": l.origin_name,
                        "destination": l.destination_name,
                        "origin_lat": l.origin_lat,
                        "origin_lon": l.origin_lon,
                        "dest_lat": l.dest_lat,
                        "dest_lon": l.dest_lon,
                        "departure": l.departure,
                        "arrival": l.arrival,
                        "duration_seconds": l.duration_seconds,
                        "distance_km": l.distance_km,
                        "max_speed_kmh": l.max_speed_kmh,
                        "stops": l.intermediate_stops,
                        "geometry": l.geometry,
                        "leg_type": l.leg_type,
                        "origin_platform": l.origin_platform,
                        "destination_platform": l.destination_platform,
                    }
                    for l in r.legs
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
            em_g = emissions_model.estimate_leg(leg)
            em_kg = round(em_g / 1000.0, 4)
            rate = round(emissions_model.leg_rate(leg), 1)
            rt["legs"][leg_idx]["emissions_kg"] = em_kg
            rt["legs"][leg_idx]["emissions_rate_g_per_km"] = rate
            total_kg += em_kg
        rt["total_emissions_kg"] = round(total_kg, 3)

    if offset_minutes is not None:
        resp["_offset_minutes"] = offset_minutes
        resp["_fallback_date"] = fallback_date
    return resp


# ---- Geometry enrichment (local OSM railway DB + arc interpolation fallback) ----

_ENRICH_CACHE: dict[str, tuple[list[dict[str, float]] | None, str | None]] = {}


def _arc_points(
    lat1: float, lon1: float, lat2: float, lon2: float, n: int = 32
) -> list[tuple[float, float]]:
    import math

    dx = lon2 - lon1
    dy = lat2 - lat1
    dist = math.sqrt(dx * dx + dy * dy)
    if dist < 1e-8:
        return [(lat1, lon1)]
    px, py = -dy / dist, dx / dist
    bulge = min(dist * 0.05, 0.02)
    pts = [
        (
            lat1 + dy * (i / n) + math.sin((i / n) * math.pi) * bulge * px,
            lon1 + dx * (i / n) + math.sin((i / n) * math.pi) * bulge * py,
        )
        for i in range(n + 1)
    ]
    return pts


def _subdivide(lat1, lon1, lat2, lon2, max_deg=0.5):
    dx, dy = abs(lat2 - lat1), abs(lon2 - lon1)
    if dx + dy <= max_deg:
        return [(lat1, lon1, lat2, lon2)]
    n = int((dx + dy) / max_deg) + 1
    return [
        (
            lat1 + (lat2 - lat1) * i / n,
            lon1 + (lon2 - lon1) * i / n,
            lat1 + (lat2 - lat1) * (i + 1) / n,
            lon1 + (lon2 - lon1) * (i + 1) / n,
        )
        for i in range(n)
    ]


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

    rnd = lambda x: round(x, 4)
    cache_key = hashlib.sha256(
        f"{rnd(origin_lat)},{rnd(origin_lon)}-{rnd(dest_lat)},{rnd(dest_lon)}".encode()
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

    # Phase 1: local railway database corridor query
    db = RailwayDB.get_instance()
    region = detect_region(origin_lat, origin_lon)
    source = None
    if region:
        db.ensure_region(region)
    if region:
        if db._region_loading.get(region):
            log.debug("_enrich_leg_geometry: region %s loading, returning None", region)
            return None, "loading"
        if db.is_ready(region):
            # Extract per-segment Transitous sub-geometries for route ranking,
            # clipped precisely between each pair of anchor points.
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

            all_coords = db.query_corridor(anchor_points, ref_geos=ref_geos)
            if all_coords:
                if len(all_coords) >= 2:
                    orig_name = anchor_points[0].get("name", "origin").replace(
                        " ", "_"
                    )
                    dest_name = anchor_points[-1].get(
                        "name", "destination"
                    ).replace(" ", "_")
                    lats = [c[0] for c in all_coords]
                    lons = [c[1] for c in all_coords]
                    log.info(
                        "  enriched %s->%s: %d coords, "
                        "bbox=(%.4f-%.4f, %.4f-%.4f)",
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
                            f"{frac_int:3d}% ({all_coords[si][0]:.4f},{all_coords[si][1]:.4f})"
                        )
                    if geometry and len(geometry) >= 2:
                        gn = len(geometry)
                        for frac_int in range(0, 101, 5):
                            frac = frac_int / 100.0
                            si = min(int(frac * (gn - 1)), gn - 1)
                            gp = geometry[si]
                            ref_samps.append(
                                f"{frac_int:3d}% ({gp['lat']:.4f},{gp['lon']:.4f})"
                            )
                        log.info(
                            "  enriched %s->%s OSM:\n    %s\n  Transitous REF:\n    %s",
                            orig_name,
                            dest_name,
                            "\n    ".join(osm_samps),
                            "\n    ".join(ref_samps),
                        )
                    else:
                        log.info(
                            "  enriched %s->%s OSM:\n    %s",
                            orig_name,
                            dest_name,
                            "\n    ".join(osm_samps),
                        )
                result = [{"lat": c[0], "lon": c[1]} for c in all_coords]
                _ENRICH_CACHE[cache_key] = (result, "railway_db")
                return result, "railway_db"
            else:
                log.debug("  query_corridor returned None")

    # Phase 2: straight-line fallback
    all_coords = []
    for i in range(len(anchor_points) - 1):
        a, b = anchor_points[i], anchor_points[i + 1]
        for sa_lat, sa_lon, sb_lat, sb_lon in _subdivide(
            a["lat"], a["lon"], b["lat"], b["lon"], max_deg=0.15
        ):
            seg = [(sa_lat, sa_lon), (sb_lat, sb_lon)]
            if all_coords:
                gap = abs(all_coords[-1][0] - seg[0][0]) + abs(
                    all_coords[-1][1] - seg[0][1]
                )
                all_coords.extend(seg[1 if gap < 0.0002 else 0 :])
            else:
                all_coords.extend(seg)
    result = [{"lat": c[0], "lon": c[1]} for c in all_coords] if all_coords else None
    source = "arc" if result else None
    _ENRICH_CACHE[cache_key] = (result, source)
    return result, source


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


def _enrich_one_leg(leg_in: dict) -> dict:
    if leg_in.get("leg_type") == "transfer":
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
    return {"index": leg_in.get("index"), "geometry": geom, "source": source}


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


def _build_snapshot(route_data: dict) -> TruthSnapshot:
    from truth.snapshot import TruthSnapshot, TruthRoute, TruthLeg

    legs = [
        TruthLeg(
            mode=l.get("mode", "REGIONAL_RAIL"),
            display_name=l.get("display_name", ""),
            operator=l.get("operator", ""),
            origin_name=l.get("origin", ""),
            destination_name=l.get("destination", ""),
            departure=l.get("departure", ""),
            arrival=l.get("arrival", ""),
            duration_seconds=l.get("duration_seconds", 0),
            distance_km=l.get("distance_km", 0),
            max_speed_kmh=l.get("max_speed_kmh", 0),
            tortuosity_pct=l.get("tortuosity_pct", 100),
            intermediate_stops=l.get("stops", []),
            origin_lat=l.get("origin_lat", 0.0),
            origin_lon=l.get("origin_lon", 0.0),
            dest_lat=l.get("dest_lat", 0.0),
            dest_lon=l.get("dest_lon", 0.0),
            geometry=l.get("geometry"),
            leg_type=l.get("leg_type", "transit"),
        )
        for l in route_data.get("legs", [])
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
    )
    return TruthSnapshot(
        snapshot_id="manual",
        created_at="",
        query={},
        routes=[route],
    )


def _build_curation(curation_data: dict, route_data: dict) -> CurationState:
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
