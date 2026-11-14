"""Dashboard / report queries (REPORT-01..06). Everything is computed from persisted data.

Conventions (documented in the API):
* Dates are LOCAL dates of the organization timezone. A range ``from..to`` covers the instants
  ``[start of from-day, start of (to + 1 day))`` in that timezone: ``from`` inclusive start of
  day, ``to`` inclusive through its last second. Range length is capped at 366 days.
* Defaults: ``to`` = today (org-local), ``from`` = ``to`` - 29 days.
* Technician filter: requests currently assigned (ACTIVE) or completed by that technician.
"""

import typing
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import Date, Select, cast, func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.errors import NotFound, ValidationFailed
from app.core.tenancy import Ctx
from app.models.assignments import Assignment
from app.models.enums import (
    AssignmentStatus,
    EstimateStatus,
    MembershipRole,
    Priority,
    RequestStatus,
)
from app.models.estimates import Estimate
from app.models.identity import Membership, User
from app.models.inventory import MaterialUsage
from app.models.org import ServiceCategory, TechnicianAvailability, TechnicianTimeOff
from app.models.requests import ServiceRequest
from app.schemas.reports import (
    DailyPoint,
    DateRange,
    DistributionItem,
    ReportSummary,
    TechnicianUtilization,
    Utilization,
)
from app.sla import service as sla_svc

MAX_RANGE_DAYS = 366
MAX_DAILY_DAYS = 90
UPCOMING_WINDOW = timedelta(days=7)
FINISHED = (RequestStatus.COMPLETED, RequestStatus.CLOSED, RequestStatus.CANCELED)
APPROVED_LABEL = "approved estimates (not collected revenue)"
UTILIZATION_EXPLANATION = (
    "Utilization = planned minutes / available minutes for ACTIVE technicians only. Planned "
    "minutes are ACTIVE or COMPLETED assignment intervals clipped to the report range; "
    "available minutes are each technician's weekly availability expanded over the range in "
    "the organization timezone, minus time off. Overlapping availability intervals (and "
    "overlapping assignments) of one technician are merged first so no minute is counted twice. "
    "'percent' is the raw ratio and can exceed 100 when work is planned outside availability; "
    "'percent_capped' is min(percent, 100). Both are null when no minutes are available."
)


def _tz(ctx: Ctx) -> ZoneInfo:
    return ZoneInfo(ctx.timezone)


def local_day_start(d: date, tz: ZoneInfo) -> datetime:
    return datetime.combine(d, time(0, 0), tzinfo=tz).astimezone(UTC)


def resolve_range(ctx: Ctx, from_: date | None, to: date | None) -> DateRange:
    tz = _tz(ctx)
    today = clock.now().astimezone(tz).date()
    to = to or today
    from_ = from_ or (to - timedelta(days=29))
    if from_ > to:
        raise ValidationFailed(
            "Invalid date range.", [{"field": "from", "message": "from must not be after to"}]
        )
    if (to - from_).days + 1 > MAX_RANGE_DAYS:
        raise ValidationFailed(
            "Date range too long.",
            [{"field": "to", "message": f"range may span at most {MAX_RANGE_DAYS} days"}],
        )
    return DateRange(
        from_date=from_,
        to_date=to,
        start_at=local_day_start(from_, tz),
        end_at=local_day_start(to + timedelta(days=1), tz),
        timezone=ctx.timezone,
    )


def _check_filters(
    db: Session, ctx: Ctx, category_id: uuid.UUID | None, technician_id: uuid.UUID | None
) -> None:
    if category_id is not None and not db.scalar(
        select(ServiceCategory.id).where(
            ServiceCategory.organization_id == ctx.org_id, ServiceCategory.id == category_id
        )
    ):
        raise NotFound("Category not found.")
    if technician_id is not None and not db.scalar(
        select(Membership.id).where(
            Membership.organization_id == ctx.org_id,
            Membership.id == technician_id,
            Membership.role == MembershipRole.TECHNICIAN,
        )
    ):
        raise NotFound("Technician not found.")


