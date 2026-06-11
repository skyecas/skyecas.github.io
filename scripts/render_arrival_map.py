#!/usr/bin/env python3
"""Render Gatwick airport map from local runway cache and overlay arrival segments.

This avoids external tile servers; it plots runway/taxiway ways extracted from the
local PBF cache and overlays the approach/runway/turn/taxi segments in distinct colours.
"""
from pathlib import Path
import gzip
import json
import math
import random
import matplotlib.pyplot as plt
from importlib.util import spec_from_file_location, module_from_spec

# load flight_osm helpers dynamically
spec = spec_from_file_location('flight_osm', str(Path('assets/py/Rail Planner/ui/flight_osm.py').resolve()))
flight_osm = module_from_spec(spec)  # type: ignore
spec.loader.exec_module(flight_osm)  # type: ignore


def haversine_km(a_lat, a_lon, b_lat, b_lon):
    R = 6371.0
    dlat = math.radians(b_lat - a_lat)
    dlon = math.radians(b_lon - a_lon)
    lat1 = math.radians(a_lat)
    lat2 = math.radians(b_lat)
    aa = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(aa), math.sqrt(1-aa))


BASE = Path('assets/py/Rail Planner/ui')
GEOJSON = BASE / 'static_routes' / 'bcn_lgw.geojson'
RUNWAY_CACHE = BASE / 'data' / 'runways.great-britain-latest.json.gz'
OUT = BASE / 'static_routes' / 'bcn_lgw_arrival_map.png'

if not GEOJSON.exists():
    raise SystemExit('Missing route geojson; run scripts/test_flight_route.py first')
if not RUNWAY_CACHE.exists():
    raise SystemExit('Missing runway cache; extract runways.great-britain-latest.json.gz first')

data = json.loads(GEOJSON.read_text())
features = data.get('features', [])

def find_feature(seg):
    for f in features:
        props = f.get('properties') or {}
        if props.get('segment') == seg:
            return f
    return None

approach = find_feature('arrival_approach')
runway = find_feature('arrival_runway')
turn = find_feature('arrival_turn')
taxi = find_feature('arrival_taxi')
arrival_full = find_feature('arrival_full') or find_feature('arrival')

# Try to load computed taxi graph path and plot it if present
TAXI_GEO = BASE / 'static_routes' / 'bcn_lgw_taxi.geojson'
taxi_graph = None
if TAXI_GEO.exists():
    try:
        taxi_graph = json.loads(TAXI_GEO.read_text())
    except Exception:
        taxi_graph = None

with gzip.open(RUNWAY_CACHE, 'rt') as f:
    rc = json.load(f)
ways = rc.get('ways', [])

# First filter runway ways within 6 km of known Gatwick coordinates so we have
# a local subset to compute a centroid from. This avoids a circular dependency.
known_lat, known_lon = 51.148102, -0.190278
near = []
for w in ways:
    coords = w.get('coords', [])
    for (lat, lon) in coords:
        d = haversine_km(known_lat, known_lon, lat, lon)
        if d <= 6.0:
            near.append(w)
            break

# determine Gatwick centroid from the nearby runway/taxiway ways bounding box
all_way_lons = []
all_way_lats = []
for w in near:
    for lat, lon in w.get('coords', []):
        all_way_lons.append(lon); all_way_lats.append(lat)
if all_way_lons:
    centroid_lon = sum(all_way_lons) / len(all_way_lons)
    centroid_lat = sum(all_way_lats) / len(all_way_lats)
else:
    # fallback to LGW known coordinates
    centroid_lat, centroid_lon = known_lat, known_lon

fig, ax = plt.subplots(figsize=(8, 8))

# Plot runway/taxiway ways (thin grey lines)
for w in near:
    coords = w.get('coords', [])
    lons = [c[1] for c in coords]
    lats = [c[0] for c in coords]
    ax.plot(lons, lats, color='#666666', linewidth=1.2, zorder=1)

# helper to plot segment feature
def plot_feature(feat, color, lw=2, z=3, label=None):
    if not feat or not feat.get('geometry'):
        return
    coords = feat['geometry']['coordinates']
    if not coords:
        return
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    ax.plot(lons, lats, color=color, linewidth=lw, zorder=z, label=label)

# Plot each segment with distinct colours
plot_feature(approach, '#6a1b9a', lw=2.4, z=4, label='Approach')
plot_feature(runway, '#000000', lw=3.0, z=5, label='Runway rollout')
plot_feature(turn, '#2e7d32', lw=2.4, z=6, label='Turn-off')
plot_feature(taxi, '#ff8f00', lw=2.4, z=6, label='Taxi to gate')

