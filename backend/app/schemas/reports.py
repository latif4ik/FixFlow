import uuid
from datetime import date, datetime

from pydantic import BaseModel


class DateRange(BaseModel):
    from_date: date
    to_date: date
    start_at: datetime  # inclusive instant (start of from_date in the org timezone)
    end_at: datetime  # exclusive instant (start of to_date + 1 day in the org timezone)
    timezone: str


class TechnicianUtilization(BaseModel):
    membership_id: uuid.UUID
    name: str
    planned_minutes: int
    available_minutes: int
    percent: float | None
    percent_capped: float | None


class Utilization(BaseModel):
    percent: float | None
    percent_capped: float | None
    planned_minutes: int
    available_minutes: int
    explanation: str
    per_technician: list[TechnicianUtilization]


class ReportSummary(BaseModel):
    range: DateRange
    counts_by_status: dict[str, int]
    open_requests: int
    overdue_requests: int
    upcoming_appointments: int
    completed_in_range: int
    technician_utilization: Utilization
    approved_estimates_total_minor: int
    approved_estimates_label: str
    material_costs_total_minor: int
    currency: str


class DailyPoint(BaseModel):
    date: date
    new_requests: int
    completed_requests: int


class DistributionItem(BaseModel):
    key: str
    label: str
    count: int