def _requests(ctx: Ctx, category_id: uuid.UUID | None, technician_id: uuid.UUID | None) -> Select:
    stmt = select(ServiceRequest.id).where(ServiceRequest.organization_id == ctx.org_id)
    if category_id:
        stmt = stmt.where(ServiceRequest.category_id == category_id)
    if technician_id:
        stmt = stmt.where(
            ServiceRequest.id.in_(
                select(Assignment.request_id).where(
                    Assignment.organization_id == ctx.org_id,
                    Assignment.technician_membership_id == technician_id,
                    Assignment.status.in_([AssignmentStatus.ACTIVE, AssignmentStatus.COMPLETED]),
                )
            )
        )
    return stmt


def _count(db: Session, base: Select, *where) -> int:
    ids = base.where(*where).subquery()
    return db.scalar(select(func.count()).select_from(ids)) or 0


# ---- interval maths (pure) -------------------------------------------------------------
Interval = tuple[datetime, datetime]


def merge_intervals(intervals: list[Interval]) -> list[Interval]:
    out: list[Interval] = []
    for s, e in sorted(i for i in intervals if i[1] > i[0]):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def subtract_intervals(base: list[Interval], cut: list[Interval]) -> list[Interval]:
    """``base`` and ``cut`` must each be merged (sorted, non-overlapping)."""
    out: list[Interval] = []
    for s, e in base:
        cur = s
        for cs, ce in cut:
            if ce <= cur or cs >= e:
                continue
            if cs > cur:
                out.append((cur, cs))
            cur = max(cur, ce)
            if cur >= e:
                break
        if cur < e:
            out.append((cur, e))
    return out


def clip(intervals: list[Interval], start: datetime, end: datetime) -> list[Interval]:
    return [(max(s, start), min(e, end)) for s, e in intervals if min(e, end) > max(s, start)]


