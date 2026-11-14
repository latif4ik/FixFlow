import uuid
from datetime import date, datetime
from typing import Annotated, Any

from pydantic import AwareDatetime, BaseModel, Field, StringConstraints, model_validator

from app.models.enums import (
    AssignmentStatus,
    FilePurpose,
    NoteKind,
    NoteVisibility,
    Priority,
    RequestStatus,
)
from app.schemas.common import ORMModel, PersonBrief
from app.schemas.estimates import EstimateSummary
from app.schemas.inventory import UsageOut

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=120)]
Description = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=20, max_length=3000)
]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=500)]
NoteText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


def _window_ok(start: datetime | None, end: datetime | None) -> None:
    if (start is None) != (end is None):
        raise ValueError("preferred window needs both a start and an end")
    if start is not None and end is not None and end <= start:
        raise ValueError("preferred window end must be after its start")


class RequestCreate(BaseModel):
    title: Title
    description: Description
    category_id: uuid.UUID
    property_id: uuid.UUID
    asset_id: uuid.UUID | None = None
    priority: Priority = Priority.NORMAL
    preferred_window_start: AwareDatetime | None = None
    preferred_window_end: AwareDatetime | None = None
    # Staff only: create on behalf of this REQUESTER membership.
    requester_membership_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _window(self) -> "RequestCreate":
        _window_ok(self.preferred_window_start, self.preferred_window_end)
        return self


class RequestPatch(BaseModel):
    title: Title | None = None
    description: Description | None = None
    preferred_window_start: AwareDatetime | None = None
    preferred_window_end: AwareDatetime | None = None
    priority: Priority | None = None
    category_id: uuid.UUID | None = None
    reason: Reason | None = None


class DuplicateIn(BaseModel):
    duplicate_of_id: uuid.UUID
    reason: Reason


class TriageIn(BaseModel):
    note: NoteText | None = None


class ReasonIn(BaseModel):
    reason: NoteText | None = None


class RequiredReasonIn(BaseModel):
    reason: NoteText


class TransitionIn(BaseModel):
    to_status: RequestStatus
    reason: NoteText | None = None
    note: NoteText | None = None


class NoteIn(BaseModel):
    body: NoteText
    visibility: NoteVisibility = NoteVisibility.PUBLIC
    kind: NoteKind = NoteKind.GENERAL
    client_command_id: uuid.UUID | None = None
    attachment_ids: list[uuid.UUID] = Field(default_factory=list, max_length=10)


# ---- output ----
class PropertyBrief(ORMModel):
    id: uuid.UUID
    name: str
    address: str


class AssetBrief(ORMModel):
    id: uuid.UUID
    code: str
    name: str


class CategoryBrief(ORMModel):
    id: uuid.UUID
    name: str


class SlaOut(BaseModel):
    """SLA-04: due instant, remaining / overdue time and the indicator."""

    budget_minutes: int
    consumed_minutes: int
    remaining_minutes: int  # negative while overdue
    overdue_by_minutes: int
    due_at: datetime | None  # null while paused, after completion/cancellation
    at_risk_at: datetime | None
    paused: bool
    stopped: bool
    stopped_at: datetime | None
    state: str  # ON_TRACK | AT_RISK | OVERDUE (stopped: the state at completion/cancellation)
    outcome: str | None  # MET | BREACHED once completed or canceled


class RequestListItem(BaseModel):
    id: uuid.UUID
    number: int
    display_id: str
    title: str
    status: RequestStatus
    priority: Priority
    category: CategoryBrief
    property: PropertyBrief
    asset: AssetBrief | None
    requester: PersonBrief | None
    created_at: datetime
    updated_at: datetime
    # ON_TRACK | AT_RISK | OVERDUE | PAUSED (finished requests: their state at the stop instant)
    sla_state: str | None = None
    sla_due_at: datetime | None = None
    plan_id: uuid.UUID | None = None
    occurrence_date: date | None = None


class FileOut(BaseModel):
    id: uuid.UUID
    purpose: FilePurpose
    note_id: uuid.UUID | None
    original_filename: str
    mime_type: str
    size_bytes: int
    width: int
    height: int
    uploaded_by_membership_id: uuid.UUID
    created_at: datetime
    url: str


class NoteOut(BaseModel):
    id: uuid.UUID
    request_id: uuid.UUID
    author: PersonBrief | None
    visibility: NoteVisibility
    kind: NoteKind
    body: str
    created_at: datetime
    attachments: list[FileOut]


class TimelineItem(BaseModel):
    id: uuid.UUID
    type: str
    label: str
    actor: PersonBrief | None
    from_status: str | None
    to_status: str | None
    data: dict[str, Any] | None
    created_at: datetime


class DuplicateBrief(BaseModel):
    id: uuid.UUID
    number: int
    display_id: str
    title: str


class OrgRef(BaseModel):
    id: uuid.UUID
    name: str


class AppointmentBrief(BaseModel):
    start_at: datetime
    end_at: datetime


class AssignmentBrief(BaseModel):
    """Summary embedded in the request detail."""

    id: uuid.UUID
    technician: PersonBrief
    start_at: datetime
    end_at: datetime
    status: AssignmentStatus


class RequestDetail(RequestListItem):
    description: str
    organization: OrgRef
    created_by: PersonBrief | None
    preferred_window_start: datetime | None
    preferred_window_end: datetime | None
    duplicate_of: DuplicateBrief | None
    status_changed_at: datetime
    completed_at: datetime | None
    closed_at: datetime | None
    canceled_at: datetime | None
    notes: list[NoteOut]
    files: list[FileOut]
    timeline: list[TimelineItem]
    allowed_actions: list[str]
    assignment: AssignmentBrief | None = None
    appointment: AppointmentBrief | None = None
    # Current estimate (caller-visible) and recorded material usage (staff / technicians).
    estimate: EstimateSummary | None = None
    sla: SlaOut | None = None
    materials: list[UsageOut] = Field(default_factory=list)
