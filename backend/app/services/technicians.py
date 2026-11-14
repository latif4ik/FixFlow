"""Technician profiles: skills, weekly availability, time off (SCHED-01 data)."""

import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.errors import NotFound
from app.core.pagination import PageParams, paginate_rows
from app.core.tenancy import Ctx
from app.models.enums import MembershipRole
from app.models.identity import Membership, User
from app.models.org import (
    Skill,
    TechnicianAvailability,
    TechnicianProfile,
    TechnicianSkill,
    TechnicianTimeOff,
)
from app.schemas.org import TechnicianOut
from app.services.members import ensure_technician_profile
from app.services.orgs import check_no_overlap
from app.services.util import like_pattern, validate_skill_ids


def _build(
    db: Session, ctx: Ctx, rows: list[tuple[Membership, User, TechnicianProfile | None]]
) -> list[TechnicianOut]:
    ids = [m.id for m, _, _ in rows]
    skills: dict[uuid.UUID, list[Skill]] = defaultdict(list)
    avail: dict[uuid.UUID, list[TechnicianAvailability]] = defaultdict(list)
    off: dict[uuid.UUID, list[TechnicianTimeOff]] = defaultdict(list)
    if ids:
        for mid, skill in db.execute(
            select(TechnicianSkill.membership_id, Skill)
            .join(Skill, Skill.id == TechnicianSkill.skill_id)
            .where(
                TechnicianSkill.organization_id == ctx.org_id,
                TechnicianSkill.membership_id.in_(ids),
            )
            .order_by(Skill.name)
        ):
            skills[mid].append(skill)
        for a in db.scalars(
            select(TechnicianAvailability)
            .where(
                TechnicianAvailability.organization_id == ctx.org_id,
                TechnicianAvailability.membership_id.in_(ids),
            )
            .order_by(TechnicianAvailability.weekday, TechnicianAvailability.start_time)
        ):
            avail[a.membership_id].append(a)
        for t in db.scalars(
            select(TechnicianTimeOff)
            .where(
                TechnicianTimeOff.organization_id == ctx.org_id,
                TechnicianTimeOff.membership_id.in_(ids),
            )
            .order_by(TechnicianTimeOff.start_at)
        ):
            off[t.membership_id].append(t)
    return [
        TechnicianOut.model_validate(
            {
                "membership_id": m.id,
                "user_id": u.id,
                "full_name": u.full_name,
                "email": u.email,
                "phone": u.phone,
                "is_active": m.is_active,
                "bio": p.bio if p else None,
                "skills": skills[m.id],
                "availability": avail[m.id],
                "time_off": off[m.id],
            },
            from_attributes=True,
        )
        for m, u, p in rows
    ]


def _base_stmt(ctx: Ctx):
    return (
        select(Membership, User, TechnicianProfile)
        .join(User, User.id == Membership.user_id)
        .outerjoin(TechnicianProfile, TechnicianProfile.membership_id == Membership.id)
        .where(
            Membership.organization_id == ctx.org_id, Membership.role == MembershipRole.TECHNICIAN
        )
    )


def list_technicians(
    db: Session,
    ctx: Ctx,
    params: PageParams,
    is_active: bool | None,
    skill_id: uuid.UUID | None,
    q: str | None,
) -> tuple[list[TechnicianOut], int]:
    stmt = _base_stmt(ctx)
    if is_active is not None:
        stmt = stmt.where(Membership.is_active.is_(is_active))
    if skill_id is not None:
        stmt = stmt.where(
            Membership.id.in_(
                select(TechnicianSkill.membership_id).where(
                    TechnicianSkill.organization_id == ctx.org_id,
                    TechnicianSkill.skill_id == skill_id,
                )
            )
        )
    if q:
        pat = like_pattern(q)
        stmt = stmt.where(
            or_(User.full_name.ilike(pat, escape="\\"), User.email.ilike(pat, escape="\\"))
        )
    rows, total = paginate_rows(db, stmt.order_by(User.full_name, Membership.id), params)
    return _build(db, ctx, [(m, u, p) for m, u, p in rows]), total


def get_technician(db: Session, ctx: Ctx, membership_id: uuid.UUID) -> TechnicianOut:
    row = db.execute(_base_stmt(ctx).where(Membership.id == membership_id)).first()
    if row is None:
        raise NotFound("Technician not found.")
    return _build(db, ctx, [(row[0], row[1], row[2])])[0]


