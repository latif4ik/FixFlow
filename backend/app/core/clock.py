"""Injectable wall clock: SLA code calls ``clock.now()`` so tests can patch it."""

from datetime import UTC, datetime


def now() -> datetime:
    return datetime.now(UTC)
