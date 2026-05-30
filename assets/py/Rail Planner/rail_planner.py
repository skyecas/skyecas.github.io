from __future__ import annotations
from requests import get
from urllib.parse import urlencode
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Callable
from collections.abc import Iterable
from enum import Enum
import json
import hashlib
from pathlib import Path
from math import ceil

from geo import Position, polyline_positions
from time_util import Time

CACHE_DIR = Path(".transitous_cache")
CACHE_DIR.mkdir(exist_ok=True)


def readable_list(items: Iterable[str], sep: str = "and") -> str:
    items = tuple(items)
    if len(items) < 3:
        return f" {sep} ".join(items)
    return ", ".join(items[:-1]) + f", {sep} {items[-1]}"

def deduplicate(items: list[str]) -> list[str]:
    out = []
    for x in items:
        if x not in out and x is not None:
            out.append(x)
    return out


class LocationBase:
    def __init__(self, position: Position, timezone: ZoneInfo, name: str = "", id: str = ""):
        self.position = position
        self.timezone = timezone
        self.name = name
        self.id = id

    @classmethod
    def from_json(cls, json: dict[str, Any]) -> LocationBase:
        return LocationBase(
            position=Position(json["lat"], json["lon"]),
            timezone=ZoneInfo(json["tz"]),
            name=json.get("name", ""),
            id=json.get("id", ""),
        )

    def __str__(self):
        name_str = self.name if self.name else "Unknown"
        id_str = f" ({self.id})" if self.id else ""
        return f"{name_str}{id_str}"

    def __repr__(self):
        return str(self)

    @property
    def latlon(self) -> str:
        return f"{self.position.latitude.degrees},{self.position.longitude.degrees}"

    @property
    def search(self) -> str:
        return getattr(self, "id", self.latlon)

    def now(self) -> Time:
        return Time(datetime.now(self.timezone), self.timezone)

    def distance(self, other: LocationBase) -> float:
        return self.position.distance(other.position)

class Location(LocationBase):
    def __init__(self, position:Position, timezone:ZoneInfo, id: str, name: str, address: str):
        super().__init__(position, timezone, name=name, id=id)
        self.address = address

    @classmethod
    def from_json(cls, json) -> Location:
        return Location(
            position=Position(json["lat"], json["lon"]),
            timezone=ZoneInfo(json["tz"]),
            id=json["id"],
            name=json["name"],
            address=", ".join(a["name"] for a in json["areas"][::-1]),
        )

    def distance_string(self, other: type[Location]) -> str:
        return f"{self.distance(other):.2f}Km"

class Stop(LocationBase):
    def __init__(
            self,
            position:Position,
            timezone: ZoneInfo,
            name: str,
            id: str | None = None,
            arrival: Time | None = None,
            departure: Time | None = None,
            track: str | None = None,
            pickup: str | None = None,
            dropoff: str | None = None,
        ):
        super().__init__(position, timezone, name=name, id=id or "")
        if arrival is not None:
            self.arrival = arrival
        if departure is not None:
            self.departure = departure
        if track is not None:
            self.track = track
        if pickup is not None:
            self.pickup = pickup
        if dropoff is not None:
            self.dropoff = dropoff

    @classmethod
    def from_json(cls, json) -> Stop:
        tz = ZoneInfo(json["tz"])
        return Stop(
            position=Position(json["lat"], json["lon"]),
            timezone=tz,
            name=json["name"],
            id=json.get("stopId"),
            arrival=Time.from_string(arrival, tz) if (arrival:=json.get("scheduledArrival")) else None,
            departure=Time.from_string(departure, tz) if (departure:=json.get("scheduledDeparture")) else None,
            track=json.get("scheduledTrack"),
            pickup=json.get("pickupType"),
            dropoff=json.get("dropoffType"),
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, LocationBase):
            return NotImplemented
        if (other_name := getattr(other, "name", None)) and self.name == other_name:
            return True
        return self.position == other.position

    @property
    def platform(self) -> str | None:
        return getattr(self, "track", None)

    def time_to(self, other: Stop) -> timedelta:
        return other.arrival.time - self.departure.time

    @classmethod
    def walk_between(cls, start: Stop, end: Stop) -> Leg:
        distance = start.distance(end)
        walk_origin = Stop(
            position=start.position,
            timezone=start.timezone,
            name=start.name,
            id=getattr(start, "id", None),
            arrival=start.arrival,
            departure=start.arrival,
            track=getattr(start, "track", None),
        )
        return Leg(
            mode="WALK",
            origin=walk_origin,
            stops=[],
            destination=Stop(
                position=end.position,
                timezone=end.timezone,
                name=end.name,
                id=getattr(end, "id", None),
                # Assume an average walking speed of 3 Km/h, round up to the next minute for padding
                arrival=(start.arrival + timedelta(seconds=ceil(distance / 3.0))).next_minute,
            )
        )

    def walk_to(self, end: Leg | Stop) -> Leg:
        if isinstance(end, Stop):
            return Stop.walk_between(self, end)
        elif isinstance(end, Leg):
            return Stop.walk_between(self, end.origin)
        raise TypeError(f"Cannot create leg from {type(self)} to ({type(end)})")

    def summary(self, verbosity: int = 1) -> str:
        parts = [self.name]
        if hasattr(self, "arrival") and self.arrival:
            parts.append(f"arr {self.arrival.time.strftime('%H:%M')}")
        if hasattr(self, "departure") and self.departure:
            parts.append(f"dep {self.departure.time.strftime('%H:%M')}")
        if verbosity >= 2 and hasattr(self, "track") and self.track:
            parts.append(f"platform {self.track}")
        return " | ".join(parts)

