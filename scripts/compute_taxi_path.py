#!/usr/bin/env python3
from pathlib import Path
import gzip
import json
import math
import heapq
from collections import deque

def haversine_km(a_lat, a_lon, b_lat, b_lon):
    R = 6371.0
    dlat = math.radians(b_lat - a_lat)
    dlon = math.radians(b_lon - a_lon)
    lat1 = math.radians(a_lat)
    lat2 = math.radians(b_lat)
    aa = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(aa), math.sqrt(1-aa))

BASE = Path('assets/py/Rail Planner/ui')
RUN_CACHE = BASE / 'data' / 'runways.great-britain-latest.json.gz'
GATE_CACHE = BASE / 'data' / 'gates.great-britain-latest.json.gz'
GEOJSON = BASE / 'static_routes' / 'bcn_lgw.geojson'
OUT_GEO = BASE / 'static_routes' / 'bcn_lgw_taxi.geojson'

if not RUN_CACHE.exists():
    raise SystemExit('Runway cache missing')
if not GATE_CACHE.exists():
    raise SystemExit('Gate cache missing')
if not GEOJSON.exists():
    raise SystemExit('Route geojson missing')

# Load runway/taxiway ways
with gzip.open(RUN_CACHE, 'rt') as f:
    rc = json.load(f)
ways = rc.get('ways', [])

# Build graph: nodes are unique (lat,lon) floats; edges between consecutive coords
node_index = {}
nodes = []
edges = {}

def add_node(lat, lon):
    key = (round(lat, 7), round(lon, 7))
    if key in node_index:
        return node_index[key]
    nid = len(nodes)
    node_index[key] = nid
    nodes.append({'lat': lat, 'lon': lon})
    edges[nid] = []
    return nid

# Filter ways to a local bbox around airport centroid (to avoid cross-country links)
def ways_nearby(ways, center_lat, center_lon, radius_km=6.0):
    out = []
    for w in ways:
        coords = w.get('coords', [])
        if not coords:
            continue
        for lat, lon in coords:
            if haversine_km(center_lat, center_lon, lat, lon) <= radius_km:
                out.append(w)
                break
    return out

# find the arrival runway feature in the route geojson and use its endpoints as thresholds
gj = json.loads(GEOJSON.read_text())
arrival_runway = None
for feat in gj.get('features', []):
    if (feat.get('properties') or {}).get('segment') == 'arrival_runway':
        arrival_runway = feat
        break

if arrival_runway and arrival_runway.get('geometry') and arrival_runway['geometry'].get('coordinates'):
    rr_coords = arrival_runway['geometry']['coordinates']
    # rr_coords are lon,lat tuples; thresholds are endpoints
    th1 = {'lat': rr_coords[0][1], 'lon': rr_coords[0][0]}
    th2 = {'lat': rr_coords[-1][1], 'lon': rr_coords[-1][0]}
    airport_centroid = ((th1['lat'] + th2['lat']) / 2.0, (th1['lon'] + th2['lon']) / 2.0)
else:
    # fallback to known LGW coords
    airport_centroid = (51.148102, -0.190278)
    th1 = {'lat': airport_centroid[0] + 0.0005, 'lon': airport_centroid[1] - 0.0005}
    th2 = {'lat': airport_centroid[0] - 0.0005, 'lon': airport_centroid[1] + 0.0005}

# use only nearby ways to build graph
nearby_ways = ways_nearby(ways, airport_centroid[0], airport_centroid[1], radius_km=6.0)

# split ways into runways and taxiways; we will NOT allow taxiing along runway ways
nearby_runways = []
nearby_taxiways = []
for w in nearby_ways:
    tags = w.get('tags') or {}
    if tags.get('aeroway') == 'runway':
        nearby_runways.append(w)
    else:
        nearby_taxiways.append(w)

