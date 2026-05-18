#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime, timedelta
from fastapi import FastAPI, Query
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

from rail_planner import TransitClient, DURATION, TRANSFERS, EMISSIONS
from emissions import CategoryBasedEmissions
from .post_parser import parse_post, write_post_cache, save_route_cache, list_sprint_posts

app = FastAPI(title="Sprint Blog Generator")

client = TransitClient(itineraries=5, search_window=7200)
emissions_model = CategoryBasedEmissions()


@app.get("/api/search-stations")
async def search_stations(q: str = Query("")):
    if not q or len(q) < 2:
        return []
    results = client.search_stations(q)
    return [
        {
            "id": r.id,
            "name": r.name,
            "lat": r.position.lat.degrees,
            "lon": r.position.lon.degrees,
        }
        for r in results
    ]


@app.get("/api/sprint-dirs")
async def sprint_dirs():
    img_dir = _project_root / "assets/img"
    dirs = sorted(
        d.name for d in img_dir.iterdir()
        if d.is_dir() and d.name.startswith("sprint")
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
        if not f.suffix.lower() in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
            continue
        if f.name in excluded:
            continue
        name_lower = f.name.lower()
        if direction == "outbound" and not name_lower.startswith("outbound"):
            continue
        if direction == "inbound" and not name_lower.startswith("inbound"):
            continue

        url = f"assets/img/{sprint}/{f.name}"
        results.append({
            "filename": f.name,
            "path": url,
            "size": f.stat().st_size,
        })

    return results


def _parse_timetable_window(error_msg: str) -> tuple[datetime, datetime] | None:
    """Extract the Transitous timetable window from error messages like
    'outside of loaded timetable window [2025-03-15, 2025-12-14['"""
    import re
    m = re.search(r'\[([^,]+),\s*([^\[]+)\[', error_msg)
    if not m:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d", "%d.%m.%Y %H:%M", "%d.%m.%Y"):
        try:
            ws = datetime.strptime(m.group(1).strip(), fmt)
        except ValueError:
            continue
        try:
            we = datetime.strptime(m.group(2).strip().rstrip(" ["), fmt)
        except ValueError:
            continue
        return (ws, we)
    return None


def _stochastic_route_fallback(
    origin, dest, via_locs, modes, original_dt,
    *, use_arrival: bool = False,
) -> list | None:
    """When Transitous has no data for the requested date, sample same-weekday
    dates across the available timetable window and return the most common
    route pattern. If use_arrival is True, search for routes arriving by that
    time instead of departing after it."""
    import re

    kw = {"arrive_before": original_dt} if use_arrival else {"depart_after": original_dt}

    # Trigger the error to discover the window
    error_msg = ""
    try:
        client.routes_between(
            origin, dest,
            via=via_locs or None,
            modes=modes,
            sort=EMISSIONS + TRANSFERS + DURATION,
            model=emissions_model,
            **kw,
        )
    except Exception as e:
        error_msg = str(e)

    window = _parse_timetable_window(error_msg)
    if not window:
        window = (datetime.now() + timedelta(days=1), datetime.now() + timedelta(days=365))
    window_start, window_end = window

    weekday = original_dt.weekday()
    candidates: list[list] = []

    # Sample up to 6 dates matching the same weekday, spread across the window
    span_days = (window_end - window_start).days
    step = max(1, span_days // 7)
    for i in range(7):
        sample = window_start + timedelta(days=i * step)
        days_ahead = weekday - sample.weekday()
        if days_ahead < 0:
            days_ahead += 7
        sample += timedelta(days=days_ahead)
        if sample > window_end:
            break
        sample = sample.replace(
            hour=original_dt.hour, minute=original_dt.minute,
            second=original_dt.second, microsecond=original_dt.microsecond,
        )
        kw = {"arrive_before": sample} if use_arrival else {"depart_after": sample}
        try:
            result = client.routes_between(
                origin, dest,
                via=via_locs or None,
                modes=modes,
                sort=EMISSIONS + TRANSFERS + DURATION,
                model=emissions_model,
                **kw,
            )
            if result:
                candidates.append(result)
        except Exception:
            continue

    if not candidates:
        return None

    def route_signature(routes):
        if not routes:
            return ()
        r = routes[0]
        return tuple(
            (l.origin.name, l.destination.name, l.mode)
            for l in r.legs if l.mode != "WALK"
        )

    # Pick the most common route pattern across all sampled dates
    signatures = [route_signature(c) for c in candidates]
    best_idx = max(
        range(len(candidates)),
        key=lambda i: sum(
            1 for j, s in enumerate(signatures) if j != i and s == signatures[i]
        ),
    )
    return candidates[best_idx]


def _serialize_geometry(geometry):
    """Convert geometry to [[lat, lon], ...] format regardless of input type."""
    if not geometry:
        return []
    # Already [[lat, lon], ...] format
    if isinstance(geometry[0], (list, tuple)):
        return [[float(p[0]), float(p[1])] for p in geometry]
    # Position objects with .lat/.lon
    if hasattr(geometry[0], 'lat'):
        return [[p.lat.degrees, p.lon.degrees] for p in geometry]
    # Dict format {"lat": ..., "lon": ...}
    if isinstance(geometry[0], dict):
        return [[float(p["lat"]), float(p["lon"])] for p in geometry]
    return []


def _time_string_to_minutes(ts: str) -> int:
    """Convert 'HH:MM' to minutes since midnight."""
    parts = ts.strip().split(":")
    return int(parts[0]) * 60 + int(parts[1])


def _minutes_to_time_string(m: int) -> str:
    """Convert minutes since midnight to 'HH:MM'."""
    m = m % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


def _apply_time_offset(route_data: dict, offset_minutes: int) -> None:
    """Shift all departure/arrival times in a route by offset_minutes.
    Wraps around midnight if needed. Only called for small offsets (<= 30 min)."""
    for leg in route_data.get("legs", []):
        if leg.get("departure"):
            base = _time_string_to_minutes(leg["departure"])
            leg["departure"] = _minutes_to_time_string(base + offset_minutes)
        if leg.get("arrival"):
            base = _time_string_to_minutes(leg["arrival"])
            leg["arrival"] = _minutes_to_time_string(base + offset_minutes)
    if route_data.get("departure"):
        base = _time_string_to_minutes(route_data["departure"])
        route_data["departure"] = _minutes_to_time_string(base + offset_minutes)
    if route_data.get("arrival"):
        base = _time_string_to_minutes(route_data["arrival"])
        route_data["arrival"] = _minutes_to_time_string(base + offset_minutes)


@app.post("/api/find-routes")
async def find_routes(body: dict):
    origin_name = body.get("origin", "")
    dest_name = body.get("destination", "")
    via = body.get("via", [])
    dep_date = body.get("date", "")
    dep_time = body.get("time", "")
    arrive_by = body.get("arrive_by", "")
    leg_type = body.get("leg_type", "transit")
    allow_fallback = body.get("allow_fallback", True)

    try:
        origin = client.exact(client.search_stations, origin_name)
        dest = client.exact(client.search_stations, dest_name)
    except (IndexError, ValueError):
        return JSONResponse({"error": f"Could not find station"}, status_code=400)

    via_locs = []
    for v in via:
        try:
            via_locs.append(client.exact(client.search_stations, v))
        except (IndexError, ValueError):
            pass

    user_set_time = bool(dep_time) or bool(arrive_by)
    use_arrival = bool(arrive_by) and not bool(dep_time)
    query_time = arrive_by if use_arrival else (dep_time or "08:00")

    if dep_date:
        query_dt = datetime.strptime(f"{dep_date} {query_time}", "%Y-%m-%d %H:%M")
    else:
        query_dt = datetime.now() + timedelta(hours=1)
        query_dt = query_dt.replace(hour=int(query_time.split(":")[0]),
                                    minute=int(query_time.split(":")[1]))

    modes = TransitClient.TRAVEL_SKYE_BUSINESS if leg_type in ('bus', 'flight') else TransitClient.TRAVEL_SKYE

    is_stochastic = False
    time_offset = 0

    route_kw = {"arrive_before": query_dt} if use_arrival else {"depart_after": query_dt}

    try:
        routes = client.routes_between(
            origin, dest,
            via=via_locs or None,
            modes=modes,
            sort=EMISSIONS + TRANSFERS + DURATION,
            model=emissions_model,
            **route_kw,
        )
    except Exception:
        routes = None

    # If direct query failed and fallback is allowed, try same-weekday sampling
    if not routes and allow_fallback:
        fallback = _stochastic_route_fallback(
            origin, dest, via_locs, modes, query_dt,
            use_arrival=use_arrival,
        )
        if fallback:
            routes = fallback
            is_stochastic = True

    if not routes:
        return JSONResponse({"error": "No routes found"}, status_code=404)

    from truth.snapshot import TruthSnapshot
    snapshot = TruthSnapshot.from_routes(routes, query=body)

    route_list = []
    for r in snapshot.routes:
        rd = {
            "route_id": r.route_id,
            "origin": r.origin_name,
            "destination": r.destination_name,
            "departure": r.departure,
            "arrival": r.arrival,
            "duration_seconds": r.duration_seconds,
            "duration_str": f"{r.duration_seconds//3600}h{(r.duration_seconds%3600)//60:02d}m",
            "total_distance_km": r.total_distance_km,
            "rail_distance_km": r.rail_distance_km,
            "walk_distance_km": r.walk_distance_km,
            "transfers": r.transfers,
            "average_speed_kmh": r.average_speed_kmh,
            "max_speed_kmh": r.max_speed_kmh,
            "tortuosity_pct": r.tortuosity_pct,
            "operators": r.operators,
            "stochastic": is_stochastic,
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
                    "geometry": _serialize_geometry(l.geometry),
                    "leg_type": l.leg_type,
                }
                for l in r.legs
            ],
        }

        # If stochastic, compute the time offset from the user's requested time.
        # Only apply small offsets (≤30 min) — larger differences mean the
        # historical timetable is too far off, so return raw historical times
        # and let the user edit them manually.
        ref_time = dep_time or arrive_by
        if is_stochastic and user_set_time and ref_time:
            ref_field = "arrival" if use_arrival else "departure"
            scheduled = _time_string_to_minutes(rd[ref_field])
            requested = _time_string_to_minutes(ref_time)
            time_offset = requested - scheduled
            if abs(time_offset) <= 30:
                _apply_time_offset(rd, time_offset)
            else:
                time_offset = 0

        route_list.append(rd)

    return {
        "snapshot_id": snapshot.snapshot_id,
        "routes": route_list,
        "stochastic": is_stochastic,
        "time_offset_minutes": time_offset if is_stochastic else 0,
    }


@app.post("/api/generate-blog")
async def generate_blog(body: dict):
    from truth.snapshot import TruthSnapshot
    from curation.state import CurationState, LegCuration
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
    import os, signal, threading, time
    threading.Thread(target=lambda: (time.sleep(0.5), os.kill(os.getpid(), signal.SIGTERM)), daemon=True).start()
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
            return {"success": True, "deleted": str(cf)}
    return JSONResponse({"error": "No cache file found"}, status_code=404)


assets_dir = _project_root / "assets"
if assets_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")


if __name__ == "__main__":
    print(f"Project root: {_project_root}")
    print(f"Starting server at http://localhost:8080")
    uvicorn.run(app, host="0.0.0.0", port=8080)
