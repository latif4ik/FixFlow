"""Asset detail (ASSET-05) and history (ASSET-04) read models."""

import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.pagination import PageParams, paginate_rows
from app.core.tenancy import Ctx, get_or_404
from app.models.assets import Asset
from app.models.assignments import Assignment
from app.models.enums import AssignmentStatus, RequestStatus
from app.models.identity import Membership, User
from app.models.inventory import InventoryItem, MaterialUsage
from app.models.maintenance import MaintenancePlan
from app.models.requests import EvidenceFile, ServiceRequest
from app.schemas.assets import (
    AssetDetail,
    AssetHistoryItem,
    AssetOut,
    LastServiceOut,
    MaterialLine,
    MaterialSummary,
    NextMaintenanceOut,
    OutcomeOut,
    WorkBrief,
)
from app.schemas.common import PersonBrief
from app.services import maintenance as maintenance_svc
from app.services.request_access import is_staff, visible_requests_stmt
from app.sla import service as sla_svc

TERMINAL = (RequestStatus.CLOSED, RequestStatus.CANCELED)
OPEN_WORK_LIMIT = 50


def _brief(r: ServiceRequest, now) -> WorkBrief:
    return WorkBrief(
        id=r.id,
        display_id=f"REQ-{r.number}",
        title=r.title,
        status=r.status,
        priority=r.priority,
        created_at=r.created_at,
        sla_state=sla_svc.cached_state(r, now),
        sla_due_at=r.sla_due_at,
    )


def _technicians(
    db: Session, org_id: uuid.UUID, request_ids: list[uuid.UUID]
) -> dict[uuid.UUID, PersonBrief]:
    """Latest ACTIVE / COMPLETED assignee per request."""
    if not request_ids:
        return {}
    rows = db.execute(
        select(Assignment.request_id, Assignment.technician_membership_id, User.full_name)
        .join(
            Membership,
            (Membership.organization_id == Assignment.organization_id)
            & (Membership.id == Assignment.technician_membership_id),
        )
        .join(User, User.id == Membership.user_id)
        .where(
            Assignment.organization_id == org_id,
            Assignment.request_id.in_(request_ids),
            Assignment.status.in_([AssignmentStatus.ACTIVE, AssignmentStatus.COMPLETED]),
        )
        .order_by(Assignment.created_at, Assignment.id)
    ).all()
    return {rid: PersonBrief(membership_id=mid, name=name) for rid, mid, name in rows}


def asset_detail(db: Session, ctx: Ctx, asset: Asset) -> AssetDetail:
    now = clock.now()
    visible = visible_requests_stmt(ctx).where(ServiceRequest.asset_id == asset.id)
    open_rows = list(
        db.scalars(
            visible.where(ServiceRequest.status.notin_(TERMINAL))
            .order_by(ServiceRequest.created_at.desc(), ServiceRequest.id)
            .limit(OPEN_WORK_LIMIT)
        )
    )
    last = db.scalars(
        visible.where(
            ServiceRequest.status.in_([RequestStatus.COMPLETED, RequestStatus.CLOSED]),
            ServiceRequest.completed_at.is_not(None),
        )
        .order_by(ServiceRequest.completed_at.desc(), ServiceRequest.id)
        .limit(1)
    ).first()
    last_out = None
    if last is not None and last.completed_at is not None:
        tech = _technicians(db, ctx.org_id, [last.id]).get(last.id)
        last_out = LastServiceOut(
            request=_brief(last, now), completed_at=last.completed_at, technician=tech
        )
    next_out = None
    if is_staff(ctx):
        best: tuple[Any, MaintenancePlan] | None = None
        for plan in db.scalars(
            select(MaintenancePlan).where(
                MaintenancePlan.organization_id == ctx.org_id,
                MaintenancePlan.asset_id == asset.id,
                MaintenancePlan.is_enabled.is_(True),
            )
        ):
            nxt = maintenance_svc.next_for(plan, asset.status)
            if nxt is not None and (best is None or nxt < best[0]):
                best = (nxt, plan)
        if best is not None:
            next_out = NextMaintenanceOut(plan_id=best[1].id, title=best[1].title, date=best[0])
    return AssetDetail(
        **AssetOut.model_validate(asset).model_dump(),
        open_work=[_brief(r, now) for r in open_rows],
        last_completed_service=last_out,
        next_maintenance=next_out,
    )


def asset_history(
    db: Session, ctx: Ctx, asset_id: uuid.UUID, params: PageParams
) -> tuple[list[AssetHistoryItem], int]:
    get_or_404(db, Asset, asset_id, ctx, "Asset")
    stmt = (
        select(ServiceRequest)
        .where(ServiceRequest.organization_id == ctx.org_id, ServiceRequest.asset_id == asset_id)
        .order_by(ServiceRequest.created_at.desc(), ServiceRequest.id)
    )
    rows, total = paginate_rows(db, stmt, params)
    reqs: list[ServiceRequest] = [r[0] for r in rows]
    ids = [r.id for r in reqs]
    techs = _technicians(db, ctx.org_id, ids)
    materials: dict[uuid.UUID, list[MaterialLine]] = defaultdict(list)
    if ids:
        usage = db.execute(
            select(
                MaterialUsage.request_id,
                MaterialUsage.item_id,
                InventoryItem.name,
                InventoryItem.unit,
                func.sum(MaterialUsage.quantity),
                func.sum(MaterialUsage.total_cost_minor),
            )
            .join(
                InventoryItem,
                (InventoryItem.organization_id == MaterialUsage.organization_id)
                & (InventoryItem.id == MaterialUsage.item_id),
            )
            .where(MaterialUsage.organization_id == ctx.org_id, MaterialUsage.request_id.in_(ids))
            .group_by(
                MaterialUsage.request_id,
                MaterialUsage.item_id,
                InventoryItem.name,
                InventoryItem.unit,
            )
            .order_by(InventoryItem.name)
        ).all()
        for rid, item_id, name, unit, qty, cost in usage:
            materials[rid].append(
                MaterialLine(
                    item_id=item_id, name=name, unit=unit, quantity=qty, total_cost_minor=int(cost)
                )
            )
    files = dict(
        db.execute(
            select(EvidenceFile.request_id, func.count())
            .where(EvidenceFile.organization_id == ctx.org_id, EvidenceFile.request_id.in_(ids))
            .group_by(EvidenceFile.request_id)
        ).all()
        if ids
        else []
    )
    items = [
        AssetHistoryItem(
            request_id=r.id,
            display_id=f"REQ-{r.number}",
            title=r.title,
            status=r.status,
            priority=r.priority,
            created_at=r.created_at,
            completed_at=r.completed_at,
            technician=techs.get(r.id),
            outcome=OutcomeOut(status=r.status, sla_outcome=r.sla_outcome),
            materials=MaterialSummary(
                items=materials.get(r.id, []),
                total_cost_minor=sum(m.total_cost_minor for m in materials.get(r.id, [])),
            ),
            attachment_count=int(files.get(r.id, 0)),
            plan_id=r.plan_id,
            occurrence_date=r.occurrence_date,
        )
        for r in reqs
    ]
    return items, total