# build graph only from taxiway ways (no runway centerlines)
prev_lat = None
prev_lon = None
taxi_segments = []  # list of tuples (n1, n2, lat1, lon1, lat2, lon2, way_tags)
for w in nearby_taxiways:
    coords = w.get('coords', [])
    tags = w.get('tags') or {}
    if len(coords) < 2:
        continue
    prev = None
    for lat, lon in coords:
        nid = add_node(lat, lon)
        if prev is not None:
            d = haversine_km(prev_lat, prev_lon, lat, lon)
            # undirected
            edges[prev].append((nid, d))
            edges[nid].append((prev, d))
            taxi_segments.append((prev, nid, prev_lat, prev_lon, lat, lon, tags))
        prev = nid
        prev_lat, prev_lon = lat, lon

# helper to remove an undirected edge
def remove_edge(a, b):
    edges[a] = [(v, w) for (v, w) in edges.get(a, []) if v != b]
    edges[b] = [(v, w) for (v, w) in edges.get(b, []) if v != a]

# build edge_allowed map so we can honor one-way taxiways and later use per-edge tags
edge_allowed = {}
edge_tags = {}
for (u, v, lat1, lon1, lat2, lon2, tags) in taxi_segments:
    edge_allowed[(u, v)] = True
    edge_tags[(u, v)] = tags
    # allow reverse by default unless one-way declared
    allow_rev = True
    oneway = tags.get('oneway')
    if oneway in ('yes', 'true', '1'):
        allow_rev = False
    if allow_rev:
        edge_allowed[(v, u)] = True
        edge_tags[(v, u)] = tags
    else:
        edge_allowed[(v, u)] = False

# runway_exits will hold detected exit nodes (populated by two methods below)
runway_exits = {}

# segment intersection helper (x=lon, y=lat)
def seg_intersection(p1, p2, q1, q2):
    x1, y1 = p1[1], p1[0]
    x2, y2 = p2[1], p2[0]
    x3, y3 = q1[1], q1[0]
    x4, y4 = q2[1], q2[0]
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-12:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denom
    if t < -1e-9 or t > 1 + 1e-9 or u < -1e-9 or u > 1 + 1e-9:
        return None
    ix = x1 + t * (x2 - x1)
    iy = y1 + t * (y2 - y1)
    # return lat, lon
    return (iy, ix)

# detect intersections between taxi segments and runway segments and split taxi edges
runway_segments = []
for w in nearby_runways:
    coords = w.get('coords') or []
    for a, b in zip(coords, coords[1:]):
        runway_segments.append((a, b, w))

# For each taxi segment, check against runway segments
for (n1, n2, lat1, lon1, lat2, lon2, tags) in list(taxi_segments):
    p1 = (lat1, lon1); p2 = (lat2, lon2)
    for (r1, r2, rway) in runway_segments:
        inter = seg_intersection(p1, p2, r1, r2)
        if not inter:
            continue
        # add intersection node into graph
        in_lat, in_lon = inter
        in_nid = add_node(in_lat, in_lon)
        # remove original edge n1-n2 and replace with n1-in_nid, in_nid-n2
        # compute distances
        # ensure the original edge exists before removing
        remove_edge(n1, n2)
        d1 = haversine_km(nodes[n1]['lat'], nodes[n1]['lon'], in_lat, in_lon)
        d2 = haversine_km(in_lat, in_lon, nodes[n2]['lat'], nodes[n2]['lon'])
        edges[n1].append((in_nid, d1)); edges[in_nid].append((n1, d1))
        edges[in_nid].append((n2, d2)); edges[n2].append((in_nid, d2))
        # update edge_allowed/tags for new splits
        edge_allowed[(n1, in_nid)] = True; edge_tags[(n1, in_nid)] = tags
        edge_allowed[(in_nid, n1)] = True; edge_tags[(in_nid, n1)] = tags
        edge_allowed[(in_nid, n2)] = True; edge_tags[(in_nid, n2)] = tags
        edge_allowed[(n2, in_nid)] = True; edge_tags[(n2, in_nid)] = tags
        # record runway exit
        runway_exits.setdefault(id(rway), {'way': rway, 'exits': []})
        runway_exits[id(rway)]['exits'].append({'nid': in_nid, 'lat': in_lat, 'lon': in_lon})
        # there might be multiple intersections on same segment; continue checking

# Proximity-based exit detection
# If a taxi segment passes close to a runway segment (within PROX_EXIT_METERS),
# split the taxi segment at the closest point and record it as a runway exit.
PROX_EXIT_METERS = 30
PROX_EXIT_KM = PROX_EXIT_METERS / 1000.0

