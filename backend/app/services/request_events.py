"""Writers for the per-request timeline (also the future SLA event source)."""

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import events as live
from app.core.audit import sanitize
from app.core.tenancy import Ctx
from app.models.assignments import Assignment
from app.models.enums import AssignmentStatus
from app.models.requests import RequestEvent, ServiceRequest
from app.sla.engine import is_sla_event

# Human-readable labels for the activity timeline.
EVENT_LABELS = {
    "REQUEST_CREATED": "Request created",
    "STATUS_CHANGED": "Status changed",
    "PRIORITY_CHANGED": "Priority changed",
    "CATEGORY_CHANGED": "Category changed",
    "DUPLICATE_LINKED": "Marked as related to another request",
    "NOTE_ADDED": "Note added",
    "FILE_UPLOADED": "File uploaded",
    "REQUEST_UPDATED": "Request details updated",
    "ASSIGNED": "Technician assigned",
    "UNASSIGNED": "Technician unassigned",
    "DECLINED": "Technician declined the job",
    "RESCHEDULED": "Appointment rescheduled",
    "ESTIMATE_SUBMITTED": "Estimate submitted for approval",
    "ESTIMATE_APPROVED": "Estimate approved",
    "ESTIMATE_REJECTED": "Estimate rejected",
    "ESTIMATE_WITHDRAWN": "Estimate withdrawn",
    "MATERIAL_USED": "Material used",
    "SLA_ESCALATED": "Escalated: request is overdue",
    "FEEDBACK_SUBMITTED": "Feedback submitted",
}
# Event types requesters never see (internal triage activity).
STAFF_ONLY_EVENTS = frozenset(
    {
        "PRIORITY_CHANGED",
        "CATEGORY_CHANGED",
        "DUPLICATE_LINKED",
        "ASSIGNED",
        "UNASSIGNED",
        "DECLINED",
        "RESCHEDULED",
        "MATERIAL_USED",
        "SLA_ESCALATED",
    }
)


def add_event(
    db: Session,
    ctx: Ctx | None,
    request: ServiceRequest,
    type_: str,
    *,
    from_status: str | None = None,
    to_status: str | None = None,
    data: dict[str, Any] | None = None,
    at: datetime | None = None,
) -> RequestEvent:
    """Append a timeline event. SLA-relevant events (create, priority change, estimate
    pause/resume, complete/cancel/reopen) re-derive the request's SLA cache in the SAME
    transaction, so no code path can forget it. ``at`` overrides the event time (seed/tests)."""
    ev = RequestEvent(
        organization_id=request.organization_id,
        request_id=request.id,
        type=type_,
        actor_membership_id=ctx.membership_id if ctx else None,
        from_status=from_status,
        to_status=to_status,
        data=sanitize(data) if data is not None else None,
    )
    if at is not None:
        ev.created_at = at
    db.add(ev)
    db.flush()
    if is_sla_event(type_, to_status):
        from app.sla.service import recompute_sla  # local import: sla.service imports models

        recompute_sla(db, request)
    _publish_changed(db, request)
    return ev


def _publish_changed(db: Session, request: ServiceRequest) -> None:
    """Queue a ``request.changed`` signal (delivered by Postgres only if the txn commits).

    Technicians addressed: those with a live (ACTIVE/COMPLETED) assignment plus any whose
    assignment row was touched in THIS transaction (so a just-unassigned/declined technician
    learns that the job disappeared)."""
    techs = db.scalars(
        select(Assignment.technician_membership_id)
        .where(
            Assignment.organization_id == request.organization_id,
            Assignment.request_id == request.id,
            Assignment.status.in_([AssignmentStatus.ACTIVE, AssignmentStatus.COMPLETED])
            | (Assignment.updated_at >= func.now()),
        )
        .distinct()
    )
    live.publish(
        db,
        {
            "org_id": request.organization_id,
            "kind": live.REQUEST_CHANGED,
            "request_id": request.id,
            "requester_membership_id": request.requester_membership_id,
            "technician_membership_ids": sorted(techs, key=str),
        },
    )
