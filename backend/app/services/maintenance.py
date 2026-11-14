"""Preventive maintenance plans and idempotent request generation (PM-01..05).

Generation safety: each plan row is locked ``FOR UPDATE`` while its occurrences are created,
``last_generated_for`` advances in the same transaction, and ``UNIQUE (plan_id,
occurrence_date)`` on service_requests is the database-level guarantee behind it (an insert
that hits it inside a SAVEPOINT is counted as "skipped" instead of failing the run). Two
concurrent runs therefore produce exactly one request per occurrence.
"""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.errors import NotFound, ValidationFailed
from app.core.pagination import PageParams, paginate_rows
from app.core.tenancy import Ctx
from app.models.assets import Asset
from app.models.enums import AssetStatus, RequestStatus
from app.models.maintenance import MaintenancePlan
from app.models.org import ServiceCategory
from app.models.requests import ServiceRequest
from app.schemas.maintenance import (
    GeneratedItem,
    GeneratedRequestBrief,
    GenerationReport,
    PlanAssetBrief,
    PlanDetail,
    PlanOut,
    PlanRun,
)
from app.schemas.requests import CategoryBrief
from app.services import maintenance_schedule as sched
from app.services.request_events import add_event

UQ_OCCURRENCE = "uq_service_requests_plan_occurrence"
HISTORY_LIMIT = 100


def _field_error(field: str, message: str) -> ValidationFailed:
    return ValidationFailed("Validation failed.", [{"field": field, "message": message}])


# ---- reading ---------------------------------------------------------------------------
def plan_snapshot(p: MaintenancePlan) -> dict[str, Any]:
    return {
        "asset_id": p.asset_id,
        "category_id": p.category_id,
        "title": p.title,
        "priority": p.priority,
        "first_date": p.first_date,
        "recurrence": p.recurrence,
        "is_enabled": p.is_enabled,
    }


def next_for(plan: MaintenancePlan, asset_status: AssetStatus) -> date | None:
    if not plan.is_enabled or asset_status == AssetStatus.RETIRED:
        return None
    return sched.next_occurrence(plan.first_date, plan.recurrence, plan.last_generated_for)


def _out(plan: MaintenancePlan, asset: Asset, cat: ServiceCategory) -> dict[str, Any]:
    return {
        "id": plan.id,
        "asset": PlanAssetBrief(id=asset.id, code=asset.code, name=asset.name, status=asset.status),
        "category": CategoryBrief(id=cat.id, name=cat.name),
        "title": plan.title,
        "description": plan.description,
        "priority": plan.priority,
        "first_date": plan.first_date,
        "recurrence": plan.recurrence,
        "is_enabled": plan.is_enabled,
        "last_generated_for": plan.last_generated_for,
        "next_occurrence": next_for(plan, asset.status),
        "created_by_membership_id": plan.created_by_membership_id,
        "created_at": plan.created_at,
        "updated_at": plan.updated_at,
    }


def _joined(ctx: Ctx):
    return (
        select(MaintenancePlan, Asset, ServiceCategory)
        .join(
            Asset,
            (Asset.organization_id == MaintenancePlan.organization_id)
            & (Asset.id == MaintenancePlan.asset_id),
        )
        .join(
            ServiceCategory,
            (ServiceCategory.organization_id == MaintenancePlan.organization_id)
            & (ServiceCategory.id == MaintenancePlan.category_id),
        )
        .where(MaintenancePlan.organization_id == ctx.org_id)
    )


def list_plans(
    db: Session,
    ctx: Ctx,
    params: PageParams,
    asset_id: uuid.UUID | None,
    is_enabled: bool | None,
) -> tuple[list[PlanOut], int]:
    stmt = _joined(ctx)
    if asset_id is not None:
        stmt = stmt.where(MaintenancePlan.asset_id == asset_id)
    if is_enabled is not None:
        stmt = stmt.where(MaintenancePlan.is_enabled.is_(is_enabled))
    rows, total = paginate_rows(
        db, stmt.order_by(MaintenancePlan.created_at.desc(), MaintenancePlan.id), params
    )
    return [PlanOut(**_out(*r)) for r in rows], total


def _load(db: Session, ctx: Ctx, plan_id: uuid.UUID, lock: bool = False):
    stmt = _joined(ctx).where(MaintenancePlan.id == plan_id)
    if lock:
        stmt = stmt.with_for_update(of=MaintenancePlan).execution_options(populate_existing=True)
    row = db.execute(stmt).first()
    if row is None:
        raise NotFound("Maintenance plan not found.")
    return row


