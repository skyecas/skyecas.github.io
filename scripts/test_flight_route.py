#!/usr/bin/env python3
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
import json
import math

def load_module(path, name):
    spec = spec_from_file_location(name, str(Path(path).resolve()))
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

srv = load_module('assets/py/Rail Planner/ui/server.py', 'ui.server')
fb_mod = load_module('assets/py/Rail Planner/ui/flight_db.py', 'ui.flight_db')

fdb_inst = fb_mod.FlightDB.get_instance()

def point_eq(a,b,eps=1e-6):
    return abs(a['lat']-b['lat'])<eps and abs(a['lon']-b['lon'])<eps

def gc_arc(lat1, lon1, lat2, lon2, steps=64):
    # reuse FlightDB gc_arc logic via math slerp
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

def build_synthetic_departure(airport, dest_lat, dest_lon):
    # fallback synthetic runway: choose heading towards destination and threshold 3km out
    lat = airport['lat']; lon = airport['lon']
    bearing = fdb_inst._bearing(lat, lon, dest_lat, dest_lon)
    # threshold approx at 3 km in bearing direction
    thr = fdb_inst._dest_point(lat, lon, bearing, 3.0)
    # build path centroid->threshold
    path = []
    for f in [0.0, 0.25, 0.5, 0.75, 1.0]:
        path.append({'lat': lat + (thr[0]-lat)*f, 'lon': lon + (thr[1]-lon)*f})
    # rollout
    for i in range(1,7):
        d = 2.0 * (i/6)
        lat_r, lon_r = fdb_inst._dest_point(thr[0], thr[1], bearing, d)
        path.append({'lat': lat_r, 'lon': lon_r})
    # transition towards GC
    gc_bearing = fdb_inst._bearing(path[-1]['lat'], path[-1]['lon'], dest_lat, dest_lon)
    ang_delta = ((gc_bearing - bearing + 540) % 360) - 180
    trans_len = 8.0
    for i in range(1,9):
        heading_i = (bearing + ang_delta*(i/8))%360
        lat_t, lon_t = fdb_inst._dest_point(path[-1]['lat'], path[-1]['lon'], heading_i, trans_len*(i/8))
        path.append({'lat': lat_t, 'lon': lon_t})
    # append small GC segment
    gcpts = gc_arc(path[-1]['lat'], path[-1]['lon'], dest_lat, dest_lon, steps=32)
    path.extend(gcpts)
    return {'path': path, 'metadata': {'synthetic': True}}

