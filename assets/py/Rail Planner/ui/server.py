#!/usr/bin/env python3
from __future__ import annotations
import re
import sys
import logging
import os
import warnings
from pathlib import Path
from typing import Any

# Suppress asyncio.iscoroutinefunction deprecation warning from FastAPI/starlette
warnings.filterwarnings("ignore", message=".*asyncio.iscoroutinefunction.*")

from fastapi import FastAPI, Query
from datetime import timedelta
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn


_script_dir = Path(__file__).parent.resolve()

# Load .env file from same directory
_env_path = _script_dir / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            _v = _v.strip('"').strip("'")
            if not os.environ.get(_k):
                os.environ[_k] = _v

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
from flight_db import FlightDB  # noqa: E402

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
    code = q.strip().upper()

    # Also search FlightDB for airports
    from flight_db import FlightDB
    fdb = FlightDB.get_instance()
    airport_results = []
    seen_ids = set()
    ap = fdb.find_airport(code)
    if ap:
        aid = f"airport_{code}"
        airport_results.append({
            "id": aid, "name": f"{ap['name']} ({code})",
            "lat": ap["lat"], "lon": ap["lon"],
        })
        seen_ids.add(aid)
    for a in fdb.search_airports(q):
        iata = a.get("iata", "")
        if not iata:
            continue
        aid = f"airport_{iata}"
        if aid not in seen_ids:
            seen_ids.add(aid)
            label = f"{a['name']} ({iata})"
            airport_results.append({
                "id": aid, "name": label,
                "lat": a["lat"], "lon": a["lon"],
            })

    # Check legacy CRS codes (lat/lon fallback) — place after Transitous results
    if code in STATION_COORDS:
        lat, lon = STATION_COORDS[code]
        return [{"id": code, "name": code, "lat": lat, "lon": lon}] + airport_results

    # Fall back to Transitous search
    import asyncio

    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, client.search_stations, q)

    # Sort: exact name match first, then UK stations, then by type priority
    # (National Rail > Underground > DLR > Coach/Bus > other), then alphabetically.
    q_lower = q.strip().lower()

    def _type_priority(code):
        return {"910": 0, "911": 0, "912": 0, "940": 1, "930": 2, "700": 3}.get(code, 4)

    def _sort_key(r):
        rid = r.id or ""
        country = rid.split("_")[0] if "_" in rid else ""
        code = rid.split("_").pop()[:3] if "_" in rid else ""
        exact = 0 if r.name.lower() == q_lower else 1
        uk = 0 if country in ("uk", "gb") else 1
        return (exact, uk, _type_priority(code), r.name.lower())

    results.sort(key=_sort_key)
    seen_ids = set(seen_ids)
    transit_results = []
    for r in results:
        rid = r.id or ""
        if rid in seen_ids:
            continue
        seen_ids.add(rid)
        transit_results.append({
            "id": rid,
            "name": r.name,
            "lat": r.position.lat.degrees,
            "lon": r.position.lon.degrees,
        })
    
    # Better matching: score by how much of the query is present in the name
    def _match_score(name, query):
        """Return a score tuple (lower is better): (words_matched, word_order, name_length, name_lower)"""
        name_lower = name.lower()
        query_lower = query.lower()
        query_words = query_lower.split()
        
        # Check how many query words appear in the name
        matched_words = sum(1 for w in query_words if w in name_lower)
        
        # Check if query words appear in order
        in_order = 0
        pos = 0
        for word in query_words:
            new_pos = name_lower.find(word, pos)
            if new_pos >= 0:
                pos = new_pos + len(word)
            else:
                in_order += 1
        
        return (-matched_words, in_order, len(name_lower), name_lower)  # Negative matched_words for descending sort
    
    # Sort airports by relevance
    airport_results_sorted = sorted(airport_results, key=lambda a: _match_score(a["name"], q))
    
    # Sort transit by relevance
    transit_results_sorted = sorted(transit_results, key=lambda t: _match_score(t["name"], q))
    
    # Merge: exact matches first, then all inexact sorted by match quality
    # (airport can rank above weak transit when it matches more query words)
    q_lower = q.strip().lower()
    exact_transit = [r for r in transit_results_sorted if r["name"].lower() == q_lower]
    exact_airports = [a for a in airport_results_sorted if a["name"].lower() == q_lower]
    
    # Combine all inexact results, sort by match score, with transit tiebreaker
    inexact = []
    for r in transit_results_sorted:
        if r["name"].lower() != q_lower:
            inexact.append((_match_score(r["name"], q), False, r["name"].lower(), r))
    for a in airport_results_sorted:
        if a["name"].lower() != q_lower:
            inexact.append((_match_score(a["name"], q), True, a["name"].lower(), a))
    inexact.sort(key=lambda x: (x[0], x[1], x[2]))
    
    return exact_transit + exact_airports + [x[3] for x in inexact]


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

    # Check for airport names with IATA code in parentheses
    import re as _re
    _iata_match = _re.search(r'\(([A-Z]{3})\)', name)
    if _iata_match:
        from flight_db import FlightDB
        ap = FlightDB.get_instance().find_airport(_iata_match.group(1))
        if ap:
            resolved = {
                "input": name,
                "key": f"airport_{ap['iata']}",
                "name": ap["name"],
                "lat": ap["lat"],
                "lon": ap["lon"],
            }
            _STATION_ALIAS_CACHE[cache_key] = resolved
            return resolved

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

            # Airport prefix: resolve via FlightDB
            if station_id.startswith("airport_"):
                iata = station_id.split("_", 1)[1]
                ap = FlightDB.get_instance().find_airport(iata)
                if ap:
                    return Location(
                        position=Position(ap["lat"], ap["lon"]),
                        timezone=ZoneInfo("Europe/London"),
                        id=iata,
                        name=ap["name"],
                        address=f"{ap.get('city', '')}, {ap.get('country', '')}",
                    )

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

    def _resolve_airport(name):
        from flight_db import FlightDB
        _d = FlightDB.get_instance()
        ap = _d.find_airport(name.strip().upper())
        if not ap:
            matches = [a for a in _d.search_airports(name) if a.get("lat") and a.get("lon")]
            ap = matches[0] if matches else None
        if ap:
            from geo import Position
            from rail_planner import Location
            return Location(
                position=Position(ap["lat"], ap["lon"]),
                timezone=ZoneInfo("Europe/London"),
                id=ap.get("iata", name),
                name=ap["name"],
                address=f"{ap.get('city', '')}, {ap.get('country', '')}",
            )
        return None

    try:
        origin = resolve_station(origin_name, origin_id)
        dest = resolve_station(dest_name, dest_id)
    except (IndexError, ValueError) as e:
        if mode != "plane":
            return JSONResponse(
                {"error": f"Could not find station for '{origin_name}' or '{dest_name}': {str(e)}"}, 
                status_code=400
            )
        # Plane mode: try FlightDB airport lookup
        origin = _resolve_airport(origin_name)
        dest = _resolve_airport(dest_name)
        if not origin:
            return JSONResponse(
                {"error": f"Could not find airport for '{origin_name}' (expected IATA code like BCN, LGW, etc.)"}, 
                status_code=400
            )
        if not dest:
            return JSONResponse(
                {"error": f"Could not find airport for '{dest_name}' (expected IATA code like BCN, LGW, etc.)"}, 
                status_code=400
            )

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

    # Plane mode: skip Transitous entirely, use FlightDB + OpenSky
    if mode == "plane":
        # Check credentials first
        username = os.environ.get("OSKY_USER", "")
        password = os.environ.get("OSKY_PASS", "")
        if not username or not password:
            resp = _route_response([], body)
            resp["_warning"] = "OpenSky credentials not configured (OSKY_USER/OSKY_PASS). Set in .env file to enable flight search."
            return resp
        
        opensky_routes = _opensky_search_flights(
            origin_name, dest_name, depart_after,
            origin, dest, origin_id, dest_id,
        )
        if opensky_routes:
            return _route_response(opensky_routes, body)
        resp = _route_response([], body)
        resp["_warning"] = f"No flights found for {origin_name} ({origin_id}) → {dest_name} ({dest_id}). Check OpenSky API credentials and ensure both airports are in the database."
        return resp

    via_locs = []
    for v in via:
        try:
            match = _best_station(v)
            if match:
                via_locs.append(match)
        except (IndexError, ValueError):
            pass

    # Default: all UK/EU rail (train, regional, high speed, subway, tram, light rail, ferry, walk)
    # This is the recommended mode — includes everything a rail journey might use.
    ALL_RAIL = TransitClient.TRAVEL_SKYE  # "RAIL,REGIONAL_RAIL,...,WALK"

    if mode == ":train" or mode == "train" or not mode:
        modes = "RAIL,REGIONAL_RAIL,REGIONAL_FAST_RAIL,HIGHSPEED_RAIL,NIGHT_RAIL,SUBURBAN,SUBWAY,TRAM,METRO"
    elif mode == ":road":
        modes = "BUS,COACH,CAR,RIDE_SHARING"
    elif mode == ":other":
        modes = "AIRPLANE,FERRY,WALK"
    elif mode == "walking":
        modes = "WALK"
    elif mode == "bus":
        modes = "BUS"
    elif mode == "coach":
        modes = "COACH"
    elif mode == "plane":
        modes = "AIRPLANE"
    elif mode == "ferry":
        modes = "FERRY"
    elif mode == "car":
        modes = "CAR,RIDE_SHARING"
    elif mode == "high_speed":
        modes = "HIGHSPEED_RAIL,REGIONAL_FAST_RAIL,NIGHT_RAIL"
    elif mode == "regional":
        modes = "REGIONAL_RAIL,SUBURBAN"
    elif mode == "subway":
        modes = "SUBWAY,METRO"
    elif mode == "light_rail":
        modes = "TRAM,SUBWAY,METRO,SUBURBAN"
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

    # OSRM fallback: try driving/walking when Transitous returns nothing
    _osrm_routes = _try_osrm_fallback(
        origin, dest, origin_name, dest_name,
        origin_id, dest_id, mode, body,
    )
    if _osrm_routes:
        return _route_response(_osrm_routes, body)

    resp = _route_response([], body)
    mode_label = body.get("mode", "train")
    resp["_warning"] = (
        warning
        or f"No routes found for {origin_name} → {dest_name} using mode={mode_label}"
    )
    return resp


