"""Assignment flows (SCHED-03..06, LIFE-02/03).

Every function here runs inside ONE caller-owned transaction (no commit): the endpoint wraps
it in ``run_idempotent`` which commits on success and rolls back on any error, so the
assignment row(s), the request transition, request_events and audit rows land together or
not at all (API-05).

Concurrency: eligibility is evaluated first for clear 422 reasons, but the authoritative
guard is the DB: the assignment INSERT runs in a SAVEPOINT and PostgreSQL's gist EXCLUDE
constraint serializes competing overlapping inserts for one technician; the loser gets
SQLSTATE 23P01 (or 40P01 when PostgreSQL resolves the mutual wait as a deadlock) ->
409 ``schedule_conflict``.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.errors import AppError, Conflict, Forbidden
from app.core.tenancy import Ctx
from app.models.assignments import UQ_ONE_ACTIVE, Assignment
from app.models.enums import AssignmentStatus, MembershipRole, RequestStatus
from app.models.identity import Membership, User
from app.models.requests import ServiceRequest
from app.schemas.assignments import AssignmentOut
from app.schemas.requests import PersonBrief
from app.services import eligibility, lifecycle
from app.services.assignment_rows import new_assignment, release_active
from app.services.request_access import (
    get_active_assignment,
    get_visible_request,
    is_assigned_technician,
    is_staff,
)
from app.services.request_events import add_event

S = RequestStatus
A = AssignmentStatus
BEFORE_WORK = (S.SCHEDULED, S.ACCEPTED)


def _sqlstate(exc: DBAPIError) -> str | None:
    orig: Any = exc.orig
    return getattr(orig, "sqlstate", None) or getattr(getattr(orig, "diag", None), "sqlstate", None)


def names(db: Session, org_id: uuid.UUID, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    rows = db.execute(
        select(Membership.id, User.full_name)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == org_id, Membership.id.in_(ids))
    ).all()
    return {r[0]: r[1] for r in rows}


def _person(n: dict[uuid.UUID, str], mid: uuid.UUID | None) -> PersonBrief | None:
    return PersonBrief(membership_id=mid, name=n.get(mid, "")) if mid else None


def assignment_out(db: Session, org_id: uuid.UUID, rows: list[Assignment]) -> list[AssignmentOut]:
    ids: set[uuid.UUID] = set()
    for a in rows:
        ids |= {a.technician_membership_id, a.assigned_by_membership_id}
        if a.released_by_membership_id:
            ids.add(a.released_by_membership_id)
    n = names(db, org_id, ids)
    return [
        AssignmentOut(
            id=a.id,
            request_id=a.request_id,
            technician=PersonBrief(
                membership_id=a.technician_membership_id, name=n.get(a.technician_membership_id, "")
            ),
            start_at=a.start_at,
            end_at=a.end_at,
            status=a.status,
            active=a.active,
            assigned_by=_person(n, a.assigned_by_membership_id),
            released_by=_person(n, a.released_by_membership_id),
            released_reason=a.released_reason,
            released_at=a.released_at,
            created_at=a.created_at,
        )
        for a in rows
    ]


def _require_staff(ctx: Ctx) -> None:
    if not is_staff(ctx):
        raise Forbidden("Only dispatchers and admins can manage assignments.")


def _require_eligible(
    db: Session,
    ctx: Ctx,
    request: ServiceRequest,
    tech_id: uuid.UUID,
    start: datetime,
    end: datetime,
    ignore: uuid.UUID | None = None,
) -> None:
    res = eligibility.evaluate(
        db, ctx, request, tech_id, start, end, for_new=True, ignore_assignment_id=ignore
    )
    if not res.eligible:
        raise AppError(
            422,
            "technician_ineligible",
            "The technician cannot take this job in the requested window.",
            {
                "technician_membership_id": str(tech_id),
                "reasons": [r.as_dict() for r in res.reasons],
            },
        )


def _conflict(exc: DBAPIError, tech_id: uuid.UUID, start: datetime, end: datetime) -> AppError:
    state = _sqlstate(exc)
    # 23P01 exclusion_violation. 40P01 deadlock_detected: two overlapping inserts of one
    # technician each wait for the other's uncommitted row while checking the exclusion
    # constraint; PostgreSQL aborts one of them, which is just another way of losing the race.
    if state in ("23P01", "40P01"):
        return AppError(
            409,
            "schedule_conflict",
            "The technician was just booked for an overlapping time. Pick another slot.",
            {
                "technician_membership_id": str(tech_id),
                "start_at": start.isoformat(),
                "end_at": end.isoformat(),
            },
        )
    if state == "23505" and UQ_ONE_ACTIVE in str(exc.orig):
        return Conflict("This request already has an active assignment.")
    raise exc


def _snapshot(db: Session, ctx: Ctx, a: Assignment, reason: str | None = None) -> dict[str, Any]:
    n = names(db, ctx.org_id, {a.technician_membership_id})
    return {
        "assignment_id": str(a.id),
        "technician": {
            "membership_id": str(a.technician_membership_id),
            "name": n.get(a.technician_membership_id, ""),
        },
        "start_at": a.start_at.isoformat(),
        "end_at": a.end_at.isoformat(),
        "reason": reason,
    }


def _log(
    db: Session,
    ctx: Ctx,
    request: ServiceRequest,
    event: str,
    a: Assignment,
    reason: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    data = {**_snapshot(db, ctx, a, reason), **(extra or {})}
    add_event(db, ctx, request, event, data=data)
    record_audit(
        db,
        ctx,
        f"assignment.{event.lower()}",
        "assignment",
        a.id,
        after={"request_id": request.id, "status": a.status.value, **data},
    )


def _insert(
    db: Session,
    ctx: Ctx,
    request: ServiceRequest,
    tech_id: uuid.UUID,
    start: datetime,
    end: datetime,
    release_old: Assignment | None = None,
    old_reason: str | None = None,
) -> Assignment:
    """INSERT in a SAVEPOINT; the DB constraint is the authority on overlap (SCHED-04)."""
    try:
        with db.begin_nested():
            if release_old is not None:
                release_active(db, ctx, request, A.RESCHEDULED, old_reason)
            return new_assignment(db, ctx, request, tech_id, start, end)
    except DBAPIError as exc:
        raise _conflict(exc, tech_id, start, end) from exc


# ---- staff commands --------------------------------------------------------------------
def assign(
    db: Session,
    ctx: Ctx,
    request_id: uuid.UUID,
    tech_id: uuid.UUID,
    start: datetime,
    end: datetime,
) -> tuple[Assignment, ServiceRequest]:
    _require_staff(ctx)
    req = get_visible_request(db, ctx, request_id, lock=True)
    if req.status != S.TRIAGED:
        raise lifecycle.invalid_transition(
            req.status, S.SCHEDULED, "Only triaged requests can be assigned."
        )
    _require_eligible(db, ctx, req, tech_id, start, end)
    a = _insert(db, ctx, req, tech_id, start, end)
    _log(db, ctx, req, "ASSIGNED", a)
    # HOOK (Phase 3): notify the technician "assignment created" here.
    lifecycle.apply_transition(
        db, ctx, req.id, S.SCHEDULED, internal=True, extra={"assignment_id": a.id}
    )
    return a, req


def reschedule(
    db: Session,
    ctx: Ctx,
    request_id: uuid.UUID,
    tech_id: uuid.UUID,
    start: datetime,
    end: datetime,
    reason: str | None,
) -> tuple[Assignment, ServiceRequest]:
    """Reassign / move before work begins: old row RESCHEDULED, new ACTIVE row, and the request
    goes back through TRIAGED to SCHEDULED so the technician must (re)accept."""
    _require_staff(ctx)
    req = get_visible_request(db, ctx, request_id, lock=True)
    old = get_active_assignment(db, req)
    if req.status not in BEFORE_WORK or old is None:
        raise lifecycle.invalid_transition(
            req.status, S.SCHEDULED, "Only scheduled or accepted requests can be rescheduled."
        )
    _require_eligible(db, ctx, req, tech_id, start, end, ignore=old.id)
    text = reason or "Rescheduled by dispatcher."
    old_snapshot = _snapshot(db, ctx, old)
    new = _insert(db, ctx, req, tech_id, start, end, release_old=old, old_reason=text)
    # old row is already released, so the staff "unassign" rule applies on the request only
    lifecycle.apply_transition(
        db, ctx, req.id, S.TRIAGED, reason=text, internal=True, extra={"reschedule": True}
    )
    _log(db, ctx, req, "RESCHEDULED", new, reason, {"previous": old_snapshot})
    lifecycle.apply_transition(
        db, ctx, req.id, S.SCHEDULED, internal=True, extra={"assignment_id": new.id}
    )
    return new, req


def unassign(
    db: Session, ctx: Ctx, request_id: uuid.UUID, reason: str
) -> tuple[Assignment, ServiceRequest]:
    _require_staff(ctx)
    req = get_visible_request(db, ctx, request_id, lock=True)
    if req.status not in BEFORE_WORK:
        raise lifecycle.invalid_transition(
            req.status, S.TRIAGED, "Work has already begun or nothing is assigned."
        )
    lifecycle.apply_transition(db, ctx, req.id, S.TRIAGED, reason=reason, internal=True)
    a = release_active(db, ctx, req, A.UNASSIGNED, reason)
    if a is None:  # lifecycle guarantees an active row here; fail loudly otherwise
        raise Conflict("No active assignment to release.")
    _log(db, ctx, req, "UNASSIGNED", a, reason)
    return a, req


# ---- technician commands ---------------------------------------------------------------
def decline(
    db: Session, ctx: Ctx, request_id: uuid.UUID, reason: str
) -> tuple[Assignment, ServiceRequest]:
    req = get_visible_request(db, ctx, request_id, lock=True)
    if not is_assigned_technician(db, ctx, req):
        raise Forbidden("Only the assigned technician can decline this job.")
    if req.status not in BEFORE_WORK:
        raise lifecycle.invalid_transition(
            req.status, S.TRIAGED, "A job can only be declined before work starts."
        )
    lifecycle.apply_transition(db, ctx, req.id, S.TRIAGED, reason=reason, internal=True)
    a = release_active(db, ctx, req, A.DECLINED, reason)
    if a is None:  # lifecycle guarantees an active row here; fail loudly otherwise
        raise Conflict("No active assignment to release.")
    _log(db, ctx, req, "DECLINED", a, reason)
    # HOOK (Phase 3): notify dispatchers "assignment declined" here.
    return a, req


def history(db: Session, ctx: Ctx, request_id: uuid.UUID) -> list[Assignment]:
    """Staff: every assignment row; technician: only their own; others: forbidden."""
    req = get_visible_request(db, ctx, request_id)
    stmt = select(Assignment).where(
        Assignment.organization_id == ctx.org_id, Assignment.request_id == req.id
    )
    if not is_staff(ctx):
        if ctx.role != MembershipRole.TECHNICIAN:
            raise Forbidden("You cannot view assignment history.")
        stmt = stmt.where(Assignment.technician_membership_id == ctx.membership_id)
    return list(db.scalars(stmt.order_by(Assignment.created_at, Assignment.id)))
