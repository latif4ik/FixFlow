"""Pure business-time calendar (SLA-01/02). No DB, no I/O.

Business time = the intervals configured per local weekday (0 = Monday), minus whole holiday
dates, in the organization's time zone. All instants in/out are timezone-aware (converted to
UTC). Interval bounds are converted to UTC before any arithmetic so DST zones stay correct.

Rounding: the exact primitives work on ``timedelta`` (``business_time_between`` /
``add_business_time``). The minute helpers floor: ``business_minutes_between`` returns
``floor(exact_seconds / 60)``; ``add_business_minutes(start, m)`` adds exactly ``m`` minutes
of business time, so ``business_minutes_between(start, add_business_minutes(start, m)) == m``.
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

ZERO = timedelta(0)
# Upper bound on scanned local days (about 27 years) so empty/all-holiday configs terminate.
MAX_SCAN_DAYS = 10_000


class BusinessCalendar:
    def __init__(
        self,
        tz: ZoneInfo,
        hours: dict[int, list[tuple[time, time]]],
        holidays: set[date] | frozenset[date] = frozenset(),
    ) -> None:
        self.tz = tz
        self.hours = {d: sorted(v) for d, v in hours.items() if v}
        self.holidays = frozenset(holidays)

    @property
    def has_business_hours(self) -> bool:
        return bool(self.hours)

    def _intervals(self, day: date) -> list[tuple[datetime, datetime]]:
        """UTC (open, close) pairs of one local day; empty on holidays and closed weekdays."""
        if day in self.holidays:
            return []
        out = []
        for open_t, close_t in self.hours.get(day.weekday(), []):
            lo = datetime.combine(day, open_t, tzinfo=self.tz).astimezone(UTC)
            hi = datetime.combine(day, close_t, tzinfo=self.tz).astimezone(UTC)
            if hi > lo:
                out.append((lo, hi))
        return out

    def is_open(self, at: datetime) -> bool:
        day = at.astimezone(self.tz).date()
        return any(lo <= at < hi for lo, hi in self._intervals(day))

    def business_time_between(self, a: datetime, b: datetime) -> timedelta:
        """Exact business time in [a, b]; zero when b <= a."""
        if b <= a:
            return ZERO
        a, b = a.astimezone(UTC), b.astimezone(UTC)
        day, last = a.astimezone(self.tz).date(), b.astimezone(self.tz).date()
        total = ZERO
        while day <= last:
            for lo, hi in self._intervals(day):
                s, e = max(lo, a), min(hi, b)
                if e > s:
                    total += e - s
            day += timedelta(days=1)
        return total

    def business_minutes_between(self, a: datetime, b: datetime) -> int:
        return int(self.business_time_between(a, b) // timedelta(minutes=1))

    def add_business_time(self, start: datetime, amount: timedelta) -> datetime | None:
        """Instant after ``amount`` of business time from ``start`` (``start`` itself for 0).

        Returns None when the calendar has no business time at all (no hours configured, or
        nothing within MAX_SCAN_DAYS). Raises ValueError for a negative amount.
        """
        if amount < ZERO:
            raise ValueError("amount must be >= 0")
        start = start.astimezone(UTC)
        if amount == ZERO:
            return start
        if not self.hours:
            return None
        remaining = amount
        day = start.astimezone(self.tz).date()
        for _ in range(MAX_SCAN_DAYS):
            for lo, hi in self._intervals(day):
                begin = max(lo, start)
                if hi <= begin:
                    continue
                avail = hi - begin
                if remaining <= avail:
                    return begin + remaining
                remaining -= avail
            day += timedelta(days=1)
        return None

    def add_business_minutes(self, start: datetime, minutes: int) -> datetime | None:
        if minutes < 0:
            raise ValueError("minutes must be >= 0")
        return self.add_business_time(start, timedelta(minutes=minutes))
