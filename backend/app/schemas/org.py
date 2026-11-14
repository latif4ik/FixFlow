import uuid
from datetime import date, datetime, time
from typing import Annotated, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AwareDatetime,
    BaseModel,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.models.enums import MembershipRole
from app.schemas.common import ORMModel, ShortName, Timestamps

Email = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        max_length=254,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    ),
]
OrgName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


def validate_timezone(v: str) -> str:
    try:
        ZoneInfo(v)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise ValueError("must be a valid IANA timezone, e.g. 'Asia/Bishkek'") from None
    return v


# ---- organization ----
class OrgOut(ORMModel):
    id: uuid.UUID
    name: str
    slug: str
    timezone: str
    is_active: bool


class OrgPatch(BaseModel):
    name: OrgName | None = None
    timezone: str | None = None

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str | None) -> str | None:
        return validate_timezone(v) if v is not None else v


# ---- intervals ----
class HoursInterval(BaseModel):
    weekday: int = Field(ge=0, le=6, description="0 = Monday ... 6 = Sunday")
    open_time: time
    close_time: time

    @model_validator(mode="after")
    def _order(self) -> "HoursInterval":
        if self.close_time <= self.open_time:
            raise ValueError("close_time must be after open_time")
        return self


class BusinessHoursBody(BaseModel):
    intervals: list[HoursInterval] = Field(max_length=70)


class AvailabilityInterval(BaseModel):
    weekday: int = Field(ge=0, le=6)
    start_time: time
    end_time: time

    @model_validator(mode="after")
    def _order(self) -> "AvailabilityInterval":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class AvailabilityBody(BaseModel):
    intervals: list[AvailabilityInterval] = Field(max_length=70)


# ---- holidays ----
class HolidayIn(BaseModel):
    date: date
    name: OrgName


class HolidayOut(ORMModel):
    id: uuid.UUID
    date: date
    name: str


# ---- members ----
class MemberOut(BaseModel):
    membership_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str
    phone: str | None = None
    role: MembershipRole
    is_active: bool
    created_at: datetime


class MemberCreate(BaseModel):
    email: Email
    full_name: OrgName
    role: MembershipRole
    password: str | None = Field(default=None, min_length=8, max_length=200)


class MemberPatch(BaseModel):
    role: MembershipRole | None = None
    is_active: bool | None = None


# ---- skills ----
class SkillIn(BaseModel):
    name: ShortName


class SkillOut(ORMModel):
    id: uuid.UUID
    name: str


# ---- categories ----
class CategoryIn(BaseModel):
    name: OrgName
    description: str | None = Field(default=None, max_length=2000)
    default_duration_minutes: int = Field(ge=30, le=1440)
    is_enabled: bool = True
    required_skill_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)


class CategoryPatch(BaseModel):
    name: OrgName | None = None
    description: str | None = Field(default=None, max_length=2000)
    default_duration_minutes: int | None = Field(default=None, ge=30, le=1440)
    is_enabled: bool | None = None
    required_skill_ids: list[uuid.UUID] | None = Field(default=None, max_length=50)


class CategoryOut(Timestamps):
    id: uuid.UUID
    name: str
    description: str | None
    default_duration_minutes: int
    is_enabled: bool
    required_skills: list[SkillOut]


# ---- technicians ----
class AvailabilityOut(ORMModel):
    id: uuid.UUID
    weekday: int
    start_time: time
    end_time: time


class TimeOffIn(BaseModel):
    start_at: AwareDatetime
    end_at: AwareDatetime
    reason: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _order(self) -> "TimeOffIn":
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        return self


class TimeOffOut(ORMModel):
    id: uuid.UUID
    start_at: datetime
    end_at: datetime
    reason: str | None


class TechnicianOut(BaseModel):
    membership_id: uuid.UUID
    user_id: uuid.UUID
    full_name: str
    email: str
    phone: str | None
    is_active: bool
    bio: str | None
    skills: list[SkillOut]
    availability: list[AvailabilityOut]
    time_off: list[TimeOffOut]


class TechnicianSkillsBody(BaseModel):
    skill_ids: list[uuid.UUID] = Field(max_length=100)


# ---- audit ----
class AuditEventOut(BaseModel):
    id: uuid.UUID
    actor_membership_id: uuid.UUID | None
    actor_name: str | None
    action: str
    target_type: str
    target_id: uuid.UUID | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    created_at: datetime
