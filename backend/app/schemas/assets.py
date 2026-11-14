import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.enums import AssetStatus, Priority, RequestStatus
from app.schemas.common import PersonBrief, Qty3Out, Timestamps
from app.schemas.org import OrgName


class PropertyIn(BaseModel):
    name: OrgName
    address: str = Field(min_length=1, max_length=1000)
    contact_instructions: str | None = Field(default=None, max_length=2000)


class PropertyPatch(BaseModel):
    name: OrgName | None = None
    address: str | None = Field(default=None, min_length=1, max_length=1000)
    contact_instructions: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None


class PropertyOut(Timestamps):
    id: uuid.UUID
    name: str
    address: str
    contact_instructions: str | None
    is_active: bool


class AccessGrantIn(BaseModel):
    membership_id: uuid.UUID


class AccessOut(BaseModel):
    membership_id: uuid.UUID
    full_name: str
    email: str
    granted_by_membership_id: uuid.UUID
    created_at: datetime


class AssetIn(BaseModel):
    property_id: uuid.UUID
    code: str = Field(min_length=1, max_length=60, pattern=r"^\S.*\S$|^\S$")
    name: OrgName
    asset_type: str = Field(min_length=1, max_length=100)
    serial_number: str | None = Field(default=None, max_length=100)
    installed_on: date | None = None
    status: AssetStatus = AssetStatus.ACTIVE
    notes: str | None = Field(default=None, max_length=4000)


class AssetPatch(BaseModel):
    property_id: uuid.UUID | None = None
    code: str | None = Field(default=None, min_length=1, max_length=60, pattern=r"^\S.*\S$|^\S$")
    name: OrgName | None = None
    asset_type: str | None = Field(default=None, min_length=1, max_length=100)
    serial_number: str | None = Field(default=None, max_length=100)
    installed_on: date | None = None
    status: AssetStatus | None = None
    notes: str | None = Field(default=None, max_length=4000)


class AssetOut(Timestamps):
    id: uuid.UUID
    property_id: uuid.UUID
    code: str
    name: str
    asset_type: str
    serial_number: str | None
    installed_on: date | None
    status: AssetStatus
    notes: str | None


# ---- asset detail / history (ASSET-04/05) ----
class WorkBrief(BaseModel):
    id: uuid.UUID
    display_id: str
    title: str
    status: RequestStatus
    priority: Priority
    created_at: datetime
    sla_state: str | None = None
    sla_due_at: datetime | None = None


class LastServiceOut(BaseModel):
    request: WorkBrief
    completed_at: datetime
    technician: PersonBrief | None


class NextMaintenanceOut(BaseModel):
    plan_id: uuid.UUID
    title: str
    date: date


class AssetDetail(AssetOut):
    open_work: list[WorkBrief]
    last_completed_service: LastServiceOut | None
    next_maintenance: NextMaintenanceOut | None  # staff only


class MaterialLine(BaseModel):
    item_id: uuid.UUID
    name: str
    unit: str
    quantity: Qty3Out
    total_cost_minor: int


class MaterialSummary(BaseModel):
    items: list[MaterialLine]
    total_cost_minor: int


class OutcomeOut(BaseModel):
    status: RequestStatus
    sla_outcome: str | None  # MET | BREACHED once completed / canceled


class AssetHistoryItem(BaseModel):
    request_id: uuid.UUID
    display_id: str
    title: str
    status: RequestStatus
    priority: Priority
    created_at: datetime
    completed_at: datetime | None  # service date
    technician: PersonBrief | None
    outcome: OutcomeOut
    materials: MaterialSummary
    attachment_count: int
    plan_id: uuid.UUID | None = None
    occurrence_date: date | None = None
