"""Read models: technician job list (/me/assignments) and the planning calendar (/schedule)."""

import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFound, ValidationFailed
from app.core.pagination import PageParams, paginate_rows
from app.core.tenancy import Ctx
from app.models.assets import Asset, Property
from app.models.assignments import Assignment
from app.models.enums import AssignmentStatus, MembershipRole, RequestStatus
from app.models.identity import Membership, User
from app.models.org import ServiceCategory, TechnicianAvailability, TechnicianTimeOff
from app.models.requests import ServiceRequest
from app.schemas.assignments import (
    AppointmentBrief,
    MyAssetBrief,
    MyAssignmentItem,
    MyCategoryBrief,
    MyJobRequest,
    MyPropertyBrief,
    ScheduleAssignment,
    ScheduleInterval,
    ScheduleOut,
    ScheduleRange,
    ScheduleTechnician,
    ScheduleTimeOff,
)
from app.services import eligibility, lifecycle
from app.services.requests import display_id

S = RequestStatus
Scope = Literal["upcoming", "active", "history"]
MAX_RANGE = timedelta(days=31)


# ---- GET /me/assignments ---------------------------------------------------------------
def my_assignments(
    db: Session, ctx: Ctx, params: PageParams, scope: Scope
) -> tuple[list[MyAssignmentItem], int]:
    stmt = (
        select(Assignment, ServiceRequest, Property, ServiceCategory, Asset, User.full_name)
        .join(
            ServiceRequest,
            (ServiceRequest.organization_id == Assignment.organization_id)
            & (ServiceRequest.id == Assignment.request_id),
        )
        .join(
            Property,
            (Property.organization_id == ServiceRequest.organization_id)
            & (Property.id == ServiceRequest.property_id),
        )
        .join(
            ServiceCategory,
            (ServiceCategory.organization_id == ServiceRequest.organization_id)
            & (ServiceCategory.id == ServiceRequest.category_id),
        )
        .outerjoin(
            Asset,
            (Asset.organization_id == ServiceRequest.organization_id)
            & (Asset.id == ServiceRequest.asset_id),
        )
        .outerjoin(
            Membership,
            (Membership.organization_id == ServiceRequest.organization_id)
            & (Membership.id == ServiceRequest.requester_membership_id),
        )
        .outerjoin(User, User.id == Membership.user_id)
        .where(
            Assignment.organization_id == ctx.org_id,
            Assignment.technician_membership_id == ctx.membership_id,
        )
    )
    if scope == "upcoming":
        stmt = stmt.where(
            Assignment.active.is_(True), ServiceRequest.status.in_([S.SCHEDULED, S.ACCEPTED])
        ).order_by(Assignment.start_at, Assignment.id)
    elif scope == "active":
        stmt = stmt.where(
            Assignment.active.is_(True), ServiceRequest.status.in_([S.IN_PROGRESS, S.BLOCKED])
        ).order_by(Assignment.start_at, Assignment.id)
    else:
        stmt = stmt.where(Assignment.status == AssignmentStatus.COMPLETED).order_by(
            Assignment.end_at.desc(), Assignment.id
        )
    rows, total = paginate_rows(db, stmt, params)
    items = []
    for a, req, prop, cat, asset, requester_name in rows:
        items.append(
            MyAssignmentItem(
                assignment_id=a.id,
                request=MyJobRequest(
                    id=req.id,
                    display_id=display_id(req.number),
                    title=req.title,
                    description=req.description,
                    status=req.status,
                    priority=req.priority,
                    category=MyCategoryBrief(id=cat.id, name=cat.name),
                    # ROLE-03: requester display name + property contact instructions only;
                    # never the requester's email or phone.
                    property=MyPropertyBrief(
                        name=prop.name,
                        address=prop.address,
                        contact_instructions=prop.contact_instructions,
                    ),
                    asset=(
                        MyAssetBrief(
                            code=asset.code, name=asset.name, serial_number=asset.serial_number
                        )
                        if asset
                        else None
                    ),
                    requester_name=requester_name,
                ),
                appointment=AppointmentBrief(start_at=a.start_at, end_at=a.end_at),
                assignment_status=a.status,
                allowed_actions=lifecycle.allowed_actions(db, ctx, req),
            )
        )
    return items, total


# ---- GET /schedule ---------------------------------------------------------------------
def _utc(dt: datetime) -> datetime:
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).astimezone(UTC)