def _require_technician(db: Session, ctx: Ctx, membership_id: uuid.UUID) -> None:
    ok = db.scalar(
        select(Membership.id).where(
            Membership.organization_id == ctx.org_id,
            Membership.id == membership_id,
            Membership.role == MembershipRole.TECHNICIAN,
        )
    )
    if ok is None:
        raise NotFound("Technician not found.")
    ensure_technician_profile(db, ctx.org_id, membership_id)


def set_skills(
    db: Session, ctx: Ctx, membership_id: uuid.UUID, skill_ids: list[uuid.UUID]
) -> TechnicianOut:
    _require_technician(db, ctx, membership_id)
    ids = validate_skill_ids(db, ctx, skill_ids, "skill_ids")
    before = sorted(
        str(i)
        for i in db.scalars(
            select(TechnicianSkill.skill_id).where(
                TechnicianSkill.organization_id == ctx.org_id,
                TechnicianSkill.membership_id == membership_id,
            )
        )
    )
    db.execute(
        delete(TechnicianSkill).where(
            TechnicianSkill.organization_id == ctx.org_id,
            TechnicianSkill.membership_id == membership_id,
        )
    )
    for sid in ids:
        db.add(
            TechnicianSkill(organization_id=ctx.org_id, membership_id=membership_id, skill_id=sid)
        )
    db.flush()
    record_audit(
        db,
        ctx,
        "technician.skills_replaced",
        "membership",
        membership_id,
        {"skill_ids": before},
        {"skill_ids": sorted(str(i) for i in ids)},
    )
    return get_technician(db, ctx, membership_id)


def _avail_dump(rows: list[TechnicianAvailability]) -> list[dict[str, Any]]:
    return [
        {"weekday": r.weekday, "start_time": r.start_time, "end_time": r.end_time} for r in rows
    ]


def set_availability(
    db: Session, ctx: Ctx, membership_id: uuid.UUID, intervals: list[dict[str, Any]]
) -> TechnicianOut:
    _require_technician(db, ctx, membership_id)
    check_no_overlap([(i["weekday"], i["start_time"], i["end_time"]) for i in intervals])
    current = list(
        db.scalars(
            select(TechnicianAvailability)
            .where(
                TechnicianAvailability.organization_id == ctx.org_id,
                TechnicianAvailability.membership_id == membership_id,
            )
            .order_by(TechnicianAvailability.weekday, TechnicianAvailability.start_time)
        )
    )
    before = _avail_dump(current)
    db.execute(
        delete(TechnicianAvailability).where(
            TechnicianAvailability.organization_id == ctx.org_id,
            TechnicianAvailability.membership_id == membership_id,
        )
    )
    for i in intervals:
        db.add(TechnicianAvailability(organization_id=ctx.org_id, membership_id=membership_id, **i))
    db.flush()
    record_audit(
        db,
        ctx,
        "technician.availability_replaced",
        "membership",
        membership_id,
        {"intervals": before},
        {"intervals": sorted(intervals, key=lambda i: (i["weekday"], i["start_time"]))},
    )
    return get_technician(db, ctx, membership_id)


def add_time_off(
    db: Session, ctx: Ctx, membership_id: uuid.UUID, data: dict[str, Any]
) -> TechnicianTimeOff:
    _require_technician(db, ctx, membership_id)
    t = TechnicianTimeOff(organization_id=ctx.org_id, membership_id=membership_id, **data)
    db.add(t)
    db.flush()
    record_audit(db, ctx, "technician.time_off_added", "membership", membership_id, None, data)
    return t


def delete_time_off(
    db: Session, ctx: Ctx, membership_id: uuid.UUID, time_off_id: uuid.UUID
) -> None:
    t = db.scalars(
        select(TechnicianTimeOff).where(
            TechnicianTimeOff.organization_id == ctx.org_id,
            TechnicianTimeOff.membership_id == membership_id,
            TechnicianTimeOff.id == time_off_id,
        )
    ).first()
    if t is None:
        raise NotFound("Time off entry not found.")
    before = {"start_at": t.start_at, "end_at": t.end_at, "reason": t.reason}
    db.delete(t)
    db.flush()
    record_audit(db, ctx, "technician.time_off_removed", "membership", membership_id, before, None)
