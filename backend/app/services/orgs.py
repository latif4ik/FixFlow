"""Organization settings, business hours, holidays."""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import time
from itertools import pairwise
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.errors import NotFound, ValidationFailed
from app.core.tenancy import Ctx, get_or_404, scoped
from app.models.identity import Organization
from app.models.org import BusinessHour, Holiday
from app.sla.service import recompute_org_open_requests


def check_no_overlap(intervals: Sequence[tuple[int, time, time]], field: str = "intervals") -> None:
    """Reject overlapping (weekday, start, end) intervals; touching ends are allowed."""
    by_day: dict[int, list[tuple[time, time]]] = defaultdict(list)
    for weekday, start, end in intervals:
        by_day[weekday].append((start, end))
    for weekday, items in by_day.items():
        items.sort()
        for (_, prev_end), (next_start, _) in pairwise(items):
            if next_start < prev_end:
                raise ValidationFailed(
                    "Intervals must not overlap within a weekday.",
                    [{"field": field, "message": f"overlapping intervals on weekday {weekday}"}],
                )


def org_snapshot(org: Organization) -> dict[str, Any]:
    return {"name": org.name, "timezone": org.timezone}


def update_org(db: Session, ctx: Ctx, data: dict[str, Any]) -> Organization:
    org = db.get(Organization, ctx.org_id)
    if org is None:  # pragma: no cover - ctx guarantees existence
        raise NotFound("Organization not found.")
    before = org_snapshot(org)
    for k, v in data.items():
        if v is not None:
            setattr(org, k, v)
    db.flush()
    after = org_snapshot(org)
    if before != after:
        record_audit(db, ctx, "org.updated", "organization", org.id, before, after)
        if before["timezone"] != after["timezone"]:
            recompute_org_open_requests(db, ctx.org_id)  # SLA-01: the calendar changed
    return org


def list_business_hours(db: Session, ctx: Ctx) -> list[BusinessHour]:
    stmt = scoped(select(BusinessHour), BusinessHour, ctx).order_by(
        BusinessHour.weekday, BusinessHour.open_time
    )
    return list(db.scalars(stmt))


def _hours_dump(rows: Sequence[BusinessHour]) -> list[dict[str, Any]]:
    return [
        {"weekday": r.weekday, "open_time": r.open_time, "close_time": r.close_time} for r in rows
    ]


def replace_business_hours(
    db: Session, ctx: Ctx, intervals: list[dict[str, Any]]
) -> list[BusinessHour]:
    check_no_overlap([(i["weekday"], i["open_time"], i["close_time"]) for i in intervals])
    before = _hours_dump(list_business_hours(db, ctx))
    db.execute(delete(BusinessHour).where(BusinessHour.organization_id == ctx.org_id))
    for i in intervals:
        db.add(BusinessHour(organization_id=ctx.org_id, **i))
    db.flush()
    rows = list_business_hours(db, ctx)
    record_audit(
        db,
        ctx,
        "org.business_hours_replaced",
        "organization",
        ctx.org_id,
        {"intervals": before},
        {"intervals": _hours_dump(rows)},
    )
    recompute_org_open_requests(db, ctx.org_id)  # SLA-01: due instants follow the new hours
    return rows


def create_holiday(db: Session, ctx: Ctx, data: dict[str, Any]) -> Holiday:
    h = Holiday(organization_id=ctx.org_id, **data)
    db.add(h)
    db.flush()
    record_audit(
        db, ctx, "holiday.created", "holiday", h.id, None, {"date": h.date, "name": h.name}
    )
    recompute_org_open_requests(db, ctx.org_id)
    return h


def delete_holiday(db: Session, ctx: Ctx, holiday_id: uuid.UUID) -> None:
    h = get_or_404(db, Holiday, holiday_id, ctx, "Holiday")
    before = {"date": h.date, "name": h.name}
    db.delete(h)
    db.flush()
    record_audit(db, ctx, "holiday.deleted", "holiday", holiday_id, before, None)
    recompute_org_open_requests(db, ctx.org_id)
