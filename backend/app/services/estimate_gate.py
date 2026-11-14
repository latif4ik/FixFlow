"""Current-estimate lookup + the ACCEPTED -> IN_PROGRESS gate (EST-04).

Kept free of service imports so the lifecycle engine can use it without cycles.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.enums import EstimateStatus
from app.models.estimates import Estimate
from app.models.requests import ServiceRequest

ES = EstimateStatus
# DRAFT (not yet submitted) and SUPERSEDED (replaced / withdrawn) never count as "current".
CURRENT_STATUSES = (ES.AWAITING_APPROVAL, ES.APPROVED, ES.REJECTED)


def current_estimate(db: Session, org_id: uuid.UUID, request_id: uuid.UUID) -> Estimate | None:
    """Latest submitted version that is still live (AWAITING_APPROVAL / APPROVED / REJECTED)."""
    return db.scalars(
        select(Estimate)
        .where(
            Estimate.organization_id == org_id,
            Estimate.request_id == request_id,
            Estimate.status.in_(CURRENT_STATUSES),
        )
        .order_by(Estimate.version.desc())
        .limit(1)
        .execution_options(populate_existing=True)
    ).first()


def start_blocker(db: Session, request: ServiceRequest) -> Estimate | None:
    """The current estimate if it blocks starting work (not APPROVED), else None."""
    est = current_estimate(db, request.organization_id, request.id)
    return est if est is not None and est.status != ES.APPROVED else None


def blocked_reason(est: Estimate) -> str:
    if est.status == ES.REJECTED:
        return (
            f"Estimate v{est.version} was rejected. A dispatcher must replace or withdraw it "
            "before work can start."
        )
    return f"Waiting for the requester to approve estimate v{est.version}."


def gate_error(est: Estimate) -> AppError:
    return AppError(
        409,
        "estimate_not_approved",
        blocked_reason(est),
        {
            "estimate_id": str(est.id),
            "estimate_status": est.status.value,
            "estimate_version": est.version,
        },
    )