# plot taxi graph paths if available (one per threshold)
if taxi_graph and taxi_graph.get('features'):
    # collect threshold and path features separately
    path_feats = [f for f in taxi_graph['features'] if (f.get('properties') or {}).get('segment', '').startswith('taxi_from_threshold_')]
    thresh_feats = [f for f in taxi_graph['features'] if (f.get('properties') or {}).get('segment') == 'runway_threshold']
    gate_feat = next((f for f in taxi_graph['features'] if (f.get('properties') or {}).get('segment') == 'gate_point'), None)

    # plot each threshold path with a distinct colour
    colours = ['#d32f2f', '#c2185b', '#7b1fa2', '#1976d2', '#0097a7', '#388e3c', '#f57c00', '#455a64']

    # determine landed threshold from arrival_runway feature (preferred) or from taxi feature props
    landed_idx = None
    # prefer arrival_runway from route geojson
    if runway and runway.get('geometry') and runway['geometry'].get('coordinates'):
        # use last coordinate as the touchdown/threshold
        rr_coords = runway['geometry']['coordinates']
        runway_thr = (rr_coords[-1][1], rr_coords[-1][0])  # lat, lon
        # find nearest threshold feature by comparing coords and use its threshold_idx prop
        best_d = float('inf')
        best_tid = None
        for f in thresh_feats:
            geom = f.get('geometry')
            props = f.get('properties') or {}
            if not geom or geom.get('type') != 'Point':
                continue
            lon, lat = geom.get('coordinates')
            d = haversine_km(runway_thr[0], runway_thr[1], lat, lon)
            if d < best_d:
                best_d = d; best_tid = props.get('threshold_idx')
        # if nearest is too far, discard
        if best_d <= 0.25:
            try:
                landed_idx = int(best_tid)
            except Exception:
                landed_idx = best_tid
    else:
        # fallback: check taxi_graph props for landed flag
        for f in taxi_graph['features']:
            props = (f.get('properties') or {})
            if props.get('segment') == 'runway_threshold' and props.get('landed'):
                try:
                    landed_idx = int(props.get('threshold_idx'))
                except Exception:
                    landed_idx = props.get('threshold_idx')
                break

    # If we have a landed threshold, highlight only that path; dim the others
    for i, f in enumerate(path_feats):
        geom = f.get('geometry')
        if not geom or geom.get('type') != 'LineString':
            continue
        coords = geom.get('coordinates')
        if not coords:
            continue
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        col = colours[i % len(colours)]
        # decide styling depending on landed detection
        props = f.get('properties') or {}
        tidx = props.get('threshold_idx')
        if landed_idx is None:
            # no landed info; show all prominently
            ax.plot(lons, lats, color=col, linewidth=3.4, zorder=8, label=props.get('segment'))
            highlight = True
        else:
            if tidx == landed_idx:
                ax.plot(lons, lats, color=col, linewidth=4.6, zorder=9, label=props.get('segment'))
                highlight = True
            else:
                # dim others
                ax.plot(lons, lats, color='#bbbbbb', linewidth=1.0, zorder=6, alpha=0.4)
                highlight = False

        # mark endpoints and annotate only for highlighted path
        if highlight and len(coords) >= 2:
            sx, sy = coords[0][0], coords[0][1]
            ex, ey = coords[-1][0], coords[-1][1]
            ax.scatter([sx], [sy], color=col, marker='o', s=36, zorder=10)
            ax.scatter([ex], [ey], color=col, marker='s', s=36, zorder=10)
            mid_idx = len(coords) // 2
            mx, my = coords[mid_idx][0], coords[mid_idx][1]
            ax.text(mx, my, props.get('segment', ''), fontsize=8, color=col, zorder=11)

    # plot thresholds and label them; highlight landed threshold if present
    for idx, f in enumerate(thresh_feats):
        geom = f.get('geometry')
        if not geom or geom.get('type') != 'Point':
            continue
        lon, lat = geom.get('coordinates')
        props = f.get('properties') or {}
        if landed_idx is not None and idx == landed_idx:
            ax.scatter([lon], [lat], color='#000000', s=80, zorder=14, marker='X')
            # annotate runway ref/name if available
            ref = props.get('runway_ref') or props.get('runway_name')
            label = f"Landed: T{idx}"
            if ref:
                label += f" ({ref})"
            ax.text(lon + 0.00008, lat + 0.00008, label, fontsize=9, zorder=15, weight='bold', color='#000000')
        else:
            # dim non-landed thresholds
            ax.scatter([lon], [lat], color='#666666', s=28, zorder=11, marker='X')
            ax.text(lon + 0.00012, lat + 0.00012, f"T{idx}", fontsize=8, zorder=12, color='#666666')

    # plot snapped gate point
    if gate_feat:
        lon, lat = gate_feat.get('geometry', {}).get('coordinates')
        ax.scatter([lon], [lat], color='cyan', s=56, zorder=13, label='Gate (snapped)')

