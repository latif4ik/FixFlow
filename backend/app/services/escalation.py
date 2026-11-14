"""Overdue escalation (SLA-06/07): notify staff ONCE when a request first becomes overdue.

Candidate rows are claimed with ``FOR UPDATE SKIP LOCKED`` so concurrent runs never process
the same request, ``overdue_notified_at`` is the persisted once-only marker, and the
notification ``dedupe_key`` (``overdue:<request id>``) is a second, database-level guard.
Paused (estimate pending) and finished requests are never escalated.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.models.requests import ServiceRequest
from app.services import notifications
from app.services.request_events import add_event
from app.sla import service as sla_svc
from app.sla.calendar import BusinessCalendar

BATCH_SIZE = 100


def _candidates(now: datetime, org_id: uuid.UUID | None):
    stmt = select(ServiceRequest).where(
        ServiceRequest.sla_stopped_at.is_(None),
        ServiceRequest.sla_paused.is_(False),
        ServiceRequest.sla_due_at < now,
        ServiceRequest.overdue_notified_at.is_(None),
    )
    if org_id is not None:
        stmt = stmt.where(ServiceRequest.organization_id == org_id)
    return stmt.order_by(ServiceRequest.sla_due_at, ServiceRequest.id).limit(BATCH_SIZE)


def escalate_overdue(
    db: Session, now: datetime | None = None, org_id: uuid.UUID | None = None
) -> int:
    """Escalate every newly overdue request (all orgs, or one). Returns how many were escalated.

    Commits once per batch; safe to run repeatedly and concurrently."""
    now = now or clock.now()
    calendars: dict[uuid.UUID, BusinessCalendar] = {}
    total = 0
    try:
        while True:
            rows = list(db.scalars(_candidates(now, org_id).with_for_update(skip_locked=True)))
            if not rows:
                break
            for req in rows:
                cal = calendars.get(req.organization_id)
                if cal is None:
                    cal = calendars[req.organization_id] = sla_svc.load_calendar(
                        db, req.organization_id
                    )
                _escalate(db, req, now, cal)
            db.commit()
            total += len(rows)
    except BaseException:
        db.rollback()
        raise
    db.rollback()  # end the (empty) read transaction
    return total


def _escalate(db: Session, req: ServiceRequest, now: datetime, cal: BusinessCalendar) -> None:
    due = req.sla_due_at
    if due is None:  # unreachable: the candidate query requires a due instant
        return
    overdue_by = cal.business_minutes_between(due, now)
    req.overdue_notified_at = now
    add_event(
        db,
        None,
        req,
        "SLA_ESCALATED",
        data={"due_at": due, "overdue_by_minutes": overdue_by, "priority": req.priority.value},
    )
    notifications.notify(
        db,
        req.organization_id,
        notifications.staff_recipients(db, req.organization_id),
        notifications.OVERDUE_ESCALATION,
        "Request overdue",
        f"Request #{req.number} {req.title} missed its SLA and is overdue "
        f"({overdue_by} business minutes past due).",
        request_id=req.id,
        data={"due_at": due, "overdue_by_minutes": overdue_by, "number": req.number},
        dedupe_key=f"overdue:{req.id}",
    )
