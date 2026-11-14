"""Pure recurrence math for maintenance plans (PM-01/02). No DB.

* WEEKLY  : first_date + 7 * k days.
* MONTHLY : same day-of-month as ``first_date``, clamped to the month's last day
  (Jan 31 -> Feb 28/29 -> Mar 31 -> Apr 30; the day never "drifts" because every
  occurrence is derived from ``first_date``, not from the previous occurrence).
"""

import calendar
from collections.abc import Iterator
from datetime import date, timedelta

from app.models.enums import Recurrence

MAX_OCCURRENCES_PER_RUN = 366


def nth_occurrence(first: date, recurrence: Recurrence, k: int) -> date:
    if k < 0:
        raise ValueError("k must be >= 0")
    if recurrence == Recurrence.WEEKLY:
        return first + timedelta(days=7 * k)
    month_index = first.month - 1 + k
    year, month = first.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(first.day, calendar.monthrange(year, month)[1]))


def _start_index(first: date, recurrence: Recurrence, after: date | None) -> int:
    """A lower bound for the first k whose occurrence is > ``after`` (never skips one)."""
    if after is None or after < first:
        return 0
    if recurrence == Recurrence.WEEKLY:
        return (after - first).days // 7
    return max(0, (after.year - first.year) * 12 + after.month - first.month - 1)


def iter_occurrences(
    first: date, recurrence: Recurrence, after: date | None = None
) -> Iterator[date]:
    """Occurrences strictly after ``after`` (all from ``first`` when None), ascending."""
    k = _start_index(first, recurrence, after)
    while True:
        d = nth_occurrence(first, recurrence, k)
        if after is None or d > after:
            yield d
        k += 1


def occurrences_due(
    first: date,
    recurrence: Recurrence,
    after: date | None,
    as_of: date,
    limit: int = MAX_OCCURRENCES_PER_RUN,
) -> list[date]:
    """Occurrences in (after, as_of], at most ``limit`` (oldest first)."""
    out: list[date] = []
    for d in iter_occurrences(first, recurrence, after):
        if d > as_of or len(out) >= limit:
            break
        out.append(d)
    return out


def next_occurrence(first: date, recurrence: Recurrence, after: date | None) -> date:
    """The first occurrence not yet generated (> ``after``)."""
    return next(iter_occurrences(first, recurrence, after))