def _try_osrm_fallback(
    origin, dest,
    origin_name, dest_name,
    origin_id, dest_id,
    mode, body,
) -> list:
    """Query OSRM when Transitous returns no results for driving/walking/airport-connections."""
    from geo import Position
    from rail_planner import Route, Leg, Stop
    from time_util import Time
    import requests as _requests

    # Determine if OSRM is appropriate
    is_airport_origin = "airport_" in origin_id
    is_airport_dest = "airport_" in dest_id
    any_airport = is_airport_origin or is_airport_dest
    is_road_mode = mode in (":road", "car", "walking")

    if not any_airport and not is_road_mode:
        return []

    # Choose OSRM profile
    if mode == "walking":
        profile = "walking"
        osrm_mode = "WALK"
    elif is_road_mode or any_airport:
        profile = "driving"
        osrm_mode = "CAR"

    o_lon = origin.position.lon.degrees
    o_lat = origin.position.lat.degrees
    d_lon = dest.position.lon.degrees
    d_lat = dest.position.lat.degrees

    url = (
        f"https://router.project-osrm.org/route/v1/{profile}"
        f"/{o_lon},{o_lat};{d_lon},{d_lat}"
        f"?overview=full&geometries=geojson"
    )
    try:
        resp = _requests.get(url, timeout=25)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.info("OSRM query failed: %s", e)
        return []

    if data.get("code") != "Ok" or not data.get("routes"):
        return []

    route_data = data["routes"][0]
    duration_s = route_data["duration"]
    geometry = route_data.get("geometry", {})
    coords = geometry.get("coordinates", [])

    geo_positions = [Position(lat, lon) for lon, lat in coords]

    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Europe/London")
    now = datetime.now(tz)
    dep_time = Time(now, tz)
    arr_time = Time(now + timedelta(seconds=duration_s), tz)

    origin_stop = Stop(
        position=origin.position,
        timezone=tz,
        name=origin_name,
        id=origin_id,
        departure=dep_time,
    )
    dest_stop = Stop(
        position=dest.position,
        timezone=tz,
        name=dest_name,
        id=dest_id,
        arrival=arr_time,
    )

    leg = Leg(
        mode=osrm_mode,
        origin=origin_stop,
        destination=dest_stop,
        stops=[],
        name=f"OSRM {profile}",
        geometry=geo_positions,
    )

    route = Route(
        origin=origin,
        destination=dest,
        departure=dep_time,
        arrival=arr_time,
        legs=[leg],
    )
    return [route]