class Leg:
    def __init__(
            self,
            mode: str,
            origin: Stop,
            destination: Stop,
            stops: list[Stop],
            id: str | None = None,
            name: str | None = None,
            operator: str | None = None,
            geometry: list[Position] | None = None,
        ):
        self.mode = mode
        self.origin = origin
        self.destination = destination

        self.departure = origin.departure
        self.arrival = destination.arrival
        self.duration = destination.arrival - origin.departure
        self.stops = stops
        if id:
            self.id = id
        if operator:
            self.operator = operator
        self.name = name
        self.geometry = geometry or []

    @classmethod
    def from_json(cls, json) -> Leg:
        return Leg(
            mode=json["mode"],
            origin=Stop.from_json(json["from"]),
            destination=Stop.from_json(json["to"]),
            stops=[Stop.from_json(stop_json) for stop_json in json.get("intermediateStops", [])],
            id=json.get("routeId", None),
            name=json.get("displayName", "Walk"),
            operator=json.get("agencyName", None),
            geometry=polyline_positions(geometry) if (geometry:=json.get("legGeometry")) else []
        )

    @classmethod
    def walk_between(cls, start: Stop | Leg, end: Stop | Leg) -> Leg:
        if not isinstance(start, (Stop, Leg)) and not isinstance(end, (Stop, Leg)):
            raise TypeError(f"Cannot create leg from {type(self)} to ({type(end)})")
        legstart = start if isinstance(start, Stop) else start.destination
        legend = end if isinstance(end, Stop) else end.origin
        return Stop.walk_between(legstart, legend)

    def walk_to(self, end: Leg | Stop) -> Leg:
        if isinstance(end, (Stop, Leg)):
            return Leg.walk_between(self.destination, end)
        raise TypeError(f"Cannot create leg from {type(self)} to ({type(end)})")

    @property
    def mode_string(self) -> str:
        return self.mode.capitalize().replace('_', ' ')

    def __str__(self):
        return f"{self.mode_string} from {self.origin.name} to {self.destination.name}"

    def __repr__(self):
        return str(self)

    def __add__(self, other: Leg) -> Leg:
        if not isinstance(other, Leg):
            raise TypeError(f"Cannot join {type(self)} to {type(other)}")
        return Leg(
            mode=self.mode,
            origin=self.origin,
            destination=other.destination,
            stops=self.stops + [Stop(
                position=self.destination.position,
                timezone=self.destination.timezone,
                name=self.destination.name,
                id=getattr(self.destination, "id", None),
                arrival=getattr(self.destination, "arrival", None),
                departure=getattr(other.origin, "departure", None),
                track=getattr(self.destination, "track", None),
                pickup=getattr(other.origin, "pickup", None),
                dropoff=getattr(self.destination, "dropoff", None),
            )] + other.stops,
            id=getattr(self, "id", None),
            name=self.name,
            operator=readable_list(
                deduplicate([
                    getattr(self, "operator", None),
                    getattr(other, "operator", None)
                ])
            )
        )

    @property
    def origin_platform(self) -> str | None:
        if track:=self.origin.platform:
            return track
        return None

    @property
    def destination_platform(self) -> str | None:
        if track:=self.destination.platform:
            return track
        return None

    @property
    def all_stops(self) -> list[Stop]:
        return [self.origin] + self.stops + [self.destination]

    def distance(self) -> float:
        if self.geometry:
            return sum(
                start.distance(end)
                for start, end in zip(self.geometry[:-1], self.geometry[1:])
            )
        return sum(
            this_stop.distance(next_stop)
            for this_stop, next_stop in zip(self.all_stops[:-1], self.all_stops[1:])
        )

    def direct_distance(self) -> float:
        return self.origin.distance(self.destination)

    def tortuosity(self) -> float:
        dist = self.direct_distance()
        if dist == 0:
            return 0.0
        return 100*self.distance()/dist

    def average_speed(self) -> float:
        if self.duration.total_seconds() == 0:
            return 0.0
        return 3600 * self.distance() / self.duration.total_seconds()

    @property
    def display(self) -> str:
        out=[]
        if op:=getattr(self, "operator", None):
            out.append(op)
        if self.name and self.name not in out:
            out.append(self.name)
        if not out:
            return self.mode_string
        return " ".join(out)

    def summary(self, verbosity: int = 1, model: EmissionsModel | None = None) -> str:
        """verbosity should be 0, 1, or 2"""
        start = self.departure.time.strftime("%H:%M")
        end = self.arrival.time.strftime("%H:%M")

        verb = self.mode_string
        at = f"{self.origin.name} {start} to {self.destination.name} {end}"
        if self.origin.name == self.destination.name:
            if (start_track:=self.origin_platform) and (end_track:=self.destination_platform):
                verb = "Transfer"
                if start_track == end_track:
                    at = f"{self.origin.name} {start}, stay on platform {start_track}"
                else:
                    at = f"{self.origin.name} {start}, platform {start_track} to platform {end_track}"

        base = f"  {self.display or verb}: {at}"

        if verbosity >= 1:
            if dist:=self.distance():
                base += f" | {dist:.1f} Km in {self.duration}"
        if verbosity >= 2:
            if speed:=self.average_speed():
                if speed > 0 and self.mode!="WALK":
                    base += f" ({int(speed)} Km/h)"
            if tour := self.tortuosity():
                if tour > 100:
                    base += f" | {self.direct_distance():.1f} Km direct ({tour:.2f} %)"
        if model and self.mode!="WALK":
            co2 = model.estimate_leg(self)
            base += f" | {co2/1000:.2f} Kg CO2"
        lines = [base]
        if verbosity >= 2 and self.stops:
            lines.append("    Stops:")
            for stop in self.stops:
                lines.append(f"      - {stop.summary(verbosity)}")
        return "\n".join(lines)

