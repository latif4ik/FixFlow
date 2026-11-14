import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.enums import EstimateStatus
from app.schemas.common import PersonBrief, Qty3Out

Money = Annotated[int, Field(ge=0, le=10**12)]
Qty = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=3)]
Text300 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Reason1000 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=1000)]


class _Strict(BaseModel):
    """Clients never send totals: unknown fields (total_minor, line_total_minor...) -> 422."""

    model_config = ConfigDict(extra="forbid")


class EstimateLineIn(_Strict):
    description: Text300
    inventory_item_id: uuid.UUID | None = None
    quantity: Qty
    unit_price_minor: Money | None = Field(
        default=None, description="Defaults to the inventory item's price when an item is set."
    )


class EstimateCreate(_Strict):
    labor_minutes: Annotated[int, Field(ge=0, le=1_000_000)] = 0
    labor_rate_minor: Money = Field(default=0, description="Per hour, in tyiyn (KGS minor units).")
    notes: Notes | None = None
    lines: Annotated[list[EstimateLineIn], Field(max_length=100)] = Field(default_factory=list)


class EstimatePatch(_Strict):
    labor_minutes: Annotated[int, Field(ge=0, le=1_000_000)] | None = None
    labor_rate_minor: Money | None = None
    notes: Notes | None = None


class EstimateLinesPut(_Strict):
    lines: Annotated[list[EstimateLineIn], Field(max_length=100)]


class DecisionIn(_Strict):
    version: Annotated[int, Field(ge=1)]
    decision: Literal["APPROVE", "REJECT"]
    reason: Reason1000 | None = None


class WithdrawIn(_Strict):
    reason: Reason1000


class EstimateLineOut(BaseModel):
    id: uuid.UUID
    position: int
    description: str
    inventory_item_id: uuid.UUID | None
    quantity: Qty3Out
    unit_price_minor: int
    line_total_minor: int


class EstimateOut(BaseModel):
    id: uuid.UUID
    request_id: uuid.UUID
    version: int
    status: EstimateStatus
    supersedes_id: uuid.UUID | None
    labor_minutes: int
    labor_rate_minor: int
    labor_cost_minor: int
    materials_total_minor: int
    total_minor: int
    currency: str
    notes: str | None
    lines: list[EstimateLineOut]
    created_by: PersonBrief | None
    created_at: datetime
    submitted_at: datetime | None
    submitted_by: PersonBrief | None
    decided_at: datetime | None
    decided_by: PersonBrief | None
    decision_reason: str | None
    withdrawn_at: datetime | None
    withdrawn_by: PersonBrief | None
    withdraw_reason: str | None


class EstimateSummary(BaseModel):
    """Current-estimate summary embedded in the request detail."""

    id: uuid.UUID
    version: int
    status: EstimateStatus
    total_minor: int
    currency: str
    labor_minutes: int
    labor_cost_minor: int
    materials_total_minor: int
    lines: list[EstimateLineOut]