# choose a gate approximation: prefer taxiway nodes close to the airport centroid
taxi_nodes = []
for w in near:
    # our runway cache only contains runway/taxiway ways; treat all nodes as candidates
    for lat, lon in w.get('coords', []):
        d = haversine_km(centroid_lat, centroid_lon, lat, lon)
        if d <= 0.8:  # within 800m of centroid
            taxi_nodes.append((lat, lon, d))
gate_candidates = []
# Try to load gate cache extracted from PBF (if present)
gate_cache = Path('assets/py/Rail Planner/ui/data/gates.great-britain-latest.json.gz')
if gate_cache.exists() and hasattr(flight_osm, 'load_gate_cache'):
    gate_candidates = flight_osm.load_gate_cache(gate_cache)

if not gate_candidates:
    # Fall back to picking taxiway nodes as before
    taxi_nodes = []
    for w in near:
        for lat, lon in w.get('coords', []):
            d = haversine_km(centroid_lat, centroid_lon, lat, lon)
            if d <= 0.8:
                taxi_nodes.append((lat, lon, d))
    if taxi_nodes:
        taxi_nodes.sort(key=lambda x: x[2])
        lat0, lon0, _ = taxi_nodes[0]
        jitter = 0.00008
        gate_lat = lat0 + (random.random() - 0.5) * jitter
        gate_lon = lon0 + (random.random() - 0.5) * jitter
    else:
        gate_lat = centroid_lat + 0.0003
        gate_lon = centroid_lon + 0.0003
else:
    # choose the gate feature closest to centroid
    best = None
    best_d = float('inf')
    for g in gate_candidates:
        d = haversine_km(centroid_lat, centroid_lon, g.get('lat'), g.get('lon'))
        if d < best_d:
            best_d = d; best = g
    if best:
        gate_lat = best.get('lat')
        gate_lon = best.get('lon')
    else:
        gate_lat = centroid_lat + 0.0003
        gate_lon = centroid_lon + 0.0003

# airport markers
# remove centroid and random gate markers; use snapped gate from taxi_graph instead
# find threshold in runway feature (first point)
if runway and runway.get('geometry') and runway['geometry'].get('coordinates'):
    rc0 = runway['geometry']['coordinates'][0]
    ax.scatter([rc0[0]], [rc0[1]], color='black', s=50, zorder=11, label='Runway threshold')

# tight bbox around plotted runway ways and arrival
all_lons = []
all_lats = []
for w in near:
    for lat, lon in w.get('coords', []):
        all_lons.append(lon); all_lats.append(lat)
for f in (approach, runway, turn, taxi):
    if f and f.get('geometry') and f['geometry'].get('coordinates'):
        for lon, lat in f['geometry']['coordinates']:
            all_lons.append(lon); all_lats.append(lat)

if not all_lons:
    # fallback to centroid +/- small box
    min_lon = centroid_lon - 0.02; max_lon = centroid_lon + 0.02
    min_lat = centroid_lat - 0.02; max_lat = centroid_lat + 0.02
else:
    min_lon = min(all_lons); max_lon = max(all_lons)
    min_lat = min(all_lats); max_lat = max(all_lats)

pad_lon = max(0.002, (max_lon - min_lon) * 0.12)
pad_lat = max(0.002, (max_lat - min_lat) * 0.12)
ax.set_xlim(min_lon - pad_lon, max_lon + pad_lon)
ax.set_ylim(min_lat - pad_lat, max_lat + pad_lat)
# Ensure equal axis scaling so degrees lon/lat draw with same scale visually
ax.set_aspect('equal', adjustable='box')

ax.set_xlabel('Longitude')
ax.set_ylabel('Latitude')
ax.set_title('Gatwick Airport — arrival segments over local runway/taxiway map')
ax.legend(loc='upper right')
fig.tight_layout()
OUT.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT, dpi=200)
print('Wrote', OUT)
