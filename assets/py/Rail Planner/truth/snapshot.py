from __future__ import annotations
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any
import hashlib
import json
from datetime import datetime

from rail_planner import Route, Leg, Stop, TransitClient


@dataclass
class TruthLeg:
    mode: str
    display_name: str
    operator: str
    origin_name: str
    destination_name: str
    departure: str
    arrival: str
    duration_seconds: int
    distance_km: float
    max_speed_kmh: float
    tortuosity_pct: float
    intermediate_stops: list[dict[str, Any]]
    origin_lat: float = 0.0
    origin_lon: float = 0.0
    dest_lat: float = 0.0
    dest_lon: float = 0.0
    geometry: list[dict[str, float]] | None = None
    leg_type: str = 'transit'


@dataclass
class TruthRoute:
    route_id: str
    origin_name: str
    destination_name: str
    departure: str
    arrival: str
    duration_seconds: int
    total_distance_km: float
    rail_distance_km: float
    walk_distance_km: float
    transfers: int
    average_speed_kmh: float
    max_speed_kmh: float
    tortuosity_pct: float
    legs: list[TruthLeg]
    operators: list[str]
    countries: list[str]


@dataclass
class TruthSnapshot:
    snapshot_id: str
    created_at: str
    query: dict[str, Any]
    routes: list[TruthRoute]
    computed_metrics: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_routes(
        cls,
        routes: list[Route],
        query: dict[str, Any],
        emissions: float | None = None,
    ) -> TruthSnapshot:
        timestamp = datetime.utcnow().isoformat() + "Z"
        raw = json.dumps({"query": query, "ts": timestamp}, sort_keys=True)
        snapshot_id = hashlib.sha256(raw.encode()).hexdigest()[:12]

        truth_routes = [_build_truth_route(r) for r in routes]

        metrics = {}
        if emissions is not None:
            metrics["total_emissions_kg"] = emissions / 1000.0

        return cls(
            snapshot_id=snapshot_id,
            created_at=timestamp,
            query=query,
            routes=truth_routes,
            computed_metrics=metrics,
            provenance={"source": "transitous", "version": 1},
        )


def _build_truth_leg(leg: Leg) -> TruthLeg:
    stops = []
    for s in leg.stops:
        stops.append({
            "name": s.name,
            "arrival": str(s.arrival.time.time())[:5] if hasattr(s, "arrival") and s.arrival else None,
            "departure": str(s.departure.time.time())[:5] if hasattr(s, "departure") and s.departure else None,
        })

    geometry = None
    if leg.geometry:
        geometry = [{"lat": p.lat.degrees, "lon": p.lon.degrees} for p in leg.geometry]

    origin_lat = leg.origin.position.lat.degrees if hasattr(leg.origin, "position") else 0
    origin_lon = leg.origin.position.lon.degrees if hasattr(leg.origin, "position") else 0
    dest_lat = leg.destination.position.lat.degrees if hasattr(leg.destination, "position") else 0
    dest_lon = leg.destination.position.lon.degrees if hasattr(leg.destination, "position") else 0

    if leg.mode == "WALK":
        return TruthLeg(
            mode="WALK",
            display_name="Walk",
            operator="",
            origin_name=leg.origin.name,
            destination_name=leg.destination.name,
            origin_lat=origin_lat, origin_lon=origin_lon,
            dest_lat=dest_lat, dest_lon=dest_lon,
            departure=str(leg.departure.time.time())[:5],
            arrival=str(leg.arrival.time.time())[:5],
            duration_seconds=int(leg.duration.total_seconds()),
            distance_km=round(leg.distance(), 1),
            max_speed_kmh=round(leg.average_speed(), 1),
            tortuosity_pct=round(leg.tortuosity(), 1),
            intermediate_stops=stops,
            geometry=geometry,
            leg_type='transfer',
        )

    return TruthLeg(
        mode=leg.mode,
        display_name=leg.display if hasattr(leg, "display") and leg.display else leg.mode_string,
        operator=getattr(leg, "operator", ""),
        origin_name=leg.origin.name,
        destination_name=leg.destination.name,
        origin_lat=origin_lat, origin_lon=origin_lon,
        dest_lat=dest_lat, dest_lon=dest_lon,
        departure=str(leg.departure.time.time())[:5],
        arrival=str(leg.arrival.time.time())[:5],
        duration_seconds=int(leg.duration.total_seconds()),
        distance_km=round(leg.distance(), 1),
        max_speed_kmh=round(leg.average_speed(), 1),
        tortuosity_pct=round(leg.tortuosity(), 1),
        intermediate_stops=stops,
        geometry=geometry,
    )


def _build_truth_route(route: Route) -> TruthRoute:
    route_id = route.signature_hash[:12]
    segments = route.segment_speeds()
    max_speed = max((s["speed"] for s in segments), default=0)

    return TruthRoute(
        route_id=route_id,
        origin_name=route.origin.name,
        destination_name=route.destination.name,
        departure=str(route.departure.time.time())[:5],
        arrival=str(route.arrival.time.time())[:5],
        duration_seconds=int(route.duration.total_seconds()),
        total_distance_km=round(route.distance(), 1),
        rail_distance_km=round(route.rail_distance(), 1),
        walk_distance_km=round(route.walk_distance(), 1),
        transfers=route.transfers,
        average_speed_kmh=round(route.average_speed(), 1),
        max_speed_kmh=round(max_speed, 1),
        tortuosity_pct=round(route.tortuosity(), 1),
        legs=[_build_truth_leg(l) for l in route.legs],
        operators=list(route.operators),
        countries=[],
    )
