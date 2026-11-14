"""Low-level assignment row operations shared by the lifecycle engine and the assignment service.

Nothing here commits; callers own the transaction.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.tenancy import Ctx
from app.models.assignments import Assignment
from app.models.enums import AssignmentStatus
from app.models.requests import ServiceRequest
from app.services.request_access import get_active_assignment


def release_active(
    db: Session,
    ctx: Ctx,
    request: ServiceRequest,
    status: AssignmentStatus,
    reason: str | None = None,
) -> Assignment | None:
    """Move the request's ACTIVE assignment to a terminal status (frees the technician slot)."""
    if status == AssignmentStatus.ACTIVE:
        raise ValueError("release_active needs a terminal status")
    a = get_active_assignment(db, request)
    if a is None:
        return None
    a.status = status
    a.active = False
    a.released_at = datetime.now(UTC)
    a.released_by_membership_id = ctx.membership_id
    a.released_reason = reason
    db.flush()
    return a


def new_assignment(
    db: Session,
    ctx: Ctx,
    request: ServiceRequest,
    technician_membership_id: uuid.UUID,
    start_at: datetime,
    end_at: datetime,
) -> Assignment:
    a = Assignment(
        organization_id=ctx.org_id,
        request_id=request.id,
        technician_membership_id=technician_membership_id,
        start_at=start_at,
        end_at=end_at,
        status=AssignmentStatus.ACTIVE,
        active=True,
        assigned_by_membership_id=ctx.membership_id,
    )
    db.add(a)
    db.flush()
    return a
