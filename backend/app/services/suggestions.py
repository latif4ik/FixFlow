"""Smart Assign (WEB-09): earliest valid slots per skilled technician.

Advisory only: nothing is reserved. Assigning still goes through POST/PUT
``/requests/{id}/assignment`` with every guard, so a stale suggestion yields the normal 409/422.

Algorithm (no per-slot queries): availability, time off and active assignments of all skilled
technicians are loaded once for the horizon. Per technician and local day the availability
intervals are clipped to [from, to], busy intervals (assignments + time off) are subtracted, and
the first 15-minute-grid start that fits ``duration`` is taken in each free gap, keeping the two
earliest NON-overlapping slots per technician. Candidates are ranked globally; each one that is
returned is re-checked with ``eligibility.evaluate`` (the single source of truth).
"""

import logging
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from math import ceil
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import AppError
from app.core.tenancy import Ctx
from app.models.assignments import Assignment
from app.models.enums import RequestStatus
from app.models.org import ServiceCategory, TechnicianAvailability, TechnicianTimeOff
from app.models.requests import ServiceRequest
from app.services import eligibility
from app.services.request_access import get_active_assignment

log = logging.getLogger(__name__)

S = RequestStatus
SUGGESTABLE = (S.TRIAGED, S.SCHEDULED, S.ACCEPTED)
GRID = 900  # seconds (15 minutes)
PER_TECH = 2

Interval = tuple[datetime, datetime]


def _grid_up(dt: datetime, offset_s: float) -> datetime:
    """Round ``dt`` up to a 15-minute boundary of the local clock (offset in seconds)."""
    t = dt.timestamp() + offset_s
    return datetime.fromtimestamp(ceil(t / GRID) * GRID - offset_s, UTC)


