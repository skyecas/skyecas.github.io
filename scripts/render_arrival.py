#!/usr/bin/env python3
from pathlib import Path
import json
import matplotlib.pyplot as plt

GEOJSON = Path('assets/py/Rail Planner/ui/static_routes/bcn_lgw.geojson')
OUT = Path('assets/py/Rail Planner/ui/static_routes/bcn_lgw_arrival.png')

if not GEOJSON.exists():
    raise SystemExit(f'GeoJSON not found: {GEOJSON}')

data = json.loads(GEOJSON.read_text())
features = data.get('features', [])
if not features:
    raise SystemExit('No features')

arrival = None
meta = None
arrival_approach = None
arrival_runway = None
arrival_turn = None
arrival_taxi = None
for f in features:
    props = f.get('properties') or {}
    seg = props.get('segment')
    if seg == 'arrival_full' or seg == 'arrival':
        arrival = f
    if seg == 'arrival_approach':
        arrival_approach = f
    if seg == 'arrival_runway':
        arrival_runway = f
    if seg == 'arrival_turn':
        arrival_turn = f
    if seg == 'arrival_taxi':
        arrival_taxi = f
    if props and ('dep_meta' in props or 'arr_meta' in props):
        meta = props

if not arrival:
    raise SystemExit('Arrival feature not found')

coords = arrival['geometry']['coordinates']
if not coords:
    raise SystemExit('Arrival has no coordinates')

lons = [c[0] for c in coords]
lats = [c[1] for c in coords]

# extract airport centroid and takeoff_end if available
dest = None
takeoff_end = None
if meta and 'arr_meta' in meta:
    arr_meta = meta['arr_meta']
    takeoff_end = arr_meta.get('takeoff_end')

# dest is last point of arrival feature
dest = coords[-1]

fig, ax = plt.subplots(figsize=(8, 6))
# plot each segment in a different colour
if arrival_approach:
    acoords = arrival_approach['geometry']['coordinates']
    ax.plot([c[0] for c in acoords], [c[1] for c in acoords], '-', color='purple', linewidth=2, label='Approach')
if arrival_runway:
    rcoords = arrival_runway['geometry']['coordinates']
    ax.plot([c[0] for c in rcoords], [c[1] for c in rcoords], '-', color='black', linewidth=2, label='Runway rollout')
if arrival_turn:
    tcoords = arrival_turn['geometry']['coordinates']
    ax.plot([c[0] for c in tcoords], [c[1] for c in tcoords], '-', color='green', linewidth=2, label='Turn-off')
if arrival_taxi:
    tcoords2 = arrival_taxi['geometry']['coordinates']
    ax.plot([c[0] for c in tcoords2], [c[1] for c in tcoords2], '-', color='orange', linewidth=2, label='Taxi to gate')

ax.scatter([lons[-1]], [lats[-1]], color='red', s=60, zorder=4, label='Airport centroid')
if takeoff_end:
    ax.scatter([takeoff_end['lon']], [takeoff_end['lat']], color='black', s=40, zorder=4, label='Runway threshold')

ax.set_xlabel('Longitude')
ax.set_ylabel('Latitude')
ax.set_title('Gatwick Arrival / Taxi (zoom)')
ax.legend()

# zoom tightly around arrival with small padding
pad_lon = max(0.02, (max(lons) - min(lons)) * 0.2)
pad_lat = max(0.02, (max(lats) - min(lats)) * 0.2)
ax.set_xlim(min(lons) - pad_lon, max(lons) + pad_lon)
ax.set_ylim(min(lats) - pad_lat, max(lats) + pad_lat)

fig.tight_layout()
OUT.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT, dpi=200)
print('Wrote', OUT)
