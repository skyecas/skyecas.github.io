#!/usr/bin/env python3
import json
from pathlib import Path
import matplotlib.pyplot as plt

in_path = Path('assets/py/Rail Planner/ui/static_routes/bcn_lgw.geojson')
out_path = Path('assets/py/Rail Planner/ui/static_routes/bcn_lgw.png')

if not in_path.exists():
    raise SystemExit(f"Input file not found: {in_path}")

data = json.loads(in_path.read_text())
features = data.get('features', [])
if not features:
    raise SystemExit('No features in geojson')

# find feature by segment property
def get_coords(seg_name):
    for f in features:
        props = f.get('properties') or {}
        if props.get('segment') == seg_name:
            return f['geometry']['coordinates']
    return []

dep = get_coords('departure')
mid = get_coords('mid_gc')
arr = get_coords('arrival')

fig, ax = plt.subplots(figsize=(12, 9))
# plot departure as dashed green, mid as blue arc, arrival as solid orange
if dep:
    lons = [c[0] for c in dep]; lats = [c[1] for c in dep]
    ax.plot(lons, lats, '--', color='green', linewidth=1.6, label='Departure (synthetic)')
if mid:
    lons = [c[0] for c in mid]; lats = [c[1] for c in mid]
    ax.plot(lons, lats, '-', color='navy', linewidth=1.8, label='Great-circle')
if arr:
    lons = [c[0] for c in arr]; lats = [c[1] for c in arr]
    ax.plot(lons, lats, '-', color='orange', linewidth=1.6, label='Arrival / Taxi')

# mark endpoints
if dep:
    ax.scatter([dep[0][0]], [dep[0][1]], color='green', s=50, zorder=4)
if arr:
    ax.scatter([arr[-1][0]], [arr[-1][1]], color='red', s=50, zorder=4)

ax.set_xlabel('Longitude')
ax.set_ylabel('Latitude')
ax.set_title('BCN → LGW route (segmented)')
ax.legend()

# compute combined bounds
all_lons = [c[0] for c in (dep + mid + arr) if c]
all_lats = [c[1] for c in (dep + mid + arr) if c]
pad_lon = (max(all_lons) - min(all_lons)) * 0.06
pad_lat = (max(all_lats) - min(all_lats)) * 0.06
ax.set_xlim(min(all_lons) - pad_lon, max(all_lons) + pad_lon)
ax.set_ylim(min(all_lats) - pad_lat, max(all_lats) + pad_lat)

fig.tight_layout()
out_path.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(out_path, dpi=180)
print('Wrote', out_path)
