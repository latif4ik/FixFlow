import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints

from app.models.enums import AssetStatus, Priority, Recurrence, RequestStatus
from app.schemas.requests import AssetBrief, CategoryBrief

PlanTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=100)]
PlanDescription = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=20, max_length=3000)
]


class PlanIn(BaseModel):
    asset_id: uuid.UUID
    category_id: uuid.UUID
    title: PlanTitle
    description: PlanDescription
    priority: Priority = Priority.NORMAL
    first_date: date
    recurrence: Recurrence


class PlanPatch(BaseModel):
    category_id: uuid.UUID | None = None
    title: PlanTitle | None = None
    description: PlanDescription | None = None
    priority: Priority | None = None
    first_date: date | None = None
    recurrence: Recurrence | None = None
    is_enabled: bool | None = None


class PlanAssetBrief(AssetBrief):
    status: AssetStatus


class PlanOut(BaseModel):
    id: uuid.UUID
    asset: PlanAssetBrief
    category: CategoryBrief
    title: str
    description: str
    priority: Priority
    first_date: date
    recurrence: Recurrence
    is_enabled: bool
    last_generated_for: date | None
    next_occurrence: date | None  # null when disabled or the asset is retired
    created_by_membership_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class GeneratedRequestBrief(BaseModel):
    id: uuid.UUID
    display_id: str
    occurrence_date: date
    status: RequestStatus
    created_at: datetime


class PlanDetail(PlanOut):
    generated_total: int
    generated: list[GeneratedRequestBrief]  # newest occurrence first (latest 100)


class GenerateIn(BaseModel):
    as_of: date


class GeneratedItem(BaseModel):
    request_id: uuid.UUID
    display_id: str
    occurrence_date: date


class PlanRun(BaseModel):
    plan_id: uuid.UUID
    organization_id: uuid.UUID
    created: list[GeneratedItem]
    skipped_existing: list[date]


class GenerationReport(BaseModel):
    as_of: date
    plans_processed: int
    requests_created: int
    skipped_existing: int
    errors: int
    plans: list[PlanRun]
