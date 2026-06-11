#!/usr/bin/env python3
"""Render only the actual arrival segments from the route geojson; exclude synthetic taxi/departure features.

This produces assets/py/Rail Planner/ui/static_routes/bcn_lgw_arrival_actual_map.png
"""
from pathlib import Path
import gzip
import json
import math
import matplotlib.pyplot as plt

BASE = Path('assets/py/Rail Planner/ui')
GEOJSON = BASE / 'static_routes' / 'bcn_lgw.geojson'
RUNWAY_CACHE = BASE / 'data' / 'runways.great-britain-latest.json.gz'
OUT = BASE / 'static_routes' / 'bcn_lgw_arrival_actual_map.png'

if not GEOJSON.exists():
    raise SystemExit('Missing route geojson; run scripts/test_flight_route.py first')
if not RUNWAY_CACHE.exists():
    raise SystemExit('Missing runway cache; extract runways.great-britain-latest.json.gz first')

def hav(a_lat, a_lon, b_lat, b_lon):
    R = 6371.0
    dlat = math.radians(b_lat - a_lat)
    dlon = math.radians(b_lon - a_lon)
    lat1 = math.radians(a_lat); lat2 = math.radians(b_lat)
    aa = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(aa), math.sqrt(1-aa))

data = json.loads(GEOJSON.read_text())
features = data.get('features', [])

# Helper to select arrival features that are NOT synthetic and not 'arrival_taxi'
def is_actual_arrival(f):
    props = f.get('properties') or {}
    seg = props.get('segment')
    if not seg:
        return False
    if not seg.startswith('arrival'):
        return False
    if seg == 'arrival_taxi':
        return False
    # exclude features explicitly flagged as synthetic
    if props.get('synthetic'):
        return False
    return True

arrival_feats = [f for f in features if is_actual_arrival(f)]

# load runway/taxiway ways for context
with gzip.open(RUNWAY_CACHE, 'rt') as f:
    rc = json.load(f)
ways = rc.get('ways', [])

# determine centroid from nearby ways (simple average)
all_lons = []
all_lats = []
for w in ways:
    for lat, lon in w.get('coords', []):
        all_lons.append(lon); all_lats.append(lat)
if all_lons:
    centroid_lon = sum(all_lons) / len(all_lons)
    centroid_lat = sum(all_lats) / len(all_lats)
else:
    centroid_lat, centroid_lon = 51.148102, -0.190278

fig, ax = plt.subplots(figsize=(10, 6))

# plot runway/taxiway in light grey for context
for w in ways:
    coords = w.get('coords', [])
    lons = [c[1] for c in coords]
    lats = [c[0] for c in coords]
    ax.plot(lons, lats, color='#dddddd', linewidth=0.9, zorder=1)

# plotting styles
styles = {
    'arrival_approach': {'color': '#6a1b9a', 'lw': 2.6, 'label': 'Approach'},
    'arrival_runway': {'color': '#000000', 'lw': 3.2, 'label': 'Runway rollout'},
    'arrival_turn': {'color': '#2e7d32', 'lw': 2.6, 'label': 'Turn-off'},
    'arrival_full': {'color': '#1976d2', 'lw': 2.6, 'label': 'Arrival (full)'}
}

# Plot arrival features only, split by segment type and compute lengths for diagnostics
diag = []
for f in arrival_feats:
    props = f.get('properties') or {}
    seg = props.get('segment')
    geom = f.get('geometry')
    if not geom:
        continue
    coords = geom.get('coordinates')
    if not coords:
        continue
    if geom.get('type') == 'LineString':
        # deduplicate consecutive identical coords
        deduped = [coords[0]]
        for pt in coords[1:]:
            if pt[0] != deduped[-1][0] or pt[1] != deduped[-1][1]:
                deduped.append(pt)
        coords = deduped

        # coords are [lon, lat]
        # If approach is very long, clip to last 5 km for visual clarity
        if seg == 'arrival_approach':
            total_len = 0.0
            clip_end = len(coords)
            for i in range(len(coords)-2, -1, -1):
                a, b = coords[i], coords[i+1]
                total_len += hav(a[1], a[0], b[1], b[0])
                if total_len > 5.0:
                    clip_end = i
                    break
            coords = coords[clip_end:]

        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        # compute length
        length_km = 0.0
        for a, b in zip(coords, coords[1:]):
            length_km += hav(a[1], a[0], b[1], b[0])
        diag.append((seg, length_km, coords[0], coords[-1]))
        s = styles.get(seg, {'color': '#444444', 'lw': 1.6, 'label': seg})
        ax.plot(lons, lats, color=s['color'], linewidth=s['lw'], zorder=5, label=s.get('label'))
        # mark endpoints
        ax.scatter([lons[0]], [lats[0]], color=s['color'], s=20, zorder=6)
        ax.scatter([lons[-1]], [lats[-1]], color=s['color'], marker='s', s=20, zorder=6)
    elif geom.get('type') == 'Point':
        lon, lat = coords
        ax.scatter([lon], [lat], color='#000000', s=30, zorder=6)

# print diagnostics for arrival segments
print('\nArrival segment diagnostics:')
for seg, length_km, start, end in diag:
    print(f" - {seg}: length_km={length_km:.3f} start={start} end={end}")
    # warn if unexpectedly long (likely full-GC included)
    if length_km > 50.0:
        print(f"   WARNING: {seg} is very long (>50 km). It may include long-range great-circle points (not local approach).")

# compute bbox around arrival features for tight zoom
all_lons = []
all_lats = []
for f in arrival_feats:
    geom = f.get('geometry')
    if not geom:
        continue
    if geom.get('type') == 'LineString':
        for lon, lat in geom.get('coordinates'):
            all_lons.append(lon); all_lats.append(lat)
    elif geom.get('type') == 'Point':
        lon, lat = geom.get('coordinates')
        all_lons.append(lon); all_lats.append(lat)

if not all_lons:
    min_lon = centroid_lon - 0.02; max_lon = centroid_lon + 0.02
    min_lat = centroid_lat - 0.02; max_lat = centroid_lat + 0.02
else:
    min_lon = min(all_lons); max_lon = max(all_lons)
    min_lat = min(all_lats); max_lat = max(all_lats)

pad_lon = max(0.001, (max_lon - min_lon) * 0.12)
pad_lat = max(0.001, (max_lat - min_lat) * 0.12)
ax.set_xlim(min_lon - pad_lon, max_lon + pad_lon)
ax.set_ylim(min_lat - pad_lat, max_lat + pad_lat)
ax.set_aspect('equal', adjustable='box')

ax.set_xlabel('Longitude')
ax.set_ylabel('Latitude')
ax.set_title('Gatwick — actual arrival segments (non-synthetic)')
ax.legend(loc='upper right')
fig.tight_layout()
OUT.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT, dpi=200)
print('Wrote', OUT)
