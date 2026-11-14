"""Candidates, assignment commands, technician lifecycle actions, job list and schedule."""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import CurrentCtx, DbDep, R, StaffCtx, require_roles
from app.core.errors import AppError
from app.core.idempotency import IdempotencyKeyHeader, run_idempotent
from app.core.pagination import Page, Pagination, make_page
from app.core.tenancy import Ctx
from app.models.enums import RequestStatus
from app.models.requests import ServiceRequest
from app.schemas.assignments import (
    AssignmentIn,
    AssignmentOut,
    AssignmentResult,
    CandidateOut,
    MyAssignmentItem,
    RequestStateBrief,
    RescheduleIn,
    ScheduleOut,
    UnassignIn,
)
from app.schemas.requests import RequestDetail, RequiredReasonIn
from app.schemas.suggestions import SuggestionsOut
from app.services import assignments as svc
from app.services import eligibility, lifecycle
from app.services import requests as requests_svc
from app.services import schedule as schedule_svc
from app.services import suggestions as suggest_svc
from app.services.request_access import get_visible_request

router = APIRouter(tags=["assignments"])
TechCtx = Annotated[Ctx, Depends(require_roles(R.TECHNICIAN))]


class NoteBody(BaseModel):
    note: str


def _result(db: Session, ctx: Ctx, a, req: ServiceRequest) -> dict[str, Any]:
    out = AssignmentResult(
        assignment=svc.assignment_out(db, ctx.org_id, [a])[0],
        request=RequestStateBrief(
            id=req.id, display_id=requests_svc.display_id(req.number), status=req.status
        ),
    )
    return out.model_dump(mode="json")


def _utc_iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def _respond(response: Response, outcome) -> Any:
    response.status_code = outcome.status
    if outcome.replayed:
        response.headers["Idempotent-Replayed"] = "true"
    return outcome.body


@router.get("/requests/{request_id}/candidates", response_model=list[CandidateOut])
def candidates(
    request_id: uuid.UUID,
    db: DbDep,
    ctx: StaffCtx,
    start_at: Annotated[datetime | None, Query()] = None,
    end_at: Annotated[datetime | None, Query()] = None,
) -> list[dict[str, Any]]:
    """Technicians for this job with eligibility reasons and workload (window optional)."""
    if (start_at is None) != (end_at is None):
        raise AppError(
            422,
            "validation_error",
            "Provide both start_at and end_at or neither.",
            [{"field": "start_at", "message": "start_at and end_at go together"}],
        )
    req = get_visible_request(db, ctx, request_id)
    return eligibility.candidates(db, ctx, req, start_at, end_at)


@router.get("/requests/{request_id}/suggestions", response_model=SuggestionsOut)
def suggestions(
    request_id: uuid.UUID,
    db: DbDep,
    ctx: StaffCtx,
    horizon_days: Annotated[int, Query(ge=1, le=31)] = 14,
    duration_minutes: Annotated[int | None, Query(ge=30, le=720)] = None,
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
) -> dict[str, Any]:
    """Smart Assign: earliest free slots of skilled, active technicians (staff only).

    The request must be TRIAGED, or SCHEDULED/ACCEPTED (reschedule mode: its own current
    assignment does not block). ``duration_minutes`` (30..720, multiple of 15) defaults to the
    category's default duration. Slots are on a 15-minute grid, inside one availability interval,
    clear of time off and active assignments (adjacency is allowed); at most 2 non-overlapping
    suggestions per technician, ranked by start, then workload, then name.

    Suggestions are ADVISORY and not reserved: assigning still goes through
    ``POST``/``PUT /requests/{id}/assignment`` with all guards, so a stale suggestion yields the
    normal 409 (schedule_conflict) or 422 (technician_ineligible) there; refresh and retry.
    """
    if duration_minutes is not None and duration_minutes % 15:
        raise AppError(
            422,
            "validation_error",
            "duration_minutes must be a multiple of 15.",
            [{"field": "duration_minutes", "message": "must be a multiple of 15"}],
        )
    req = get_visible_request(db, ctx, request_id)
    return suggest_svc.suggest(db, ctx, req, horizon_days, duration_minutes, limit)


@router.post("/requests/{request_id}/assignment", response_model=AssignmentResult, status_code=201)
def assign(
    request_id: uuid.UUID,
    body: AssignmentIn,
    response: Response,
    db: DbDep,
    ctx: StaffCtx,
    idempotency_key: IdempotencyKeyHeader = None,
) -> Any:
    """Assign a technician (TRIAGED -> SCHEDULED). Supports ``Idempotency-Key``."""

    def op() -> tuple[int, Any]:
        a, req = svc.assign(
            db, ctx, request_id, body.technician_membership_id, body.start_at, body.end_at
        )
        return 201, _result(db, ctx, a, req)

    payload = {
        "t": str(body.technician_membership_id),
        "s": _utc_iso(body.start_at),
        "e": _utc_iso(body.end_at),
    }
    return _respond(
        response,
        run_idempotent(
            db, ctx, idempotency_key, f"POST /requests/{request_id}/assignment", payload, op
        ),
    )


