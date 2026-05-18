from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

@dataclass
class Time:
    _time: datetime
    timezone: ZoneInfo

    @property
    def time(self) -> datetime:
        return self._time.astimezone(self.timezone)

    def __add__(self, other: timedelta) -> Time:
        if isinstance(other, timedelta):
            return Time(self.time + other, self.timezone)
        else:
            raise TypeError(f"Cannot add {type(self)} to {type(other)}")

    def __sub__(self, other: Time | datetime | timedelta) -> timedelta | Time:
        if isinstance(other, timedelta):
            return Time(self.time - other, self.timezone)
        elif isinstance(other, datetime):
            return self.time - other.astimezone(self.time.tzinfo)
        elif isinstance(other, Time):
            return self.time - other.time
        else:
            raise TypeError(f"Cannot subtract {type(self)} from {type(other)}")

    def __rsub__(self, other: Time | datetime) -> timedelta:
        if isinstance(other, datetime):
            return other.astimezone(self.time.tzinfo) - self.time
        elif isinstance(other, Time):
            return other.time - self.time
        else:
            raise TypeError(f"Cannot subtract {type(other)} from {type(self)}")

    def __eq__(self, other: Time | datetime) -> bool:
        if isinstance(other, datetime):
            return self.time == other.astimezone(self.time.tzinfo)
        elif isinstance(other, Time):
            return self.time == other.time
        else:
            raise TypeError(f"Cannot compare {type(other)} and {type(self)}")

    def __gt__(self, other: Time | datetime) -> bool:
        if isinstance(other, datetime):
            return self.time > other.astimezone(self.time.tzinfo)
        elif isinstance(other, Time):
            return self.time > other.time
        else:
            raise TypeError(f"Cannot compare {type(other)} and {type(self)}")

    def __ge__(self, other: Time | datetime) -> bool:
        if isinstance(other, datetime):
            return self.time >= other.astimezone(self.time.tzinfo)
        elif isinstance(other, Time):
            return self.time >= other.time
        else:
            raise TypeError(f"Cannot compare {type(other)} and {type(self)}")

    def __lt__(self, other: Time | datetime) -> bool:
        if isinstance(other, datetime):
            return self.time < other.astimezone(self.time.tzinfo)
        elif isinstance(other, Time):
            return self.time < other.time
        else:
            raise TypeError(f"Cannot compare {type(other)} and {type(self)}")

    def __le__(self, other: Time | datetime) -> bool:
        if isinstance(other, datetime):
            return self.time <= other.astimezone(self.time.tzinfo)
        elif isinstance(other, Time):
            return self.time <= other.time
        else:
            raise TypeError(f"Cannot compare {type(other)} and {type(self)}")

    @property
    def format(self) -> str:
        return self.time.astimezone(timezone.utc).replace(second=0, tzinfo=None).isoformat(timespec="seconds")+"Z"

    @classmethod
    def from_string(cls, text: str, tz: str | ZoneInfo | None = None):
        return Time(
            datetime.fromisoformat(text),
            ZoneInfo(tz) if isinstance(tz, str) else tz
        )

    def now(self) -> Time:
        return Time(datetime.now(), self.timezone)

    @property
    def as_today(self) -> Time:
        return Time(
            datetime.now().replace(
                hour=self.time.hour,
                minute=self.time.minute,
                second=self.time.second,
                microsecond=self.time.microsecond
            ),
            self.timezone
        )

    @property
    def closest_past_equivelent(self) -> Time:
        as_today = self.as_today
        if self.now().time > as_today.time:
            return as_today
        return Time(as_today.time - timedelta(days=7), self.timezone)

    @property
    def closest_future_equivelent(self) -> Time:
        as_today = self.as_today
        if self.now().time < as_today.time:
            return as_today
        return Time(as_today.time + timedelta(days=7), self.timezone)

    @property
    def next_minute(self) -> Time:
        return Time(self.time.replace(second=0)+timedelta(seconds=60), self.timezone)
