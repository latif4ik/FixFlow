"""Inventory + material usage endpoints (INV-01..06)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response

from app.core.deps import AdminCtx, CurrentCtx, DbDep, StaffCtx
from app.core.idempotency import IdempotencyKeyHeader, run_idempotent
from app.core.pagination import Page, Pagination, make_page
from app.schemas.inventory import (
    AdditionIn,
    AdjustmentIn,
    ConsumeIn,
    ItemCreate,
    ItemOut,
    ItemPatch,
    MovementOut,
    UsageOut,
)
from app.services import inventory as svc

router = APIRouter(tags=["inventory"])


@router.get("/inventory/low-stock", response_model=list[ItemOut])
def low_stock(db: DbDep, ctx: StaffCtx) -> list[ItemOut]:
    """Active items with stock <= reorder threshold, most depleted first."""
    return svc.low_stock(db, ctx)


@router.get("/inventory", response_model=Page[ItemOut])
def list_items(
    db: DbDep,
    ctx: CurrentCtx,
    params: Pagination,
    q: Annotated[str | None, Query(max_length=100)] = None,
    active: bool | None = None,
    low_stock: bool = False,
) -> dict:
    """Staff: full items. Technicians: active items with id/code/name/unit/stock only."""
    items, total = svc.list_items(db, ctx, params, q, active, low_stock)
    return make_page(items, total, params)


@router.post("/inventory", response_model=ItemOut, status_code=201)
def create_item(body: ItemCreate, db: DbDep, ctx: AdminCtx) -> ItemOut:
    item = svc.create_item(
        db,
        ctx,
        body.code,
        body.name,
        body.unit,
        body.stock_quantity,
        body.reorder_threshold,
        body.unit_price_minor,
    )
    out = svc._item_out(item, ctx)
    db.commit()
    return out


@router.get("/inventory/{item_id}", response_model=ItemOut)
def get_item(item_id: uuid.UUID, db: DbDep, ctx: CurrentCtx) -> ItemOut:
    return svc.get_item(db, ctx, item_id)


@router.patch("/inventory/{item_id}", response_model=ItemOut)
def patch_item(item_id: uuid.UUID, body: ItemPatch, db: DbDep, ctx: AdminCtx) -> ItemOut:
    """Edit name/unit/threshold/price or deactivate (items are never deleted). Stock changes
    go through additions/adjustments so the ledger stays complete."""
    item = svc.patch_item(db, ctx, item_id, body.model_dump(exclude_unset=True))
    out = svc._item_out(item, ctx)
    db.commit()
    return out


def _movement_body(db: DbDep, ctx: Any, mv: Any) -> dict[str, Any]:
    return svc.movement_out(db, ctx, [mv])[0].model_dump(mode="json")


@router.post("/inventory/{item_id}/additions", response_model=MovementOut, status_code=201)
def add_stock(
    item_id: uuid.UUID,
    body: AdditionIn,
    response: Response,
    db: DbDep,
    ctx: AdminCtx,
    idempotency_key: IdempotencyKeyHeader = None,
) -> Any:
    def op() -> tuple[int, Any]:
        return 201, _movement_body(
            db, ctx, svc.add_stock(db, ctx, item_id, body.quantity, body.reason)
        )

    outcome = run_idempotent(
        db,
        ctx,
        idempotency_key,
        f"POST /inventory/{item_id}/additions",
        body.model_dump(mode="json"),
        op,
    )
    response.status_code = outcome.status
    if outcome.replayed:
        response.headers["Idempotent-Replayed"] = "true"
    return outcome.body


@router.post("/inventory/{item_id}/adjustments", response_model=MovementOut, status_code=201)
def adjust_stock(
    item_id: uuid.UUID,
    body: AdjustmentIn,
    response: Response,
    db: DbDep,
    ctx: AdminCtx,
    idempotency_key: IdempotencyKeyHeader = None,
) -> Any:
    """Signed correction; can never make stock negative (409 insufficient_stock)."""

    def op() -> tuple[int, Any]:
        return 201, _movement_body(
            db, ctx, svc.adjust_stock(db, ctx, item_id, body.delta, body.reason)
        )

    outcome = run_idempotent(
        db,
        ctx,
        idempotency_key,
        f"POST /inventory/{item_id}/adjustments",
        body.model_dump(mode="json"),
        op,
    )
    response.status_code = outcome.status
    if outcome.replayed:
        response.headers["Idempotent-Replayed"] = "true"
    return outcome.body


@router.get("/inventory/{item_id}/movements", response_model=Page[MovementOut])
def movements(item_id: uuid.UUID, db: DbDep, ctx: StaffCtx, params: Pagination) -> dict:
    items, total = svc.list_movements(db, ctx, item_id, params)
    return make_page(items, total, params)


@router.post("/requests/{request_id}/materials", response_model=UsageOut, status_code=201)
def consume_material(
    request_id: uuid.UUID, body: ConsumeIn, response: Response, db: DbDep, ctx: CurrentCtx
) -> UsageOut:
    """Assigned technician records consumption on an IN_PROGRESS job. ``client_command_id``
    makes retries safe: 201 first time, 200 + the original record on an identical replay,
    409 ``idempotency_key_reused`` for a different payload, 409 ``insufficient_stock``."""
    usage, created = svc.consume(
        db, ctx, request_id, body.client_command_id, body.item_id, body.quantity
    )
    response.status_code = 201 if created else 200
    if not created:
        response.headers["Idempotent-Replayed"] = "true"
    return svc.usage_out(db, ctx, [usage])[0]


@router.get("/requests/{request_id}/materials", response_model=list[UsageOut])
def request_materials(request_id: uuid.UUID, db: DbDep, ctx: CurrentCtx) -> list[UsageOut]:
    return svc.list_usage(db, ctx, request_id)
