from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


# g/km per passenger for non-rail modes. Values are operational unless uplifted
# by _lifecycle_uplift().
MODE_BASE_RATES: dict[str, float] = {
    "WALK": 0.0,
    "BIKE": 0.0,
    "TRAM": 7.0,
    "SUBWAY": 4.0,
    "METRO": 4.0,
    "CABLE_CAR": 5.0,
    "FUNICULAR": 5.0,
    "AERIAL_LIFT": 5.0,
    "AREAL_LIFT": 5.0,
    "BUS": 105.0,
    "COACH": 27.0,
    "FERRY": 120.0,
    "CAR": 170.0,
    "CAR_PARKING": 170.0,
    "CAR_DROPOFF": 170.0,
    "RIDE_SHARING": 120.0,
    "RENTAL": 170.0,
    "ODM": 170.0,
    "FLEX": 170.0,
    "AIRPLANE": 250.0,
}

RAIL_MODES = {
    "RAIL",
    "REGIONAL_RAIL",
    "REGIONAL_FAST_RAIL",
    "HIGHSPEED_RAIL",
    "NIGHT_RAIL",
    "LONG_DISTANCE",
    "SUBURBAN",
}

# Rail rates (g/km per passenger) by traction type.
RAIL_ELECTRIC: dict[str, float] = {
    "RAIL": 20.0,
    "REGIONAL_RAIL": 25.0,
    "REGIONAL_FAST_RAIL": 15.0,
    "HIGHSPEED_RAIL": 6.0,
    "NIGHT_RAIL": 20.0,
    "LONG_DISTANCE": 15.0,
    "SUBURBAN": 25.0,
}

RAIL_DIESEL: dict[str, float] = {
    "RAIL": 80.0,
    "REGIONAL_RAIL": 85.0,
    "REGIONAL_FAST_RAIL": 75.0,
    "HIGHSPEED_RAIL": 80.0,
    "NIGHT_RAIL": 100.0,
    "LONG_DISTANCE": 80.0,
    "SUBURBAN": 70.0,
}

RAIL_BI_MODE: dict[str, float] = {
    "RAIL": 50.0,
    "REGIONAL_RAIL": 55.0,
    "REGIONAL_FAST_RAIL": 45.0,
    "HIGHSPEED_RAIL": 55.0,
    "NIGHT_RAIL": 60.0,
    "LONG_DISTANCE": 50.0,
    "SUBURBAN": 50.0,
}

RAIL_BLENDED: dict[str, float] = {
    "RAIL": 35.0,
    "REGIONAL_RAIL": 41.0,
    "REGIONAL_FAST_RAIL": 30.0,
    "HIGHSPEED_RAIL": 15.0,
    "NIGHT_RAIL": 50.0,
    "LONG_DISTANCE": 30.0,
    "SUBURBAN": 35.0,
}

# Approximate 2024 grid intensity, gCO2e/kWh. Used to adjust electric rail by
# country where the route geometry gives us a plausible split.
GRID_INTENSITY_G_PER_KWH: dict[str, float] = {
    "United Kingdom": 162.0,
    "Ireland": 332.0,
    "France": 56.0,
    "Belgium": 139.0,
    "Netherlands": 300.0,
    "Germany": 380.0,
    "Switzerland": 42.0,
    "Austria": 96.0,
    "Spain": 165.0,
    "Italy": 260.0,
    "Denmark": 154.0,
    "Sweden": 21.0,
    "Norway": 18.0,
    "Luxembourg": 180.0,
    "Czechia": 430.0,
    "Poland": 650.0,
    "Portugal": 190.0,
    "Finland": 90.0,
}

ELECTRIC_KWH_PER_PKM: dict[str, float] = {
    "RAIL": 0.060,
    "REGIONAL_RAIL": 0.070,
    "REGIONAL_FAST_RAIL": 0.050,
    "HIGHSPEED_RAIL": 0.040,
    "NIGHT_RAIL": 0.070,
    "LONG_DISTANCE": 0.050,
    "SUBURBAN": 0.080,
}

