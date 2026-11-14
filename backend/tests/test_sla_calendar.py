import random
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.sla.calendar import BusinessCalendar

TZ = ZoneInfo("Asia/Bishkek")  # UTC+6, no DST
WEEK = {d: [(time(9), time(18))] for d in range(5)}


def local(y, m, d, hh=0, mm=0, ss=0) -> datetime:
    return datetime(y, m, d, hh, mm, ss, tzinfo=TZ).astimezone(UTC)


def cal(hours=None, holidays=()) -> BusinessCalendar:
    return BusinessCalendar(TZ, WEEK if hours is None else hours, set(holidays))


# 2026-11-13 is a Friday
def test_friday_1700_plus_8h_is_monday_1600():
    due = cal().add_business_minutes(local(2026, 11, 13, 17), 480)
    assert due == local(2026, 11, 16, 16)
    assert due is not None and due.astimezone(TZ).weekday() == 0


def test_monday_holiday_pushes_to_tuesday():
    c = cal(holidays=[date(2026, 11, 16)])
    assert c.add_business_minutes(local(2026, 11, 13, 17), 480) == local(2026, 11, 17, 16)


def test_start_before_opening_and_after_closing():
    c = cal()
    assert c.add_business_minutes(local(2026, 11, 11, 6), 60) == local(2026, 11, 11, 10)
    assert c.add_business_minutes(local(2026, 11, 11, 20), 60) == local(2026, 11, 12, 10)
    assert c.add_business_minutes(local(2026, 11, 14, 12), 60) == local(2026, 11, 16, 10)


def test_zero_minutes_returns_start():
    s = local(2026, 11, 14, 12)  # Saturday
    assert cal().add_business_minutes(s, 0) == s


def test_end_of_interval_boundary_stays_on_closing_time():
    assert cal().add_business_minutes(local(2026, 11, 12, 9), 540) == local(2026, 11, 12, 18)


def test_overnight_gap_not_counted():
    c = cal()
    assert c.business_minutes_between(local(2026, 11, 12, 17), local(2026, 11, 13, 10)) == 120
    assert c.business_minutes_between(local(2026, 11, 13, 17), local(2026, 11, 16, 10)) == 120


def test_weekend_and_holiday_count_zero():
    c = cal(holidays=[date(2026, 11, 16)])
    assert c.business_minutes_between(local(2026, 11, 14), local(2026, 11, 17)) == 0
    assert c.business_minutes_between(local(2026, 11, 14), local(2026, 11, 17, 10)) == 60


def test_multiple_intervals_per_day():
    c = cal({d: [(time(9), time(13)), (time(14), time(18))] for d in range(5)})
    assert c.business_minutes_between(local(2026, 11, 12, 12), local(2026, 11, 12, 15)) == 120
    assert c.add_business_minutes(local(2026, 11, 12, 12), 120) == local(2026, 11, 12, 15)
    assert c.add_business_minutes(local(2026, 11, 12, 9), 480) == local(2026, 11, 12, 18)
    assert c.add_business_minutes(local(2026, 11, 12, 13, 30), 30) == local(2026, 11, 12, 14, 30)


def test_timezone_conversion_utc_plus_6():
    c = cal()
    # 03:00 UTC == 09:00 Bishkek (open); 02:59 UTC == 08:59 (closed)
    assert c.is_open(datetime(2026, 11, 12, 3, 0, tzinfo=UTC))
    assert not c.is_open(datetime(2026, 11, 12, 2, 59, tzinfo=UTC))
    assert c.add_business_minutes(datetime(2026, 11, 12, 3, 0, tzinfo=UTC), 60) == datetime(
        2026, 11, 12, 4, 0, tzinfo=UTC
    )


def test_late_utc_evening_belongs_to_next_local_day():
    # 2026-11-12 20:00 UTC = 2026-11-13 02:00 Bishkek (Friday, before opening)
    due = cal().add_business_minutes(datetime(2026, 11, 12, 20, 0, tzinfo=UTC), 60)
    assert due == local(2026, 11, 13, 10)


def test_seconds_floor():
    c = cal()
    a = local(2026, 11, 12, 10, 0, 0)
    assert c.business_minutes_between(a, local(2026, 11, 12, 10, 0, 59)) == 0
    assert c.business_minutes_between(a, local(2026, 11, 12, 10, 1, 0)) == 1
    assert c.business_time_between(a, local(2026, 11, 12, 10, 0, 59)) == timedelta(seconds=59)


def test_reversed_range_is_zero():
    assert cal().business_minutes_between(local(2026, 11, 12, 12), local(2026, 11, 12, 10)) == 0


def test_no_business_hours_returns_none():
    c = BusinessCalendar(TZ, {}, set())
    assert not c.has_business_hours
    assert c.add_business_minutes(local(2026, 11, 12, 10), 60) is None
    assert c.add_business_minutes(local(2026, 11, 12, 10), 0) == local(2026, 11, 12, 10)
    assert c.business_minutes_between(local(2026, 11, 12), local(2026, 11, 19)) == 0


def test_negative_minutes_rejected():
    with pytest.raises(ValueError, match="minutes"):
        cal().add_business_minutes(local(2026, 11, 12, 10), -1)


def test_dst_zone_uses_wall_clock_hours():
    ny = ZoneInfo("America/New_York")
    c = BusinessCalendar(ny, WEEK)
    # Sat 2026-03-07 -> Mon 2026-03-09 spans the DST switch (Sun 03-08); 09-18 local still holds
    start = datetime(2026, 3, 6, 17, 0, tzinfo=ny)
    due = c.add_business_minutes(start, 120)
    assert due == datetime(2026, 3, 9, 10, 0, tzinfo=ny).astimezone(UTC)


@pytest.mark.parametrize("seed", range(5))
def test_between_add_roundtrip_random(seed):
    rng = random.Random(seed)  # noqa: S311 - deterministic test data
    hols = {date(2026, 11, 16), date(2026, 11, 25)}
    c = cal({d: [(time(9), time(13)), (time(14), time(18))] for d in range(5)}, hols)
    base = local(2026, 11, 1)
    for _ in range(120):
        start = base + timedelta(seconds=rng.randrange(0, 40 * 86400))
        m = rng.randrange(0, 5000)
        end = c.add_business_minutes(start, m)
        assert end is not None
        assert c.business_minutes_between(start, end) == m
        if m:
            assert c.business_time_between(start, end) == timedelta(minutes=m)
