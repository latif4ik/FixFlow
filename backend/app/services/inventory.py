"""Inventory items, stock ledger and material consumption (INV-01..06).

Stock safety lives in the database: ``stock_quantity >= 0`` is a CHECK, and every change is a
single conditional ``UPDATE ... SET stock = stock -/+ :q ... RETURNING`` so concurrent writers
cannot oversell. Consumption writes the usage record, the ledger row, the request event and the
audit row in the SAME transaction as the decrement, and is replay-safe through the unique
``(organization_id, client_command_id)`` key plus a payload hash.
"""

import hashlib
import json
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import money
from app.core.audit import record_audit
from app.core.errors import AppError, Conflict, Forbidden, NotFound, ValidationFailed
from app.core.pagination import PageParams, paginate_rows
from app.core.tenancy import Ctx
from app.models.enums import MembershipRole, RequestStatus, StockMovementKind
from app.models.inventory import InventoryItem, MaterialUsage, StockMovement
from app.schemas.inventory import ItemOut, MovementOut, UsageItemBrief, UsageOut
from app.schemas.requests import PersonBrief
from app.services.assignments import names
from app.services.request_access import (
    get_visible_request,
    is_assigned_technician,
    is_staff,
)
from app.services.request_events import add_event

_CLIENT_CMD_CONSTRAINT = "uq_material_usage_org_client_command"
R = MembershipRole


def _require_admin(ctx: Ctx) -> None:
    if ctx.role != R.ADMIN:
        raise Forbidden("Only admins can change inventory.")


def _item_out(item: InventoryItem, ctx: Ctx) -> ItemOut:
    if ctx.role == R.TECHNICIAN:
        return ItemOut(
            id=item.id,
            code=item.code,
            name=item.name,
            unit=item.unit,
            stock_quantity=item.stock_quantity,
        )
    return ItemOut(
        id=item.id,
        code=item.code,
        name=item.name,
        unit=item.unit,
        stock_quantity=item.stock_quantity,
        reorder_threshold=item.reorder_threshold,
        unit_price_minor=item.unit_price_minor,
        currency=money.CURRENCY,
        is_active=item.is_active,
        low_stock=item.stock_quantity <= item.reorder_threshold,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _get_item(db: Session, ctx: Ctx, item_id: uuid.UUID) -> InventoryItem:
    item = db.scalars(
        select(InventoryItem)
        .where(InventoryItem.organization_id == ctx.org_id, InventoryItem.id == item_id)
        .execution_options(populate_existing=True)
    ).first()
    if item is None or (ctx.role == R.TECHNICIAN and not item.is_active):
        raise NotFound("Inventory item not found.")
    return item


def _require_reader(ctx: Ctx) -> None:
    if ctx.role not in (R.ADMIN, R.DISPATCHER, R.TECHNICIAN):
        raise Forbidden("Your role cannot view inventory.")


# ---- items -----------------------------------------------------------------------------
def create_item(
    db: Session,
    ctx: Ctx,
    code: str,
    name: str,
    unit: str,
    stock: Decimal,
    threshold: Decimal,
    price: int,
) -> InventoryItem:
    _require_admin(ctx)
    exists = db.scalar(
        select(InventoryItem.id).where(
            InventoryItem.organization_id == ctx.org_id, InventoryItem.code == code
        )
    )
    if exists is not None:
        raise Conflict("An item with this code already exists.", {"fields": ["code"]})
    item = InventoryItem(
        organization_id=ctx.org_id,
        code=code,
        name=name,
        unit=unit,
        stock_quantity=stock,
        reorder_threshold=threshold,
        unit_price_minor=price,
    )
    db.add(item)
    db.flush()
    if stock > 0:
        _movement(db, ctx, item, StockMovementKind.ADDITION, stock, "Initial stock", stock)
    record_audit(
        db,
        ctx,
        "inventory.item_create",
        "inventory_item",
        item.id,
        after={"code": code, "name": name, "stock_quantity": stock, "unit_price_minor": price},
    )
    return item


def patch_item(db: Session, ctx: Ctx, item_id: uuid.UUID, changes: dict[str, Any]) -> InventoryItem:
    _require_admin(ctx)
    item = _get_item(db, ctx, item_id)
    before = {k: getattr(item, k) for k in changes}
    for k, v in changes.items():
        if v is not None:
            setattr(item, k, v)
    db.flush()
    record_audit(
        db,
        ctx,
        "inventory.item_update",
        "inventory_item",
        item.id,
        before=before,
        after={k: getattr(item, k) for k in changes},
    )
    return item


def get_item(db: Session, ctx: Ctx, item_id: uuid.UUID) -> ItemOut:
    _require_reader(ctx)
    return _item_out(_get_item(db, ctx, item_id), ctx)


def list_items(
    db: Session,
    ctx: Ctx,
    params: PageParams,
    q: str | None,
    active: bool | None,
    low_stock: bool,
) -> tuple[list[ItemOut], int]:
    _require_reader(ctx)
    stmt = select(InventoryItem).where(InventoryItem.organization_id == ctx.org_id)
    if ctx.role == R.TECHNICIAN:
        stmt = stmt.where(InventoryItem.is_active.is_(True))
    elif active is not None:
        stmt = stmt.where(InventoryItem.is_active.is_(active))
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            func.lower(InventoryItem.code).like(like) | func.lower(InventoryItem.name).like(like)
        )
    if low_stock:
        stmt = stmt.where(InventoryItem.stock_quantity <= InventoryItem.reorder_threshold)
    rows, total = paginate_rows(db, stmt.order_by(InventoryItem.code, InventoryItem.id), params)
    return [_item_out(r[0], ctx) for r in rows], total