def schedule(
    db: Session,
    ctx: Ctx,
    start: datetime,
    end: datetime,
    technician_id: uuid.UUID | None,
) -> ScheduleOut:
    start, end = _utc(start), _utc(end)
    if end <= start:
        raise ValidationFailed("Invalid range.", [{"field": "to", "message": "must be after from"}])
    if end - start > MAX_RANGE:
        raise ValidationFailed(
            "Range too large.", [{"field": "to", "message": "range may be at most 31 days"}]
        )
    tz = eligibility.tz_of(ctx)

    mq = (
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.organization_id == ctx.org_id,
            Membership.role == MembershipRole.TECHNICIAN,
        )
        .order_by(User.full_name, Membership.id)
    )
    if technician_id is not None:
        mq = mq.where(Membership.id == technician_id)
    techs = db.execute(mq).all()
    if technician_id is not None and not techs:
        raise NotFound("Technician not found.")
    ids = [m.id for m, _ in techs]

    rows = db.execute(
        select(Assignment, ServiceRequest)
        .join(
            ServiceRequest,
            (ServiceRequest.organization_id == Assignment.organization_id)
            & (ServiceRequest.id == Assignment.request_id),
        )
        .where(
            Assignment.organization_id == ctx.org_id,
            Assignment.technician_membership_id.in_(ids or [uuid.uuid4()]),
            Assignment.status.in_([AssignmentStatus.ACTIVE, AssignmentStatus.COMPLETED]),
            Assignment.start_at < end,
            Assignment.end_at > start,
        )
        .order_by(Assignment.start_at, Assignment.id)
    ).all()
    by_tech: dict[uuid.UUID, list[tuple[Assignment, ServiceRequest]]] = defaultdict(list)
    for a, r in rows:
        by_tech[a.technician_membership_id].append((a, r))

    avail_by: dict[uuid.UUID, list[TechnicianAvailability]] = defaultdict(list)
    off_by: dict[uuid.UUID, list[TechnicianTimeOff]] = defaultdict(list)
    for av in db.scalars(
        select(TechnicianAvailability).where(
            TechnicianAvailability.organization_id == ctx.org_id,
            TechnicianAvailability.membership_id.in_(ids or [uuid.uuid4()]),
        )
    ):
        avail_by[av.membership_id].append(av)
    for t in db.scalars(
        select(TechnicianTimeOff)
        .where(
            TechnicianTimeOff.organization_id == ctx.org_id,
            TechnicianTimeOff.membership_id.in_(ids or [uuid.uuid4()]),
            # one day of margin so a conflict just outside the range is still detected
            TechnicianTimeOff.start_at < end + timedelta(days=1),
            TechnicianTimeOff.end_at > start - timedelta(days=1),
        )
        .order_by(TechnicianTimeOff.start_at)
    ):
        off_by[t.membership_id].append(t)

    first_day = start.astimezone(tz).date() - timedelta(days=1)
    last_day = end.astimezone(tz).date() + timedelta(days=1)
    out: list[ScheduleTechnician] = []
    for m, u in techs:
        items = by_tech.get(m.id, [])
        if not m.is_active and not items and technician_id is None:
            continue  # inactive technicians only appear when they have planned/past work
        intervals: list[ScheduleInterval] = []
        day = first_day
        while day <= last_day:
            for s, e in eligibility.local_intervals(avail_by[m.id], tz, day):
                if s < end and e > start:
                    intervals.append(ScheduleInterval(start_at=s, end_at=e))
            day += timedelta(days=1)
        offs = off_by[m.id]
        sched: list[ScheduleAssignment] = []
        for a, r in items:
            reasons: list[str] = []
            if a.active:
                if not eligibility.window_in_availability(avail_by[m.id], tz, a.start_at, a.end_at):
                    reasons.append("outside_availability")
                if any(t.start_at < a.end_at and t.end_at > a.start_at for t in offs):
                    reasons.append("time_off")
                # time off outside the visible range can still collide only inside the window
            sched.append(
                ScheduleAssignment(
                    assignment_id=a.id,
                    request_id=r.id,
                    display_id=display_id(r.number),
                    title=r.title,
                    priority=r.priority,
                    request_status=r.status,
                    assignment_status=a.status,
                    start_at=a.start_at,
                    end_at=a.end_at,
                    conflict=bool(reasons),
                    conflict_reasons=reasons,
                )
            )
        out.append(
            ScheduleTechnician(
                membership_id=m.id,
                name=u.full_name,
                is_active=m.is_active,
                availability=intervals,
                time_off=[
                    ScheduleTimeOff(id=t.id, start_at=t.start_at, end_at=t.end_at, reason=t.reason)
                    for t in offs
                    if t.start_at < end and t.end_at > start
                ],
                assignments=sched,
            )
        )
    return ScheduleOut(
        range=ScheduleRange(from_=start, to=end, timezone=ctx.timezone), technicians=out
    )