def get_plan(db: Session, ctx: Ctx, plan_id: uuid.UUID) -> PlanDetail:
    plan, asset, cat = _load(db, ctx, plan_id)
    return _detail(db, ctx, plan, asset, cat)


def _detail(
    db: Session, ctx: Ctx, plan: MaintenancePlan, asset: Asset, cat: ServiceCategory
) -> PlanDetail:
    where = (ServiceRequest.organization_id == ctx.org_id, ServiceRequest.plan_id == plan.id)
    total = db.scalar(select(func.count()).select_from(ServiceRequest).where(*where)) or 0
    reqs = db.scalars(
        select(ServiceRequest)
        .where(*where)
        .order_by(ServiceRequest.occurrence_date.desc())
        .limit(HISTORY_LIMIT)
    )
    generated = [
        GeneratedRequestBrief(
            id=r.id,
            display_id=f"REQ-{r.number}",
            occurrence_date=r.occurrence_date,
            status=r.status,
            created_at=r.created_at,
        )
        for r in reqs
        if r.occurrence_date is not None
    ]
    return PlanDetail(**_out(plan, asset, cat), generated_total=total, generated=generated)


# ---- writing (caller commits) ----------------------------------------------------------
def _enabled_category(db: Session, ctx: Ctx, category_id: uuid.UUID) -> None:
    ok = db.scalar(
        select(ServiceCategory.id).where(
            ServiceCategory.organization_id == ctx.org_id,
            ServiceCategory.id == category_id,
            ServiceCategory.is_enabled.is_(True),
        )
    )
    if ok is None:
        raise _field_error("category_id", "Category is not available.")


def create_plan(db: Session, ctx: Ctx, data: dict[str, Any]) -> PlanDetail:
    asset = db.scalars(
        select(Asset).where(Asset.organization_id == ctx.org_id, Asset.id == data["asset_id"])
    ).first()
    if asset is None:
        raise _field_error("asset_id", "Asset not found.")
    if asset.status != AssetStatus.ACTIVE:
        raise _field_error(
            "asset_id", f"Plans can only be created for ACTIVE assets (this one is {asset.status})."
        )
    _enabled_category(db, ctx, data["category_id"])
    plan = MaintenancePlan(
        organization_id=ctx.org_id, created_by_membership_id=ctx.membership_id, **data
    )
    db.add(plan)
    db.flush()
    db.refresh(plan)
    record_audit(
        db, ctx, "maintenance_plan.created", "maintenance_plan", plan.id, None, plan_snapshot(plan)
    )
    return get_plan(db, ctx, plan.id)


def update_plan(db: Session, ctx: Ctx, plan_id: uuid.UUID, data: dict[str, Any]) -> PlanDetail:
    plan, asset, _ = _load(db, ctx, plan_id, lock=True)
    before = plan_snapshot(plan)
    if data.get("category_id") not in (None, plan.category_id):
        _enabled_category(db, ctx, data["category_id"])
    if data.get("is_enabled") and not plan.is_enabled and asset.status == AssetStatus.RETIRED:
        raise _field_error("is_enabled", "A plan of a retired asset cannot be enabled.")
    for k, v in data.items():
        if v is not None:
            setattr(plan, k, v)
    db.flush()
    db.refresh(plan)
    after = plan_snapshot(plan)
    if before != after:
        action = "maintenance_plan.updated"
        if before["is_enabled"] != after["is_enabled"]:
            action = (
                "maintenance_plan.enabled" if after["is_enabled"] else "maintenance_plan.disabled"
            )
        record_audit(db, ctx, action, "maintenance_plan", plan.id, before, after)
    return get_plan(db, ctx, plan.id)