def _latlon_to_xy_km(lat, lon, ref_lat):
    # simple equirectangular projection to km using reference latitude
    R = 6371.0
    x = math.radians(lon) * math.cos(math.radians(ref_lat)) * R
    y = math.radians(lat) * R
    return x, y

def _closest_point_on_seg(p1, p2, q):
    # return closest point on segment p1-p2 to point q, all in (lat,lon)
    ref_lat = (p1[0] + p2[0] + q[0]) / 3.0
    x1, y1 = _latlon_to_xy_km(p1[0], p1[1], ref_lat)
    x2, y2 = _latlon_to_xy_km(p2[0], p2[1], ref_lat)
    xq, yq = _latlon_to_xy_km(q[0], q[1], ref_lat)
    dx = x2 - x1; dy = y2 - y1
    denom = dx*dx + dy*dy
    if denom == 0:
        t = 0.0
    else:
        t = ((xq - x1) * dx + (yq - y1) * dy) / denom
        t = max(0.0, min(1.0, t))
    xc = x1 + t * dx; yc = y1 + t * dy
    # convert back to lat/lon approx
    lat_c = math.degrees(yc / 6371.0)
    lon_c = math.degrees(xc / (6371.0 * math.cos(math.radians(ref_lat))))
    return (lat_c, lon_c), t

def _point_to_seg_dist_km(pt, a, b):
    # compute distance in km from point pt to segment a-b
    (c, _) = _closest_point_on_seg(a, b, pt)
    return haversine_km(pt[0], pt[1], c[0], c[1])

# iterate taxi segments and look for close approaches to runway segments
for (n1, n2, lat1, lon1, lat2, lon2, tags) in list(taxi_segments):
    # skip if the edge no longer exists (was split by intersection)
    if not any(v == n2 for (v, _) in edges.get(n1, [])):
        continue
    p1 = (lat1, lon1); p2 = (lat2, lon2)
    for (r1, r2, rway) in runway_segments:
        # already handled by exact intersection earlier
        if seg_intersection(p1, p2, r1, r2):
            continue
        # compute minimal distance between the two segments via endpoint projections
        # candidates: distance from taxi endpoints to runway segment, and projections of runway endpoints onto taxi seg
        d_p1 = _point_to_seg_dist_km(p1, r1, r2)
        d_p2 = _point_to_seg_dist_km(p2, r1, r2)
        # project runway endpoints onto taxi segment
        (proj_r1, t1) = _closest_point_on_seg(p1, p2, r1)
        (proj_r2, t2) = _closest_point_on_seg(p1, p2, r2)
        d_proj_r1 = haversine_km(proj_r1[0], proj_r1[1], r1[0], r1[1])
        d_proj_r2 = haversine_km(proj_r2[0], proj_r2[1], r2[0], r2[1])
        # choose minimum
        dmin = min(d_p1, d_p2, d_proj_r1, d_proj_r2)
        if dmin <= PROX_EXIT_KM:
            # pick point on taxi segment corresponding to the minimal candidate
            if dmin == d_proj_r1:
                close_pt = proj_r1
            elif dmin == d_proj_r2:
                close_pt = proj_r2
            elif dmin == d_p1:
                close_pt = p1
            else:
                close_pt = p2
            # avoid adding if a node already exists very close
            existing_nid = None
            existing_d = float('inf')
            for nid, n in enumerate(nodes):
                dtmp = haversine_km(close_pt[0], close_pt[1], n['lat'], n['lon'])
                if dtmp < existing_d:
                    existing_d = dtmp; existing_nid = nid
            if existing_d <= 0.00001:
                exit_nid = existing_nid
            else:
                exit_nid = add_node(close_pt[0], close_pt[1])
            # split edge n1-n2 at exit_nid if still present
            if any(v == n2 for (v, _) in edges.get(n1, [])):
                remove_edge(n1, n2)
                d1 = haversine_km(nodes[n1]['lat'], nodes[n1]['lon'], nodes[exit_nid]['lat'], nodes[exit_nid]['lon'])
                d2 = haversine_km(nodes[exit_nid]['lat'], nodes[exit_nid]['lon'], nodes[n2]['lat'], nodes[n2]['lon'])
                edges[n1].append((exit_nid, d1)); edges[exit_nid].append((n1, d1))
                edges[exit_nid].append((n2, d2)); edges[n2].append((exit_nid, d2))
                # copy tags/permissions
                edge_allowed[(n1, exit_nid)] = True; edge_tags[(n1, exit_nid)] = tags
                edge_allowed[(exit_nid, n1)] = True; edge_tags[(exit_nid, n1)] = tags
                edge_allowed[(exit_nid, n2)] = True; edge_tags[(exit_nid, n2)] = tags
                edge_allowed[(n2, exit_nid)] = True; edge_tags[(n2, exit_nid)] = tags
            # record runway exit
            runway_exits.setdefault(id(rway), {'way': rway, 'exits': []})
            runway_exits[id(rway)]['exits'].append({'nid': exit_nid, 'lat': nodes[exit_nid]['lat'], 'lon': nodes[exit_nid]['lon']})
            # stop checking this taxi segment against other runway segments
            break
