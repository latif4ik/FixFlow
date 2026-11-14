import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import PersonBrief


class SuggestionSla(BaseModel):
    due_at: datetime | None
    slot_ends_after_due: bool


class SuggestionOut(BaseModel):
    technician: PersonBrief
    start_at: datetime
    end_at: datetime
    workload_minutes_next_7_days: int
    sla: SuggestionSla
    reason: str


class SkippedTechnician(BaseModel):
    technician: PersonBrief
    reason_codes: list[str]


class SuggestionsOut(BaseModel):
    request_id: uuid.UUID
    duration_minutes: int
    horizon: dict[str, datetime]
    suggestions: list[SuggestionOut]
    skipped: list[SkippedTechnician]
    unskilled_technicians: int