def low_stock(db: Session, ctx: Ctx) -> list[ItemOut]:
    """Active items with stock <= threshold, most depleted (lowest stock/threshold) first."""
    if not is_staff(ctx):
        raise Forbidden("Only dispatchers and admins can view the low-stock list.")
    ratio = func.coalesce(
        InventoryItem.stock_quantity / func.nullif(InventoryItem.reorder_threshold, 0), 0
    )
    rows = db.scalars(
        select(InventoryItem)
        .where(
            InventoryItem.organization_id == ctx.org_id,
            InventoryItem.is_active.is_(True),
            InventoryItem.stock_quantity <= InventoryItem.reorder_threshold,
        )
        .order_by(ratio, InventoryItem.code)
    )
    return [_item_out(i, ctx) for i in rows]


# ---- stock ledger ----------------------------------------------------------------------
def _movement(
    db: Session,
    ctx: Ctx,
    item: InventoryItem,
    kind: StockMovementKind,
    delta: Decimal,
    reason: str,
    stock_after: Decimal,
    usage_id: uuid.UUID | None = None,
) -> StockMovement:
    mv = StockMovement(
        organization_id=ctx.org_id,
        item_id=item.id,
        kind=kind,
        delta=delta,
        reason=reason,
        actor_membership_id=ctx.membership_id,
        material_usage_id=usage_id,
        stock_after=stock_after,
    )
    db.add(mv)
    db.flush()
    return mv


def _apply_delta(
    db: Session, ctx: Ctx, item_id: uuid.UUID, delta: Decimal
) -> tuple[Decimal, InventoryItem]:
    """Atomic ``stock = stock + delta`` that can never go below zero."""
    res = db.execute(
        update(InventoryItem)
        .where(
            InventoryItem.organization_id == ctx.org_id,
            InventoryItem.id == item_id,
            InventoryItem.stock_quantity + delta >= 0,
        )
        .values(stock_quantity=InventoryItem.stock_quantity + delta, updated_at=func.now())
        .returning(InventoryItem.stock_quantity)
        .execution_options(synchronize_session=False)
    ).first()
    item = _get_item(db, ctx, item_id)  # 404 if missing / other org
    if res is None:
        raise AppError(
            409,
            "insufficient_stock",
            "Stock cannot go below zero.",
            {"available": str(item.stock_quantity), "requested": str(-delta)},
        )
    return res[0], item


def add_stock(
    db: Session, ctx: Ctx, item_id: uuid.UUID, quantity: Decimal, reason: str
) -> StockMovement:
    _require_admin(ctx)
    after, item = _apply_delta(db, ctx, item_id, quantity)
    mv = _movement(db, ctx, item, StockMovementKind.ADDITION, quantity, reason, after)
    record_audit(
        db,
        ctx,
        "inventory.stock_add",
        "inventory_item",
        item.id,
        after={"delta": quantity, "stock_after": after, "reason": reason},
    )
    return mv


def adjust_stock(
    db: Session, ctx: Ctx, item_id: uuid.UUID, delta: Decimal, reason: str
) -> StockMovement:
    _require_admin(ctx)
    if delta == 0:
        raise ValidationFailed(
            "Adjustment cannot be zero.", [{"field": "delta", "message": "must not be zero"}]
        )
    after, item = _apply_delta(db, ctx, item_id, delta)
    mv = _movement(db, ctx, item, StockMovementKind.ADJUSTMENT, delta, reason, after)
    record_audit(
        db,
        ctx,
        "inventory.stock_adjust",
        "inventory_item",
        item.id,
        after={"delta": delta, "stock_after": after, "reason": reason},
    )
    return mv