def disable_plans_for_retired_asset(db: Session, ctx: Ctx, asset_id: uuid.UUID) -> int:
    """ASSET-04: retiring an asset disables its enabled plans (each audited)."""
    plans = list(
        db.scalars(
            select(MaintenancePlan)
            .where(
                MaintenancePlan.organization_id == ctx.org_id,
                MaintenancePlan.asset_id == asset_id,
                MaintenancePlan.is_enabled.is_(True),
            )
            .order_by(MaintenancePlan.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    for p in plans:
        p.is_enabled = False
        record_audit(
            db,
            ctx,
            "maintenance_plan.disabled",
            "maintenance_plan",
            p.id,
            {"is_enabled": True},
            {"is_enabled": False, "reason": "asset retired"},
        )
    db.flush()
    return len(plans)


# ---- generation ------------------------------------------------------------------------
def _is_occurrence_conflict(exc: IntegrityError) -> bool:
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None) == UQ_OCCURRENCE


def _generate_for_plan(db: Session, plan_id: uuid.UUID, as_of: date) -> PlanRun | None:
    plan = db.scalars(
        select(MaintenancePlan)
        .where(MaintenancePlan.id == plan_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if plan is None or not plan.is_enabled:
        return None
    asset = db.scalars(
        select(Asset)
        .where(Asset.organization_id == plan.organization_id, Asset.id == plan.asset_id)
        .execution_options(populate_existing=True)
    ).one()
    if asset.status == AssetStatus.RETIRED:
        return None
    run = PlanRun(
        plan_id=plan.id, organization_id=plan.organization_id, created=[], skipped_existing=[]
    )
    due = sched.occurrences_due(plan.first_date, plan.recurrence, plan.last_generated_for, as_of)
    for d in due:
        req = ServiceRequest(
            organization_id=plan.organization_id,
            requester_membership_id=None,
            created_by_membership_id=None,
            property_id=asset.property_id,
            asset_id=asset.id,
            category_id=plan.category_id,
            title=f"{plan.title} ({d.isoformat()})",
            description=plan.description,
            priority=plan.priority,
            status=RequestStatus.SUBMITTED,
            plan_id=plan.id,
            occurrence_date=d,
        )
        try:
            with db.begin_nested():
                req.number = db.execute(
                    text(
                        "UPDATE organizations SET request_seq = request_seq + 1 "
                        "WHERE id = :org RETURNING request_seq"
                    ),
                    {"org": plan.organization_id},
                ).scalar_one()
                db.add(req)
                db.flush()
        except IntegrityError as exc:
            if not _is_occurrence_conflict(exc):
                raise
            run.skipped_existing.append(d)
        else:
            add_event(
                db,
                None,
                req,
                "REQUEST_CREATED",
                to_status=req.status.value,
                data={
                    "number": req.number,
                    "priority": req.priority.value,
                    "source": "maintenance",
                    "plan_id": plan.id,
                    "occurrence_date": d,
                },
            )
            run.created.append(
                GeneratedItem(request_id=req.id, display_id=f"REQ-{req.number}", occurrence_date=d)
            )
        plan.last_generated_for = d
    if due:
        db.flush()
    return run


def generate(
    db: Session,
    org_id: uuid.UUID | None,
    as_of: date,
    *,
    commit_each: bool = True,
    ctx: Ctx | None = None,
) -> GenerationReport:
    """Create a request for every occurrence due on or before ``as_of`` (PM-02/03).

    ``commit_each=True`` (CLI): one transaction per plan, a failing plan is rolled back and
    counted in ``errors``. ``commit_each=False`` (API, idempotency wrapper): everything runs in
    the caller's transaction and errors propagate."""
    stmt = select(MaintenancePlan.id).where(MaintenancePlan.is_enabled.is_(True))
    if org_id is not None:
        stmt = stmt.where(MaintenancePlan.organization_id == org_id)
    plan_ids = list(db.scalars(stmt.order_by(MaintenancePlan.id)))
    if commit_each:
        db.rollback()  # do not hold the listing transaction while plans are processed
    runs: list[PlanRun] = []
    errors = 0
    for pid in plan_ids:
        try:
            run = _generate_for_plan(db, pid, as_of)
            if commit_each:
                db.commit()
        except Exception:
            if not commit_each:
                raise
            db.rollback()
            errors += 1
            continue
        if run is not None:
            runs.append(run)
    created = sum(len(r.created) for r in runs)
    if ctx is not None and created:
        record_audit(
            db,
            ctx,
            "maintenance.generate",
            "organization",
            ctx.org_id,
            None,
            {"as_of": as_of, "requests_created": created},
        )
        if commit_each:
            db.commit()
    return GenerationReport(
        as_of=as_of,
        plans_processed=len(runs),
        requests_created=created,
        skipped_existing=sum(len(r.skipped_existing) for r in runs),
        errors=errors,
        plans=[r for r in runs if r.created or r.skipped_existing],
    )
