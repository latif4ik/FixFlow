"""Requester satisfaction feedback (WEB-02, DATA-01). One immutable row per request."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.errors import Conflict, Forbidden
from app.core.tenancy import Ctx
from app.models.enums import RequestStatus
from app.models.feedback import Feedback
from app.services import notifications
from app.services.request_access import get_visible_request, is_owner_requester
from app.services.request_events import add_event

ELIGIBLE = frozenset({RequestStatus.COMPLETED, RequestStatus.CLOSED})


def get_feedback(db: Session, org_id: uuid.UUID, request_id: uuid.UUID) -> Feedback | None:
    return db.scalars(
        select(Feedback).where(
            Feedback.organization_id == org_id, Feedback.request_id == request_id
        )
    ).first()


def submit_feedback(
    db: Session, ctx: Ctx, request_id: uuid.UUID, rating: int, comment: str | None
) -> Feedback:
    try:
        request = get_visible_request(db, ctx, request_id, lock=True)
        if not is_owner_requester(ctx, request):
            raise Forbidden("Only the requester who created this request can leave feedback.")
        if request.status not in ELIGIBLE:
            raise Conflict(
                "Feedback can only be left once the work is completed or closed.",
                {"status": request.status.value},
            )
        if get_feedback(db, ctx.org_id, request.id) is not None:
            raise Conflict("Feedback was already submitted for this request.")
        fb = Feedback(
            organization_id=ctx.org_id,
            request_id=request.id,
            requester_membership_id=ctx.membership_id,
            rating=rating,
            comment=comment,
        )
        db.add(fb)
        db.flush()
        add_event(db, ctx, request, "FEEDBACK_SUBMITTED", data={"rating": rating})
        record_audit(
            db,
            ctx,
            "request.feedback",
            "service_request",
            request.id,
            after={"feedback_id": fb.id, "rating": rating},
        )
        notifications.notify(
            db,
            ctx.org_id,
            notifications.staff_recipients(db, ctx.org_id),
            notifications.FEEDBACK_RECEIVED,
            "Feedback received",
            f"Requester rated request #{request.number} {request.title}: {rating}/5.",
            request_id=request.id,
            data={"rating": rating},
            dedupe_key=f"feedback:{fb.id}",
        )
        db.commit()
        return fb
    except BaseException:
        db.rollback()
        raise