def full_route(origin_name, dest_name):
    olist = fdb_inst.search_airports(origin_name)
    dlist = fdb_inst.search_airports(dest_name)
    if not olist or not dlist:
        print('Airport not found')
        return
    oa = olist[0]; da = dlist[0]
    print('Origin', oa['iata'], oa['lat'], oa['lon'])
    print('Dest', da['iata'], da['lat'], da['lon'])
    # origin departure
    dep = fdb_inst.build_detailed_departure(oa, da['lat'], da['lon'])
    if dep is None:
        dep = build_synthetic_departure(oa, da['lat'], da['lon'])
    # dest arrival: build departure from dest towards origin, then extract taxi/runway portion
    dest_dep = fdb_inst.build_detailed_departure(da, oa['lat'], oa['lon'])
    if dest_dep is None:
        # fallback synthetic arrival taxi (reverse of synthesized departure)
        dest_dep = build_synthetic_departure(da, oa['lat'], oa['lon'])
        # synthetic has full path, treat entire reversed as arrival taxi
        arr_path = list(reversed(dest_dep['path']))
        # compute mid GC from dep end to first arrival point
        dep_end = dep['path'][-1]
        arr_start = arr_path[0]
        mid_gc = gc_arc(dep_end['lat'], dep_end['lon'], arr_start['lat'], arr_start['lon'], steps=96)
    else:
        # dest_dep.path = ground_path + rollout + transition + gc_pts
        dest_info = fdb_inst.estimate_ground_and_departure(da)
        ground_len = len(dest_info['ground_path']) if dest_info and dest_info.get('ground_path') else 0
        rollout_steps = 6
        # transition steps derived from metadata transition_len_km
        trans_len_km = dest_dep.get('metadata', {}).get('transition_len_km', 8.0)
        trans_steps = max(4, int(trans_len_km))
        gc_start = ground_len + rollout_steps + trans_steps
        gc_pts = dest_dep['path'][gc_start:]
        rollout_seg = dest_dep['path'][ground_len : ground_len + rollout_steps]
        ground_seg = dest_dep['path'][:ground_len]

        # Build arrival segments: approach_glide (last N GC pts -> threshold), runway_landing (reversed rollout),
        # turn_off curve, taxi_to_gate (reversed ground to a gate near centroid)
        # Build a local approach glide segment ending at the runway threshold.
        # Avoid using long-range GC points; sample a short great-circle from ~approach_km
        # out to the threshold so the approach is local to Gatwick.
        approach_km = 50.0
        n_approach = 24
        approach_glide = []
        threshold = dest_info.get('threshold') if dest_info else None
        if threshold:
            # bearing from threshold toward origin (i.e., where the aircraft came from)
            bearing_to_origin = fdb_inst._bearing(threshold['lat'], threshold['lon'], oa['lat'], oa['lon'])
            # start point approx approach_km out along the reciprocal bearing
            start_lat, start_lon = fdb_inst._dest_point(threshold['lat'], threshold['lon'], (bearing_to_origin + 180) % 360, approach_km)
            # sample GC from start -> threshold
            approach_glide = gc_arc(start_lat, start_lon, threshold['lat'], threshold['lon'], steps=n_approach)
        else:
            # fallback: nearest n points from gc_pts
            n = min(24, len(gc_pts))
            approach_glide = [p for p in (gc_pts[-n:] if gc_pts else [])]
        # runway_landing: small segment along runway into the threshold
        runway_landing = []
        if dest_info and dest_info.get('runway_heading_deg'):
            th = threshold
            # step back along runway a short distance (0.8 km) to show landing rollout
            back_pt = fdb_inst._dest_point(th['lat'], th['lon'], (dest_info['runway_heading_deg'] + 180) % 360, 0.8)
            runway_landing = [ {'lat': back_pt[0], 'lon': back_pt[1]}, {'lat': th['lat'], 'lon': th['lon']} ]
        else:
            runway_landing = list(reversed(rollout_seg))

        # taxi start: first point after runway threshold (start of ground_seg when reversed)
        taxi_start = list(reversed(ground_seg))[0] if ground_seg else runway_landing[-1] if runway_landing else approach_glide[-1]

        # build a smooth turn: interpolate headings between runway_landing[-1] and taxi_start
        def interp_latlon(a, b, steps):
            pts = []
            for i in range(1, steps + 1):
                t = i / steps
                lat = a['lat'] + (b['lat'] - a['lat']) * t
                lon = a['lon'] + (b['lon'] - a['lon']) * t
                pts.append({'lat': lat, 'lon': lon})
            return pts

        turn_steps = 6
        if runway_landing:
            turn_start = runway_landing[-1]
        elif approach_glide:
            turn_start = approach_glide[-1]
        else:
            turn_start = taxi_start
        turn_curve = interp_latlon(turn_start, taxi_start, turn_steps)

        # taxi to gate: reverse ground_seg but end at a gate offset from centroid (small offset)
        centroid = dest_info['centroid'] if dest_info else {'lat': da['lat'], 'lon': da['lon']}
        # deterministic small gate offset based on IATA
        import hashlib
        h = hashlib.sha256(da['iata'].encode('utf8')).digest()
        off_lat = ((h[0] % 100) / 10000.0) * (1 if h[1] % 2 == 0 else -1) * 0.1
        off_lon = ((h[2] % 100) / 10000.0) * (1 if h[3] % 2 == 0 else -1) * 0.1
        gate = {'lat': centroid['lat'] + off_lat, 'lon': centroid['lon'] + off_lon}

        taxi_core = list(reversed(ground_seg))
        # replace final point with gate
        if taxi_core:
            taxi_core[-1] = gate
        else:
            taxi_core = [gate]

        arr_path = approach_glide + runway_landing + turn_curve + taxi_core
        dep_end = dep['path'][-1]
        arr_start = arr_path[0]
        mid_gc = gc_arc(dep_end['lat'], dep_end['lon'], arr_start['lat'], arr_start['lon'], steps=96)
        arr_segments = {
            'approach': approach_glide,
            'runway': runway_landing,
            'turn': turn_curve,
            'taxi': taxi_core,
        }
    # Keep the segments separate so they can be visualised differently later
    dep_path = dep['path']
    mid_path = mid_gc
    arr_path = arr_path
    return {
        'origin': oa,
        'dest': da,
        'dep_meta': dep.get('metadata'),
        'arr_meta': dest_dep.get('metadata'),
        'dep_path': dep_path,
        'mid_path': mid_path,
        'arr_path': arr_path,
        'path': dep_path + mid_path + arr_path,
    }

