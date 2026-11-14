"""Estimate endpoints (EST-01..06). Staff author + submit; the requester decides."""

import uuid
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response

from app.core.deps import CurrentCtx, DbDep, StaffCtx
from app.core.idempotency import IdempotencyKeyHeader, Outcome, run_idempotent
from app.core.pagination import Page, Pagination, make_page
from app.core.tenancy import Ctx
from app.models.enums import EstimateStatus
from app.models.estimates import Estimate
from app.schemas.estimates import (
    DecisionIn,
    EstimateCreate,
    EstimateLinesPut,
    EstimateOut,
    EstimatePatch,
    WithdrawIn,
)
from app.services import estimates as svc
from app.services.estimates import build_out

router = APIRouter(tags=["estimates"])


def _body(db: DbDep, ctx: Ctx, est: Estimate) -> dict[str, Any]:
    return build_out(db, ctx, [est])[0].model_dump(mode="json")


def _run(
    response: Response,
    db: DbDep,
    ctx: Ctx,
    key: str | None,
    endpoint: str,
    payload: Any,
    status: int,
    fn: Callable[[], Estimate],
) -> Any:
    def op() -> tuple[int, Any]:
        return status, _body(db, ctx, fn())

    outcome: Outcome = run_idempotent(db, ctx, key, endpoint, payload, op)
    response.status_code = outcome.status
    if outcome.replayed:
        response.headers["Idempotent-Replayed"] = "true"
    return outcome.body


@router.post("/requests/{request_id}/estimates", response_model=EstimateOut, status_code=201)
def create_estimate(
    request_id: uuid.UUID,
    body: EstimateCreate,
    response: Response,
    db: DbDep,
    ctx: StaffCtx,
    idempotency_key: IdempotencyKeyHeader = None,
) -> Any:
    """Create the next DRAFT version (labor + material lines). Totals are computed server-side."""
    return _run(
        response,
        db,
        ctx,
        idempotency_key,
        f"POST /requests/{request_id}/estimates",
        body.model_dump(mode="json"),
        201,
        lambda: svc.create_draft(
            db, ctx, request_id, body.labor_minutes, body.labor_rate_minor, body.notes, body.lines
        ),
    )


@router.get("/requests/{request_id}/estimates", response_model=list[EstimateOut])
def request_estimates(request_id: uuid.UUID, db: DbDep, ctx: CurrentCtx) -> list[EstimateOut]:
    """Revision history, oldest version first (requesters: submitted versions only;
    technicians: the current approved estimate only)."""
    return svc.list_for_request(db, ctx, request_id)


@router.get("/estimates", response_model=Page[EstimateOut])
def list_estimates(
    db: DbDep,
    ctx: StaffCtx,
    params: Pagination,
    status: Annotated[list[EstimateStatus] | None, Query()] = None,
    request_id: uuid.UUID | None = None,
) -> dict:
    items, total = svc.list_all(db, ctx, params, status, request_id)
    return make_page(items, total, params)


@router.get("/estimates/{estimate_id}", response_model=EstimateOut)
def get_estimate(estimate_id: uuid.UUID, db: DbDep, ctx: CurrentCtx) -> EstimateOut:
    est, _ = svc.load_visible(db, ctx, estimate_id)
    return build_out(db, ctx, [est])[0]


@router.patch("/estimates/{estimate_id}", response_model=EstimateOut)
def patch_estimate(
    estimate_id: uuid.UUID, body: EstimatePatch, db: DbDep, ctx: StaffCtx
) -> dict[str, Any]:
    """Edit labor/notes of a DRAFT; submitted estimates are immutable (409)."""
    est = svc.patch_draft(db, ctx, estimate_id, body.model_dump(exclude_unset=True))
    out = _body(db, ctx, est)
    db.commit()
    return out


@router.put("/estimates/{estimate_id}/lines", response_model=EstimateOut)
def put_estimate_lines(
    estimate_id: uuid.UUID, body: EstimateLinesPut, db: DbDep, ctx: StaffCtx
) -> dict[str, Any]:
    """Replace the whole material-line list of a DRAFT."""
    est = svc.put_lines(db, ctx, estimate_id, body.lines)
    out = _body(db, ctx, est)
    db.commit()
    return out


@router.post("/estimates/{estimate_id}/submit", response_model=EstimateOut)
def submit_estimate(
    estimate_id: uuid.UUID,
    response: Response,
    db: DbDep,
    ctx: StaffCtx,
    idempotency_key: IdempotencyKeyHeader = None,
) -> Any:
    """DRAFT -> AWAITING_APPROVAL; supersedes the previous live version."""
    return _run(
        response,
        db,
        ctx,
        idempotency_key,
        f"POST /estimates/{estimate_id}/submit",
        {},
        200,
        lambda: svc.submit(db, ctx, estimate_id),
    )


@router.post("/estimates/{estimate_id}/decision", response_model=EstimateOut)
def decide_estimate(
    estimate_id: uuid.UUID,
    body: DecisionIn,
    response: Response,
    db: DbDep,
    ctx: CurrentCtx,
    idempotency_key: IdempotencyKeyHeader = None,
) -> Any:
    """Requester approves/rejects the pending version. Stale/duplicate decisions -> 409."""
    return _run(
        response,
        db,
        ctx,
        idempotency_key,
        f"POST /estimates/{estimate_id}/decision",
        body.model_dump(mode="json"),
        200,
        lambda: svc.decide(db, ctx, estimate_id, body.version, body.decision, body.reason),
    )


@router.post("/estimates/{estimate_id}/withdraw", response_model=EstimateOut)
def withdraw_estimate(
    estimate_id: uuid.UUID,
    body: WithdrawIn,
    response: Response,
    db: DbDep,
    ctx: StaffCtx,
    idempotency_key: IdempotencyKeyHeader = None,
) -> Any:
    """Withdraw a rejected/pending estimate (opens the start gate if nothing newer is live)."""
    return _run(
        response,
        db,
        ctx,
        idempotency_key,
        f"POST /estimates/{estimate_id}/withdraw",
        body.model_dump(mode="json"),
        200,
        lambda: svc.withdraw(db, ctx, estimate_id, body.reason),
    )