class Route:
    def __init__(
            self,
            origin: Location,
            destination: Location,
            departure: Time,
            arrival: Time,
            legs: list[Leg],
        ):
        self.origin = origin
        self.destination = destination
        self.legs = legs
        self.departure = departure
        self.arrival = arrival
        self.duration = (self.arrival - self.departure)

        self._repair_platforms()
        self._compute_transfers()

    def _repair_platforms(self):
        for start, end in zip(self.legs[:-1], self.legs[1:]):
            start.destination.track = (
                start.destination_platform or end.origin_platform
            )

    def _compute_transfers(self):
        self.transfers = max(0, len([leg for leg in self.legs if leg.mode != "WALK"]) - 1)

    @classmethod
    def from_json(cls, origin: Location, destination: Location, json: dict[str, Any]):
        return Route(
            origin=origin,
            destination=destination,
            departure=Time.from_string(json["startTime"], origin.timezone),
            arrival=Time.from_string(json["endTime"], destination.timezone),
            legs=[Leg.from_json(leg) for leg in json["legs"]],
        )

    @property
    def stop_ids(self) -> set[str]:
        return set(id for leg in self.legs for stop in leg.stops if (id:=getattr(stop, "id", None)))

    @property
    def operators(self) -> set[str]:
        return set(operator for leg in self.legs if (operator:=getattr(leg, "operator", None)))

    @property
    def signature(self) -> tuple:
        return tuple(
            (
                leg.display,
                leg.origin.name,
                leg.destination.name,
                leg.departure.time.strftime("%A %H:%M"),
                leg.arrival.time.strftime("%A %H:%M"),
                int(leg.duration.total_seconds()//60),
                int(leg.distance()/1000),
            )
            for leg in self.legs
        )

    @property
    def signature_hash(self) -> str:
        return hashlib.sha256(str(self.signature).encode("utf-8")).hexdigest()

    def __str__(self):
        string = f"Route from {self.origin.name} to {self.destination.name}"
        if len(self.legs) > 1:
            string += f", Via {readable_list(deduplicate([leg.origin.name for leg in self.legs[1:]]))}"
        return string

    def __repr__(self):
        return str(self)

    def __add__(self, other: Route):
        if not isinstance(other, Route):
            raise TypeError(f"Cannot join {type(self)} with {type(other)}")
        start_leg, end_leg = self.legs[-1], other.legs[0]

        # Are we on the same service?
        if start_leg.name == end_leg.name:
            legs = self.legs[:-1] + [start_leg+end_leg] + other.legs[1:]
        # Otherwise, add a transfer
        else:
            legs = self.legs + [start_leg.walk_to(end_leg)] + other.legs

        return Route(
            origin= self.origin,
            destination= other.destination,
            departure= self.departure,
            arrival= other.arrival,
            legs=legs,
        )

    @property
    def stops(self) -> list[Stop]:
        stops = []
        for leg in self.legs:
            for stop in leg.all_stops:
                if stop not in stops:
                    stops.append(stop)
        return stops

    @property
    def stop_names(self) -> list[str]:
        return deduplicate([stop.name for leg in self.legs for stop in leg.all_stops])

    def direct_distance(self) -> float:
        return self.origin.distance(self.destination)

    def distance(self) -> float:
        return self.rail_distance() + self.transfer_distance() + self.walk_distance()

    def rail_distance(self) -> float:
        return sum(
            leg.distance() for leg in self.legs if leg.mode != "WALK"
        )

    def tortuosity(self) -> float:
        """How much longer is the route compared to a straight line between start and end"""
        return 100 * self.distance() / self.direct_distance()

    def via_tortuosity(self) -> float:
        """How much longer is the route compared to a straight line between each intermediate"""
        if len(self.legs) <= 1:
            return self.tortuosity()
        return 100 * sum(
            leg.distance() / leg.direct_distance()
            for leg in self.legs
        )

    def walk_distance(self) -> float:
        return sum(
            leg.distance() for leg in self.legs if leg.mode == "WALK"
        )

    def transfer_distance(self) -> float:
        if len(self.legs) <= 1:
            return 0.0

        return sum(
            this_leg.destination.distance(next_leg.origin)
            for this_leg, next_leg in zip(self.legs[:-1], self.legs[1:])
        )

    def operational_speed(self) -> float:
        rail_dist = self.rail_distance()
        rail_time = sum(
            leg.duration.total_seconds()
            for leg in self.legs
            if leg.mode != "WALK"
        )
        if rail_time == 0:
            return 0.0
        return 3600 * rail_dist / rail_time

    def average_speed(self) -> float:
        if self.duration.total_seconds() == 0:
            return 0.0
        return 3600 * self.distance() / self.duration.total_seconds()

    def segment_speeds(self) -> list[tuple[Any]]:
        segments = []
        for leg in self.legs:
            if leg.mode == "WALK":
                continue
            for a, b in zip(leg.all_stops[:-1], leg.all_stops[1:]):
                duration = a.time_to(b)
                if duration.total_seconds() == 0:
                    continue
                speed = 3600 * a.distance(b) / duration.total_seconds()
                segments.append({
                    "from": a.name,
                    "to": b.name,
                    "distance": a.distance(b),
                    "duration": duration,
                    "speed": speed,
                    "leg": leg
                })
        return segments

    def fastest_segment(self)->float:
        segments = self.segment_speeds()
        return max(segments, key=lambda x: x["speed"]) if segments else None

    def slowest_segment(self)->float:
        segments = self.segment_speeds()
        return min(segments, key=lambda x: x["speed"]) if segments else None

    def dwell_times(self)->list[tuple[str,timedelta]]:
        dwells = []
        stops = [stop for leg in self.legs for stop in leg.stops if hasattr(stop, "arrival") and hasattr(stop, "departure")]
        search_space = zip(stops + self.legs[:-1], stops + self.legs[1:])
        for start, end in search_space:
            dwell = end.departure - start.arrival
            if dwell.total_seconds() > 0:
                dwells.append((
                    start.destination.name if isinstance(start, Leg) else start.name,
                    timedelta(seconds=dwell.total_seconds()//1),
                ))
        return dwells

    def longest_dwell(self)->timedelta | None:
        dwells = self.dwell_times()
        return max(dwells, key=lambda x: x[1]) if dwells else None

    def shortest_dwell(self)->timedelta | None:
        dwells = self.dwell_times()
        return min(dwells, key=lambda x: x[1]) if dwells else None

    def summary(self, verbosity: int = 2, model: EmissionsModel | None = None) -> str:
        """verbosity should be 0, 1, or 2"""
        start = self.departure.time.strftime("%A %H:%M")
        end = self.arrival.time.strftime("%A %H:%M")
        header = (
            f"{self.origin.name} {start} to "
            f"{self.destination.name} {end} "
            f"({self.duration})"
        )
        if verbosity >= 1:
            header += (
                f"\nDistance: {self.distance():.1f} Km | "
                f"Transfers: {self.transfers} | "
                f"Avg speed: {int(self.average_speed())} Km/h"
            )
        if model:
            total_co2 = model.estimate_route(self)
            header += f" | Estimated CO2: {total_co2/1000:.2f} Kg ({total_co2/(self.distance()):.2f} g/Km)"
        lines = [header]
        for leg in self.legs:
            lines.append(leg.summary(verbosity, model))
        if verbosity >= 2:
            if dist := self.direct_distance():
                distance_compare = (
                    f"Geodesic Distance: {dist:.1f} Km | "
                    f"Excess: {self.distance()-dist:.1f} Km | "
                    f"tortuosity: {self.tortuosity():.2f} %\n"
                )
                lines[0] = lines[0].replace("Distance", f"{distance_compare}Rail Distance")
            if fastest := self.fastest_segment():
                lines.append(
                    f"Fastest segment: "
                    f"{fastest['from']} to {fastest['to']} "
                    f"({int(fastest['speed'])} Km/h)"
                )
            if dwell := self.longest_dwell():
                station, time = dwell
                lines.append(
                    f"Longest dwell: {station} ({time})"
                )
        return "\n".join(lines)

class SortMetric(Enum):
    DURATION = "duration"
    WAIT_TIME = "wait time"
    TRAVEL_DISTANCE = "travel time"
    TRANSFERS = "transfers"
    RELIABILITY = "reliability"
    WALK_DISTANCE = "walk time"
    TORTUOSITY = "tortuosity"
    VIA_TORTUOSITY = "via_tortuosity"
    EMISSIONS = "emissions"
    CO2_INTENSITY = "co2 intensity"

class SortMode:
    def __init__(self, *metrics: str):
        seen = []
        for m in metrics:
            if m not in seen:
                seen.append(m)
        self._metrics = tuple(seen)

    def __add__(self, other: SortMode) -> SortMode:
        if not isinstance(other, SortMode):
            return NotImplemented
        return SortMode(*(self._metrics + other._metrics))

    def __iter__(self):
        return iter(self._metrics)

    def __repr__(self):
        return f"SortMode{self._metrics}"

DURATION = SortMode(SortMetric.DURATION)
WALK_DISTANCE = SortMode(SortMetric.WALK_DISTANCE)
TRAVEL_DISTANCE = SortMode(SortMetric.TRAVEL_DISTANCE)
WAIT_TIME = SortMode(SortMetric.WAIT_TIME)
RELIABILITY = SortMode(SortMetric.RELIABILITY)
TRANSFERS = SortMode(SortMetric.TRANSFERS)
tortuosity = SortMode(SortMetric.TORTUOSITY)
VIA_tortuosity = SortMode(SortMetric.VIA_TORTUOSITY)
EMISSIONS = SortMode(SortMetric.EMISSIONS)
CO2_INTENSITY = SortMode(SortMetric.CO2_INTENSITY)

def compute_metric(metric: SortMetric, route: Route, emissions: float | None = None) -> float:
    match metric:
        case SortMetric.DURATION:
            return route.duration.total_seconds()
        case SortMetric.WAIT_TIME:
            dwell = route.longest_dwell()
            return dwell[1].total_seconds() if dwell else 0
        case SortMetric.RELIABILITY:
            dwell = route.shortest_dwell()
            return dwell[1].total_seconds() if dwell else 0
        case SortMetric.TRANSFERS:
            return route.transfers
        case SortMetric.WALK_DISTANCE:
            return route.walk_distance()
        case SortMetric.TRAVEL_DISTANCE:
            return route.transfer_distance()
        case SortMetric.TORTUOSITY:
            return route.tortuosity()
        case SortMetric.VIA_TORTUOSITY:
            return route.via_tortuosity()
        case SortMetric.EMISSIONS:
            if emissions is None:
                raise ValueError("Emissions metric requires emissions value")
            return emissions
        case SortMetric.CO2_INTENSITY:
            if emissions is None:
                raise ValueError("CO2 intensity metric requires emissions value")
            return emissions / distance if (distance := route.distance()) > 0 else 0.0
    raise ValueError(f"Unknown metric {metric}")

class TransitClient:
    API_BASE = "https://api.transitous.org/api"
    TRAIN_MODES = "HIGHSPEED_RAIL,LONG_DISTANCE,NIGHT_RAIL,REGIONAL_FAST_RAIL,REGIONAL_RAIL,SUBURBAN,SUBWAY,TRAM"

    TRAVEL_ALL = "TRANSIT"
    TRAVEL_RAIL = "RAIL,REGIONAL_RAIL,REGIONAL_FAST_RAIL,HIGHSPEED_RAIL,NIGHT_RAIL,SUBURBAN"
    TRAVEL_RAIL_FAST = "HIGHSPEED_RAIL,REGIONAL_FAST_RAIL,NIGHT_RAIL"
    TRAVEL_PUBLIC = "RAIL,REGIONAL_RAIL,HIGHSPEED_RAIL,NIGHT_RAIL,BUS,COACH,TRAM,SUBWAY,METRO,FERRY"
    TRAVEL_RAIL_LOCAL = "BUS,TRAM,SUBWAY,METRO,REGIONAL_RAIL,SUBURBAN"
    TRAVEL_LONG_DISTANCE = "HIGHSPEED_RAIL,LONG_DISTANCE,NIGHT_RAIL,AIRPLANE,COACH"
    TRAVEL_LOW_EMMISIONS = "WALK,BIKE,RAIL,REGIONAL_RAIL,HIGHSPEED_RAIL,SUBWAY,TRAM,FERRY"
    TRAVEL_URBAN = "WALK,BIKE,SUBWAY,METRO,TRAM"
    TRAVEL_DOOR_TO_DOOR = "CAR,RIDE_SHARING,RAIL,HIGHSPEED_RAIL,AIRPLANE"
    TRAVEL_SCENIC = "RAIL,REGIONAL_RAIL,FUNICULAR,AERIAL_LIFT,CABLE_CAR,NIGHT_RAIL"
    TRAVEL_SKYE = "RAIL,REGIONAL_RAIL,REGIONAL_FAST_RAIL,HIGHSPEED_RAIL,NIGHT_RAIL,SUBURBAN,SUBWAY,TRAM,METRO,WALK"
    TRAVEL_SKYE_BUSINESS = "RAIL,REGIONAL_RAIL,REGIONAL_FAST_RAIL,HIGHSPEED_RAIL,NIGHT_RAIL,SUBURBAN,SUBWAY,TRAM,METRO,BUS,COACH,AIRPLANE,WALK"

    def __init__(self, itineraries:int=5, search_window:int=7200):
        self.itineraries = itineraries
        self.search_window = search_window

    def _cache_key(self, url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()

    def get(self, url: str, params: dict[str, Any]) -> dict[str, str]:
        full_url = f"{self.API_BASE}/{url}"
        if params:
            full_url += f"?{urlencode(params, doseq=True)}"

        key = self._cache_key(full_url)
        cache_file = CACHE_DIR / f"{key}.json"
        if cache_file.exists():
            return json.loads(cache_file.read_text())

        response = get(full_url)
        if response.status_code == 404:
            raise ValueError(f"Nothing found for {url}")
        elif response.status_code != 200:
            response.raise_for_status()

        data = response.json()
        cache_file.write_text(json.dumps(data))
        return data

    def search_locations(self, name, **kwargs) -> list[Location]:
        data = self.get(
            "v1/geocode",
            {
                "text":name,
                "language":"en",
                **kwargs
            })
        return [Location.from_json(location) for location in data]

    def exact(self, function: Callable[[str], list[Location]], name: str, ) -> Location:
        locations = function(name)
        for loc in locations:
            if loc.name == name:
                return loc
        return locations[0]

    def search_address(self, name: str) -> list[Location]:
        return self.search_locations(name, type="ADDRESS")

    def search_place(self, name: str) -> list[Location]:
        return self.search_locations(name, type="PLACE")

    def search_stations(self, name: str) -> list[Location]:
        return self.search_locations(name, type="STOP", mode=self.TRAIN_MODES)

    def _normalise_modes(self, modes: str | list[str]) -> str:
        if isinstance(modes, str):
            return modes
        flat = []
        for m in modes:
            flat.extend(m.split(","))
        return ",".join(sorted(set(flat)))

    def _resolve_locations(
        self,
        places: Location | str | list[Location | str] | None
    ) -> list[Location] | None:
        if places is None:
            return None
        if not isinstance(places, list):
            places = [places]
        resolved = []
        for p in places:
            if isinstance(p, Location):
                resolved.append(p)
            else:
                resolved.append(self.exact(self.search_stations, p))
        return resolved

    def _resolve_location_names(self, places: Location | str | list[Location | str] | None) -> list[str]:
        if places is None:
            return ""
        elif isinstance(places, Location):
            return places.name
        elif isinstance(places, str):
            return places
        return [
            p if isinstance(p, str) else p.name for p in places
        ]

    def _resolve_location_search(self, places: Location | str | list[Location | str] | None) -> list[str]:
        if places is None:
            return ""
        return [p.search for p in self._resolve_locations(places)]

    def _route_contains_avoid(self, route: Route, avoid_names: set[str]) -> bool:
        return bool(set(route.stop_names) & avoid_names)

    def _filter_avoid(self, routes: list[Route], avoid: Location | str | list[Location | str]) -> list[Route]:
        avoid_places = set() if avoid is None else set(self._resolve_location_names(avoid))
        return [
            r for r in routes
            if not self._route_contains_avoid(r, avoid_places)
        ]

    def _deduplicate_routes(self, routes: list[Route]) -> list[Route]:
        seen = set()
        unique = []
        for route in routes:
            h = route.signature_hash
            if h not in seen:
                seen.add(h)
                unique.append(route)
        return unique

    def _sort_routes(self, routes: list[Route], mode: SortMode, model: EmissionsModel | None = None) -> list[Route]:
        if mode is None:
            return self._deduplicate_routes(routes)

        return sorted(self._deduplicate_routes(routes), key=lambda r: tuple(
            compute_metric(
                metric,
                r,
                model.estimate_route(r) if model else None
            )
            for metric in mode
        ))

    def _find_routes(
            self,
            start: Location,
            end: Location,
            depart_after: Time | datetime | None = None,
            arrive_before: Time | datetime | None = None,
            via: Location | str |list[Location | str] | None = None,
            avoid: Location | str | list[Location | str] | None = None,
            modes: str | list[str] = "TRANSIT",
            model: EmissionsModel | None = None,
            sort: SortMode = TRANSFERS + DURATION,
            adjust_time: bool = False,
            method: str = "RAPTOR,PONG",
        ) -> list[Route]:
        assert (depart_after is None)^(arrive_before is None), "Provide either a departure or arrival time."
        assert via is None or len(via) <=2, "Cannot have more than 2 stops via."
        methods = set(method.split(",")).intersection(("RAPTOR", "PONG", "TB"))
        assert methods, "Must supply at least one method: RAPTOR, PONG, or TB"

        if len(methods) > 1:
            routes = []
            for mthd in methods:
                routes.extend(self._find_routes(
                    start=start, end=end, depart_after=depart_after, arrive_before=arrive_before,
                    via=via, avoid=avoid, modes=modes, model=model, sort=None, adjust_time=adjust_time, method=mthd
                ))
            return self._sort_routes(routes, sort, model)

        params = {
            "fromPlace":start.search,
            "toPlace":end.search,
            "searchWindow": self.search_window,
            "itineraries": self.itineraries,
            "algorithm": method,
        }
        if via:
            params["via"]=",".join(self._resolve_location_search(via))

        if isinstance(modes, str):
            params["transitModes"] = modes
        else:
            params["transitModes"] = self._normalise_modes(modes)

        if depart_after is not None:
            if isinstance(depart_after, datetime):
                params["time"] = Time(depart_after.astimezone(start.timezone), start.timezone)
            else:
                params["time"] = depart_after
        else:
            if isinstance(arrive_before, datetime):
                params["time"] = Time(arrive_before.astimezone(end.timezone), end.timezone)
            else:
                params["time"] = arrive_before
            params["arriveBy"] = "true"

        if adjust_time:
            params["time"] = params["time"].closest_past_equivelent.format
        else:
            params["time"] = params["time"].format

        data = self.get(
            "v5/plan",
            params
        )
        routes = self._filter_avoid(
            routes=[Route.from_json(start, end, route) for route in data["itineraries"]],
            avoid=avoid or [],
        )
        return self._sort_routes(routes, sort, model)

    def routes_between(
        self,
        start: Location,
        end: Location,
        depart_after: Time | datetime | None = None,
        arrive_before: Time | datetime | None = None,
        via: Location | str |list[Location | str] | None = None,
        avoid: Location | str | list[Location | str] | None = None,
        modes: str | list[str] = "TRANSIT",
        model: EmissionsModel | None = None,
        sort: SortMode = TRANSFERS + DURATION,
        adjust_time: bool = False,
        method: str = "RAPTOR,PONG"
    ) -> list[Route] | None:
        VIA = self._resolve_locations(via)
        if VIA is None or len(VIA) <= 2:
            return self._find_routes(
                start=start,
                end=end,
                depart_after=depart_after,
                arrive_before=arrive_before,
                via=VIA,
                avoid=avoid,
                modes=modes,
                model=model,
                sort=sort,
                adjust_time=adjust_time,
                method=method,
            )

        found_routes: list[Route] = []
        all_visits: list[Location] = [start] + VIA + [end]
        for intermediate_start, intermediate_end in zip(all_visits[:-1], all_visits[1:]):
            intermediate = []
            # first pass is special
            if not found_routes:
                intermediate = self._find_routes(
                    start=intermediate_start,
                    end=intermediate_end,
                    depart_after=depart_after,
                    arrive_before=arrive_before,
                    avoid=avoid,
                    modes=modes,
                    model=model,
                    sort=sort,
                    adjust_time=adjust_time,
                    method=method,
                )
            elif depart_after is not None:
                for route in found_routes:
                    intermediate.extend(
                        self.onward_route(
                            route,
                            end=intermediate_end,
                            avoid=avoid,
                            modes=modes,
                            model=model,
                            sort=sort,
                            method=method,
                        )
                    )
            elif arrive_before is not None:
                for route in found_routes:
                    intermediate.extend(
                        self.backward_route(
                            route,
                            start=intermediate_start,
                            avoid=avoid,
                            modes=modes,
                            model=model,
                            sort=sort,
                            method=method,
                        )
                    )
            else:
                raise ValueError("Could not determine arrival/departure time")
            found_routes = intermediate
            intermediate = []
        return self._sort_routes(found_routes, sort, model)

    def onward_route(
            self,
            previous_route: Route,
            end: Location,
            transfer_time: Time | datetime | timedelta | None = None,
            via: Location | str |list[Location | str] | None = None,
            avoid: Location | str | list[Location | str] | None = None,
            modes: str | list[str] = "TRANSIT",
            model: EmissionsModel | None = None,
            sort: SortMode = TRANSFERS + DURATION,
            method: str = "RAPTOR,PONG",
        ) -> list[Route] | None:
        if transfer_time is None:
            transfer_departure = previous_route.arrival
        elif isinstance(transfer_time, Time):
            transfer_departure = transfer_time
        elif isinstance(transfer_time, datetime):
            tz = previous_route.arrival.time.tzinfo
            transfer_departure = Time(transfer_time.astimezone(tz), tz)
        elif isinstance(transfer_time, timedelta):
            transfer_departure = previous_route.arrival + transfer_time
        else:
            raise ValueError(f"transfer time cannot be {type(transfer_time)}")

        if next_routes := self.routes_between(
            start=previous_route.destination,
            end=end,
            depart_after=transfer_departure,
            via=via,
            avoid=avoid,
            modes=modes,
            model=model,
            sort=sort,
            adjust_time=False,
            method=method,
        ):
            return [previous_route + r for r in next_routes]
        raise ValueError(f"No route onwards route from {previous_route.destination} to {end} could be found.")

    def backward_route(
            self,
            following_route: Route,
            start: Location,
            transfer_time: Time | datetime | timedelta | None = None,
            via: Location | str |list[Location | str] | None = None,
            avoid: Location | str | list[Location | str] | None = None,
            modes: str | list[str] = "TRANSIT",
            model: EmissionsModel | None = None,
            sort: SortMode = TRANSFERS + DURATION,
            method: str = "RAPTOR,PONG",
        ) -> list[Route] | None:
        if transfer_time is None:
            transfer_arrival = following_route.departure
        elif isinstance(transfer_time, Time):
            transfer_arrival = transfer_time
        elif isinstance(transfer_time, datetime):
            tz = following_route.departure.time.tzinfo
            transfer_arrival = Time(transfer_time.astimezone(tz), tz)
        elif isinstance(transfer_time, timedelta):
            transfer_arrival = following_route.departure - transfer_time
        else:
            raise ValueError(f"transfer time cannot be {type(transfer_time)}")

        if next_routes := self.routes_between(
            start=start,
            end=following_route.origin,
            arrive_before=transfer_arrival,
            via=via,
            avoid=avoid,
            modes=modes,
            model=model,
            sort=sort,
            adjust_time=False,
            method=method,
        ):
            return [r + following_route for r in next_routes]
        raise ValueError(f"No route backwards route from {start} to {following_route.origin} could be found.")


if __name__ == "__main__":
    from emissions import CategoryBasedEmissions

    transport = TransitClient(10, 7200)

    origin = transport.exact(transport.search_stations, "Havant")
    destination = transport.exact(transport.search_stations, "St. Pancras")

    emissions = CategoryBasedEmissions()

    routes = transport.routes_between(
        origin,
        destination,
        arrive_before=datetime(2026,5,10,4),
        via=["Three Bridges"],
        # avoid=["London Victoria", "Lille Europe", "Lille Flandres"],
        modes=TransitClient.TRAVEL_SKYE,
        sort=EMISSIONS+TRANSFERS+DURATION,
        model=emissions,
    )

    for route in routes:
        print(route.summary(1, emissions))
        print()