def minutes(intervals: list[Interval]) -> int:
    return int(sum((e - s).total_seconds() for s, e in intervals) // 60)


def available_intervals(
    avail: list[TechnicianAvailability],
    time_off: list[Interval],
    tz: ZoneInfo,
    from_: date,
    to: date,
    start: datetime,
    end: datetime,
) -> list[Interval]:
    by_weekday: dict[int, list[TechnicianAvailability]] = defaultdict(list)
    for a in avail:
        by_weekday[a.weekday].append(a)
    raw: list[Interval] = []
    day = from_
    while day <= to:
        for a in by_weekday.get(day.weekday(), []):
            raw.append(
                (
                    datetime.combine(day, a.start_time, tzinfo=tz).astimezone(UTC),
                    datetime.combine(day, a.end_time, tzinfo=tz).astimezone(UTC),
                )
            )
        day += timedelta(days=1)
    merged = merge_intervals(clip(raw, start, end))
    return subtract_intervals(merged, merge_intervals(clip(time_off, start, end)))


def _pct(planned: int, available: int) -> tuple[float | None, float | None]:
    if available <= 0:
        return None, None
    raw = round(planned * 100 / available, 1)
    return raw, min(raw, 100.0)


def utilization(
    db: Session, ctx: Ctx, rng: DateRange, technician_id: uuid.UUID | None
) -> Utilization:
    tz = _tz(ctx)
    stmt = (
        select(Membership.id, User.full_name)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.organization_id == ctx.org_id,
            Membership.role == MembershipRole.TECHNICIAN,
            Membership.is_active.is_(True),
            User.is_active.is_(True),
        )
        .order_by(User.full_name, Membership.id)
    )
    if technician_id:
        stmt = stmt.where(Membership.id == technician_id)
    techs = list(db.execute(stmt).all())
    ids = [t[0] for t in techs]
    avail: dict[uuid.UUID, list[TechnicianAvailability]] = defaultdict(list)
    off: dict[uuid.UUID, list[Interval]] = defaultdict(list)
    planned: dict[uuid.UUID, list[Interval]] = defaultdict(list)
    if ids:
        for a in db.scalars(
            select(TechnicianAvailability).where(
                TechnicianAvailability.organization_id == ctx.org_id,
                TechnicianAvailability.membership_id.in_(ids),
            )
        ):
            avail[a.membership_id].append(a)
        for o in db.scalars(
            select(TechnicianTimeOff).where(
                TechnicianTimeOff.organization_id == ctx.org_id,
                TechnicianTimeOff.membership_id.in_(ids),
                TechnicianTimeOff.start_at < rng.end_at,
                TechnicianTimeOff.end_at > rng.start_at,
            )
        ):
            off[o.membership_id].append((o.start_at, o.end_at))
        for a in db.scalars(
            select(Assignment).where(
                Assignment.organization_id == ctx.org_id,
                Assignment.technician_membership_id.in_(ids),
                Assignment.status.in_([AssignmentStatus.ACTIVE, AssignmentStatus.COMPLETED]),
                Assignment.start_at < rng.end_at,
                Assignment.end_at > rng.start_at,
            )
        ):
            planned[a.technician_membership_id].append((a.start_at, a.end_at))
    per: list[TechnicianUtilization] = []
    tot_planned = tot_avail = 0
    for mid, name in techs:
        p = minutes(merge_intervals(clip(planned[mid], rng.start_at, rng.end_at)))
        a = minutes(
            available_intervals(
                avail[mid], off[mid], tz, rng.from_date, rng.to_date, rng.start_at, rng.end_at
            )
        )
        raw, capped = _pct(p, a)
        per.append(
            TechnicianUtilization(
                membership_id=mid,
                name=name,
                planned_minutes=p,
                available_minutes=a,
                percent=raw,
                percent_capped=capped,
            )
        )
        tot_planned += p
        tot_avail += a
    raw, capped = _pct(tot_planned, tot_avail)
    return Utilization(
        percent=raw,
        percent_capped=capped,
        planned_minutes=tot_planned,
        available_minutes=tot_avail,
        explanation=UTILIZATION_EXPLANATION,
        per_technician=per,
    )


# ---- REPORT-01/02/03/04/05 summary -----------------------------------------------------
def summary(
    db: Session,
    ctx: Ctx,
    from_: date | None,
    to: date | None,
    category_id: uuid.UUID | None,
    technician_id: uuid.UUID | None,
) -> ReportSummary:
    rng = resolve_range(ctx, from_, to)
    _check_filters(db, ctx, category_id, technician_id)
    now = clock.now()
    base = _requests(ctx, category_id, technician_id)
    ids = base.subquery()

    counts = {s.value: 0 for s in RequestStatus}
    for status, n in db.execute(
        select(ServiceRequest.status, func.count())
        .where(ServiceRequest.id.in_(select(ids.c.id)))
        .group_by(ServiceRequest.status)
    ):
        counts[status.value] = n

    open_n = _count(db, base, ServiceRequest.status.notin_(FINISHED))
    overdue = _count(db, base, sla_svc.state_clause("OVERDUE", now))
    completed = _count(
        db,
        base,
        ServiceRequest.completed_at >= rng.start_at,
        ServiceRequest.completed_at < rng.end_at,
    )

    upcoming_stmt = (
        select(func.count())
        .select_from(Assignment)
        .where(
            Assignment.organization_id == ctx.org_id,
            Assignment.status == AssignmentStatus.ACTIVE,
            Assignment.start_at >= now,
            Assignment.start_at <= now + UPCOMING_WINDOW,
        )
    )
    if technician_id:
        upcoming_stmt = upcoming_stmt.where(Assignment.technician_membership_id == technician_id)
    if category_id:
        upcoming_stmt = upcoming_stmt.where(
            Assignment.request_id.in_(_requests(ctx, category_id, None))
        )
    upcoming = db.scalar(upcoming_stmt) or 0

    est_stmt = select(func.coalesce(func.sum(Estimate.total_minor), 0)).where(
        Estimate.organization_id == ctx.org_id,
        Estimate.status == EstimateStatus.APPROVED,
        Estimate.decided_at >= rng.start_at,
        Estimate.decided_at < rng.end_at,
    )
    mat_stmt = select(func.coalesce(func.sum(MaterialUsage.total_cost_minor), 0)).where(
        MaterialUsage.organization_id == ctx.org_id,
        MaterialUsage.created_at >= rng.start_at,
        MaterialUsage.created_at < rng.end_at,
    )
    if category_id or technician_id:
        est_stmt = est_stmt.where(Estimate.request_id.in_(select(ids.c.id)))
        mat_stmt = mat_stmt.where(MaterialUsage.request_id.in_(select(ids.c.id)))
    return ReportSummary(
        range=rng,
        counts_by_status=counts,
        open_requests=open_n,
        overdue_requests=overdue,
        upcoming_appointments=upcoming,
        completed_in_range=completed,
        technician_utilization=utilization(db, ctx, rng, technician_id),
        approved_estimates_total_minor=int(db.scalar(est_stmt) or 0),
        approved_estimates_label=APPROVED_LABEL,
        material_costs_total_minor=int(db.scalar(mat_stmt) or 0),
        currency="KGS",
    )