# load gates and pick best gate by heuristic
with gzip.open(GATE_CACHE, 'rt') as f:
    gc = json.load(f)
gates = gc.get('gates', [])

# pick gate closest to airport centroid from GEOJSON arrival_full or from known coords
gj = json.loads(GEOJSON.read_text())
arrival_feat = None
for feat in gj.get('features', []):
    if (feat.get('properties') or {}).get('segment') == 'arrival_full':
        arrival_feat = feat; break
if arrival_feat and arrival_feat.get('geometry') and arrival_feat['geometry'].get('coordinates'):
    arr_coords = arrival_feat['geometry']['coordinates']
    airport_centroid = {'lat': arr_coords[-1][1], 'lon': arr_coords[-1][0]}
else:
    airport_centroid = {'lat': 51.148102, 'lon': -0.190278}

def gate_score(g):
    # prefer explicit gate nodes (tag aeroway=gate), then apron, then proximity
    tags = g.get('tags') or {}
    score = 0
    if tags.get('aeroway') == 'gate':
        score -= 1000
    if tags.get('aeroway') == 'apron':
        score -= 500
    # penalty distance
    d = haversine_km(airport_centroid['lat'], airport_centroid['lon'], g.get('lat'), g.get('lon'))
    score += d
    return score

# find runway threshold: arrival_runway first coord
run_thresh = None
for feat in gj.get('features', []):
    if (feat.get('properties') or {}).get('segment') == 'arrival_runway':
        coords = feat.get('geometry', {}).get('coordinates')
        if coords:
            # take last point of runway rollout as threshold
            run_thresh = {'lon': coords[-1][0], 'lat': coords[-1][1]}
            break
if not run_thresh:
    # fallback from arrival_full first coordinate
    if arrival_feat and arrival_feat.get('geometry') and arrival_feat['geometry'].get('coordinates'):
        run_thresh = {'lon': arrival_feat['geometry']['coordinates'][0][0], 'lat': arrival_feat['geometry']['coordinates'][0][1]}
    else:
        run_thresh = {'lat': 51.1506619, 'lon': -0.1720282}

# find nearest graph node function
def nearest_node(lat, lon):
    best = None; bd = float('inf')
    for nid, n in enumerate(nodes):
        d = haversine_km(lat, lon, n['lat'], n['lon'])
        if d < bd:
            bd = d; best = nid
    return best

# find start node (nearest to runway threshold). Try both thresholds and pick the one
# that's connected to the taxiway graph component.
start = None
start_candidates = []
for cand in (th1, th2, run_thresh):
    try:
        nid = nearest_node(cand['lat'], cand['lon'])
        start_candidates.append((cand, nid))
    except Exception:
        continue

# pick the candidate whose node is present in the graph and in the largest reachable component
for cand, nid in start_candidates:
    if nid in nodes and nid is not None:
        start = nid
        break
if start is None:
    start = nearest_node(run_thresh['lat'], run_thresh['lon'])
    if start is None:
        raise SystemExit('Could not find graph node for threshold')

