#!/usr/bin/env python3
from __future__ import annotations
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Any

# Allow running from both the script dir and the project root
_script_dir = Path(__file__).parent
sys.path.insert(0, str(_script_dir))

from rail_planner import TransitClient, SortMode, DURATION, TRANSFERS, EMISSIONS
from emissions import CategoryBasedEmissions
from truth.snapshot import TruthSnapshot
from curation.state import CurationState, LegCuration
from narrative.blog import generate_blog_post


def find_project_root() -> Path:
    """Walk up from script dir to find _posts/ directory."""
    for parent in [_script_dir, *list(_script_dir.parents)]:
        if (parent / "_posts").is_dir():
            return parent
    return Path.cwd()


def search_prompt(client: TransitClient, label: str) -> Any:
    query = input(f"  {label} station name: ").strip()
    results = client.search_stations(query)
    if not results:
        print(f"  No results for '{query}'")
        return search_prompt(client, label)
    if len(results) == 1:
        print(f"  -> {results[0].name}")
        return results[0]
    print(f"  Found {len(results)} matches:")
    for i, loc in enumerate(results):
        print(f"    [{i}] {loc.name} ({loc.id})")
    choice = int(input("  Select [0]: ") or "0")
    print(f"  -> {results[choice].name}")
    return results[choice]


def interactive_curation(snapshot: TruthSnapshot) -> CurationState:
    routes = snapshot.routes
    print(f"\nFound {len(routes)} routes.")

    for i, r in enumerate(routes):
        dur = r.duration_seconds
        h, m = divmod(dur // 60, 60)
        print(f"  [{i}] {r.departure}-{r.arrival} "
              f"({h}h{m:02d}m, {r.transfers} transfers, "
              f"{r.total_distance_km:.0f}km, {r.average_speed_kmh:.0f}km/h)")

    choice = int(input(f"\nSelect route [0]: ") or "0")

    curation = CurationState(
        snapshot_id=snapshot.snapshot_id,
        selected_route_index=choice,
        trip_title=input("Blog post title: ").strip(),
        trip_date=input("Date (YYYY-MM-DD): ").strip(),
        trip_description=input("Description: ").strip(),
        destination_notes=input("Destination notes: ").strip(),
        overall_notes=input("Overall journey notes: ").strip(),
    )

    tags = input("Tags (space-separated) [train travel canonical]: ").strip()
    if tags:
        curation.trip_tags = tags.split()

    selected = routes[choice]
    for i, leg in enumerate(selected.legs):
        print(f"\n--- Leg {i}: {leg.origin_name} -> {leg.destination_name} "
              f"({leg.mode}) ---")
        notes = input(f"  Notes for {leg.origin_name}: ").strip()
        highlight = input(f"  Highlight this leg? (y/N): ").strip().lower() == "y"
        photos_raw = input(f"  Photos (comma-separated filenames): ").strip()
        photos = [p.strip() for p in photos_raw.split(",") if p.strip()]

        if notes or highlight or photos:
            lc = LegCuration(leg_index=i, highlighted=highlight, notes=notes, photos=photos)
            curation.leg_curations[i] = lc

    return curation


def main():
    client = TransitClient(itineraries=5, search_window=7200)
    emissions = CategoryBasedEmissions()

    print("=== Sprint Blog Generator ===")
    print()

    origin = search_prompt(client, "Origin")
    dest = search_prompt(client, "Destination")

    dep_date = input("Departure date (YYYY-MM-DD) [today]: ").strip()
    dep_time = input("Departure time (HH:MM) [08:00]: ").strip() or "08:00"
    if dep_date:
        depart_after = datetime.strptime(f"{dep_date} {dep_time}", "%Y-%m-%d %H:%M")
    else:
        depart_after = datetime.strptime(dep_time, "%H:%M").replace(
            year=datetime.now().year,
            month=datetime.now().month,
            day=datetime.now().day,
        )

    via_raw = input("Via stations (comma-separated, optional): ").strip()
    via = [v.strip() for v in via_raw.split(",")] if via_raw else None

    print("\nSearching routes...")
    routes = client.routes_between(
        origin, dest,
        depart_after=depart_after,
        via=via,
        modes=TransitClient.TRAVEL_SKYE,
        sort=EMISSIONS + TRANSFERS + DURATION,
        model=emissions,
    )

    if not routes:
        print("No routes found!")
        return

    snapshot = TruthSnapshot.from_routes(
        routes,
        query={
            "origin": origin.name,
            "destination": dest.name,
            "time": depart_after.isoformat(),
            "via": via,
        },
    )

    curation = interactive_curation(snapshot)

    print("\nGenerating blog post...")
    post = generate_blog_post(snapshot, curation)

    project_root = find_project_root()
    out_path = project_root / f"_posts/{curation.trip_date}-sprint.md"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(post)
    print(f"\nBlog post written to {out_path}")


if __name__ == "__main__":
    main()
