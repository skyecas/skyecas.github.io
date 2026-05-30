from __future__ import annotations
from enum import Enum
from rail_planner import Leg, Route

class EmissionsModel:
    def estimate_leg(self, leg: Leg) -> float:
        raise NotImplementedError

    def estimate_route(self, route: Route) -> float:
        return sum(self.estimate_leg(leg) for leg in route.legs)


class CategoryBasedEmissions(EmissionsModel):
    class EmissionCategory(str, Enum):
        ZERO = "zero"
        VERY_LOW = "very_low"
        LOW = "low"
        MEDIUM = "medium"
        HIGH = "high"

    MODE_TO_CATEGORY = {
        # Human powered
        "WALK": EmissionCategory.ZERO,
        "BIKE": EmissionCategory.ZERO,

        # Mostly electric urban
        "TRAM": EmissionCategory.VERY_LOW,
        "SUBWAY": EmissionCategory.VERY_LOW,
        "METRO": EmissionCategory.VERY_LOW,
        "CABLE_CAR": EmissionCategory.VERY_LOW,
        "FUNICULAR": EmissionCategory.VERY_LOW,
        "AERIAL_LIFT": EmissionCategory.VERY_LOW,
        "AREAL_LIFT": EmissionCategory.VERY_LOW,  # typo variant

        # Rail family
        "RAIL": EmissionCategory.LOW,
        "REGIONAL_RAIL": EmissionCategory.LOW,
        "REGIONAL_FAST_RAIL": EmissionCategory.LOW,
        "SUBURBAN": EmissionCategory.LOW,
        "HIGHSPEED_RAIL": EmissionCategory.LOW,
        "NIGHT_RAIL": EmissionCategory.LOW,
        "LONG_DISTANCE": EmissionCategory.LOW,

        # Road public
        "BUS": EmissionCategory.MEDIUM,
        "COACH": EmissionCategory.MEDIUM,
        "FERRY": EmissionCategory.MEDIUM,

        # Individual motorised
        "CAR": EmissionCategory.HIGH,
        "CAR_PARKING": EmissionCategory.HIGH,
        "CAR_DROPOFF": EmissionCategory.HIGH,
        "RIDE_SHARING": EmissionCategory.HIGH,
        "RENTAL": EmissionCategory.HIGH,
        "ODM": EmissionCategory.HIGH,
        "FLEX": EmissionCategory.HIGH,

        # Aviation
        "AIRPLANE": EmissionCategory.HIGH,
    }

    CATEGORY_CO2 = {
        EmissionCategory.ZERO: 0,
        EmissionCategory.VERY_LOW: 5,
        EmissionCategory.LOW: 20,
        EmissionCategory.MEDIUM: 80,
        EmissionCategory.HIGH: 250,
    }

    def estimate_leg(self, leg) -> float:
        mode = leg.mode
        category = self.MODE_TO_CATEGORY.get(mode, self.EmissionCategory.MEDIUM)
        rate = self.CATEGORY_CO2[category]
        return rate * leg.distance()