# compute reachable component from start
q = deque([start])
reachable = {start}
while q:
    u = q.popleft()
    for v,_ in edges.get(u, []):
        if v not in reachable:
            reachable.add(v); q.append(v)

# choose best gate whose nearest graph node is reachable
best_gate = None
best_score = float('inf')
best_gate_node = None
for g in gates:
    g_lat = g.get('lat'); g_lon = g.get('lon')
    if g_lat is None or g_lon is None:
        continue
    nid = nearest_node(g_lat, g_lon)
    if nid is None:
        continue
    score = gate_score(g)
    # small bias towards gates closer to runway threshold in graph-distance
    nd = haversine_km(nodes[nid]['lat'], nodes[nid]['lon'], run_thresh['lat'], run_thresh['lon'])
    score += nd * 0.1
    # prefer reachable nodes by small bonus
    if nid in reachable:
        score -= 0.5
    if score < best_score:
        best_score = score; best_gate = g; best_gate_node = nid

if best_gate is None:
    raise SystemExit('No gates with coordinates in cache')

gate_lat = best_gate.get('lat')
gate_lon = best_gate.get('lon')

# snap gate to nearest taxiway node
def nearest_node_with_dist(lat, lon):
    best = None
    bd = float('inf')
    for nid, n in enumerate(nodes):
        d = haversine_km(lat, lon, n['lat'], n['lon'])
        if d < bd:
            bd = d; best = nid
    return best, bd

gate_nid, gate_nd = nearest_node_with_dist(gate_lat, gate_lon)
if gate_nid is None:
    raise SystemExit('Could not snap gate to taxiway nodes')

# Constrained shortest path finder (accounts for turn-angle constraints and one-way edges)
def turn_angle(prev_nid, cur_nid, next_nid):
    # return absolute turn angle in degrees between vector prev->cur and cur->next
    if prev_nid is None:
        return 0.0
    a = nodes[prev_nid]
    b = nodes[cur_nid]
    c = nodes[next_nid]
    # approximate local projection: scale lon by cos(lat)
    lat_scale = math.cos(math.radians(b['lat']))
    v1x = (b['lon'] - a['lon']) * lat_scale
    v1y = (b['lat'] - a['lat'])
    v2x = (c['lon'] - b['lon']) * lat_scale
    v2y = (c['lat'] - b['lat'])
    # compute angle
    dot = v1x * v2x + v1y * v2y
    mag1 = math.hypot(v1x, v1y); mag2 = math.hypot(v2x, v2y)
    if mag1 == 0 or mag2 == 0:
        return 0.0
    cosang = max(-1.0, min(1.0, dot / (mag1 * mag2)))
    ang = math.degrees(math.acos(cosang))
    return ang

def constrained_shortest_path(start_nid, goal_nid, max_turn_deg=150.0):
    # state: (cost, cur, prev)
    pq = [(0.0, start_nid, None)]
    best = {(start_nid, None): 0.0}
    parent = {}
    while pq:
        cost, cur, prev_n = heapq.heappop(pq)
        if cost != best.get((cur, prev_n), None):
            continue
        if cur == goal_nid:
            # reconstruct path from (cur, prev_n)
            path = [cur]
            state = (cur, prev_n)
            while state in parent:
                pstate = parent[state]
                path.append(pstate[0])
                state = pstate
            path.reverse()
            return path
        for (nbr, wgt) in edges.get(cur, []):
            # enforce edge allowed
            if not edge_allowed.get((cur, nbr), True):
                continue
            # forbid immediate reversal (no three-point turns)
            if prev_n is not None and nbr == prev_n:
                continue
            ang = turn_angle(prev_n, cur, nbr)
            if ang > max_turn_deg:
                continue
            ncost = cost + wgt + (ang * 0.01)
            state = (nbr, cur)
            if ncost < best.get(state, float('inf')):
                best[state] = ncost
                parent[state] = (cur, prev_n)
                heapq.heappush(pq, (ncost, nbr, cur))
    return None

# collect runway threshold coordinates from nearby runway ways
def way_length_km(coords):
    total = 0.0
    for a, b in zip(coords, coords[1:]):
        total += haversine_km(a[0], a[1], b[0], b[1])
    return total

