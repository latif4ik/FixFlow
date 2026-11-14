import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.enums import AssetStatus
from app.schemas.common import Timestamps
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
