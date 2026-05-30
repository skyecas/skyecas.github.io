#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
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

    def resolve_station(name, station_id=""):
        if station_id:
            from geo import Position
            from rail_planner import Location
            return Location(
                position=Position(0, 0), timezone=ZoneInfo("Europe/London"),
                id=station_id, name=name, address=name,
            )
        return client.exact(client.search_stations, name)

    try:
        origin = resolve_station(origin_name, origin_id)
        dest = resolve_station(dest_name, dest_id)
    except (IndexError, ValueError):
        return JSONResponse({"error": f"Could not find station"}, status_code=400)

    via_locs = []
    for v in via:
        try:
            via_locs.append(client.exact(client.search_stations, v))
        except (IndexError, ValueError):
            pass

    if dep_date:
        depart_after = datetime.strptime(f"{dep_date} {dep_time}", "%Y-%m-%d %H:%M")
    else:
        from datetime import timedelta
        depart_after = datetime.now() + timedelta(hours=1)

    if mode == "walking":
        modes = "WALK"
    elif mode in ("bus", "plane", "coach"):
        modes = TransitClient.TRAVEL_SKYE_BUSINESS
    elif mode == "ferry":
        modes = TransitClient.TRAVEL_SKYE + ",FERRY"
    elif mode == "car":
        modes = "CAR,RIDE_SHARING"
    elif mode == "high_speed":
        modes = "HIGHSPEED_RAIL,REGIONAL_FAST_RAIL,NIGHT_RAIL"
    elif mode == "regional":
        modes = "REGIONAL_RAIL,SUBURBAN"
    elif mode == "light_rail":
        modes = "TRAM,SUBWAY,METRO,SUBURBAN"
    elif mode:
        modes = TransitClient.TRAVEL_SKYE
    else:
        modes = TransitClient.TRAVEL_SKYE_BUSINESS if leg_type in ('bus', 'flight') else TransitClient.TRAVEL_SKYE

    try:
        routes = client.routes_between(
            origin, dest,
            depart_after=depart_after,
            via=via_locs or None,
            modes=modes,
            sort=EMISSIONS + TRANSFERS + DURATION,
            model=emissions_model,
        )
    except Exception as e:
        if "400" in str(e) and dep_date:
            from datetime import timedelta
            user_dt = depart_after
            target_weekday = user_dt.weekday()
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            days_ahead = target_weekday - today.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            first_match = today + timedelta(days=days_ahead)
            for week_offset in range(0, 9):
                alt_date = first_match + timedelta(weeks=week_offset)
                alt_dt = alt_date.replace(hour=user_dt.hour, minute=user_dt.minute)
                try:
                    alt_routes = client.routes_between(
                        origin, dest,
                        depart_after=alt_dt,
                        via=via_locs or None,
                        modes=modes,
                        sort=EMISSIONS + TRANSFERS + DURATION,
                        model=emissions_model,
                    )
                except Exception:
                    continue
                offset_min = int((alt_dt - user_dt).total_seconds() / 60)
                alt_body = dict(body, date=alt_dt.strftime("%Y-%m-%d"))
                return _route_response(alt_routes, alt_body, offset_min, alt_dt.strftime("%Y-%m-%d"))
        return JSONResponse({"error": str(e)}, status_code=500)

    return _route_response(routes, body)


def _route_response(routes, query_body, offset_minutes=None, fallback_date=None):
    from truth.snapshot import TruthSnapshot
    snapshot = TruthSnapshot.from_routes(routes, query=query_body)

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
                "duration_str": f"{r.duration_seconds//3600}h{(r.duration_seconds%3600)//60:02d}m",
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
                    }
                    for l in r.legs
                ],
            }
            for r in snapshot.routes
        ],
    }
    if offset_minutes is not None:
        resp["_offset_minutes"] = offset_minutes
        resp["_fallback_date"] = fallback_date
    return resp


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
    import threading, os, time
    threading.Thread(target=lambda: (time.sleep(0.5), os._exit(0)), daemon=True).start()
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