def _next_boundary(now: datetime) -> datetime:
    """Strictly after ``now`` so the slot never starts in the past by the time it is checked."""
    return datetime.fromtimestamp((now.timestamp() // GRID + 1) * GRID, UTC)


def _merge(intervals: list[Interval]) -> list[Interval]:
    out: list[Interval] = []
    for s, e in sorted(intervals):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def _subtract(base: Interval, busy: list[Interval]) -> list[Interval]:
    """``busy`` must be merged and sorted."""
    free: list[Interval] = []
    cur = base[0]
    for bs, be in busy:
        if be <= cur:
            continue
        if bs >= base[1]:
            break
        if bs > cur:
            free.append((cur, bs))
        cur = max(cur, be)
    if cur < base[1]:
        free.append((cur, base[1]))
    return free


def find_slots(
    avail: list[TechnicianAvailability],
    busy: list[Interval],
    ctx_tz,
    start: datetime,
    horizon_end: datetime,
    duration: timedelta,
    limit: int = PER_TECH,
    *,
    finish_by_end: bool = False,
) -> list[Interval]:
    """Earliest non-overlapping ``duration`` windows (15-min grid) for one technician.

    ``finish_by_end`` (explicit from/to window): the slot must also END by ``horizon_end``.
    """
    busy = _merge(busy)
    slots: list[Interval] = []
    day = start.astimezone(ctx_tz).date()
    last_day = horizon_end.astimezone(ctx_tz).date()
    while day <= last_day and len(slots) < limit:
        for a_start, a_end in eligibility.local_intervals(avail, ctx_tz, day):
            lo, hi = max(a_start, start), (min(a_end, horizon_end) if finish_by_end else a_end)
            if lo >= hi or lo > horizon_end:
                continue
            for fs, fe in _subtract((lo, hi), busy):
                cursor = fs
                while len(slots) < limit:
                    offset = cursor.astimezone(ctx_tz).utcoffset()
                    s = _grid_up(cursor, offset.total_seconds() if offset else 0.0)
                    if s > horizon_end or s + duration > fe:
                        break
                    slots.append((s, s + duration))
                    cursor = s + duration  # alternatives never overlap each other
        day += timedelta(days=1)
    return slots


def suggest(
    db: Session,
    ctx: Ctx,
    req: ServiceRequest,
    horizon_days: int,
    duration_minutes: int | None,
    limit: int,
    window_from: datetime | None = None,
    window_to: datetime | None = None,
) -> dict[str, Any]:
    """``window_from``/``window_to`` (UTC) restrict the search to [max(from, next 15 min), to]."""
    if req.status not in SUGGESTABLE:
        raise AppError(
            409,
            "invalid_state",
            "Suggestions are only available for triaged, scheduled or accepted requests.",
            {"status": req.status.value},
        )
    if duration_minutes is None:
        duration_minutes = db.scalar(
            select(ServiceCategory.default_duration_minutes).where(
                ServiceCategory.organization_id == ctx.org_id,
                ServiceCategory.id == req.category_id,
            )
        )
        duration_minutes = max(30, ceil((duration_minutes or 60) / 15) * 15)
    duration = timedelta(minutes=duration_minutes)

    now = clock.now()
    start = _next_boundary(now)
    windowed = window_from is not None or window_to is not None
    if windowed:
        if window_from is not None:
            start = max(start, window_from)
        horizon_end = window_to or max(start, now) + timedelta(days=horizon_days)
    else:
        horizon_end = now + timedelta(days=horizon_days)
    tz = eligibility.tz_of(ctx)

    own = get_active_assignment(db, req) if req.status in (S.SCHEDULED, S.ACCEPTED) else None
    ignore_id = own.id if own else None

    cands = eligibility.candidates(db, ctx, req)
    skilled = [c for c in cands if not any(r["code"] == "missing_skills" for r in c["reasons"])]
    unskilled = len(cands) - len(skilled)
    ids = [c["membership_id"] for c in skilled]

    avail: dict[uuid.UUID, list[TechnicianAvailability]] = defaultdict(list)
    busy: dict[uuid.UUID, list[Interval]] = defaultdict(list)
    if ids:
        for a in db.scalars(
            select(TechnicianAvailability).where(
                TechnicianAvailability.organization_id == ctx.org_id,
                TechnicianAvailability.membership_id.in_(ids),
            )
        ):
            avail[a.membership_id].append(a)
        for off in db.scalars(
            select(TechnicianTimeOff).where(
                TechnicianTimeOff.organization_id == ctx.org_id,
                TechnicianTimeOff.membership_id.in_(ids),
                TechnicianTimeOff.start_at < horizon_end + timedelta(days=1),
                TechnicianTimeOff.end_at > start,
            )
        ):
            busy[off.membership_id].append((off.start_at, off.end_at))
        stmt = select(Assignment).where(
            Assignment.organization_id == ctx.org_id,
            Assignment.technician_membership_id.in_(ids),
            Assignment.active.is_(True),
            Assignment.start_at < horizon_end + timedelta(days=1),
            Assignment.end_at > start,
        )
        if ignore_id is not None:
            stmt = stmt.where(Assignment.id != ignore_id)
        for asg in db.scalars(stmt):
            busy[asg.technician_membership_id].append((asg.start_at, asg.end_at))

    raw: list[tuple[datetime, int, str, dict[str, Any], Interval]] = []
    skipped: list[dict[str, Any]] = []
    for c in skilled:
        mid = c["membership_id"]
        slots = (
            find_slots(
                avail[mid], busy[mid], tz, start, horizon_end, duration, finish_by_end=windowed
            )
            if avail[mid]
            else []
        )
        if not slots:
            skipped.append(
                {
                    "technician": {"membership_id": mid, "name": c["name"]},
                    "reason_codes": [
                        "no_free_slot_in_horizon" if avail[mid] else "no_availability"
                    ],
                }
            )
            continue
        for slot in slots:
            raw.append(
                (slot[0], c["workload"]["planned_minutes_next_7_days"], c["name"].lower(), c, slot)
            )
    raw.sort(key=lambda r: (r[0], r[1], r[2]))

    due = req.sla_due_at
    earliest = raw[0][0] if raw else None
    min_load = min((r[1] for r in raw), default=0)
    out: list[dict[str, Any]] = []
    seen: dict[uuid.UUID, int] = defaultdict(int)
    for s, load, _n, c, (slot_s, slot_e) in raw:
        if len(out) >= limit:
            break
        mid = c["membership_id"]
        res = eligibility.evaluate(
            db, ctx, req, mid, slot_s, slot_e, for_new=True, ignore_assignment_id=ignore_id
        )
        if not res.eligible:  # must never happen; advisory list stays safe regardless
            log.warning(
                "suggestion rejected by eligibility",
                extra={"request_id": str(req.id), "technician": str(mid)},
            )
            continue
        parts = ["Earliest free slot" if s == earliest else "Next free slot"]
        if seen[mid]:
            parts = ["Alternative slot"]
        if load == min_load:
            parts.append("lightest workload")
        late = due is not None and slot_e > due
        if late:
            parts.append("ends after SLA due")
        seen[mid] += 1
        out.append(
            {
                "technician": {"membership_id": mid, "name": c["name"]},
                "start_at": slot_s,
                "end_at": slot_e,
                "workload_minutes_next_7_days": load,
                "sla": {"due_at": due, "slot_ends_after_due": late},
                "reason": " · ".join(parts),
            }
        )
    return {
        "request_id": req.id,
        "duration_minutes": duration_minutes,
        "horizon": {"from": start, "to": horizon_end},
        "suggestions": out,
        "skipped": skipped,
        "unskilled_technicians": unskilled,
    }
