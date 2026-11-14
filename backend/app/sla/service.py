"""DB side of the SLA engine: calendar loading and the persisted cache on service_requests."""

import uuid
from collections import defaultdict
from datetime import datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.models.identity import DEFAULT_TIMEZONE, Organization
from app.models.org import BusinessHour, Holiday
from app.models.requests import RequestEvent, ServiceRequest
from app.sla import engine
from app.sla.calendar import BusinessCalendar
from app.sla.engine import SlaState

DEFAULT_OPEN_CLOSE = (time(9, 0), time(18, 0))


def load_calendar(db: Session, org_id: uuid.UUID) -> BusinessCalendar:
    tz_name = db.scalar(select(Organization.timezone).where(Organization.id == org_id))
    try:
        tz = ZoneInfo(tz_name or DEFAULT_TIMEZONE)
    except Exception:  # unknown zone name stored: fall back rather than break every request
        tz = ZoneInfo(DEFAULT_TIMEZONE)
    hours: dict[int, list] = defaultdict(list)
    for h in db.scalars(select(BusinessHour).where(BusinessHour.organization_id == org_id)):
        hours[h.weekday].append((h.open_time, h.close_time))
    if not hours:  # SLA-01 default: Mon-Fri 09:00-18:00 until an admin configures hours
        hours = {d: [DEFAULT_OPEN_CLOSE] for d in range(5)}
    holidays = set(db.scalars(select(Holiday.date).where(Holiday.organization_id == org_id)))
    return BusinessCalendar(tz, dict(hours), holidays)


def _sla_events_stmt():
    return select(RequestEvent).where(RequestEvent.type.in_(sorted(engine.SLA_EVENT_TYPES)))


def sla_events(db: Session, request: ServiceRequest) -> list[RequestEvent]:
    return list(
        db.scalars(
            _sla_events_stmt()
            .where(
                RequestEvent.organization_id == request.organization_id,
                RequestEvent.request_id == request.id,
            )
            .order_by(RequestEvent.created_at, RequestEvent.id)
        )
    )


def live_state(
    db: Session,
    request: ServiceRequest,
    now: datetime | None = None,
    calendar: BusinessCalendar | None = None,
) -> SlaState:
    cal = calendar or load_calendar(db, request.organization_id)
    return engine.compute_sla(request, sla_events(db, request), cal, now or clock.now())


def apply_state(request: ServiceRequest, st: SlaState) -> None:
    """Write the cacheable part of ``st`` onto the request row (no flush/commit)."""
    request.sla_budget_minutes = st.budget_minutes
    request.sla_due_at = st.due_at
    request.sla_at_risk_at = st.at_risk_at
    request.sla_paused = st.paused
    request.sla_stopped_at = st.stopped_at
    request.sla_outcome = st.outcome
    request.sla_consumed_minutes = st.consumed_minutes if st.stopped else None


def recompute_sla(
    db: Session,
    request: ServiceRequest,
    now: datetime | None = None,
    calendar: BusinessCalendar | None = None,
) -> SlaState:
    """Re-derive the SLA cache from the request's events. Runs in the caller's transaction."""
    db.flush()  # the triggering event (and request status) must be visible to the query
    st = live_state(db, request, now, calendar)
    apply_state(request, st)
    db.flush()
    return st


def recompute_org_open_requests(db: Session, org_id: uuid.UUID) -> int:
    """Re-derive every open (not stopped) request of one org, e.g. after the calendar changed."""
    cal = load_calendar(db, org_id)
    rows = list(
        db.scalars(
            select(ServiceRequest)
            .where(
                ServiceRequest.organization_id == org_id, ServiceRequest.sla_stopped_at.is_(None)
            )
            .order_by(ServiceRequest.id)
            .with_for_update()
        )
    )
    return _recompute_many(db, rows, cal)


def recompute_all(db: Session) -> int:
    """Recompute every request of every org (seed / backfill). Caller commits."""
    total = 0
    for org_id in db.scalars(select(Organization.id)).all():
        cal = load_calendar(db, org_id)
        rows = list(
            db.scalars(
                select(ServiceRequest)
                .where(ServiceRequest.organization_id == org_id)
                .order_by(ServiceRequest.id)
            )
        )
        total += _recompute_many(db, rows, cal)
    return total


def _recompute_many(db: Session, rows: list[ServiceRequest], cal: BusinessCalendar) -> int:
    if not rows:
        return 0
    by_req: dict[uuid.UUID, list[RequestEvent]] = defaultdict(list)
    for ev in db.scalars(
        _sla_events_stmt()
        .where(
            RequestEvent.organization_id == rows[0].organization_id,
            RequestEvent.request_id.in_([r.id for r in rows]),
        )
        .order_by(RequestEvent.created_at, RequestEvent.id)
    ):
        by_req[ev.request_id].append(ev)
    now = clock.now()
    for r in rows:
        apply_state(r, engine.compute_sla(r, by_req.get(r.id, []), cal, now))
    db.flush()
    return len(rows)


# ---- list/cache helpers (no events needed) ---------------------------------------------
LIVE_FILTERS = ("ON_TRACK", "AT_RISK", "OVERDUE", "PAUSED")


def cached_state(req: ServiceRequest, now: datetime) -> str | None:
    """List-level SLA state from the cached columns: ON_TRACK | AT_RISK | OVERDUE | PAUSED.

    Stopped requests report their historical state at the stop instant (never PAUSED). None
    when the request has no SLA cache (rows written without the lifecycle)."""
    if req.sla_budget_minutes is None:
        return None
    if req.sla_stopped_at is not None:
        return engine.stopped_state(
            req.sla_budget_minutes, req.sla_consumed_minutes or 0, req.sla_outcome or engine.MET
        )
    if req.sla_paused:
        return "PAUSED"
    if req.sla_due_at is not None and req.sla_due_at < now:
        return engine.OVERDUE
    if req.sla_at_risk_at is not None and req.sla_at_risk_at <= now:
        return engine.AT_RISK
    return engine.ON_TRACK


def state_clause(state: str, now: datetime):
    """SQL predicate equivalent to ``cached_state(...) == state`` for live (not stopped) rows."""
    R = ServiceRequest
    live = (R.sla_stopped_at.is_(None)) & (R.sla_budget_minutes.is_not(None))
    if state == "PAUSED":
        return live & R.sla_paused.is_(True)
    running = live & R.sla_paused.is_(False)
    overdue = R.sla_due_at < now
    at_risk = R.sla_at_risk_at <= now
    if state == "OVERDUE":
        return running & overdue
    if state == "AT_RISK":
        return running & at_risk & (R.sla_due_at.is_(None) | (R.sla_due_at >= now))
    return (
        running
        & (R.sla_due_at.is_(None) | (R.sla_due_at >= now))
        & (R.sla_at_risk_at.is_(None) | (R.sla_at_risk_at > now))
    )
