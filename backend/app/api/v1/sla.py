"""SLA operations: demo escalation trigger (admin) and the overdue queue (staff)."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.core import clock
from app.core.deps import AdminCtx, DbDep, StaffCtx
from app.core.pagination import Pagination
from app.schemas.requests import RequestListItem
from app.services import escalation
from app.services import requests as requests_svc
from app.sla import service as sla_svc

router = APIRouter(tags=["sla"])


class EscalationResult(BaseModel):
    escalated: int


class OverdueItem(RequestListItem):
    overdue_by_minutes: int
    escalated_at: str | None = None


class OverdueQueue(BaseModel):
    count: int
    items: list[OverdueItem]
    page: int
    page_size: int


@router.post("/admin/sla/escalate", response_model=EscalationResult)
def escalate(db: DbDep, ctx: AdminCtx) -> EscalationResult:
    """Run the overdue escalation now, for the caller's organization only (SLA-07 demo)."""
    return EscalationResult(escalated=escalation.escalate_overdue(db, clock.now(), ctx.org_id))


@router.get("/dashboard/overdue", response_model=OverdueQueue)
def overdue_queue(db: DbDep, ctx: StaffCtx, params: Pagination) -> OverdueQueue:
    """Overdue queue (SLA-06): requests past their due instant, most overdue first."""
    now = clock.now()
    rows, total = requests_svc.list_requests_with_rows(
        db, ctx, params, sla_states=["OVERDUE"], sort="due", now=now
    )
    cal = sla_svc.load_calendar(db, ctx.org_id)
    items = []
    for item, req in rows:
        due = req.sla_due_at
        overdue_by = cal.business_minutes_between(due, now) if due is not None else 0
        items.append(
            OverdueItem(
                **item.model_dump(),
                overdue_by_minutes=overdue_by,
                escalated_at=req.overdue_notified_at.isoformat()
                if req.overdue_notified_at
                else None,
            )
        )
    return OverdueQueue(count=total, items=items, page=params.page, page_size=params.page_size)
