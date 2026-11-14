"""Dashboard reports (REPORT-01..06). Staff only (ADMIN, DISPATCHER); always org-scoped.

Date parameters are local dates of the organization timezone: ``from`` is inclusive from the
start of that day, ``to`` is inclusive through the end of that day (internally exclusive at the
start of ``to + 1 day``). At most 366 days; default range is the last 30 days.
"""

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.core.deps import DbDep, StaffCtx
from app.schemas.reports import DailyPoint, DistributionItem, ReportSummary
from app.services import reports as svc

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/summary", response_model=ReportSummary)
def summary(
    db: DbDep,
    ctx: StaffCtx,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
    category_id: uuid.UUID | None = None,
    technician_id: uuid.UUID | None = None,
) -> ReportSummary:
    """counts_by_status is a CURRENT snapshot of all requests matching category/technician
    (not limited to the range); completed_in_range, approved estimates (decided_at) and material
    costs (created_at) use the range; upcoming_appointments = ACTIVE assignments starting within
    the next 7 days; utilization ignores category_id (capacity is not per category)."""
    return svc.summary(db, ctx, from_, to, category_id, technician_id)


@router.get("/daily", response_model=list[DailyPoint])
def daily(
    db: DbDep, ctx: StaffCtx, days: Annotated[int, Query(ge=1, le=svc.MAX_DAILY_DAYS)] = 14
) -> list[DailyPoint]:
    """New and completed requests per org-local day for the past N days, today included."""
    return svc.daily(db, ctx, days)


@router.get("/distribution", response_model=list[DistributionItem])
def distribution(
    db: DbDep,
    ctx: StaffCtx,
    by: Literal["priority", "category"],
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
    category_id: uuid.UUID | None = None,
    technician_id: uuid.UUID | None = None,
) -> list[DistributionItem]:
    """Requests CREATED in the range, grouped by priority or category (zeros included)."""
    return svc.distribution(db, ctx, by, from_, to, category_id, technician_id)