def _opensky_search_flights(
    origin_name: str, dest_name: str,
    dep_dt,
    origin_loc, dest_loc,
    origin_id: str = "", dest_id: str = "",
) -> list:
    """Query OpenSky Network for historical flights and return Route objects."""
    from datetime import datetime as _datetime
    from zoneinfo import ZoneInfo as _ZoneInfo
    import requests as _requests

    username = os.environ.get("OSKY_USER", "")
    password = os.environ.get("OSKY_PASS", "")
    if not username or not password:
        log.warning("OpenSky credentials not configured; set OSKY_USER/OSKY_PASS")
        return []

    db = FlightDB.get_instance()

    def _airport_icao(name, sid=""):
        # Try ID first (airport_BCN -> extract IATA)
        if sid:
            iata = sid.split("airport_", 1)[-1] if "airport_" in sid else ""
            if iata:
                ap = db.find_airport(iata)
                if ap and ap.get("icao"):
                    return ap["icao"]
        # Try extracting IATA from name "(BCN)"
        import re as _re
        _m = _re.search(r'\(([A-Z]{3})\)', name)
        if _m:
            ap = db.find_airport(_m.group(1))
            if ap and ap.get("icao"):
                return ap["icao"]
        # Fallback: raw name lookup
        ap = db.find_airport(name.strip().upper())
        if ap and ap.get("icao"):
            return ap["icao"]
        matches = [a for a in db.search_airports(name) if a.get("icao")]
        return matches[0]["icao"] if matches else None

    orig_icao = _airport_icao(origin_name, origin_id)
    dest_icao = _airport_icao(dest_name, dest_id)
    if not orig_icao or not dest_icao:
        missing = []
        if not orig_icao: missing.append(f"origin '{origin_name}'")
        if not dest_icao: missing.append(f"destination '{dest_name}'")
        log.warning("Could not resolve ICAO codes for %s", " / ".join(missing))
        return []

    _now = _datetime.now()
    target = dep_dt.replace(tzinfo=None)
    if target > _now:
        while target > _now:
            target -= timedelta(days=7)
    elif (_now - target).days > 30:
        while (_now - target).days > 30:
            target += timedelta(days=7)

    day_start = target.replace(hour=0, minute=0, second=0, microsecond=0)
    begin_ts = int(day_start.timestamp())
    end_ts = begin_ts + 2 * 86400

    url = f"https://opensky-network.org/api/flights/arrival?airport={dest_icao}&begin={begin_ts}&end={end_ts}"
    try:
        resp = _requests.get(url, auth=(username, password), timeout=30)
        resp.raise_for_status()
        flights = resp.json()
    except Exception as e:
        error_msg = f"OpenSky query failed ({type(e).__name__}): {str(e)}"
        if "403" in str(e):
            error_msg += " [Check OpenSky credentials and account permissions]"
        elif "401" in str(e):
            error_msg += " [Invalid OpenSky credentials]"
        log.warning("%s", error_msg)
        return []

    if not isinstance(flights, list):
        return []

    flights = [f for f in flights if f.get("estDepartureAirport") == orig_icao]

    req_ts = int(dep_dt.timestamp())
    flights.sort(key=lambda f: abs((f.get("firstSeen") or 0) - req_ts))

    from rail_planner import Route, Leg, Stop
    from geo import Position
    from time_util import Time

    tz = _ZoneInfo("Europe/London")
    routes = []
    for f in flights:
        callsign = (f.get("callsign") or "").strip()
        icao24 = f.get("icao24") or ""
        if not callsign:
            continue
        first_ts = f.get("firstSeen")
        last_ts = f.get("lastSeen")
        if not first_ts or not last_ts:
            continue

        dep_utc = _datetime.fromtimestamp(first_ts, tz=_ZoneInfo("UTC")).astimezone(tz)
        arr_utc = _datetime.fromtimestamp(last_ts, tz=_ZoneInfo("UTC")).astimezone(tz)

        op_match = re.match(r"^([A-Z]{2,3})", callsign)
        operator = op_match.group(1) if op_match else ""

        origin_stop = Stop(
            position=Position(origin_loc.position.lat.degrees, origin_loc.position.lon.degrees),
            timezone=tz,
            name=origin_loc.name,
            id=origin_loc.id,
            departure=Time(dep_utc, tz),
        )
        dest_stop = Stop(
            position=Position(dest_loc.position.lat.degrees, dest_loc.position.lon.degrees),
            timezone=tz,
            name=dest_loc.name,
            id=dest_loc.id,
            arrival=Time(arr_utc, tz),
        )

        leg = Leg(
            mode="AIRPLANE",
            origin=origin_stop,
            destination=dest_stop,
            stops=[],
            id=icao24,
            name=callsign,
            operator=operator,
        )

        route = Route(
            origin=origin_loc,
            destination=dest_loc,
            departure=Time(dep_utc, tz),
            arrival=Time(arr_utc, tz),
            legs=[leg],
        )
        routes.append(route)

    return routes


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
        mode = (leg.get("mode") or "RAIL").upper()
        distance_km = float(leg.get("distance_km") or 0)
        distance_source = leg.get("distance_source", "scheduled")

        # Flight distance fallback: compute great-circle + surface/taxi uplift
        if distance_km <= 0 and mode in {"PLANE", "AIRPLANE", "FLIGHT"}:
            # Prefer enriched geometry if provided by enrichment step
            geom = leg.get("geometry") or leg.get("enriched_geometry")
            if geom and isinstance(geom, list) and len(geom) >= 2:
                # compute polyline length
                import math

                def _poly_len_km(g):
                    s = 0.0
                    for j in range(1, len(g)):
                        lat1, lon1 = g[j - 1]["lat"], g[j - 1]["lon"]
                        lat2, lon2 = g[j]["lat"], g[j]["lon"]
                        # haversine
                        R = 6371.0
                        dlat = math.radians(lat2 - lat1)
                        dlon = math.radians(lon2 - lon1)
                        a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
                        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
                        s += R * c
                    return s

                distance_km = _poly_len_km(geom)
                distance_source = "flight_arc"
            else:
                # Try airport name/coords via FlightDB
                origin_lat = leg.get("origin_lat")
                origin_lon = leg.get("origin_lon")
                dest_lat = leg.get("dest_lat")
                dest_lon = leg.get("dest_lon")
                if origin_lat is None or dest_lat is None:
                    # Try searching by name
                    fdb = FlightDB.get_instance()
                    o_candidates = fdb.search_airports(leg.get("origin", "") or "")
                    d_candidates = fdb.search_airports(leg.get("destination", "") or "")
                    if o_candidates:
                        origin_lat = o_candidates[0]["lat"]
                        origin_lon = o_candidates[0]["lon"]
                    if d_candidates:
                        dest_lat = d_candidates[0]["lat"]
                        dest_lon = d_candidates[0]["lon"]
            if origin_lat is not None and dest_lat is not None:
                    # haversine between airport centroids
                    import math

                    R = 6371.0
                    lat1 = math.radians(float(origin_lat))
                    lat2 = math.radians(float(dest_lat))
                    dlat = lat2 - lat1
                    dlon = math.radians(float(dest_lon) - float(origin_lon))
                    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
                    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
                    gc = R * c
                    # Surface/taxi + uplift heuristics
                    # Surface km: conservative default 15 km (taxi/approach)
                    surface_km = 15.0
                    # Routing uplift: short-haul has proportionally more detours
                    if gc <= 500:
                        uplift = 1.10
                        surface_km = 12.0
                    elif gc <= 2000:
                        uplift = 1.06
                        surface_km = 15.0
                    else:
                        uplift = 1.03
                        surface_km = 18.0
                    distance_km = gc * uplift + surface_km
                    distance_source = "airport_gc_estimate"
                    # Try to refine surface_km using OSM runway/taxiway data via FlightDB
                    try:
                        fdb = FlightDB.get_instance()
                        origin_airps = fdb.search_airports(leg.get('origin', '') or '')
                        dest_airps = fdb.search_airports(leg.get('destination', '') or '')
                        if origin_airps:
                            oinfo = fdb.estimate_ground_and_departure(origin_airps[0])
                            if oinfo and oinfo.get('distance_km') is not None:
                                surface_km = min(30.0, max(5.0, oinfo.get('distance_km')))
                        if dest_airps:
                            dinfo = fdb.estimate_ground_and_departure(dest_airps[0])
                            if dinfo and dinfo.get('distance_km') is not None:
                                surface_km = max(surface_km, min(30.0, max(5.0, dinfo.get('distance_km'))))
                        distance_km = gc * uplift + surface_km
                        distance_source = 'airport_gc_estimate'
                    except Exception:
                        pass
        detail = _emissions_detail(
            mode=mode,
            operator=leg.get("operator", ""),
            distance_km=distance_km,
            distance_source=distance_source,
            countries=leg.get("countries") or [],
            traction_hint=leg.get("traction_hint"),
        )
        detail["index"] = leg.get("index", i)
        legs.append(detail)
    return {"legs": legs}


