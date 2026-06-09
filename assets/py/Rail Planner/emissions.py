from __future__ import annotations
from rail_planner import Leg, Route


# g/km per passenger — UK DEFRA / industry-informed factors (2024-25)
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
	"RIDE_SHARING": 170.0,
	"RENTAL": 170.0,
	"ODM": 170.0,
	"FLEX": 170.0,
	"AIRPLANE": 250.0,
}

# Rail rates (g/km per passenger) by traction type
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
	"NIGHT_RAIL": 60.0,
	"LONG_DISTANCE": 50.0,
	"SUBURBAN": 50.0,
}

# Default blended rate for unknown operators
RAIL_BLENDED: dict[str, float] = {
	"RAIL": 35.0,
	"REGIONAL_RAIL": 41.0,
	"REGIONAL_FAST_RAIL": 30.0,
	"HIGHSPEED_RAIL": 6.0,
	"NIGHT_RAIL": 50.0,
	"LONG_DISTANCE": 30.0,
	"SUBURBAN": 35.0,
}

# UK TOC → primary traction type
# https://en.wikipedia.org/wiki/List_of_train_operating_companies_in_the_United_Kingdom
ELECTRIC_OPERATORS: set[str] = {
	"Southern",
	"Thameslink",
	"Great Northern",
	"Southeastern",
	"South Western Railway",
	"Merseyrail",
	"c2c",
	"Greater Anglia",
	"Gatwick Express",
	"Heathrow Express",
	"Stansted Express",
	"London Overground",
	"Elizabeth Line",
	"Eurostar",
	"Avanti West Coast",
	"LNER",
	"Hull Trains",
	"East Midlands Railway",
}

DIESEL_OPERATORS: set[str] = {
	"CrossCountry",
	"Chiltern Railways",
	"Transport for Wales",
	"Caledonian Sleeper",
	"Grand Central",
	"ScotRail",
	"Northern",
	"TransPennine Express",
	"West Midlands Trains",
	"Night Riviera",
}

BI_MODE_OPERATORS: set[str] = {
	"Great Western Railway",
}


def _traction(mode: str, operator: str) -> float:
	if operator in ELECTRIC_OPERATORS:
		table = RAIL_ELECTRIC
	elif operator in DIESEL_OPERATORS:
		table = RAIL_DIESEL
	elif operator in BI_MODE_OPERATORS:
		table = RAIL_BI_MODE
	else:
		table = RAIL_BLENDED
	return table.get(mode, RAIL_BLENDED.get(mode, 35.0))


class EmissionsModel:
	def estimate_leg(self, leg: Leg) -> float:
		raise NotImplementedError

	def estimate_route(self, route: Route) -> float:
		return sum(self.estimate_leg(leg) for leg in route.legs)

	def leg_rate(self, leg: Leg) -> float:
		"""Return g/km rate for a leg without multiplying by distance"""
		if leg.mode in MODE_BASE_RATES:
			return MODE_BASE_RATES[leg.mode]
		if leg.mode in RAIL_BLENDED:
			return _traction(leg.mode, getattr(leg, "operator", ""))
		return MODE_BASE_RATES.get("BUS", 105.0)


class OperatorEmissionsModel(EmissionsModel):
	def estimate_leg(self, leg: Leg) -> float:
		return self.leg_rate(leg) * leg.distance()


class CategoryBasedEmissions(EmissionsModel):
	"""Legacy model kept for backwards compatibility"""
	def estimate_leg(self, leg: Leg) -> float:
		from enum import Enum
		class EmissionCategory(str, Enum):
			ZERO = "zero"
			VERY_LOW = "very_low"
			LOW = "low"
			MEDIUM = "medium"
			HIGH = "high"
		MODE_TO_CATEGORY = {
			"WALK": EmissionCategory.ZERO,
			"BIKE": EmissionCategory.ZERO,
			"TRAM": EmissionCategory.VERY_LOW,
			"SUBWAY": EmissionCategory.VERY_LOW,
			"METRO": EmissionCategory.VERY_LOW,
			"CABLE_CAR": EmissionCategory.VERY_LOW,
			"FUNICULAR": EmissionCategory.VERY_LOW,
			"AERIAL_LIFT": EmissionCategory.VERY_LOW,
			"AREAL_LIFT": EmissionCategory.VERY_LOW,
			"RAIL": EmissionCategory.LOW,
			"REGIONAL_RAIL": EmissionCategory.LOW,
			"REGIONAL_FAST_RAIL": EmissionCategory.LOW,
			"SUBURBAN": EmissionCategory.LOW,
			"HIGHSPEED_RAIL": EmissionCategory.LOW,
			"NIGHT_RAIL": EmissionCategory.LOW,
			"LONG_DISTANCE": EmissionCategory.LOW,
			"BUS": EmissionCategory.MEDIUM,
			"COACH": EmissionCategory.MEDIUM,
			"FERRY": EmissionCategory.MEDIUM,
			"CAR": EmissionCategory.HIGH,
			"CAR_PARKING": EmissionCategory.HIGH,
			"CAR_DROPOFF": EmissionCategory.HIGH,
			"RIDE_SHARING": EmissionCategory.HIGH,
			"RENTAL": EmissionCategory.HIGH,
			"ODM": EmissionCategory.HIGH,
			"FLEX": EmissionCategory.HIGH,
			"AIRPLANE": EmissionCategory.HIGH,
		}
		CATEGORY_CO2 = {
			EmissionCategory.ZERO: 0,
			EmissionCategory.VERY_LOW: 5,
			EmissionCategory.LOW: 20,
			EmissionCategory.MEDIUM: 80,
			EmissionCategory.HIGH: 250,
		}
		category = MODE_TO_CATEGORY.get(leg.mode, EmissionCategory.MEDIUM)
		rate = CATEGORY_CO2[category]
		return rate * leg.distance()