OPERATOR_TRACTION: dict[str, str] = {
    "southern": "electric",
    "thameslink": "electric",
    "great northern": "electric",
    "southeastern": "electric",
    "south western railway": "electric",
    "merseyrail": "electric",
    "c2c": "electric",
    "greater anglia": "electric",
    "gatwick express": "electric",
    "heathrow express": "electric",
    "stansted express": "electric",
    "london overground": "electric",
    "elizabeth line": "electric",
    "eurostar": "electric",
    "tgv": "electric",
    "sncf": "electric",
    "ouigo": "electric",
    "thalys": "electric",
    "eurocity": "electric",
    "intercity express": "electric",
    "ice": "electric",
    "db fernverkehr": "electric",
    "sbb": "electric",
    "ns": "electric",
    "sncb": "electric",
    "nmbs": "electric",
    "avanti west coast": "electric",
    "lner": "electric",
    "hull trains": "electric",
    "east midlands railway": "bi-mode",
    "great western railway": "bi-mode",
    "crosscountry": "diesel",
    "chiltern railways": "diesel",
    "transport for wales": "diesel",
    "caledonian sleeper": "diesel",
    "grand central": "diesel",
    "scotrail": "diesel",
    "northern": "diesel",
    "transpennine express": "bi-mode",
    "west midlands trains": "diesel",
    "night riviera": "diesel",
}

OPERATOR_RATE_OVERRIDES: dict[str, tuple[float, str]] = {
    "eurostar": (4.0, "operator high-speed electric estimate"),
    "tgv": (5.0, "operator high-speed electric estimate"),
    "ouigo": (5.0, "operator high-speed electric estimate"),
    "thalys": (6.0, "operator high-speed electric estimate"),
    "ice": (18.0, "operator long-distance electric estimate"),
    "intercity express": (18.0, "operator long-distance electric estimate"),
    "sncf": (12.0, "operator electric rail estimate"),
    "sbb": (4.0, "low-carbon grid electric rail estimate"),
    "ns": (8.0, "low-carbon electricity contract estimate"),
    "sncb": (16.0, "operator electric rail estimate"),
    "nmbs": (16.0, "operator electric rail estimate"),
}

COUNTRY_DEFAULT_TRACTION: dict[str, str] = {
    "United Kingdom": "blended",
    "Ireland": "diesel",
    "France": "electric",
    "Belgium": "electric",
    "Netherlands": "electric",
    "Germany": "electric",
    "Switzerland": "electric",
    "Austria": "electric",
    "Spain": "electric",
    "Italy": "electric",
    "Denmark": "electric",
    "Sweden": "electric",
    "Norway": "electric",
}


@dataclass
class EmissionsEstimate:
    distance_km: float
    distance_source: str
    confidence: str
    rate_g_per_km: float
    rate_min_g_per_km: float
    rate_max_g_per_km: float
    kg: float
    min_kg: float
    max_kg: float
    operational_kg: float
    lifecycle_kg: float
    radiative_forcing_kg: float
    traction: str
    traction_source: str
    countries: list[str]
    grid_intensity_g_per_kwh: float | None
    lifecycle_uplift_pct: float
    radiative_forcing_multiplier: float
    assumptions: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def _operator_key(operator: str) -> str:
    return (operator or "").strip().lower()


def _operator_contains(operator: str, table: dict[str, object]) -> str | None:
    op = _operator_key(operator)
    for key in table:
        if key in op:
            return key
    return None


def _avg_grid_intensity(countries: list[str]) -> float | None:
    values = [
        GRID_INTENSITY_G_PER_KWH[c] for c in countries if c in GRID_INTENSITY_G_PER_KWH
    ]
    if not values:
        return None
    return sum(values) / len(values)


def _distance_confidence(distance_source: str, traction_source: str) -> str:
    if distance_source == "osm" and traction_source in {
        "operator",
        "operator-rate",
        "osm",
    }:
        return "high"
    if distance_source in {"osm", "transitous", "scheduled"}:
        return "medium"
    return "low"


def _distance_uncertainty(confidence: str) -> float:
    return {"high": 0.08, "medium": 0.18, "low": 0.45}.get(confidence, 0.3)