def _enrich_one_leg(leg_in: dict) -> dict:
    if leg_in.get("leg_type", "transit") not in {"transit", "unincluded"}:
        # If this is a flight leg, return a great-circle flight arc fallback
        if leg_in.get("mode") in {"plane", "PLANE", "flight"}:
            from math import radians, sin, cos, atan2

            def _flight_arc(lat1, lon1, lat2, lon2, steps=32):
                # simple great-circle interpolation (slerp on unit sphere)
                import math

                lat1r = math.radians(lat1)
                lon1r = math.radians(lon1)
                lat2r = math.radians(lat2)
                lon2r = math.radians(lon2)
                # convert to cartesian
                x1 = math.cos(lat1r) * math.cos(lon1r)
                y1 = math.cos(lat1r) * math.sin(lon1r)
                z1 = math.sin(lat1r)
                x2 = math.cos(lat2r) * math.cos(lon2r)
                y2 = math.cos(lat2r) * math.sin(lon2r)
                z2 = math.sin(lat2r)
                dot = max(-1.0, min(1.0, x1 * x2 + y1 * y2 + z1 * z2))
                omega = math.acos(dot)
                pts = []
                if omega == 0:
                    return [{"lat": lat1, "lon": lon1}, {"lat": lat2, "lon": lon2}]
                for i in range(steps + 1):
                    t = i / steps
                    s1 = math.sin((1 - t) * omega) / math.sin(omega)
                    s2 = math.sin(t * omega) / math.sin(omega)
                    x = s1 * x1 + s2 * x2
                    y = s1 * y1 + s2 * y2
                    z = s1 * z1 + s2 * z2
                    lat = math.degrees(math.atan2(z, math.hypot(x, y)))
                    lon = math.degrees(math.atan2(y, x))
                    pts.append({"lat": lat, "lon": lon})
                return pts

            if leg_in.get("origin_lat") is not None and leg_in.get("dest_lat") is not None:
                arc = _flight_arc(leg_in.get("origin_lat"), leg_in.get("origin_lon"), leg_in.get("dest_lat"), leg_in.get("dest_lon"))
                return {"index": leg_in.get("index"), "geometry": arc, "source": "flight_arc"}
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
        # Get file size before deleting
        file_size = cache_path.stat().st_size
        cache_path.unlink()
        print(f"Deleted railway cache: {cache_path} ({file_size / (1024**2):.1f} MB)")
        return {"success": True, "deleted": str(cache_path), "size_bytes": file_size}
    return JSONResponse({"error": "No railway cache found"}, status_code=404)


assets_dir = _project_root / "assets"
if assets_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")


if __name__ == "__main__":
    print(f"Project root: {_project_root}")
    print("Starting server at http://localhost:8080")
    uvicorn.run(app, host="0.0.0.0", port=8080)