MIN_RUNWAY_KM = 1.5  # ignore very short 'runways' that are not main runways
thresholds = []
for w in nearby_runways:
    tags = w.get('tags') or {}
    coords = w.get('coords') or []
    if len(coords) < 2:
        continue
    length_km = way_length_km(coords)
    if length_km < MIN_RUNWAY_KM:
        # skip short or non-main runways (e.g., small strips)
        continue
    # endpoints as thresholds
    thresholds.append({'lat': coords[0][0], 'lon': coords[0][1], 'way': w, 'length_km': length_km, 'coords': coords, 'endpoint': 'start'})
    thresholds.append({'lat': coords[-1][0], 'lon': coords[-1][1], 'way': w, 'length_km': length_km, 'coords': coords, 'endpoint': 'end'})

# detect runway exits: taxiway nodes that coincide with runway coords
runway_exits = {}
for w in nearby_runways:
    coords = w.get('coords') or []
    # precompute cumulative distances along runway
    cum = [0.0]
    for a, b in zip(coords, coords[1:]):
        cum.append(cum[-1] + haversine_km(a[0], a[1], b[0], b[1]))
    exits = []
    for idx, (lat, lon) in enumerate(coords):
        key = (round(lat, 7), round(lon, 7))
        if key in node_index:
            nid = node_index[key]
            exits.append({'idx': idx, 'nid': nid, 'lat': lat, 'lon': lon, 'dist': cum[idx]})
    if exits:
        runway_exits[id(w)] = {'way': w, 'coords': coords, 'cumdist': cum, 'exits': exits}

# dedupe thresholds by rounded coords
seen_th = set()
uniq_thresholds = []
for t in thresholds:
    key = (round(t['lat'], 6), round(t['lon'], 6))
    if key in seen_th:
        continue
    seen_th.add(key)
    uniq_thresholds.append(t)

# determine which threshold we likely landed on using arrival runway info (run_thresh)
landed_threshold_idx = None
if run_thresh:
    best_d = float('inf')
    for ii, t in enumerate(uniq_thresholds):
        d = haversine_km(run_thresh['lat'], run_thresh['lon'], t['lat'], t['lon'])
        if d < best_d:
            best_d = d; landed_threshold_idx = ii
    # if the best match is farther than 0.2 km it's probably not a direct match; unset
    if best_d > 0.2:
        landed_threshold_idx = None

features = []

