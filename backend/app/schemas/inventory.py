import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.enums import StockMovementKind
from app.schemas.common import PersonBrief, Qty3Out

Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Unit = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]
Qty = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=3)]
QtyNonNeg = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=3)]
SignedQty = Annotated[Decimal, Field(max_digits=12, decimal_places=3)]
Money = Annotated[int, Field(ge=0, le=10**12)]
StockReason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=300)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ItemCreate(_Strict):
    code: Code
    name: Name
    unit: Unit
    stock_quantity: QtyNonNeg = Decimal(0)
    reorder_threshold: QtyNonNeg = Decimal(0)
    unit_price_minor: Money = 0


class ItemPatch(_Strict):
    name: Name | None = None
    unit: Unit | None = None
    reorder_threshold: QtyNonNeg | None = None
    unit_price_minor: Money | None = None
    is_active: bool | None = None


class AdditionIn(_Strict):
    quantity: Qty
    reason: StockReason


class AdjustmentIn(_Strict):
    delta: SignedQty
    reason: StockReason


class ItemOut(BaseModel):
    """Staff see every field; technicians only id/code/name/unit/stock_quantity (rest null)."""

    id: uuid.UUID
    code: str
    name: str
    unit: str
    stock_quantity: Qty3Out
    reorder_threshold: Qty3Out | None = None
    unit_price_minor: int | None = None
    currency: str | None = None
    is_active: bool | None = None
    low_stock: bool | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MovementOut(BaseModel):
    id: uuid.UUID
    item_id: uuid.UUID
    kind: StockMovementKind
    delta: Qty3Out
    reason: str
    actor: PersonBrief | None
    material_usage_id: uuid.UUID | None
    stock_after: Qty3Out
    created_at: datetime


class ConsumeIn(_Strict):
    client_command_id: uuid.UUID
    item_id: uuid.UUID
    quantity: Qty


class UsageItemBrief(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    unit: str


class UsageOut(BaseModel):
    id: uuid.UUID
    request_id: uuid.UUID
    item: UsageItemBrief
    quantity: Qty3Out
    unit_cost_minor_snapshot: int
    total_cost_minor: int
    currency: str = "KGS"
    client_command_id: uuid.UUID
    technician: PersonBrief | None
    created_at: datetime