def _traction_uncertainty(traction: str, traction_source: str) -> float:
    if traction_source in {"operator", "operator-rate", "osm"}:
        return 0.10
    if traction == "unknown":
        return 0.35
    return 0.22


def _lifecycle_uplift(mode: str) -> float:
    if mode in {"WALK", "BIKE"}:
        return 0.0
    if mode in RAIL_MODES or mode in {"TRAM", "SUBWAY", "METRO"}:
        return 0.12
    if mode == "AIRPLANE":
        return 0.15
    if mode == "FERRY":
        return 0.12
    return 0.08


def _normalise_mode(mode: str) -> str:
    mode = (mode or "RAIL").upper()
    return {
        "TRAIN": "RAIL",
        "HIGH_SPEED": "HIGHSPEED_RAIL",
        "REGIONAL": "REGIONAL_RAIL",
        "PLANE": "AIRPLANE",
        "WALKING": "WALK",
    }.get(mode, mode)


def _rail_rate(
    mode: str, traction: str, countries: list[str]
) -> tuple[float, float | None]:
    grid = _avg_grid_intensity(countries)
    if traction == "electric":
        if grid is not None:
            return grid * ELECTRIC_KWH_PER_PKM.get(mode, 0.06), grid
        return RAIL_ELECTRIC.get(mode, RAIL_ELECTRIC["RAIL"]), None
    if traction == "diesel":
        return RAIL_DIESEL.get(mode, RAIL_DIESEL["RAIL"]), grid
    if traction == "bi-mode":
        return RAIL_BI_MODE.get(mode, RAIL_BI_MODE["RAIL"]), grid
    return RAIL_BLENDED.get(mode, RAIL_BLENDED["RAIL"]), grid


def _infer_rail_traction(operator: str, countries: list[str]) -> tuple[str, str]:
    if key := _operator_contains(operator, OPERATOR_TRACTION):
        return OPERATOR_TRACTION[key], "operator"
    country_tractions = [
        COUNTRY_DEFAULT_TRACTION[c] for c in countries if c in COUNTRY_DEFAULT_TRACTION
    ]
    if country_tractions:
        if all(t == "electric" for t in country_tractions):
            return "electric", "country-default"
        if all(t == "diesel" for t in country_tractions):
            return "diesel", "country-default"
        return "blended", "country-default"
    return "unknown", "mode-default"


class EmissionsModel:
    def estimate_leg(self, leg: Any) -> float:
        raise NotImplementedError

    def estimate_route(self, route: Any) -> float:
        return sum(self.estimate_leg(leg) for leg in route.legs)

    def leg_rate(self, leg: Any) -> float:
        """Return expected g/km rate for a leg without multiplying by distance."""
        return self.estimate_leg_detail(leg).rate_g_per_km

    def estimate_leg_detail(
        self,
        leg: Any,
        *,
        distance_km: float | None = None,
        distance_source: str | None = None,
        countries: list[str] | None = None,
        traction_hint: str | None = None,
    ) -> EmissionsEstimate:
        raise NotImplementedError


