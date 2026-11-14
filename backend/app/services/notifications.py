"""In-app notifications (COMM-03/04).

``notify`` inserts rows in the CALLER's transaction (no commit), de-duplicated by
``dedupe_key``. It is the single place Phase 3b hooks live push into (pg_notify/SSE): publish
after the surrounding transaction commits, keyed by recipient membership id.

Every read/write here is scoped to (org, recipient membership) so one user can never see or
mark another user's notification (404).
"""

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.audit import sanitize
from app.core.errors import NotFound
from app.core.pagination import PageParams, paginate_rows
from app.core.tenancy import Ctx
from app.models.enums import MembershipRole
from app.models.identity import Membership
from app.models.notifications import Notification

# notification types
ASSIGNMENT_CREATED = "ASSIGNMENT_CREATED"
ASSIGNMENT_RESCHEDULED = "ASSIGNMENT_RESCHEDULED"
ASSIGNMENT_REMOVED = "ASSIGNMENT_REMOVED"
ASSIGNMENT_DECLINED = "ASSIGNMENT_DECLINED"
ESTIMATE_SUBMITTED = "ESTIMATE_SUBMITTED"
ESTIMATE_DECIDED = "ESTIMATE_DECIDED"
JOB_COMPLETED = "JOB_COMPLETED"
REWORK_REQUESTED = "REWORK_REQUESTED"
OVERDUE_ESCALATION = "OVERDUE_ESCALATION"  # Phase 3b


def staff_recipients(db: Session, org_id: uuid.UUID) -> list[uuid.UUID]:
    """Active ADMIN + DISPATCHER memberships of the org."""
    return list(
        db.scalars(
            select(Membership.id).where(
                Membership.organization_id == org_id,
                Membership.is_active.is_(True),
                Membership.role.in_([MembershipRole.ADMIN, MembershipRole.DISPATCHER]),
            )
        )
    )


def notify(
    db: Session,
    org_id: uuid.UUID,
    recipients: Iterable[uuid.UUID | None],
    type_: str,
    title: str,
    body: str,
    request_id: uuid.UUID | None = None,
    data: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
    *,
    exclude: uuid.UUID | None = None,
) -> int:
    """Insert one row per distinct recipient (minus ``exclude``, normally the actor).

    Returns the number of rows actually inserted. No commit. Duplicate (recipient, dedupe_key)
    is silently skipped.
    """
    ids = [r for r in dict.fromkeys(recipients) if r is not None and r != exclude]
    if not ids:
        return 0
    rows = [
        {
            "organization_id": org_id,
            "recipient_membership_id": rid,
            "type": type_,
            "title": title[:200],
            "body": body,
            "request_id": request_id,
            "data": sanitize(data) if data is not None else None,
            "dedupe_key": dedupe_key,
        }
        for rid in ids
    ]
    res = db.execute(
        pg_insert(Notification)
        .values(rows)
        .on_conflict_do_nothing(
            index_elements=["organization_id", "recipient_membership_id", "dedupe_key"]
        )
        .returning(Notification.id)
    )
    return len(res.all())


# ---- reading / marking -----------------------------------------------------------------
def _own(ctx: Ctx) -> Any:
    return (
        Notification.organization_id == ctx.org_id,
        Notification.recipient_membership_id == ctx.membership_id,
    )


def list_notifications(
    db: Session, ctx: Ctx, params: PageParams, unread_only: bool
) -> tuple[list[Notification], int]:
    stmt = select(Notification).where(*_own(ctx))
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    rows, total = paginate_rows(
        db, stmt.order_by(Notification.created_at.desc(), Notification.id.desc()), params
    )
    return [r[0] for r in rows], total


def unread_count(db: Session, ctx: Ctx) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(*_own(ctx), Notification.read_at.is_(None))
        )
        or 0
    )


def mark_read(db: Session, ctx: Ctx, notification_id: uuid.UUID) -> Notification:
    n = db.scalars(
        select(Notification).where(*_own(ctx), Notification.id == notification_id).with_for_update()
    ).first()
    if n is None:
        raise NotFound("Notification not found.")
    if n.read_at is None:
        n.read_at = datetime.now(UTC)
    db.commit()
    return n


def mark_all_read(db: Session, ctx: Ctx) -> int:
    res = db.execute(
        update(Notification)
        .where(*_own(ctx), Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    db.commit()
    return getattr(res, "rowcount", 0) or 0
