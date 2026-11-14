import uuid
from datetime import datetime
from typing import Any

from pydantic import AwareDatetime, BaseModel, Field

from app.models.enums import AssignmentStatus, EstimateStatus, Priority, RequestStatus
from app.schemas.requests import AppointmentBrief, PersonBrief, Reason


class AssignmentIn(BaseModel):
    technician_membership_id: uuid.UUID
    start_at: AwareDatetime
    end_at: AwareDatetime


class RescheduleIn(AssignmentIn):
    reason: Reason | None = None


class UnassignIn(BaseModel):
    reason: Reason


class AssignmentOut(BaseModel):
    id: uuid.UUID
    request_id: uuid.UUID
    technician: PersonBrief
    start_at: datetime
    end_at: datetime
    status: AssignmentStatus
    active: bool
    assigned_by: PersonBrief | None
    released_by: PersonBrief | None
    released_reason: str | None
    released_at: datetime | None
    created_at: datetime


class RequestStateBrief(BaseModel):
    id: uuid.UUID
    display_id: str
    status: RequestStatus


class AssignmentResult(BaseModel):
    assignment: AssignmentOut
    request: RequestStateBrief


class WorkloadOut(BaseModel):
    active_assignments: int
    planned_minutes_next_7_days: int


class CandidateOut(BaseModel):
    membership_id: uuid.UUID
    name: str
    skills: list[str]
    eligible: bool
    reasons: list[dict[str, Any]]
    available: bool | None
    workload: WorkloadOut


class MyPropertyBrief(BaseModel):
    name: str
    address: str
    contact_instructions: str | None


class MyAssetBrief(BaseModel):
    code: str
    name: str
    serial_number: str | None


class MyCategoryBrief(BaseModel):
    id: uuid.UUID
    name: str


class MyJobRequest(BaseModel):
    id: uuid.UUID
    display_id: str
    title: str
    description: str
    status: RequestStatus
    priority: Priority
    category: MyCategoryBrief
    property: MyPropertyBrief
    asset: MyAssetBrief | None
    requester_name: str | None


class MyAssignmentItem(BaseModel):
    assignment_id: uuid.UUID
    request: MyJobRequest
    appointment: AppointmentBrief
    assignment_status: AssignmentStatus
    allowed_actions: list[str]
    # Current estimate status (null when none was ever submitted) and, while the estimate gate
    # blocks "start", a human-readable explanation for the mobile app.
    estimate_status: EstimateStatus | None = None
    start_blocked_reason: str | None = None


class ScheduleInterval(BaseModel):
    start_at: datetime
    end_at: datetime


class ScheduleTimeOff(ScheduleInterval):
    id: uuid.UUID
    reason: str | None


class ScheduleAssignment(BaseModel):
    assignment_id: uuid.UUID
    request_id: uuid.UUID
    display_id: str
    title: str
    priority: Priority
    request_status: RequestStatus
    assignment_status: AssignmentStatus
    start_at: datetime
    end_at: datetime
    conflict: bool
    conflict_reasons: list[str]


class ScheduleTechnician(BaseModel):
    membership_id: uuid.UUID
    name: str
    is_active: bool
    availability: list[ScheduleInterval]
    time_off: list[ScheduleTimeOff]
    assignments: list[ScheduleAssignment]


class ScheduleRange(BaseModel):
    from_: datetime = Field(serialization_alias="from")
    to: datetime
    timezone: str


class ScheduleOut(BaseModel):
    range: ScheduleRange
    technicians: list[ScheduleTechnician]