# ---- REPORT-05 daily series --------------------------------------------------------------
def daily(db: Session, ctx: Ctx, days: int) -> list[DailyPoint]:
    tz = _tz(ctx)
    today = clock.now().astimezone(tz).date()
    first = today - timedelta(days=days - 1)
    start, end = local_day_start(first, tz), local_day_start(today + timedelta(days=1), tz)

    def series(col) -> dict[date, int]:
        day = cast(func.timezone(ctx.timezone, col), Date)
        rows = db.execute(
            select(day, func.count())
            .where(ServiceRequest.organization_id == ctx.org_id, col >= start, col < end)
            .group_by(day)
        )
        return {typing.cast(date, d): n for d, n in rows}

    created = series(ServiceRequest.created_at)
    done = series(ServiceRequest.completed_at)
    return [
        DailyPoint(
            date=first + timedelta(days=i),
            new_requests=created.get(first + timedelta(days=i), 0),
            completed_requests=done.get(first + timedelta(days=i), 0),
        )
        for i in range(days)
    ]


# ---- REPORT-06 distribution --------------------------------------------------------------
def distribution(
    db: Session,
    ctx: Ctx,
    by: str,
    from_: date | None,
    to: date | None,
    category_id: uuid.UUID | None,
    technician_id: uuid.UUID | None,
) -> list[DistributionItem]:
    rng = resolve_range(ctx, from_, to)
    _check_filters(db, ctx, category_id, technician_id)
    ids = _requests(ctx, category_id, technician_id).where(
        ServiceRequest.created_at >= rng.start_at, ServiceRequest.created_at < rng.end_at
    )
    in_range = ServiceRequest.id.in_(ids.subquery().select())
    if by == "priority":
        got = dict(
            db.execute(
                select(ServiceRequest.priority, func.count())
                .where(in_range)
                .group_by(ServiceRequest.priority)
            ).all()
        )
        return [
            DistributionItem(key=p.value, label=p.value.title(), count=got.get(p, 0))
            for p in (Priority.HIGH, Priority.NORMAL, Priority.LOW)
        ]
    counts = dict(
        db.execute(
            select(ServiceRequest.category_id, func.count())
            .where(in_range)
            .group_by(ServiceRequest.category_id)
        ).all()
    )
    cats = db.scalars(
        select(ServiceCategory)
        .where(ServiceCategory.organization_id == ctx.org_id)
        .order_by(ServiceCategory.name)
    )
    items = [
        DistributionItem(key=str(c.id), label=c.name, count=counts.get(c.id, 0))
        for c in cats
        if c.is_enabled or counts.get(c.id, 0) > 0
    ]
    return sorted(items, key=lambda i: (-i.count, i.label))