class OperatorEmissionsModel(EmissionsModel):
    def estimate_leg(self, leg: Any) -> float:
        return self.estimate_leg_detail(leg).kg * 1000.0

    def estimate_leg_detail(
        self,
        leg: Any,
        *,
        distance_km: float | None = None,
        distance_source: str | None = None,
        countries: list[str] | None = None,
        traction_hint: str | None = None,
    ) -> EmissionsEstimate:
        mode = _normalise_mode(getattr(leg, "mode", "RAIL"))
        operator = getattr(leg, "operator", "") or ""
        countries = list(dict.fromkeys(countries or []))
        distance = float(distance_km if distance_km is not None else leg.distance())
        distance_source = distance_source or (
            "transitous" if getattr(leg, "geometry", None) else "scheduled"
        )
        assumptions = []

        traction = "not-applicable"
        traction_source = "mode"
        grid = None
        if mode in RAIL_MODES:
            if traction_hint:
                traction = traction_hint
                traction_source = "osm"
            elif key := _operator_contains(operator, OPERATOR_RATE_OVERRIDES):
                traction = "electric"
                traction_source = "operator-rate"
            else:
                traction, traction_source = _infer_rail_traction(operator, countries)

            if key := _operator_contains(operator, OPERATOR_RATE_OVERRIDES):
                rate, source = OPERATOR_RATE_OVERRIDES[key]
                assumptions.append(source)
                grid = _avg_grid_intensity(countries)
            else:
                rate, grid = _rail_rate(mode, traction, countries)
                assumptions.append(f"{traction} rail via {traction_source}")
        else:
            rate = MODE_BASE_RATES.get(mode, MODE_BASE_RATES["BUS"])
            if mode == "FERRY":
                assumptions.append("foot-passenger ferry allocation")
            elif mode == "AIRPLANE":
                assumptions.append("short-haul passenger flight factor")
            elif mode in {"CAR", "CAR_PARKING", "CAR_DROPOFF", "RENTAL", "ODM", "FLEX"}:
                assumptions.append("single-occupancy car assumption")

        confidence = _distance_confidence(distance_source, traction_source)
        uncertainty = _distance_uncertainty(confidence) + _traction_uncertainty(
            traction, traction_source
        )
        lifecycle_pct = _lifecycle_uplift(mode)
        rf_multiplier = 1.9 if mode == "AIRPLANE" else 1.0
        operational_kg = rate * distance / 1000.0
        lifecycle_kg = operational_kg * lifecycle_pct
        rf_kg = operational_kg * (rf_multiplier - 1.0)
        total_kg = operational_kg + lifecycle_kg + rf_kg
        min_rate = max(0.0, rate * (1.0 - uncertainty))
        max_rate = rate * (1.0 + uncertainty)
        min_kg = max(0.0, total_kg * (1.0 - uncertainty))
        max_kg = total_kg * (1.0 + uncertainty)

        if (
            countries
            and grid is not None
            and mode in RAIL_MODES
            and traction == "electric"
        ):
            assumptions.append(f"electric rail grid intensity {grid:.0f} gCO2e/kWh")
        if distance_source == "osm":
            assumptions.append("distance from enriched OSM railway geometry")
        elif distance_source == "transitous":
            assumptions.append("distance from Transitous service geometry")
        elif distance_source == "endpoint":
            assumptions.append("distance estimated from endpoints")

        return EmissionsEstimate(
            distance_km=round(distance, 4),
            distance_source=distance_source,
            confidence=confidence,
            rate_g_per_km=round(
                rate * (1.0 + lifecycle_pct + (rf_multiplier - 1.0)), 3
            ),
            rate_min_g_per_km=round(
                min_rate * (1.0 + lifecycle_pct + (rf_multiplier - 1.0)), 3
            ),
            rate_max_g_per_km=round(
                max_rate * (1.0 + lifecycle_pct + (rf_multiplier - 1.0)), 3
            ),
            kg=round(total_kg, 4),
            min_kg=round(min_kg, 4),
            max_kg=round(max_kg, 4),
            operational_kg=round(operational_kg, 4),
            lifecycle_kg=round(lifecycle_kg, 4),
            radiative_forcing_kg=round(rf_kg, 4),
            traction=traction,
            traction_source=traction_source,
            countries=countries,
            grid_intensity_g_per_kwh=round(grid, 1) if grid is not None else None,
            lifecycle_uplift_pct=round(lifecycle_pct * 100.0, 1),
            radiative_forcing_multiplier=rf_multiplier,
            assumptions=assumptions,
        )


class CategoryBasedEmissions(EmissionsModel):
    """Legacy model kept for backwards compatibility."""

    def estimate_leg(self, leg: Any) -> float:
        return self.estimate_leg_detail(leg).kg * 1000.0

    def estimate_leg_detail(
        self,
        leg: Any,
        *,
        distance_km: float | None = None,
        distance_source: str | None = None,
        countries: list[str] | None = None,
        traction_hint: str | None = None,
    ) -> EmissionsEstimate:
        model = OperatorEmissionsModel()
        return model.estimate_leg_detail(
            leg,
            distance_km=distance_km,
            distance_source=distance_source,
            countries=countries,
            traction_hint=traction_hint,
        )
