"""Technician eligibility: the single source of truth for candidates AND assignment guards.

Reason codes (stable): inactive, missing_skills, invalid_window, in_past, outside_availability,
time_off, overlap.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenancy import Ctx
from app.models.assignments import Assignment
from app.models.enums import MembershipRole
from app.models.identity import Membership, User
from app.models.org import (
    CategoryRequiredSkill,
    Skill,
    TechnicianAvailability,
    TechnicianSkill,
    TechnicianTimeOff,
)
from app.models.requests import ServiceRequest

MIN_APPOINTMENT = timedelta(minutes=30)


@dataclass
class Reason:
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


@dataclass
class EligibilityResult:
    eligible: bool
    reasons: list[Reason]


def tz_of(ctx: Ctx) -> ZoneInfo:
    return ZoneInfo(ctx.timezone)


# ---- pure helpers (shared with the schedule view) --------------------------------------
def local_intervals(
    avail: list[TechnicianAvailability], tz: ZoneInfo, day: date
) -> list[tuple[datetime, datetime]]:
    """Concrete UTC intervals of the weekly availability on local date ``day``."""
    out = []
    for a in avail:
        if a.weekday != day.weekday():
            continue
        s = datetime.combine(day, a.start_time, tzinfo=tz).astimezone(UTC)
        e = datetime.combine(day, a.end_time, tzinfo=tz).astimezone(UTC)
        out.append((s, e))
    return sorted(out)


def window_in_availability(
    avail: list[TechnicianAvailability], tz: ZoneInfo, start: datetime, end: datetime
) -> bool:
    """True when [start, end] lies entirely within ONE interval of one local day."""
    ls, le = start.astimezone(tz), end.astimezone(tz)
    if ls.date() != le.date():
        return False  # crossing local midnight is never inside a single daily interval
    st: time = ls.time().replace(tzinfo=None)
    et: time = le.time().replace(tzinfo=None)
    return any(a.weekday == ls.weekday() and a.start_time <= st and et <= a.end_time for a in avail)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


# ---- data access -----------------------------------------------------------------------
def required_skill_names(db: Session, request: ServiceRequest) -> list[str]:
    return list(
        db.scalars(
            select(Skill.name)
            .join(CategoryRequiredSkill, CategoryRequiredSkill.skill_id == Skill.id)
            .where(
                CategoryRequiredSkill.organization_id == request.organization_id,
                CategoryRequiredSkill.category_id == request.category_id,
            )
            .order_by(Skill.name)
        )
    )


def technician_skill_names(db: Session, org_id: uuid.UUID, mid: uuid.UUID) -> list[str]:
    return list(
        db.scalars(
            select(Skill.name)
            .join(TechnicianSkill, TechnicianSkill.skill_id == Skill.id)
            .where(TechnicianSkill.organization_id == org_id, TechnicianSkill.membership_id == mid)
            .order_by(Skill.name)
        )
    )


def availability_rows(
    db: Session, org_id: uuid.UUID, mid: uuid.UUID
) -> list[TechnicianAvailability]:
    return list(
        db.scalars(
            select(TechnicianAvailability).where(
                TechnicianAvailability.organization_id == org_id,
                TechnicianAvailability.membership_id == mid,
            )
        )
    )


def active_assignments_in(
    db: Session,
    org_id: uuid.UUID,
    mid: uuid.UUID,
    start: datetime,
    end: datetime,
    ignore_assignment_id: uuid.UUID | None = None,
) -> list[tuple[Assignment, int]]:
    stmt = (
        select(Assignment, ServiceRequest.number)
        .join(
            ServiceRequest,
            (ServiceRequest.organization_id == Assignment.organization_id)
            & (ServiceRequest.id == Assignment.request_id),
        )
        .where(
            Assignment.organization_id == org_id,
            Assignment.technician_membership_id == mid,
            Assignment.active.is_(True),
            Assignment.start_at < end,
            Assignment.end_at > start,
        )
        .order_by(Assignment.start_at)
    )
    if ignore_assignment_id is not None:
        stmt = stmt.where(Assignment.id != ignore_assignment_id)
    return [(a, n) for a, n in db.execute(stmt).all()]


def _technician(db: Session, org_id: uuid.UUID, mid: uuid.UUID) -> tuple[Membership, User] | None:
    row = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == org_id, Membership.id == mid)
    ).first()
    return (row[0], row[1]) if row else None


# ---- evaluation ------------------------------------------------------------------------
def evaluate(
    db: Session,
    ctx: Ctx,
    request: ServiceRequest,
    technician_membership_id: uuid.UUID,
    start_at: datetime | None,
    end_at: datetime | None,
    *,
    for_new: bool,
    ignore_assignment_id: uuid.UUID | None = None,
    skills_only: bool = False,
) -> EligibilityResult:
    """All reasons the technician cannot take ``request`` in [start_at, end_at)."""
    reasons: list[Reason] = []
    tech = _technician(db, ctx.org_id, technician_membership_id)
    if (
        tech is None
        or tech[0].role != MembershipRole.TECHNICIAN
        or not tech[0].is_active
        or not tech[1].is_active
    ):
        reasons.append(Reason("inactive", "The technician is not an active technician."))
        return EligibilityResult(False, reasons)

    required = required_skill_names(db, request)
    have = set(technician_skill_names(db, ctx.org_id, technician_membership_id))
    missing = [s for s in required if s not in have]
    if missing:
        reasons.append(
            Reason(
                "missing_skills",
                "The technician lacks required skills: " + ", ".join(missing) + ".",
                {"skills": missing},
            )
        )
    if skills_only or start_at is None or end_at is None:
        return EligibilityResult(not reasons, reasons)

    start_at, end_at = _aware(start_at), _aware(end_at)
    if end_at <= start_at or end_at - start_at < MIN_APPOINTMENT:
        reasons.append(
            Reason("invalid_window", "The appointment must be at least 30 minutes long.")
        )
        return EligibilityResult(False, reasons)
    if for_new and start_at < datetime.now(UTC):
        reasons.append(Reason("in_past", "The appointment cannot start in the past."))
    avail = availability_rows(db, ctx.org_id, technician_membership_id)
    if not window_in_availability(avail, tz_of(ctx), start_at, end_at):
        reasons.append(
            Reason(
                "outside_availability",
                "The window is outside the technician's weekly availability.",
            )
        )
    off = db.scalars(
        select(TechnicianTimeOff)
        .where(
            TechnicianTimeOff.organization_id == ctx.org_id,
            TechnicianTimeOff.membership_id == technician_membership_id,
            TechnicianTimeOff.start_at < end_at,
            TechnicianTimeOff.end_at > start_at,
        )
        .order_by(TechnicianTimeOff.start_at)
    ).all()
    if off:
        reasons.append(
            Reason(
                "time_off",
                "The technician has time off in this window.",
                {"time_off_id": str(off[0].id), "time_off_ids": [str(o.id) for o in off]},
            )
        )
    clashes = active_assignments_in(
        db, ctx.org_id, technician_membership_id, start_at, end_at, ignore_assignment_id
    )
    if clashes:
        reasons.append(
            Reason(
                "overlap",
                "The technician already has an active assignment in this window.",
                {
                    "assignments": [
                        {
                            "request_number": n,
                            "display_id": f"REQ-{n}",
                            "start_at": a.start_at.isoformat(),
                            "end_at": a.end_at.isoformat(),
                        }
                        for a, n in clashes
                    ]
                },
            )
        )
    return EligibilityResult(not reasons, reasons)


def candidates(
    db: Session,
    ctx: Ctx,
    request: ServiceRequest,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> list[dict[str, Any]]:
    """Every active technician with eligibility, reasons and workload (SCHED-05)."""
    rows = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.organization_id == ctx.org_id,
            Membership.role == MembershipRole.TECHNICIAN,
            Membership.is_active.is_(True),
            User.is_active.is_(True),
        )
    ).all()
    now = datetime.now(UTC)
    horizon = now + timedelta(days=7)
    has_window = start_at is not None and end_at is not None
    out: list[dict[str, Any]] = []
    for m, u in rows:
        res = evaluate(db, ctx, request, m.id, start_at, end_at, for_new=True)
        active = db.scalars(
            select(Assignment).where(
                Assignment.organization_id == ctx.org_id,
                Assignment.technician_membership_id == m.id,
                Assignment.active.is_(True),
            )
        ).all()
        minutes = 0
        for a in active:
            lo, hi = max(a.start_at, now), min(a.end_at, horizon)
            if hi > lo:
                minutes += int((hi - lo).total_seconds() // 60)
        reasons = [r.as_dict() for r in res.reasons]
        out.append(
            {
                "membership_id": m.id,
                "name": u.full_name,
                "skills": technician_skill_names(db, ctx.org_id, m.id),
                "eligible": res.eligible,
                "reasons": reasons,
                "available": (
                    not any(
                        r["code"] in ("outside_availability", "time_off", "overlap")
                        for r in reasons
                    )
                    if has_window
                    else None
                ),
                "workload": {
                    "active_assignments": len(active),
                    "planned_minutes_next_7_days": minutes,
                },
            }
        )
    out.sort(
        key=lambda c: (
            not c["eligible"],
            c["workload"]["planned_minutes_next_7_days"],
            c["name"].lower(),
        )
    )
    return out
