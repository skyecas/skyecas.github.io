from __future__ import annotations
from math import cos, radians, degrees, acos, tan, atan, sin, asin, atan2, sqrt
from polyline import decode

def hav(rads: int | float) -> float:
    return 0.5 * (1 - cos(rads))

def ahav(x: int | float) -> float:
    return acos(1 - 2*x)

class Angle:
    def __init__(self, deg: int | float | None = None, rad: int | float | None = None):
        assert (deg is None)^(rad is None), "Provide a single degree or radian value"
        self.rad = float(rad) if rad is not None else radians(deg or 0.0)
        self.deg = degrees(self.rad)

    @property
    def radians(self) -> float:
        return self.rad

    @property
    def degrees(self) -> float:
        return self.deg

    def __str__(self):
        return str(self.radians)

    def __repr__(self):
        return str(self)

    def __sub__(self, other: Angle) -> Angle:
        return Angle(self.deg - other.deg)

    def __add__(self, other: Angle) -> Angle:
        return Angle(self.deg + other.deg)

    def __eq__(self, other: Angle) -> bool:
        return self.rad == other.rad

    @property
    def cos(self) -> float:
        return cos(self.rad)

    @property
    def sin(self) -> float:
        return sin(self.rad)

    @property
    def tan(self) -> float:
        return tan(self.rad)

    @property
    def hav(self) -> float:
        return hav(self.rad)

    @classmethod
    def acos(cls, value: float) -> Angle:
        return Angle(rad=acos(value))

    @classmethod
    def asin(cls, value: float) -> Angle:
        return Angle(rad=asin(value))

    @classmethod
    def atan(cls, value: float) -> Angle:
        return Angle(rad=atan(value))

    @classmethod
    def ahav(cls, value: float) -> Angle:
        return Angle(rad=ahav(value))

class Position:
    def __init__(self, latitude: Angle | float | int = 0, longitude: Angle | float | int = 0):
        self.lat = Angle(deg=latitude) if not isinstance(latitude, Angle) else latitude
        self.lon = Angle(deg=longitude) if not isinstance(longitude, Angle) else longitude

    @classmethod
    def from_json(cls, json: dict[str, str]) -> Position:
        return Position(
            float(json["lat"]),
            float(json["lon"]),
        )

    @property
    def latitude(self) -> Angle:
        return self.lat

    @property
    def longitude(self) -> Angle:
        return self.lon

    def __str__(self):
        return f"{self.lat.deg}N, {self.lon.deg}"

    def __repr__(self):
        return str(self)

    def __sub__(self, other: Position):
        return Position(self.lat - other.lat, self.lon - other.lon)

    def __add__(self, other: Position):
        return Position(self.lat + other.lat, self.lon + other.lon)

    def __eq__(self, other: Position) -> bool:
        return self.lat == other.lat and self.lon == other.lon

    def haversine_angle(self, other: Position) -> Angle:
        d_pos = self-other
        return Angle.ahav(d_pos.lat.hav + self.lat.cos*other.lat.cos*d_pos.lon.hav)

    def haversine_dist(self, other: Position) -> float:
        return 6371 * self.haversine_angle(other).radians

    def vincenty_dist(self, other: Position) -> float | None:
        # WGS 84
        equitorial = 6378137  # meters
        polar = 6356752.314245  # meters; b = (1 - f)a
        flattening = 1 / 298.257223563
        MAX_ITERATIONS = 200
        CONVERGENCE_THRESHOLD = 1e-12

        if self == other:
            return 0.0

        U1 = atan((1 - flattening) * self.lat.tan)
        U2 = atan((1 - flattening) * other.lat.tan)
        L = (other - self).longitude.radians
        Lambda = L

        sinU1 = sin(U1)
        cosU1 = cos(U1)
        sinU2 = sin(U2)
        cosU2 = cos(U2)

        for _ in range(MAX_ITERATIONS):
            sinLambda = sin(Lambda)
            cosLambda = cos(Lambda)
            sinSigma = sqrt((cosU2 * sinLambda) ** 2 +
                                (cosU1 * sinU2 - sinU1 * cosU2 * cosLambda) ** 2)
            if sinSigma == 0:
                return 0.0  # coincident points
            cosSigma = sinU1 * sinU2 + cosU1 * cosU2 * cosLambda
            sigma = atan2(sinSigma, cosSigma)
            sinAlpha = cosU1 * cosU2 * sinLambda / sinSigma
            cosSqAlpha = 1 - sinAlpha ** 2
            try:
                cos2SigmaM = cosSigma - 2 * sinU1 * sinU2 / cosSqAlpha
            except ZeroDivisionError:
                cos2SigmaM = 0
            C = flattening / 16 * cosSqAlpha * (4 + flattening * (4 - 3 * cosSqAlpha))
            LambdaPrev = Lambda
            Lambda = L + (1 - C) * flattening * sinAlpha * (sigma + C * sinSigma *
                                                (cos2SigmaM + C * cosSigma *
                                                    (-1 + 2 * cos2SigmaM ** 2)))
            if abs(Lambda - LambdaPrev) < CONVERGENCE_THRESHOLD:
                break  # successful convergence
        else:
            return None  # failure to converge

        uSq = cosSqAlpha * (equitorial ** 2 - polar ** 2) / (polar ** 2)
        A = 1 + uSq / 16384 * (4096 + uSq * (-768 + uSq * (320 - 175 * uSq)))
        B = uSq / 1024 * (256 + uSq * (-128 + uSq * (74 - 47 * uSq)))
        deltaSigma = B * sinSigma * (cos2SigmaM + B / 4 * (cosSigma *
                    (-1 + 2 * cos2SigmaM ** 2) - B / 6 * cos2SigmaM *
                    (-3 + 4 * sinSigma ** 2) * (-3 + 4 * cos2SigmaM ** 2)))
        s = polar * A * (sigma - deltaSigma)

        return s/1000

    def distance(self, other: Position) -> float:
        return self.vincenty_dist(other) or self.haversine_dist(other)

def polyline_positions(json: dict[str, str]) -> list[Position]:
    polyline = json.get("points")
    precision = json.get("precision")
    if polyline is None or precision is None:
        return []
    return [
        Position(lat, lon)
        for lat, lon in decode(polyline, int(precision))
    ]
