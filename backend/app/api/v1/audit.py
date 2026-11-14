import uuid

from fastapi import APIRouter
from pydantic import AwareDatetime
from sqlalchemy import select

from app.core.deps import AdminCtx, DbDep
from app.core.pagination import Page, Pagination, make_page, paginate_rows
from app.models.audit import AuditEvent
from app.models.identity import Membership, User
from app.schemas.org import AuditEventOut

router = APIRouter(tags=["audit"])


@router.get("/audit", response_model=Page[AuditEventOut])
def list_audit(
    db: DbDep,
    ctx: AdminCtx,
    params: Pagination,
    action: str | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    actor: uuid.UUID | None = None,
    date_from: AwareDatetime | None = None,
    date_to: AwareDatetime | None = None,
) -> dict:
    stmt = (
        select(AuditEvent, User.full_name)
        .outerjoin(
            Membership,
            (Membership.organization_id == AuditEvent.organization_id)
            & (Membership.id == AuditEvent.actor_membership_id),
        )
        .outerjoin(User, User.id == Membership.user_id)
        .where(AuditEvent.organization_id == ctx.org_id)
    )
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    if target_type:
        stmt = stmt.where(AuditEvent.target_type == target_type)
    if target_id:
        stmt = stmt.where(AuditEvent.target_id == target_id)
    if actor:
        stmt = stmt.where(AuditEvent.actor_membership_id == actor)
    if date_from:
        stmt = stmt.where(AuditEvent.created_at >= date_from)
    if date_to:
        stmt = stmt.where(AuditEvent.created_at <= date_to)
    stmt = stmt.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
    rows, total = paginate_rows(db, stmt, params)
    items = [
        AuditEventOut(
            id=e.id,
            actor_membership_id=e.actor_membership_id,
            actor_name=name,
            action=e.action,
            target_type=e.target_type,
            target_id=e.target_id,
            before=e.before,
            after=e.after,
            created_at=e.created_at,
        )
        for e, name in rows
    ]
    return make_page(items, total, params)
