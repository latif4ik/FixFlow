"""Request dependencies: DB session, authenticated session user, org context, role guards."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.errors import AppError, Forbidden, Unauthorized
from app.core.security import hash_token
from app.core.tenancy import Ctx
from app.db.session import get_db
from app.models.enums import MembershipRole
from app.models.identity import Membership, Organization, Session, User

LAST_USED_REFRESH = timedelta(minutes=1)

DbDep = Annotated[DbSession, Depends(get_db)]


@dataclass(frozen=True)
class SessionUser:
    user: User
    session: Session


def _bearer(authorization: str | None) -> str:
    if not authorization:
        raise Unauthorized("Authentication required.")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise Unauthorized("Invalid authorization header.")
    return token.strip()


def get_session_user(
    db: DbDep,
    authorization: Annotated[str | None, Header()] = None,
) -> SessionUser:
    token = _bearer(authorization)
    session = db.scalars(select(Session).where(Session.token_hash == hash_token(token))).first()
    if session is None or session.revoked_at is not None:
        raise Unauthorized("Invalid or revoked session.")
    now = datetime.now(UTC)
    if session.expires_at <= now:
        raise AppError(401, "session_expired", "Session expired. Please sign in again.")
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise Unauthorized("Invalid or revoked session.")
    if session.last_used_at is None or now - session.last_used_at > LAST_USED_REFRESH:
        session.last_used_at = now
        db.commit()
    return SessionUser(user=user, session=session)


SessionUserDep = Annotated[SessionUser, Depends(get_session_user)]


def get_ctx(
    su: SessionUserDep,
    db: DbDep,
    x_org_id: Annotated[str | None, Header(alias="X-Org-Id")] = None,
) -> Ctx:
    """Resolve session -> active user -> active org -> active membership, on every request."""
    if not x_org_id:
        raise AppError(400, "org_required", "The X-Org-Id header is required.")
    try:
        org_id = uuid.UUID(x_org_id)
    except ValueError:
        raise AppError(400, "org_required", "X-Org-Id must be a valid UUID.") from None
    row = db.execute(
        select(Membership, Organization)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(
            Membership.user_id == su.user.id,
            Membership.organization_id == org_id,
            Membership.is_active.is_(True),
            Organization.is_active.is_(True),
        )
    ).first()
    if row is None:
        raise AppError(403, "org_access_denied", "You do not have access to this organization.")
    membership, org = row
    return Ctx(
        user_id=su.user.id,
        org_id=org.id,
        membership_id=membership.id,
        role=membership.role,
        timezone=org.timezone,
    )


CurrentCtx = Annotated[Ctx, Depends(get_ctx)]


def require_roles(*roles: MembershipRole):
    allowed = frozenset(roles)

    def dependency(ctx: CurrentCtx) -> Ctx:
        if ctx.role not in allowed:
            raise Forbidden("Your role is not allowed to perform this action.")
        return ctx

    return dependency


R = MembershipRole
AdminCtx = Annotated[Ctx, Depends(require_roles(R.ADMIN))]
StaffCtx = Annotated[Ctx, Depends(require_roles(R.ADMIN, R.DISPATCHER))]