# For each threshold, build a path (snap threshold to nearest taxiway node, then follow prev to gate)
for i, t in enumerate(uniq_thresholds):
    # We are landing on the runway: enforce directional exit rules.
    # If endpoint is 'start' we assume landing travel was from end->start, so the aircraft
    # will leave the runway heading towards the 'start' direction; conversely for 'end'.
    # To enforce this, prefer taxi nodes that are located in that half-space forward of the
    # threshold along the runway vector.
    th_nid, th_d = nearest_node_with_dist(t['lat'], t['lon'])
    if th_nid is None:
        continue
    # Prefer real runway exits if available and downstream along landing roll
    snapped_th_nid = None
    th_coord_key = (round(t['lat'], 7), round(t['lon'], 7))
    if id(t['way']) in runway_exits:
        info = runway_exits[id(t['way'])]
        # find exits downstream of threshold (based on cumdist)
        # determine threshold index along way
        coords = info['coords']
        thr_idx = 0
        for j, (latj, lonj) in enumerate(coords):
            if round(latj, 7) == round(t['lat'], 7) and round(lonj, 7) == round(t['lon'], 7):
                thr_idx = j; break
        # choose nearest exit downstream (if endpoint == 'start', downstream means increasing idx)
        candidate = None
        best_dd = float('inf')
        for ex in info['exits']:
            ex_idx = ex['idx']
            if t.get('endpoint') == 'start' and ex_idx >= thr_idx:
                dd = ex['dist'] - info['cumdist'][thr_idx]
            elif t.get('endpoint') == 'end' and ex_idx <= thr_idx:
                dd = info['cumdist'][thr_idx] - ex['dist']
            else:
                continue
            if dd >= 0 and dd < best_dd:
                best_dd = dd; candidate = ex
        if candidate:
            snapped_th_nid = candidate['nid']
    if snapped_th_nid is None:
        # directional snap: compute runway vector and prefer nodes forward of threshold
        coords = t.get('coords') or []
        if len(coords) >= 2:
            if t.get('endpoint') == 'start':
                runway_vec = (coords[1][0] - coords[0][0], coords[1][1] - coords[0][1])
            else:
                runway_vec = (coords[-2][0] - coords[-1][0], coords[-2][1] - coords[-1][1])
        else:
            runway_vec = None

        # find nearest taxi node in the forward half-space if possible
        snapped_th_nid = None
        snapped_th_d = float('inf')
        for nid, n in enumerate(nodes):
            # vector from threshold to node
            vx = n['lat'] - t['lat']
            vy = n['lon'] - t['lon']
            if runway_vec:
                dot = vx * runway_vec[0] + vy * runway_vec[1]
                if dot < 0:
                    # node is behind threshold relative to landing direction; skip
                    continue
            d = haversine_km(t['lat'], t['lon'], n['lat'], n['lon'])
            if d < snapped_th_d:
                snapped_th_d = d; snapped_th_nid = nid
        if snapped_th_nid is None:
            # fall back to closest node regardless of direction
            snapped_th_nid, snapped_th_d = nearest_node_with_dist(t['lat'], t['lon'])
        if snapped_th_nid is None:
            continue
    # compute constrained path from threshold to gate (enforcing turn constraints and one-way)
    path_nodes = constrained_shortest_path(snapped_th_nid, gate_nid)
    if path_nodes is None:
        # try a relaxed search: allow starting from nearby taxi nodes within 200m and prepend connector
        fallback = None
        max_search_km = 0.2
        nearest_candidates = []
        for nid, n in enumerate(nodes):
            d = haversine_km(nodes[snapped_th_nid]['lat'], nodes[snapped_th_nid]['lon'], n['lat'], n['lon'])
            if d <= max_search_km:
                nearest_candidates.append((d, nid))
        nearest_candidates.sort()
        for _, cand in nearest_candidates:
            p = constrained_shortest_path(cand, gate_nid)
            if p:
                # prepend connector from snapped_th_nid to cand
                fallback = [snapped_th_nid] + p
                break
        if fallback:
            path_nodes = fallback
        else:
            # no path found; skip this threshold
            continue

    # convert to coordinates lon,lat
    path_coords = [[nodes[n]['lon'], nodes[n]['lat']] for n in path_nodes]
    # attach runway ref/name info if available
    runway_ref = None
    runway_name = None
    try:
        runway_ref = (t.get('way') or {}).get('tags', {}).get('ref')
        runway_name = (t.get('way') or {}).get('tags', {}).get('name')
    except Exception:
        runway_ref = runway_ref
    props = {'segment': f'taxi_from_threshold_{i}', 'threshold_idx': i}
    if runway_ref:
        props['runway_ref'] = runway_ref
    if runway_name:
        props['runway_name'] = runway_name
    if landed_threshold_idx is not None and i == landed_threshold_idx:
        props['landed'] = True
    features.append({
        'type': 'Feature',
        'properties': props,
        'geometry': {'type': 'LineString', 'coordinates': path_coords}
    })
    # include threshold point
    th_props = {'segment': 'runway_threshold', 'threshold_idx': i}
    if landed_threshold_idx is not None and i == landed_threshold_idx:
        th_props['landed'] = True
        if runway_ref:
            th_props['runway_ref'] = runway_ref
        if runway_name:
            th_props['runway_name'] = runway_name
    features.append({
        'type': 'Feature',
        'properties': th_props,
        'geometry': {'type': 'Point', 'coordinates': [t['lon'], t['lat']]}
    })

# include snapped gate point
features.append({
    'type': 'Feature',
    'properties': {'segment': 'gate_point', 'snapped_to_node': gate_nid},
    'geometry': {'type': 'Point', 'coordinates': [nodes[gate_nid]['lon'], nodes[gate_nid]['lat']]}
})

fc = {'type': 'FeatureCollection', 'features': features}
OUT_GEO.write_text(json.dumps(fc))
print('Wrote', OUT_GEO, 'thresholds:', len(uniq_thresholds))
