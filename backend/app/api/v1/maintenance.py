import uuid

from fastapi import APIRouter, Response

from app.core.deps import DbDep, StaffCtx
from app.core.idempotency import IdempotencyKeyHeader, run_idempotent
from app.core.pagination import Page, Pagination, make_page
from app.schemas.maintenance import (
    GenerateIn,
    GenerationReport,
    PlanDetail,
    PlanIn,
    PlanOut,
    PlanPatch,
)
from app.services import maintenance as svc

router = APIRouter(tags=["maintenance"])


@router.get("/maintenance-plans", response_model=Page[PlanOut])
def list_plans(
    db: DbDep,
    ctx: StaffCtx,
    params: Pagination,
    asset_id: uuid.UUID | None = None,
    is_enabled: bool | None = None,
) -> dict:
    items, total = svc.list_plans(db, ctx, params, asset_id, is_enabled)
    return make_page(items, total, params)


@router.post("/maintenance-plans", response_model=PlanDetail, status_code=201)
def create_plan(body: PlanIn, db: DbDep, ctx: StaffCtx) -> PlanDetail:
    try:
        out = svc.create_plan(db, ctx, body.model_dump())
        db.commit()
    except BaseException:
        db.rollback()
        raise
    return out


@router.post("/maintenance-plans/generate", response_model=GenerationReport)
def generate(
    body: GenerateIn,
    response: Response,
    db: DbDep,
    ctx: StaffCtx,
    idempotency_key: IdempotencyKeyHeader = None,
) -> dict:
    """Generate the requests of every occurrence due on or before ``as_of`` (caller's org)."""

    def op() -> tuple[int, dict]:
        report = svc.generate(db, ctx.org_id, body.as_of, commit_each=False, ctx=ctx)
        return 200, report.model_dump(mode="json")

    outcome = run_idempotent(
        db, ctx, idempotency_key, "POST /maintenance-plans/generate", {"as_of": str(body.as_of)}, op
    )
    if outcome.replayed:
        response.headers["Idempotent-Replayed"] = "true"
    return outcome.body


@router.get("/maintenance-plans/{plan_id}", response_model=PlanDetail)
def get_plan(plan_id: uuid.UUID, db: DbDep, ctx: StaffCtx) -> PlanDetail:
    return svc.get_plan(db, ctx, plan_id)


@router.patch("/maintenance-plans/{plan_id}", response_model=PlanDetail)
def patch_plan(plan_id: uuid.UUID, body: PlanPatch, db: DbDep, ctx: StaffCtx) -> PlanDetail:
    try:
        out = svc.update_plan(db, ctx, plan_id, body.model_dump(exclude_unset=True))
        db.commit()
    except BaseException:
        db.rollback()
        raise
    return out
