import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.core.deps import AdminCtx, CurrentCtx, DbDep, StaffCtx
from app.core.errors import Forbidden
from app.core.pagination import Page, Pagination, make_page
from app.models.enums import MembershipRole
from app.models.org import TechnicianTimeOff
from app.schemas.org import (
    AvailabilityBody,
    TechnicianOut,
    TechnicianSkillsBody,
    TimeOffIn,
    TimeOffOut,
)
from app.services import technicians as svc

router = APIRouter(prefix="/technicians", tags=["technicians"])


@router.get("", response_model=Page[TechnicianOut])
def list_technicians(
    db: DbDep,
    ctx: StaffCtx,
    params: Pagination,
    is_active: bool | None = None,
    skill_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> dict:
    items, total = svc.list_technicians(db, ctx, params, is_active, skill_id, q)
    return make_page(items, total, params)


@router.get("/me", response_model=TechnicianOut)
def my_profile(db: DbDep, ctx: CurrentCtx) -> TechnicianOut:
    if ctx.role != MembershipRole.TECHNICIAN:
        raise Forbidden("Only technicians have a technician profile.")
    return svc.get_technician(db, ctx, ctx.membership_id)


@router.get("/{membership_id}", response_model=TechnicianOut)
def get_technician(membership_id: uuid.UUID, db: DbDep, ctx: CurrentCtx) -> TechnicianOut:
    allowed = ctx.role in (MembershipRole.ADMIN, MembershipRole.DISPATCHER) or (
        ctx.role == MembershipRole.TECHNICIAN and membership_id == ctx.membership_id
    )
    if not allowed:
        raise Forbidden("Your role is not allowed to perform this action.")
    return svc.get_technician(db, ctx, membership_id)


@router.put("/{membership_id}/skills", response_model=TechnicianOut)
def put_skills(
    membership_id: uuid.UUID, body: TechnicianSkillsBody, db: DbDep, ctx: AdminCtx
) -> TechnicianOut:
    out = svc.set_skills(db, ctx, membership_id, body.skill_ids)
    db.commit()
    return out


@router.put("/{membership_id}/availability", response_model=TechnicianOut)
def put_availability(
    membership_id: uuid.UUID, body: AvailabilityBody, db: DbDep, ctx: AdminCtx
) -> TechnicianOut:
    out = svc.set_availability(db, ctx, membership_id, [i.model_dump() for i in body.intervals])
    db.commit()
    return out


@router.post("/{membership_id}/time-off", response_model=TimeOffOut, status_code=201)
def add_time_off(
    membership_id: uuid.UUID, body: TimeOffIn, db: DbDep, ctx: AdminCtx
) -> TechnicianTimeOff:
    t = svc.add_time_off(db, ctx, membership_id, body.model_dump())
    db.commit()
    return t


@router.delete("/{membership_id}/time-off/{time_off_id}", status_code=204)
def delete_time_off(
    membership_id: uuid.UUID, time_off_id: uuid.UUID, db: DbDep, ctx: AdminCtx
) -> Response:
    svc.delete_time_off(db, ctx, membership_id, time_off_id)
    db.commit()
    return Response(status_code=204)
