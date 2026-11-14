"""Staff/membership administration (ORG-04, ROLE-05, AUTH-05)."""

import uuid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.pagination import PageParams, paginate_rows
from app.core.security import hash_password
from app.core.tenancy import Ctx
from app.models.enums import MembershipRole
from app.models.identity import Membership, User
from app.models.org import TechnicianProfile
from app.services.auth import revoke_all_sessions
from app.services.security_events import record_security_event
from app.services.util import like_pattern


def list_members(
    db: Session,
    ctx: Ctx,
    params: PageParams,
    role: MembershipRole | None,
    is_active: bool | None,
    q: str | None,
) -> tuple[list[Any], int]:
    stmt = (
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == ctx.org_id)
    )
    if role is not None:
        stmt = stmt.where(Membership.role == role)
    if is_active is not None:
        stmt = stmt.where(Membership.is_active.is_(is_active))
    if q:
        pat = like_pattern(q)
        stmt = stmt.where(
            or_(User.full_name.ilike(pat, escape="\\"), User.email.ilike(pat, escape="\\"))
        )
    stmt = stmt.order_by(User.full_name, Membership.id)
    return paginate_rows(db, stmt, params)


def get_member(db: Session, ctx: Ctx, membership_id: uuid.UUID) -> tuple[Membership, User]:
    row = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == ctx.org_id, Membership.id == membership_id)
    ).first()
    if row is None:
        raise NotFound("Member not found.")
    return row[0], row[1]


def ensure_technician_profile(db: Session, org_id: uuid.UUID, membership_id: uuid.UUID) -> None:
    if db.get(TechnicianProfile, membership_id) is None:
        db.add(TechnicianProfile(organization_id=org_id, membership_id=membership_id))
        db.flush()


def create_member(
    db: Session,
    ctx: Ctx,
    *,
    email: str,
    full_name: str,
    role: MembershipRole,
    password: str | None,
) -> tuple[Membership, User]:
    user = db.scalars(select(User).where(User.email == email)).first()
    if user is None:
        if not password:
            raise ValidationFailed(
                "A password is required for a new user.",
                [{"field": "password", "message": "required when the email is not registered"}],
            )
        user = User(email=email, full_name=full_name, password_hash=hash_password(password))
        db.add(user)
        db.flush()
    else:
        exists = db.scalar(
            select(Membership.id).where(
                Membership.organization_id == ctx.org_id, Membership.user_id == user.id
            )
        )
        if exists is not None:
            raise Conflict(
                "This user is already a member of the organization.",
                {"fields": ["email"]},
            )
    membership = Membership(organization_id=ctx.org_id, user_id=user.id, role=role)
    db.add(membership)
    db.flush()
    if role == MembershipRole.TECHNICIAN:
        ensure_technician_profile(db, ctx.org_id, membership.id)
    record_audit(
        db,
        ctx,
        "membership.created",
        "membership",
        membership.id,
        None,
        {"user_id": user.id, "email": user.email, "role": role, "is_active": True},
    )
    return membership, user


def _snapshot(m: Membership) -> dict[str, Any]:
    return {"role": m.role, "is_active": m.is_active}


def update_member(
    db: Session,
    ctx: Ctx,
    membership_id: uuid.UUID,
    role: MembershipRole | None,
    is_active: bool | None,
) -> tuple[Membership, User]:
    # Lock all active admins of this org so concurrent demotions serialize.
    admins = db.scalars(
        select(Membership)
        .where(
            Membership.organization_id == ctx.org_id,
            Membership.role == MembershipRole.ADMIN,
            Membership.is_active.is_(True),
        )
        .order_by(Membership.id)
        .with_for_update()
    ).all()
    membership, user = get_member(db, ctx, membership_id)
    is_self = membership.id == ctx.membership_id
    new_role = role if role is not None else membership.role
    new_active = is_active if is_active is not None else membership.is_active

    if is_self and (new_role != membership.role or new_active is False):
        raise ValidationFailed(
            "You cannot change your own role or deactivate yourself.",
            [{"field": "membership_id", "message": "self-modification is not allowed"}],
        )
    removes_admin = (
        membership.role == MembershipRole.ADMIN
        and membership.is_active
        and (new_role != MembershipRole.ADMIN or not new_active)
    )
    if removes_admin and not any(a.id != membership.id for a in admins):
        raise Conflict("The organization must keep at least one active admin.")

    before = _snapshot(membership)
    role_changed = new_role != membership.role
    active_changed = new_active != membership.is_active
    old_role = membership.role
    membership.role = new_role
    membership.is_active = new_active
    db.flush()
    if not (role_changed or active_changed):
        return membership, user

    if new_role == MembershipRole.TECHNICIAN:
        ensure_technician_profile(db, ctx.org_id, membership.id)

    after = _snapshot(membership)
    if role_changed:
        record_audit(db, ctx, "membership.role_changed", "membership", membership.id, before, after)
        record_security_event(
            db,
            "membership_role_changed",
            user_id=user.id,
            details={
                "organization_id": ctx.org_id,
                "membership_id": membership.id,
                "from": old_role,
                "to": new_role,
                "actor_user_id": ctx.user_id,
            },
        )
    if active_changed:
        action = "membership.activated" if new_active else "membership.deactivated"
        record_audit(db, ctx, action, "membership", membership.id, before, after)
        if not new_active:
            record_security_event(
                db,
                "membership_deactivated",
                user_id=user.id,
                details={
                    "organization_id": ctx.org_id,
                    "membership_id": membership.id,
                    "actor_user_id": ctx.user_id,
                },
            )
            remaining = db.scalar(
                select(func.count())
                .select_from(Membership)
                .where(Membership.user_id == user.id, Membership.is_active.is_(True))
            )
            if not remaining:
                revoke_all_sessions(db, user.id, "last_membership_deactivated")
    return membership, user
