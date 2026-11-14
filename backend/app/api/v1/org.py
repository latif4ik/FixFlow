import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response
from sqlalchemy import select

from app.core.deps import AdminCtx, CurrentCtx, DbDep, StaffCtx
from app.core.pagination import Page, Pagination, make_page, paginate_rows
from app.models.enums import MembershipRole
from app.models.identity import Membership, Organization, User
from app.models.org import Holiday
from app.schemas.org import (
    BusinessHoursBody,
    HolidayIn,
    HolidayOut,
    HoursInterval,
    MemberCreate,
    MemberOut,
    MemberPatch,
    OrgOut,
    OrgPatch,
)
from app.services import members as member_service
from app.services import orgs as org_service

router = APIRouter(tags=["organization"])


def _member_out(m: Membership, u: User) -> MemberOut:
    return MemberOut(
        membership_id=m.id,
        user_id=u.id,
        email=u.email,
        full_name=u.full_name,
        phone=u.phone,
        role=m.role,
        is_active=m.is_active,
        created_at=m.created_at,
    )


@router.get("/org", response_model=OrgOut)
def get_org(db: DbDep, ctx: CurrentCtx) -> Organization:
    return db.scalars(select(Organization).where(Organization.id == ctx.org_id)).one()


@router.patch("/org", response_model=OrgOut)
def patch_org(body: OrgPatch, db: DbDep, ctx: AdminCtx) -> Organization:
    org = org_service.update_org(db, ctx, body.model_dump(exclude_unset=True))
    db.commit()
    return org


@router.get("/org/business-hours", response_model=BusinessHoursBody)
def get_hours(db: DbDep, ctx: CurrentCtx) -> BusinessHoursBody:
    rows = org_service.list_business_hours(db, ctx)
    return BusinessHoursBody(
        intervals=[
            HoursInterval(weekday=r.weekday, open_time=r.open_time, close_time=r.close_time)
            for r in rows
        ]
    )


@router.put("/org/business-hours", response_model=BusinessHoursBody)
def put_hours(body: BusinessHoursBody, db: DbDep, ctx: AdminCtx) -> BusinessHoursBody:
    rows = org_service.replace_business_hours(db, ctx, [i.model_dump() for i in body.intervals])
    db.commit()
    return BusinessHoursBody(
        intervals=[
            HoursInterval(weekday=r.weekday, open_time=r.open_time, close_time=r.close_time)
            for r in rows
        ]
    )


@router.get("/org/holidays", response_model=Page[HolidayOut])
def list_holidays(db: DbDep, ctx: CurrentCtx, params: Pagination) -> dict:
    stmt = (
        select(Holiday)
        .where(Holiday.organization_id == ctx.org_id)
        .order_by(Holiday.date, Holiday.id)
    )
    rows, total = paginate_rows(db, stmt, params)
    return make_page([HolidayOut.model_validate(r[0]) for r in rows], total, params)


@router.post("/org/holidays", response_model=HolidayOut, status_code=201)
def add_holiday(body: HolidayIn, db: DbDep, ctx: AdminCtx) -> Holiday:
    h = org_service.create_holiday(db, ctx, body.model_dump())
    db.commit()
    return h


@router.delete("/org/holidays/{holiday_id}", status_code=204)
def remove_holiday(holiday_id: uuid.UUID, db: DbDep, ctx: AdminCtx) -> Response:
    org_service.delete_holiday(db, ctx, holiday_id)
    db.commit()
    return Response(status_code=204)


@router.get("/org/members", response_model=Page[MemberOut])
def list_members(
    db: DbDep,
    ctx: StaffCtx,
    params: Pagination,
    role: MembershipRole | None = None,
    is_active: bool | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> dict:
    rows, total = member_service.list_members(db, ctx, params, role, is_active, q)
    return make_page([_member_out(m, u) for m, u in rows], total, params)


@router.post("/org/members", response_model=MemberOut, status_code=201)
def create_member(body: MemberCreate, db: DbDep, ctx: AdminCtx) -> MemberOut:
    m, u = member_service.create_member(
        db, ctx, email=body.email, full_name=body.full_name, role=body.role, password=body.password
    )
    db.commit()
    return _member_out(m, u)


@router.patch("/org/members/{membership_id}", response_model=MemberOut)
def patch_member(
    membership_id: uuid.UUID, body: MemberPatch, db: DbDep, ctx: AdminCtx
) -> MemberOut:
    m, u = member_service.update_member(db, ctx, membership_id, body.role, body.is_active)
    db.commit()
    return _member_out(m, u)