if __name__ == '__main__':
    out = full_route('Barcelona', 'Gatwick')
    print('Merged path points:', len(out['path']))
    # print sample
    print(json.dumps({'origin': out['origin'], 'dest': out['dest'], 'dep_meta': out['dep_meta'], 'arr_meta': out['arr_meta'], 'sample_start': out['path'][:5], 'sample_end': out['path'][-5:]}, indent=2))
    # write GeoJSON file with separate features for departure, mid_gc, and arrival
    dep_coords = [[p['lon'], p['lat']] for p in out['dep_path']]
    mid_coords = [[p['lon'], p['lat']] for p in out['mid_path']]
    arr_coords = [[p['lon'], p['lat']] for p in out['arr_path']]
    # Always build arrival segments from dest_info (LGW has valid PBF data)
    dest_info = fdb_inst.estimate_ground_and_departure(out['dest']) if hasattr(fdb_inst, 'estimate_ground_and_departure') else None
    app_coords = []; rwy_coords = []; turn_coords = []; taxi_coords = []
    if dest_info and dest_info.get('threshold') and len(arr_coords) >= 2:
        th = dest_info['threshold']
        # find index in arr_path closest to threshold
        best_i = 0; best_d = float('inf')
        for j, (lon, lat) in enumerate(arr_coords):
            d = math.hypot(lat - th['lat'], lon - th['lon'])
            if d < best_d:
                best_d = d; best_i = j
        # approach: first ~24 pts leading to threshold
        n_app = min(24, max(4, best_i))
        app_coords = arr_coords[:n_app]
        # runway: ~0.8 km before threshold to threshold
        rwy_end = best_i + 1
        rwy_start = max(0, best_i - 3)
        rwy_coords = arr_coords[rwy_start:rwy_end]
        # turn: ~6 pts after threshold
        turn_start = rwy_end
        turn_end = min(len(arr_coords), turn_start + 6)
        turn_coords = arr_coords[turn_start:turn_end]
        # taxi: remaining
        taxi_coords = arr_coords[turn_end:]
    if not turn_coords and not taxi_coords and len(arr_coords) >= 4:
        # fallback: simple 3-way split (head=approach, mid=runway+turn, tail=taxi)
        split = len(arr_coords) // 3
        app_coords = arr_coords[:split]
        rwy_coords = arr_coords[split:split+4]
        turn_coords = arr_coords[split+4:split+10]
        taxi_coords = arr_coords[split+10:]

    features = [
        {
            "type": "Feature",
            "properties": {"segment": "departure", "origin": out['origin']['iata']},
            "geometry": {"type": "LineString", "coordinates": dep_coords},
        },
        {
            "type": "Feature",
            "properties": {"segment": "mid_gc"},
            "geometry": {"type": "LineString", "coordinates": mid_coords},
        },
        {
            "type": "Feature",
            "properties": {"segment": "arrival_full", "dest": out['dest']['iata']},
            "geometry": {"type": "LineString", "coordinates": arr_coords},
        },
        {
            "type": "Feature",
            "properties": {"segment": "arrival_approach"},
            "geometry": {"type": "LineString", "coordinates": app_coords},
        },
        {
            "type": "Feature",
            "properties": {"segment": "arrival_runway"},
            "geometry": {"type": "LineString", "coordinates": rwy_coords},
        },
        {
            "type": "Feature",
            "properties": {"segment": "arrival_turn"},
            "geometry": {"type": "LineString", "coordinates": turn_coords},
        },
        {
            "type": "Feature",
            "properties": {"segment": "arrival_taxi"},
            "geometry": {"type": "LineString", "coordinates": taxi_coords},
        },
    ]
    # include metadata as a separate feature with properties
    meta_feat = {
        "type": "Feature",
        "properties": {"dep_meta": out.get('dep_meta'), "arr_meta": out.get('arr_meta')},
        "geometry": None,
    }
    fc = {"type": "FeatureCollection", "features": features + [meta_feat]}
    out_path = Path('assets/py/Rail Planner/ui/static_routes/bcn_lgw.geojson')
    out_path.write_text(json.dumps(fc))
    print('Wrote', out_path)
