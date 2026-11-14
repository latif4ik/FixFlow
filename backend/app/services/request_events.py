"""Writers for the per-request timeline (also the future SLA event source)."""

from typing import Any

from sqlalchemy.orm import Session

from app.core.audit import sanitize
from app.core.tenancy import Ctx
from app.models.requests import RequestEvent, ServiceRequest

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
}
# Event types requesters never see (internal triage activity).
STAFF_ONLY_EVENTS = frozenset({"PRIORITY_CHANGED", "CATEGORY_CHANGED", "DUPLICATE_LINKED"})


def add_event(
    db: Session,
    ctx: Ctx | None,
    request: ServiceRequest,
    type_: str,
    *,
    from_status: str | None = None,
    to_status: str | None = None,
    data: dict[str, Any] | None = None,
) -> RequestEvent:
    ev = RequestEvent(
        organization_id=request.organization_id,
        request_id=request.id,
        type=type_,
        actor_membership_id=ctx.membership_id if ctx else None,
        from_status=from_status,
        to_status=to_status,
        data=sanitize(data) if data is not None else None,
    )
    db.add(ev)
    db.flush()
    return ev