@router.put("/requests/{request_id}/assignment", response_model=AssignmentResult)
def reschedule(
    request_id: uuid.UUID,
    body: RescheduleIn,
    response: Response,
    db: DbDep,
    ctx: StaffCtx,
    idempotency_key: IdempotencyKeyHeader = None,
) -> Any:
    """Reschedule / reassign before work begins; the technician must accept again."""

    def op() -> tuple[int, Any]:
        a, req = svc.reschedule(
            db,
            ctx,
            request_id,
            body.technician_membership_id,
            body.start_at,
            body.end_at,
            body.reason,
        )
        return 200, _result(db, ctx, a, req)

    payload = {
        "t": str(body.technician_membership_id),
        "s": _utc_iso(body.start_at),
        "e": _utc_iso(body.end_at),
        "r": body.reason,
    }
    return _respond(
        response,
        run_idempotent(
            db, ctx, idempotency_key, f"PUT /requests/{request_id}/assignment", payload, op
        ),
    )


@router.post("/requests/{request_id}/assignment/unassign", response_model=AssignmentResult)
def unassign(
    request_id: uuid.UUID,
    body: UnassignIn,
    response: Response,
    db: DbDep,
    ctx: StaffCtx,
    idempotency_key: IdempotencyKeyHeader = None,
) -> Any:
    """Remove the technician before work begins (reason required). POST rather than DELETE
    with a body, which many proxies/clients drop."""

    def op() -> tuple[int, Any]:
        a, req = svc.unassign(db, ctx, request_id, body.reason)
        return 200, _result(db, ctx, a, req)

    return _respond(
        response,
        run_idempotent(
            db,
            ctx,
            idempotency_key,
            f"POST /requests/{request_id}/assignment/unassign",
            {"r": body.reason},
            op,
        ),
    )


@router.post("/requests/{request_id}/decline", response_model=AssignmentResult)
def decline(
    request_id: uuid.UUID,
    body: RequiredReasonIn,
    response: Response,
    db: DbDep,
    ctx: TechCtx,
    idempotency_key: IdempotencyKeyHeader = None,
) -> Any:
    """Assigned technician declines before starting; the request returns to TRIAGED."""

    def op() -> tuple[int, Any]:
        a, req = svc.decline(db, ctx, request_id, body.reason)
        return 200, _result(db, ctx, a, req)

    return _respond(
        response,
        run_idempotent(
            db, ctx, idempotency_key, f"POST /requests/{request_id}/decline", {"r": body.reason}, op
        ),
    )


def _do(
    db: Session,
    ctx: Ctx,
    request_id: uuid.UUID,
    to: RequestStatus,
    reason: str | None = None,
    note: str | None = None,
) -> RequestDetail:
    lifecycle.transition(db, ctx, request_id, to, reason=reason, note_body=note)
    return requests_svc.get_detail(db, ctx, request_id)


@router.post("/requests/{request_id}/accept", response_model=RequestDetail)
def accept(request_id: uuid.UUID, db: DbDep, ctx: TechCtx) -> RequestDetail:
    return _do(db, ctx, request_id, RequestStatus.ACCEPTED)


@router.post("/requests/{request_id}/start", response_model=RequestDetail)
def start(request_id: uuid.UUID, db: DbDep, ctx: TechCtx) -> RequestDetail:
    # The estimate approval gate (EST-04) is a guard of the lifecycle rule "start".
    return _do(db, ctx, request_id, RequestStatus.IN_PROGRESS)


@router.post("/requests/{request_id}/block", response_model=RequestDetail)
def block(request_id: uuid.UUID, body: RequiredReasonIn, db: DbDep, ctx: TechCtx) -> RequestDetail:
    return _do(db, ctx, request_id, RequestStatus.BLOCKED, reason=body.reason)


@router.post("/requests/{request_id}/resume", response_model=RequestDetail)
def resume(request_id: uuid.UUID, body: NoteBody, db: DbDep, ctx: TechCtx) -> RequestDetail:
    return _do(db, ctx, request_id, RequestStatus.IN_PROGRESS, note=body.note)


@router.post("/requests/{request_id}/complete", response_model=RequestDetail)
def complete(request_id: uuid.UUID, body: NoteBody, db: DbDep, ctx: TechCtx) -> RequestDetail:
    return _do(db, ctx, request_id, RequestStatus.COMPLETED, note=body.note)


@router.get("/requests/{request_id}/assignments", response_model=list[AssignmentOut])
def assignment_history(request_id: uuid.UUID, db: DbDep, ctx: CurrentCtx) -> list[AssignmentOut]:
    """Staff: full history. Technician: only their own rows. Requesters: 403."""
    rows = svc.history(db, ctx, request_id)
    return svc.assignment_out(db, ctx.org_id, rows)


@router.get("/me/assignments", response_model=Page[MyAssignmentItem])
def my_assignments(
    db: DbDep,
    ctx: TechCtx,
    params: Pagination,
    scope: Annotated[Literal["upcoming", "active", "history"], Query()] = "upcoming",
) -> dict:
    items, total = schedule_svc.my_assignments(db, ctx, params, scope)
    return make_page(items, total, params)


@router.get("/schedule", response_model=ScheduleOut, response_model_by_alias=True)
def schedule(
    db: DbDep,
    ctx: StaffCtx,
    from_: Annotated[datetime, Query(alias="from")],
    to: Annotated[datetime, Query()],
    technician_id: uuid.UUID | None = None,
) -> ScheduleOut:
    """Planned workloads per technician for [from, to) (max 31 days), with conflict flags."""
    return schedule_svc.schedule(db, ctx, from_, to, technician_id)
