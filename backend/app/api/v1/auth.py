from fastapi import APIRouter, Request, Response
from sqlalchemy import select

from app.core.deps import CurrentCtx, DbDep, SessionUserDep
from app.core.errors import NotFound
from app.models.identity import Organization, User
from app.schemas.auth import (
    CurrentMembershipResponse,
    LoginRequest,
    LoginResponse,
    MembershipOut,
    MeResponse,
)
from app.schemas.common import OrgBrief, UserBrief
from app.services import auth as auth_service

router = APIRouter(tags=["auth"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _memberships(rows) -> list[MembershipOut]:
    return [
        MembershipOut(membership_id=m.id, organization=OrgBrief.model_validate(o), role=m.role)
        for m, o in rows
    ]


@router.post("/auth/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, db: DbDep) -> LoginResponse:
    result = auth_service.login(
        db,
        body.email,
        body.password,
        _client_ip(request),
        request.headers.get("user-agent"),
    )
    return LoginResponse(
        token=result.token,
        expires_at=result.session.expires_at,
        user=UserBrief.model_validate(result.user),
        memberships=_memberships(result.memberships),
    )


@router.post("/auth/logout", status_code=204)
def logout(request: Request, db: DbDep, su: SessionUserDep) -> Response:
    auth_service.revoke_session(db, su.session, _client_ip(request))
    db.commit()
    return Response(status_code=204)


@router.get("/me", response_model=MeResponse)
def me(db: DbDep, su: SessionUserDep) -> MeResponse:
    return MeResponse(
        user=UserBrief.model_validate(su.user),
        memberships=_memberships(auth_service.active_memberships(db, su.user.id)),
    )


@router.get("/me/membership", response_model=CurrentMembershipResponse)
def current_membership(db: DbDep, ctx: CurrentCtx) -> CurrentMembershipResponse:
    user = db.get(User, ctx.user_id)
    org = db.scalars(select(Organization).where(Organization.id == ctx.org_id)).first()
    if user is None or org is None:  # pragma: no cover - ctx guarantees both
        raise NotFound()
    return CurrentMembershipResponse(
        membership_id=ctx.membership_id,
        role=ctx.role,
        organization=OrgBrief.model_validate(org),
        user=UserBrief.model_validate(user),
    )