def movement_out(db: Session, ctx: Ctx, rows: list[StockMovement]) -> list[MovementOut]:
    n = names(db, ctx.org_id, {m.actor_membership_id for m in rows})
    return [
        MovementOut(
            id=m.id,
            item_id=m.item_id,
            kind=m.kind,
            delta=m.delta,
            reason=m.reason,
            actor=PersonBrief(
                membership_id=m.actor_membership_id, name=n.get(m.actor_membership_id, "")
            ),
            material_usage_id=m.material_usage_id,
            stock_after=m.stock_after,
            created_at=m.created_at,
        )
        for m in rows
    ]


def list_movements(
    db: Session, ctx: Ctx, item_id: uuid.UUID, params: PageParams
) -> tuple[list[MovementOut], int]:
    if not is_staff(ctx):
        raise Forbidden("Only dispatchers and admins can view stock movements.")
    item = _get_item(db, ctx, item_id)
    rows, total = paginate_rows(
        db,
        select(StockMovement)
        .where(StockMovement.organization_id == ctx.org_id, StockMovement.item_id == item.id)
        .order_by(StockMovement.created_at.desc(), StockMovement.id.desc()),
        params,
    )
    return movement_out(db, ctx, [r[0] for r in rows]), total


# ---- consumption -----------------------------------------------------------------------
def _usage_hash(request_id: uuid.UUID, item_id: uuid.UUID, quantity: Decimal) -> str:
    canonical = json.dumps(
        {"request_id": str(request_id), "item_id": str(item_id), "quantity": f"{quantity:.3f}"},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _find_usage(db: Session, ctx: Ctx, command_id: uuid.UUID) -> MaterialUsage | None:
    return db.scalars(
        select(MaterialUsage)
        .where(
            MaterialUsage.organization_id == ctx.org_id,
            MaterialUsage.client_command_id == command_id,
        )
        .execution_options(populate_existing=True)
    ).first()


def _replay(existing: MaterialUsage, ctx: Ctx, phash: str) -> MaterialUsage:
    if existing.payload_hash != phash or existing.technician_membership_id != ctx.membership_id:
        raise AppError(
            409,
            "idempotency_key_reused",
            "This client_command_id was already used with a different payload.",
        )
    return existing


def _is_constraint(exc: IntegrityError, name: str) -> bool:
    return getattr(getattr(exc.orig, "diag", None), "constraint_name", None) == name


def consume(
    db: Session,
    ctx: Ctx,
    request_id: uuid.UUID,
    command_id: uuid.UUID,
    item_id: uuid.UUID,
    quantity: Decimal,
) -> tuple[MaterialUsage, bool]:
    """Returns (usage, created); ``created`` False = identical replay (HTTP 200).
    Commits on success; rolls back on any error."""
    try:
        return _consume(db, ctx, request_id, command_id, item_id, quantity)
    except BaseException:
        db.rollback()
        raise


def _consume(
    db: Session,
    ctx: Ctx,
    request_id: uuid.UUID,
    command_id: uuid.UUID,
    item_id: uuid.UUID,
    quantity: Decimal,
) -> tuple[MaterialUsage, bool]:
    if ctx.role != R.TECHNICIAN:
        raise Forbidden("Only the assigned technician can record material usage.")
    # The request row lock serializes consumption per request and guards the status check.
    req = get_visible_request(db, ctx, request_id, lock=True)
    phash = _usage_hash(req.id, item_id, quantity)
    existing = _find_usage(db, ctx, command_id)
    if existing is not None:
        usage = _replay(existing, ctx, phash)
        db.rollback()
        return usage, False
    if not is_assigned_technician(db, ctx, req):
        raise Forbidden("Only the assigned technician can record material usage.")
    if req.status != RequestStatus.IN_PROGRESS:
        raise Conflict(
            "Materials can only be recorded while the job is in progress.",
            {"status": req.status.value},
        )
    try:
        with db.begin_nested():  # decrement + inserts roll back together on a key race
            usage = _consume_locked(
                db, ctx, req.id, req.number, command_id, item_id, quantity, phash
            )
    except IntegrityError as exc:
        if not _is_constraint(exc, _CLIENT_CMD_CONSTRAINT):
            raise
        db.rollback()
        existing = _find_usage(db, ctx, command_id)
        if existing is None:
            raise
        return _replay(existing, ctx, phash), False
    db.commit()
    return usage, True


def _consume_locked(
    db: Session,
    ctx: Ctx,
    request_id: uuid.UUID,
    request_number: int,
    command_id: uuid.UUID,
    item_id: uuid.UUID,
    quantity: Decimal,
    phash: str,
) -> MaterialUsage:
    res = db.execute(
        update(InventoryItem)
        .where(
            InventoryItem.organization_id == ctx.org_id,
            InventoryItem.id == item_id,
            InventoryItem.is_active.is_(True),
            InventoryItem.stock_quantity >= quantity,
        )
        .values(stock_quantity=InventoryItem.stock_quantity - quantity, updated_at=func.now())
        .returning(InventoryItem.stock_quantity, InventoryItem.unit_price_minor)
        .execution_options(synchronize_session=False)
    ).first()
    if res is None:
        item = db.scalars(
            select(InventoryItem)
            .where(InventoryItem.organization_id == ctx.org_id, InventoryItem.id == item_id)
            .execution_options(populate_existing=True)
        ).first()
        if item is None:
            raise NotFound("Inventory item not found.")
        if not item.is_active:
            raise ValidationFailed(
                "This item is inactive.", [{"field": "item_id", "message": "item is inactive"}]
            )
        raise AppError(
            409,
            "insufficient_stock",
            "Not enough stock for this item.",
            {
                "item_id": str(item_id),
                "available": str(item.stock_quantity),
                "requested": str(quantity),
            },
        )
    stock_after, unit_cost = res
    total = money.line_total_minor(quantity, unit_cost)
    usage = MaterialUsage(
        organization_id=ctx.org_id,
        request_id=request_id,
        item_id=item_id,
        technician_membership_id=ctx.membership_id,
        quantity=quantity,
        unit_cost_minor_snapshot=unit_cost,
        total_cost_minor=total,
        client_command_id=command_id,
        payload_hash=phash,
    )
    db.add(usage)
    db.flush()
    item = db.scalars(
        select(InventoryItem)
        .where(InventoryItem.organization_id == ctx.org_id, InventoryItem.id == item_id)
        .execution_options(populate_existing=True)
    ).one()
    _movement(
        db,
        ctx,
        item,
        StockMovementKind.CONSUMPTION,
        -quantity,
        f"Used on request #{request_number}",
        stock_after,
        usage.id,
    )
    data = {
        "usage_id": usage.id,
        "item_id": item_id,
        "item_code": item.code,
        "quantity": str(quantity),
        "total_cost_minor": total,
    }
    from app.models.requests import ServiceRequest

    req = db.get(ServiceRequest, request_id)
    if req is not None:
        add_event(db, ctx, req, "MATERIAL_USED", data=data)
    record_audit(
        db,
        ctx,
        "inventory.consume",
        "material_usage",
        usage.id,
        after={**data, "request_id": request_id, "stock_after": stock_after},
    )
    return usage


def usage_out(db: Session, ctx: Ctx, rows: list[MaterialUsage]) -> list[UsageOut]:
    if not rows:
        return []
    items = {
        i.id: i
        for i in db.scalars(
            select(InventoryItem).where(
                InventoryItem.organization_id == ctx.org_id,
                InventoryItem.id.in_({r.item_id for r in rows}),
            )
        )
    }
    n = names(db, ctx.org_id, {r.technician_membership_id for r in rows})
    return [
        UsageOut(
            id=r.id,
            request_id=r.request_id,
            item=UsageItemBrief(
                id=r.item_id,
                code=items[r.item_id].code,
                name=items[r.item_id].name,
                unit=items[r.item_id].unit,
            ),
            quantity=r.quantity,
            unit_cost_minor_snapshot=r.unit_cost_minor_snapshot,
            total_cost_minor=r.total_cost_minor,
            client_command_id=r.client_command_id,
            technician=PersonBrief(
                membership_id=r.technician_membership_id,
                name=n.get(r.technician_membership_id, ""),
            ),
            created_at=r.created_at,
        )
        for r in rows
    ]


def list_usage(db: Session, ctx: Ctx, request_id: uuid.UUID) -> list[UsageOut]:
    """Usage rows of a request. Requesters never see internal material costs (403)."""
    req = get_visible_request(db, ctx, request_id)
    if ctx.role == R.REQUESTER:
        raise Forbidden("Material usage is not visible to requesters.")
    rows = list(
        db.scalars(
            select(MaterialUsage)
            .where(MaterialUsage.organization_id == ctx.org_id, MaterialUsage.request_id == req.id)
            .order_by(MaterialUsage.created_at, MaterialUsage.id)
        )
    )
    return usage_out(db, ctx, rows)
