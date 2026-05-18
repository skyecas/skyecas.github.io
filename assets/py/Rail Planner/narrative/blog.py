from __future__ import annotations
from datetime import timedelta

from truth.snapshot import TruthSnapshot, TruthRoute, TruthLeg
from curation.state import CurationState, LegCuration, SectionCuration


def _format_duration(seconds: int) -> str:
    delta = timedelta(seconds=seconds)
    total_hours = int(delta.total_seconds() // 3600)
    total_minutes = int((delta.total_seconds() % 3600) // 60)
    return f"{total_hours}h {total_minutes}m"


def _mode_emoji(mode: str) -> str:
    emojis = {
        "HIGHSPEED_RAIL": "🚄",
        "NIGHT_RAIL": "🚃",
        "REGIONAL_FAST_RAIL": "🚆",
        "REGIONAL_RAIL": "🚆",
        "RAIL": "🚆",
        "LONG_DISTANCE": "🚆",
        "SUBWAY": "🚇",
        "TRAM": "🚊",
        "BUS": "🚌",
        "COACH": "🚌",
        "FERRY": "⛴️",
        "WALK": "🚶",
        "AIRPLANE": "✈️",
    }
    return emojis.get(mode, "🚄")


def _country_flag(code: str) -> str:
    _uk_map = {"UK": "GB"}
    code = _uk_map.get(code, code)
    return chr(0x1F1E6 + ord(code[0]) - 65) + chr(0x1F1E6 + ord(code[1]) - 65)


def _format_countries(countries: list[str]) -> str:
    if not countries:
        return ""
    flags = "".join(_country_flag(c) for c in countries)
    codes = ", ".join(countries)
    return f"Countries: {len(countries)} ({codes}) {flags}"


def _compute_stats(legs: list[TruthLeg]) -> dict:
    transit_legs = [l for l in legs if l.leg_type == 'transit' and l.mode != "WALK"]
    walk_legs = [l for l in legs if l.mode == "WALK"]
    transfer_legs = [l for l in legs if l.leg_type == 'transfer']
    bus_legs = [l for l in legs if l.leg_type == 'bus']
    flight_legs = [l for l in legs if l.leg_type == 'flight']
    longest = max(transit_legs, key=lambda l: l.distance_km) if transit_legs else None
    longest_time = max(transit_legs, key=lambda l: l.duration_seconds) if transit_legs else None
    return {
        "train_count": len(transit_legs),
        "walk_count": len(walk_legs),
        "transfer_count": len(transfer_legs),
        "bus_count": len(bus_legs),
        "flight_count": len(flight_legs),
        "longest_leg": longest,
        "longest_time_leg": longest_time,
    }


def generate_blog_post(snapshot: TruthSnapshot, curation: CurationState) -> str:
    if not snapshot.routes:
        return ""

    route = snapshot.routes[curation.selected_route_index]
    legs = route.legs
    stats = _compute_stats(legs)

    sections = _build_sections(legs, curation)

    lines = []
    lines.append("---")
    lines.append(f"layout: post")
    lines.append(f"title: {curation.trip_title}")
    lines.append(f"date: {curation.trip_date} 00:00:00-0000")
    lines.append(f"description: {curation.trip_description}")
    lines.append(f"tags: {' '.join(curation.trip_tags)}")
    lines.append(f"categories: {curation.trip_category}")
    lines.append("related_posts: false")
    lines.append("toc:")
    lines.append("  sidebar: left")
    lines.append("---")
    lines.append("")

    lines.append("# Location")
    lines.append("")
    lines.append(curation.destination_notes)
    lines.append("")

    lines.append("# Summary")
    lines.append("")
    lines.append(f"Time: {_format_duration(route.duration_seconds)}")
    lines.append("")

    if curation.countries:
        lines.append(_format_countries(curation.countries))
        lines.append("")

    total_distance = route.total_distance_km
    lines.append(f"Distance: {total_distance:.0f}Km")
    if route.transfers:
        lines.append("")
        lines.append(f"Transfers: {route.transfers}")
    lines.append("")

    if route.max_speed_kmh:
        lines.append(f"Fastest speed: {route.max_speed_kmh:.0f}Km/h")
        lines.append("")

    if route.average_speed_kmh:
        lines.append(f"Average speed: {route.average_speed_kmh:.0f}Km/h")
        lines.append("")

    if stats["train_count"]:
        parts = [f"Trains: {stats['train_count']}"]
        if stats["walk_count"]:
            parts.append(f"Walks: {stats['walk_count']}")
        if stats["transfer_count"]:
            parts.append(f"Transfers: {stats['transfer_count']}")
        if stats["bus_count"]:
            parts.append(f"Buses: {stats['bus_count']}")
        if stats["flight_count"]:
            parts.append(f"Flights: {stats['flight_count']}")
        lines.append(" &bull; ".join(parts))
        lines.append("")

    if stats["longest_leg"]:
        ll = stats["longest_leg"]
        lines.append(f"Longest leg: {ll.origin_name} → {ll.destination_name} ({ll.distance_km:.0f}Km, {_format_duration(ll.duration_seconds)})")
        lines.append("")
    if stats["longest_time_leg"] and stats["longest_time_leg"] != stats["longest_leg"]:
        lt = stats["longest_time_leg"]
        lines.append(f"Longest time on a train: {lt.origin_name} → {lt.destination_name} ({_format_duration(lt.duration_seconds)}, {lt.distance_km:.0f}Km)")
        lines.append("")

    if curation.trains_notes:
        lines.append(f"Trains: {curation.trains_notes}")
        lines.append("")
    if curation.stations_notes:
        lines.append(f"Stations: {curation.stations_notes}")
        lines.append("")
    if curation.overall_notes:
        lines.append(curation.overall_notes)
        lines.append("")

    _write_map(lines, route)

    lines.append("")
    lines.append(f"# {curation.outbound_label}")
    lines.append("")
    lines.append(
        f"Planned time: {_format_duration(route.duration_seconds)}"
    )
    lines.append("")
    lines.append(f"Transfers: {route.transfers}")
    lines.append("")
    lines.append(f"Distance: {route.rail_distance_km:.0f}Km")
    lines.append("")
    if curation.countries:
        lines.append(_format_countries(curation.countries))
        lines.append("")

    for section in sections:
        _write_section(lines, section, legs, curation)

    return "\n".join(lines)


def _route_to_geojson(route: TruthRoute) -> dict:
    features = []
    seen_stops: dict[str, bool] = {}

    def mark_stop(name: str, lat: float, lon: float, stop_type: str = "stop"):
        key = f"{lat:.3f},{lon:.3f}"
        if key in seen_stops:
            return
        seen_stops[key] = True
        features.append({
            "type": "Feature",
            "properties": {"name": name, "type": stop_type},
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
        })

    for i, leg in enumerate(route.legs):
        if leg.leg_type in ('transfer', 'unincluded'):
            continue
        if leg.geometry and len(leg.geometry) > 1:
            coords = [[p[1], p[0]] for p in leg.geometry]
            features.append({
                "type": "Feature",
                "properties": {
                    "mode": leg.mode,
                    "name": leg.display_name,
                    "operator": leg.operator,
                    "distance_km": leg.distance_km,
                },
                "geometry": {"type": "LineString", "coordinates": coords},
            })
        else:
            coords = [[leg.origin_lon, leg.origin_lat], [leg.dest_lon, leg.dest_lat]]
            features.append({
                "type": "Feature",
                "properties": {
                    "mode": leg.mode,
                    "name": leg.display_name,
                    "operator": leg.operator,
                    "distance_km": leg.distance_km,
                },
                "geometry": {"type": "LineString", "coordinates": coords},
            })

        leg_type = "transfer" if i > 0 and route.legs[i - 1].mode != "WALK" and leg.mode != "WALK" else "stop"
        if i == 0:
            mark_stop(leg.origin_name, leg.origin_lat, leg.origin_lon, "origin")
        else:
            mark_stop(leg.origin_name, leg.origin_lat, leg.origin_lon, leg_type)
        mark_stop(leg.destination_name, leg.dest_lat, leg.dest_lon,
                  "destination" if i == len(route.legs) - 1 else leg_type)

    return {"type": "FeatureCollection", "features": features}


def _mode_colour(mode: str) -> str:
    colours = {
        "HIGHSPEED_RAIL": "#2196F3",
        "NIGHT_RAIL": "#9C27B0",
        "LONG_DISTANCE": "#3F51B5",
        "REGIONAL_FAST_RAIL": "#4CAF50",
        "REGIONAL_RAIL": "#8BC34A",
        "RAIL": "#8BC34A",
        "SUBWAY": "#FF9800",
        "TRAM": "#FF5722",
        "BUS": "#795548",
        "COACH": "#6D4C41",
        "AIRPLANE": "#1A237E",
        "FERRY": "#00BCD4",
        "WALK": "#9E9E9E",
    }
    return colours.get(mode, "#2196F3")


def _write_map(lines: list[str], route: TruthRoute) -> None:
    geojson = _route_to_geojson(route)
    import json as _json
    geojson_str = _json.dumps(geojson)

    map_id = f"route-map-{route.route_id}"

    lines.append("")
    lines.append('<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />')
    lines.append('<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>')
    lines.append("")
    lines.append(f'<div id="{map_id}" style="height: 400px; border-radius: 8px; margin: 16px 0;"></div>')
    lines.append("<script>")
    lines.append(f"  (function() {{")
    lines.append(f"    var map = L.map('{map_id}', {{ scrollWheelZoom: false }});")
    lines.append(f"    L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{")
    lines.append(f"      attribution: '&copy; <a href=\"https://www.openstreetmap.org/copyright\">OSM</a> &copy; <a href=\"https://carto.com/\">CARTO</a>', maxZoom: 18")
    lines.append(f"    }}).addTo(map);")
    lines.append("")
    lines.append(f"    var geojson = {geojson_str};")
    lines.append("")
    lines.append(r"    var modeColours = {")
    lines.append(r"      HIGHSPEED_RAIL: '#2196F3', NIGHT_RAIL: '#9C27B0',")
    lines.append(r"      LONG_DISTANCE: '#3F51B5', REGIONAL_FAST_RAIL: '#4CAF50',")
    lines.append(r"      REGIONAL_RAIL: '#8BC34A', RAIL: '#8BC34A', SUBWAY: '#FF9800',")
    lines.append(r"      TRAM: '#FF5722', BUS: '#795548', COACH: '#6D4C41',")
    lines.append(r"      AIRPLANE: '#1A237E', FERRY: '#00BCD4', WALK: '#9E9E9E',")
    lines.append(r"    };")
    lines.append("")
    lines.append(r"    var bounds = [];")
    lines.append(r"    L.geoJSON(geojson, {")
    lines.append(r"      style: function(feature) {")
    lines.append(r"        if (feature.geometry.type === 'LineString') {")
    lines.append(r"          return {")
    lines.append(r"            color: modeColours[feature.properties.mode] || '#2196F3',")
    lines.append(r"            weight: 4, opacity: 0.8")
    lines.append(r"          };")
    lines.append(r"        }")
    lines.append(r"      },")
    lines.append(r"      pointToLayer: function(feature, latlng) {")
    lines.append(r"        var type = feature.properties.type;")
    lines.append(r"        var colours = {origin: '#4CAF50', destination: '#f44336', transfer: '#FF9800', stop: '#2196F3'};")
    lines.append(r"        var sizes = {origin: 12, destination: 12, transfer: 8, stop: 6};")
    lines.append(r"        return L.circleMarker(latlng, {")
    lines.append(r"          radius: sizes[type] || 6,")
    lines.append(r"          fillColor: colours[type] || '#2196F3',")
    lines.append(r"          color: '#fff', weight: 2, fillOpacity: 0.9")
    lines.append(r"        });")
    lines.append(r"      },")
    lines.append(r"      onEachFeature: function(feature, layer) {")
    lines.append(r"        var p = feature.properties;")
    lines.append(r"        var tooltip = p.name || (p.mode + ': ' + (p.operator || '') + ' ' + (p.name || ''));")
    lines.append(r"        if (p.distance_km) tooltip += ' (' + p.distance_km.toFixed(0) + ' km)';")
    lines.append(r"        layer.bindTooltip(tooltip);")
    lines.append(r"        if (feature.geometry.type === 'LineString') {")
    lines.append(r"          feature.geometry.coordinates.forEach(function(c) { bounds.push(c); });")
    lines.append(r"        } else {")
    lines.append(r"          bounds.push(feature.geometry.coordinates);")
    lines.append(r"        }")
    lines.append(r"      }")
    lines.append(r"    }).addTo(map);")
    lines.append(r"    if (bounds.length) map.fitBounds(bounds, {padding: [30, 30]});")
    lines.append(r"  }})();")
    lines.append("</script>")
    lines.append("")


def _build_sections(
    legs: list[TruthLeg], curation: CurationState
) -> list[SectionCuration]:
    """Group legs into logical sections based on meaningful stop locations."""
    sections: list[SectionCuration] = []
    current_legs: list[int] = []
    section_origin = legs[0].origin_name if legs else ""

    for i, leg in enumerate(legs):
        if leg.leg_type == 'transfer':
            if current_legs:
                current_legs.append(i)
            continue
        if leg.leg_type == 'unincluded':
            current_legs.append(i)
            continue
        if leg.mode == "WALK":
            if current_legs:
                current_legs.append(i)
            continue

        if leg.origin_name != section_origin and current_legs:
            sections.append(SectionCuration(
                section_name=section_origin,
                leg_indices=current_legs,
            ))
            current_legs = []
            section_origin = leg.origin_name

        current_legs.append(i)

    if current_legs:
        final_stop = legs[-1].destination_name if legs else section_origin
        sections.append(SectionCuration(
            section_name=section_origin,
            leg_indices=current_legs,
        ))

    return sections


def _leg_table_row(leg: TruthLeg) -> str:
    dep = leg.departure
    arr = leg.arrival
    dest = leg.destination_name
    if leg.leg_type == 'transfer':
        return ""
    if leg.leg_type == 'unincluded':
        return f"| ~~{dep}~~ | ~~{arr}~~ | ~~{dest} *(unincluded)* ~~ |"
    if leg.leg_type == 'bus':
        return f"| {dep} | {arr} | {dest} *({_mode_emoji(leg.mode)} Bus)* |"
    if leg.leg_type == 'flight':
        return f"| {dep} | {arr} | {dest} *({_mode_emoji(leg.mode)} Flight)* |"
    if leg.mode == "WALK":
        return f"| {dep} | {arr} | {dest} *(walk)* |"
    return f"| {dep} | {arr} | {dest} |"


def _write_section(
    lines: list[str],
    section: SectionCuration,
    legs: list[TruthLeg],
    curation: CurationState,
) -> None:
    leg_cur = curation.leg_curations.get(section.leg_indices[0])

    lines.append(f"## {section.section_name}")
    lines.append("")

    has_table_rows = False
    transfer_notes = []
    for idx in section.leg_indices:
        if idx < len(legs):
            leg = legs[idx]
            if leg.leg_type == 'transfer':
                transfer_notes.append(f"*Transfer at {leg.origin_name} → {leg.destination_name} ({leg.duration_seconds//60} min)*")
            else:
                if not has_table_rows:
                    lines.append("| Departure | Arrival | Location |")
                    lines.append("| :-------: | :-----: | :------- |")
                    has_table_rows = True
                lines.append(_leg_table_row(leg))
    if has_table_rows:
        lines.append("")

    for note in transfer_notes:
        lines.append(note)
        lines.append("")

    if leg_cur and leg_cur.notes:
        lines.append(leg_cur.notes)
        lines.append("")

    if leg_cur and leg_cur.photos:
        _write_photos(lines, leg_cur.photos, curation)

    lines.append("")


def _sprint_dir_from_date(date_str: str) -> str:
    m = date_str.strip().split("-") if date_str else []
    if len(m) >= 2:
        return f"sprint{m[0][2:]}{m[1]}"
    return "sprint"

def _write_photos(lines: list[str], photos: list[str], curation: CurationState) -> None:
    sprint = _sprint_dir_from_date(curation.trip_date)
    lines.append('<swiper-container keyboard="true" navigation="true" pagination="true" pagination-clickable="true" pagination-dynamic-bullets="true" rewind="true">')
    for photo in photos:
        lines.append(
            f'  <swiper-slide>{{% include figure.liquid loading="eager" '
            f'path="assets/img/{sprint}/{photo}" class="img-fluid rounded z-depth-1" %}}</swiper-slide>'
        )
    lines.append("</swiper-container>")
