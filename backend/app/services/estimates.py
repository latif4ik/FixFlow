"""Versioned, approval-gated estimates (EST-01..06, DATA-04).

Concurrency model:
* every mutation (create/edit/submit/withdraw/decision) locks the REQUEST row first (one
  lock order: request -> estimate), which serializes estimate operations per request;
* the requester decision is ONE conditional UPDATE (``status='AWAITING_APPROVAL' AND
  version=:v``) whose rowcount decides the winner, so two simultaneous decisions (or a decision
  on a version that was just superseded) can never both succeed.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core import money
from app.core.audit import record_audit
from app.core.errors import AppError, Conflict, Forbidden, NotFound, ValidationFailed
from app.core.pagination import PageParams, paginate_rows
from app.core.tenancy import Ctx
from app.models.enums import EstimateStatus, MembershipRole, RequestStatus
from app.models.estimates import Estimate, EstimateLine
from app.models.inventory import InventoryItem
from app.models.requests import ServiceRequest
from app.schemas.estimates import (
    EstimateLineIn,
    EstimateLineOut,
    EstimateListItem,
    EstimateOut,
    EstimateRequestBrief,
    EstimateSummary,
)
from app.schemas.requests import PersonBrief
from app.services import notifications
from app.services.assignments import names
from app.services.estimate_gate import CURRENT_STATUSES, current_estimate
from app.services.request_access import (
    get_visible_request,
    is_owner_requester,
    is_staff,
)
from app.services.request_events import add_event

ES = EstimateStatus
S = RequestStatus
# Requests on which estimates may still be created / revised / submitted.
OPEN_FOR_ESTIMATES = frozenset(
    {S.TRIAGED, S.SCHEDULED, S.ACCEPTED, S.IN_PROGRESS, S.BLOCKED, S.REOPENED}
)


def _require_staff(ctx: Ctx) -> None:
    if not is_staff(ctx):
        raise Forbidden("Only dispatchers and admins can manage estimates.")


def _require_open(req: ServiceRequest) -> None:
    if req.status not in OPEN_FOR_ESTIMATES:
        raise Conflict(
            "Estimates cannot be changed on a request in this state.",
            {"status": req.status.value},
        )


def _immutable() -> AppError:
    return AppError(
        409,
        "estimate_immutable",
        "A submitted estimate cannot be changed. Create a new version instead.",
    )


# ---- loading + visibility --------------------------------------------------------------
def _get(db: Session, ctx: Ctx, estimate_id: uuid.UUID) -> Estimate:
    est = db.scalars(
        select(Estimate)
        .where(Estimate.organization_id == ctx.org_id, Estimate.id == estimate_id)
        .execution_options(populate_existing=True)
    ).first()
    if est is None:
        raise NotFound("Estimate not found.")
    return est


def _visible_to(db: Session, ctx: Ctx, est: Estimate) -> bool:
    if is_staff(ctx):
        return True
    if ctx.role == MembershipRole.REQUESTER:
        return est.status != ES.DRAFT
    cur = current_estimate(db, ctx.org_id, est.request_id)
    return cur is not None and cur.id == est.id and cur.status == ES.APPROVED


def load_visible(db: Session, ctx: Ctx, estimate_id: uuid.UUID) -> tuple[Estimate, ServiceRequest]:
    """Estimate + its request, else 404 (other org / other requester / hidden version)."""
    est = _get(db, ctx, estimate_id)
    req = get_visible_request(db, ctx, est.request_id)
    if not _visible_to(db, ctx, est):
        raise NotFound("Estimate not found.")
    return est, req


def _lock_for_edit(
    db: Session, ctx: Ctx, estimate_id: uuid.UUID
) -> tuple[Estimate, ServiceRequest]:
    _require_staff(ctx)
    est = _get(db, ctx, estimate_id)
    req = get_visible_request(db, ctx, est.request_id, lock=True)
    est = _get(db, ctx, estimate_id)  # re-read under the request lock
    return est, req


# ---- output ----------------------------------------------------------------------------
def _lines_by_estimate(
    db: Session, org_id: uuid.UUID, ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[EstimateLine]]:
    out: dict[uuid.UUID, list[EstimateLine]] = {i: [] for i in ids}
    if ids:
        rows = db.scalars(
            select(EstimateLine)
            .where(EstimateLine.organization_id == org_id, EstimateLine.estimate_id.in_(ids))
            .order_by(EstimateLine.estimate_id, EstimateLine.position)
            .execution_options(populate_existing=True)
        )
        for ln in rows:
            out[ln.estimate_id].append(ln)
    return out


def _line_out(ln: EstimateLine) -> EstimateLineOut:
    return EstimateLineOut(
        id=ln.id,
        position=ln.position,
        description=ln.description,
        inventory_item_id=ln.inventory_item_id,
        quantity=ln.quantity,
        unit_price_minor=ln.unit_price_minor,
        line_total_minor=ln.line_total_minor,
    )


def build_out(db: Session, ctx: Ctx, ests: list[Estimate]) -> list[EstimateOut]:
    lines = _lines_by_estimate(db, ctx.org_id, [e.id for e in ests])
    ids: set[uuid.UUID] = set()
    for e in ests:
        ids |= {
            i
            for i in (
                e.created_by_membership_id,
                e.submitted_by_membership_id,
                e.decided_by_membership_id,
                e.withdrawn_by_membership_id,
            )
            if i
        }
    n = names(db, ctx.org_id, ids)

    def person(mid: uuid.UUID | None) -> PersonBrief | None:
        return PersonBrief(membership_id=mid, name=n.get(mid, "")) if mid else None

    hide_internal = ctx.role == MembershipRole.TECHNICIAN
    return [
        EstimateOut(
            id=e.id,
            request_id=e.request_id,
            version=e.version,
            status=e.status,
            supersedes_id=e.supersedes_id,
            labor_minutes=e.labor_minutes,
            labor_rate_minor=e.labor_rate_minor,
            labor_cost_minor=e.labor_cost_minor,
            materials_total_minor=e.materials_total_minor,
            total_minor=e.total_minor,
            currency=e.currency,
            notes=None if hide_internal else e.notes,
            lines=[_line_out(ln) for ln in lines[e.id]],
            created_by=person(e.created_by_membership_id),
            created_at=e.created_at,
            submitted_at=e.submitted_at,
            submitted_by=person(e.submitted_by_membership_id),
            decided_at=e.decided_at,
            decided_by=person(e.decided_by_membership_id),
            decision_reason=None if hide_internal else e.decision_reason,
            withdrawn_at=e.withdrawn_at,
            withdrawn_by=person(e.withdrawn_by_membership_id),
            withdraw_reason=None if hide_internal else e.withdraw_reason,
        )
        for e in ests
    ]


def current_summary(db: Session, ctx: Ctx, req: ServiceRequest) -> EstimateSummary | None:
    """Estimate summary for the request detail, honoring the caller's visibility."""
    est = current_estimate(db, ctx.org_id, req.id)
    if est is None and is_staff(ctx):
        est = db.scalars(
            select(Estimate)
            .where(
                Estimate.organization_id == ctx.org_id,
                Estimate.request_id == req.id,
                Estimate.status == ES.DRAFT,
            )
            .execution_options(populate_existing=True)
        ).first()
    if est is None:
        return None
    if ctx.role == MembershipRole.TECHNICIAN and est.status != ES.APPROVED:
        return None
    lines = _lines_by_estimate(db, ctx.org_id, [est.id])[est.id]
    return EstimateSummary(
        id=est.id,
        version=est.version,
        status=est.status,
        total_minor=est.total_minor,
        currency=est.currency,
        labor_minutes=est.labor_minutes,
        labor_cost_minor=est.labor_cost_minor,
        materials_total_minor=est.materials_total_minor,
        lines=[_line_out(ln) for ln in lines],
    )


# ---- money -----------------------------------------------------------------------------
def _resolve_lines(
    db: Session, ctx: Ctx, lines: list[EstimateLineIn]
) -> list[tuple[EstimateLineIn, int, int]]:
    """(line, unit_price_minor, line_total_minor) with item defaults applied (org-scoped)."""
    item_ids = {ln.inventory_item_id for ln in lines if ln.inventory_item_id}
    prices: dict[uuid.UUID, int] = {}
    if item_ids:
        prices = {
            r[0]: r[1]
            for r in db.execute(
                select(InventoryItem.id, InventoryItem.unit_price_minor).where(
                    InventoryItem.organization_id == ctx.org_id, InventoryItem.id.in_(item_ids)
                )
            )
        }
    errors: list[dict[str, str]] = []
    out: list[tuple[EstimateLineIn, int, int]] = []
    for i, ln in enumerate(lines):
        if ln.inventory_item_id and ln.inventory_item_id not in prices:
            errors.append({"field": f"lines.{i}.inventory_item_id", "message": "unknown item"})
            continue
        price = ln.unit_price_minor
        if price is None:
            if ln.inventory_item_id is None:
                errors.append(
                    {"field": f"lines.{i}.unit_price_minor", "message": "unit price is required"}
                )
                continue
            price = prices[ln.inventory_item_id]
        out.append((ln, price, money.line_total_minor(ln.quantity, price)))
    if errors:
        raise ValidationFailed("Invalid estimate lines.", errors)
    return out


def _replace_lines(db: Session, ctx: Ctx, est: Estimate, lines: list[EstimateLineIn]) -> int:
    resolved = _resolve_lines(db, ctx, lines)
    db.execute(
        delete(EstimateLine).where(
            EstimateLine.organization_id == ctx.org_id, EstimateLine.estimate_id == est.id
        )
    )
    for pos, (ln, price, total) in enumerate(resolved, start=1):
        db.add(
            EstimateLine(
                organization_id=ctx.org_id,
                estimate_id=est.id,
                position=pos,
                description=ln.description,
                inventory_item_id=ln.inventory_item_id,
                quantity=ln.quantity,
                unit_price_minor=price,
                line_total_minor=total,
            )
        )
    db.flush()
    return sum(r[2] for r in resolved)


def _apply_totals(est: Estimate, materials_total: int) -> None:
    est.labor_cost_minor = money.labor_cost_minor(est.labor_minutes, est.labor_rate_minor)
    est.materials_total_minor = materials_total
    est.total_minor = est.labor_cost_minor + est.materials_total_minor


def _lines_total(db: Session, org_id: uuid.UUID, estimate_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.coalesce(func.sum(EstimateLine.line_total_minor), 0)).where(
                EstimateLine.organization_id == org_id, EstimateLine.estimate_id == estimate_id
            )
        )
        or 0
    )


# ---- commands --------------------------------------------------------------------------
# Every command below runs in ONE caller-owned transaction (no commit).
def create_draft(
    db: Session,
    ctx: Ctx,
    request_id: uuid.UUID,
    labor_minutes: int,
    labor_rate_minor: int,
    notes: str | None,
    lines: list[EstimateLineIn],
) -> Estimate:
    _require_staff(ctx)
    req = get_visible_request(db, ctx, request_id, lock=True)
    _require_open(req)
    base = select(Estimate).where(
        Estimate.organization_id == ctx.org_id, Estimate.request_id == req.id
    )
    if db.scalars(base.where(Estimate.status == ES.DRAFT)).first() is not None:
        raise AppError(
            409, "draft_exists", "This request already has a draft estimate. Edit or submit it."
        )
    max_version = db.scalar(
        select(func.coalesce(func.max(Estimate.version), 0)).where(
            Estimate.organization_id == ctx.org_id, Estimate.request_id == req.id
        )
    )
    previous = db.scalars(
        base.where(Estimate.status != ES.DRAFT).order_by(Estimate.version.desc()).limit(1)
    ).first()
    est = Estimate(
        organization_id=ctx.org_id,
        request_id=req.id,
        version=int(max_version or 0) + 1,
        status=ES.DRAFT,
        supersedes_id=previous.id if previous else None,
        labor_minutes=labor_minutes,
        labor_rate_minor=labor_rate_minor,
        labor_cost_minor=0,
        materials_total_minor=0,
        total_minor=0,
        currency=money.CURRENCY,
        notes=notes,
        created_by_membership_id=ctx.membership_id,
    )
    db.add(est)
    db.flush()
    total = _replace_lines(db, ctx, est, lines)
    _apply_totals(est, total)
    db.flush()
    record_audit(
        db,
        ctx,
        "estimate.create",
        "estimate",
        est.id,
        after={
            "request_id": req.id,
            "version": est.version,
            "total_minor": est.total_minor,
            "supersedes_id": est.supersedes_id,
        },
    )
    return est


def patch_draft(db: Session, ctx: Ctx, estimate_id: uuid.UUID, changes: dict[str, Any]) -> Estimate:
    est, req = _lock_for_edit(db, ctx, estimate_id)
    if est.status != ES.DRAFT:
        raise _immutable()
    _require_open(req)
    before = {"total_minor": est.total_minor, "labor_minutes": est.labor_minutes}
    for k in ("labor_minutes", "labor_rate_minor", "notes"):
        if k in changes:
            setattr(est, k, changes[k])
    _apply_totals(est, _lines_total(db, ctx.org_id, est.id))
    db.flush()
    record_audit(
        db,
        ctx,
        "estimate.update",
        "estimate",
        est.id,
        before=before,
        after={"total_minor": est.total_minor, "labor_minutes": est.labor_minutes},
    )
    return est


def put_lines(
    db: Session, ctx: Ctx, estimate_id: uuid.UUID, lines: list[EstimateLineIn]
) -> Estimate:
    est, req = _lock_for_edit(db, ctx, estimate_id)
    if est.status != ES.DRAFT:
        raise _immutable()
    _require_open(req)
    before_total = est.total_minor
    total = _replace_lines(db, ctx, est, lines)
    _apply_totals(est, total)
    db.flush()
    record_audit(
        db,
        ctx,
        "estimate.update_lines",
        "estimate",
        est.id,
        before={"total_minor": before_total},
        after={"total_minor": est.total_minor, "line_count": len(lines)},
    )
    return est


def submit(db: Session, ctx: Ctx, estimate_id: uuid.UUID) -> Estimate:
    est, req = _lock_for_edit(db, ctx, estimate_id)
    if est.status != ES.DRAFT:
        raise AppError(409, "estimate_not_draft", "Only a draft estimate can be submitted.")
    _require_open(req)
    now = datetime.now(UTC)
    # The previous live version (pending / approved / rejected) is replaced by this one.
    superseded = list(
        db.scalars(
            select(Estimate).where(
                Estimate.organization_id == ctx.org_id,
                Estimate.request_id == req.id,
                Estimate.status.in_(CURRENT_STATUSES),
                Estimate.id != est.id,
            )
        )
    )
    for old in superseded:
        old.status = ES.SUPERSEDED
    db.flush()  # frees the one-pending slot before the new row takes it
    est.status = ES.AWAITING_APPROVAL
    est.submitted_at = now
    est.submitted_by_membership_id = ctx.membership_id
    db.flush()
    sup = [
        {"estimate_id": str(o.id), "version": o.version, "was": "SUPERSEDED"} for o in superseded
    ]
    # SLA pause source (Phase 3b): the clock pauses while an estimate awaits approval.
    add_event(
        db,
        ctx,
        req,
        "ESTIMATE_SUBMITTED",
        data={
            "estimate_id": est.id,
            "version": est.version,
            "total_minor": est.total_minor,
            "superseded": sup,
        },
    )
    record_audit(
        db,
        ctx,
        "estimate.submit",
        "estimate",
        est.id,
        before={"status": ES.DRAFT.value},
        after={
            "status": est.status.value,
            "version": est.version,
            "total_minor": est.total_minor,
            "superseded": sup,
        },
    )
    notifications.notify(
        db,
        ctx.org_id,
        [req.requester_membership_id],
        notifications.ESTIMATE_SUBMITTED,
        "Estimate awaiting your approval",
        f"Estimate v{est.version} ({_fmt(est.total_minor)} KGS) for request #{req.number} "
        "needs your decision.",
        request_id=req.id,
        data={"estimate_id": est.id, "version": est.version, "total_minor": est.total_minor},
        dedupe_key=f"estimate-submitted:{est.id}",
        exclude=ctx.membership_id,
    )
    return est


def _fmt(minor: int) -> str:
    return f"{Decimal(minor) / Decimal(100):.2f}"


def decide(
    db: Session,
    ctx: Ctx,
    estimate_id: uuid.UUID,
    version: int,
    decision: str,
    reason: str | None,
) -> Estimate:
    est, req = load_visible(db, ctx, estimate_id)
    if not is_owner_requester(ctx, req):
        raise Forbidden("Only the requester of this request can decide on its estimate.")
    if decision == "REJECT" and not (reason and len(reason.strip()) >= 5):
        raise ValidationFailed(
            "A reason is required to reject an estimate.",
            [{"field": "reason", "message": "must be at least 5 characters"}],
        )
    # Lock order is always request -> estimate (same as submit/withdraw): deciding without the
    # request lock deadlocks against a concurrent submit of the next version.
    req = get_visible_request(db, ctx, req.id, lock=True)
    if req.status not in OPEN_FOR_ESTIMATES:
        raise Conflict("This request is no longer open.", {"status": req.status.value})
    new_status = ES.APPROVED if decision == "APPROVE" else ES.REJECTED
    now = datetime.now(UTC)
    res = db.execute(
        update(Estimate)
        .where(
            Estimate.id == estimate_id,
            Estimate.organization_id == ctx.org_id,
            Estimate.status == ES.AWAITING_APPROVAL,
            Estimate.version == version,
        )
        .values(
            status=new_status,
            decided_at=now,
            decided_by_membership_id=ctx.membership_id,
            decision_reason=reason.strip() if reason else None,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if getattr(res, "rowcount", 0) != 1:
        cur = _get(db, ctx, estimate_id)
        raise AppError(
            409,
            "estimate_not_pending",
            "This estimate version is no longer awaiting a decision.",
            {"estimate_status": cur.status.value, "estimate_version": cur.version},
        )
    est = _get(db, ctx, estimate_id)
    # SLA resume source (Phase 3b).
    add_event(
        db,
        ctx,
        req,
        "ESTIMATE_APPROVED" if new_status == ES.APPROVED else "ESTIMATE_REJECTED",
        data={
            "estimate_id": est.id,
            "version": est.version,
            "total_minor": est.total_minor,
            "reason": est.decision_reason,
        },
    )
    record_audit(
        db,
        ctx,
        "estimate.decide",
        "estimate",
        est.id,
        before={"status": ES.AWAITING_APPROVAL.value},
        after={
            "status": new_status.value,
            "decision": decision,
            "version": est.version,
            "decided_by_membership_id": ctx.membership_id,
            "reason": est.decision_reason,
        },
    )
    verb = "approved" if new_status == ES.APPROVED else "rejected"
    notifications.notify(
        db,
        ctx.org_id,
        notifications.staff_recipients(db, ctx.org_id),
        notifications.ESTIMATE_DECIDED,
        f"Estimate {verb}",
        f"Estimate v{est.version} for request #{req.number} was {verb} by the requester.",
        request_id=req.id,
        data={"estimate_id": est.id, "version": est.version, "decision": new_status.value},
        dedupe_key=f"estimate-decided:{est.id}",
        exclude=ctx.membership_id,
    )
    return est


def withdraw(db: Session, ctx: Ctx, estimate_id: uuid.UUID, reason: str) -> Estimate:
    est, req = _lock_for_edit(db, ctx, estimate_id)
    now = datetime.now(UTC)
    prev = est.status
    res = db.execute(
        update(Estimate)
        .where(
            Estimate.id == estimate_id,
            Estimate.organization_id == ctx.org_id,
            Estimate.status.in_([ES.AWAITING_APPROVAL, ES.REJECTED]),
        )
        .values(
            status=ES.SUPERSEDED,
            withdrawn_at=now,
            withdrawn_by_membership_id=ctx.membership_id,
            withdraw_reason=reason.strip(),
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if getattr(res, "rowcount", 0) != 1:
        raise AppError(
            409,
            "estimate_not_withdrawable",
            "Only a rejected or pending estimate can be withdrawn.",
            {"estimate_status": prev.value},
        )
    est = _get(db, ctx, estimate_id)
    add_event(
        db,
        ctx,
        req,
        "ESTIMATE_WITHDRAWN",
        data={
            "estimate_id": est.id,
            "version": est.version,
            "was": prev.value,
            "reason": est.withdraw_reason,
        },
    )
    record_audit(
        db,
        ctx,
        "estimate.withdraw",
        "estimate",
        est.id,
        before={"status": prev.value},
        after={"status": ES.SUPERSEDED.value, "reason": est.withdraw_reason},
    )
    return est


# ---- queries ---------------------------------------------------------------------------
def list_for_request(db: Session, ctx: Ctx, request_id: uuid.UUID) -> list[EstimateOut]:
    req = get_visible_request(db, ctx, request_id)
    stmt = select(Estimate).where(
        Estimate.organization_id == ctx.org_id, Estimate.request_id == req.id
    )
    stmt = stmt.execution_options(populate_existing=True)
    rows = list(db.scalars(stmt.order_by(Estimate.version)))
    rows = [e for e in rows if _visible_to(db, ctx, e)]
    return build_out(db, ctx, rows)


def list_all(
    db: Session,
    ctx: Ctx,
    params: PageParams,
    status: list[EstimateStatus] | None,
    request_id: uuid.UUID | None,
) -> tuple[list[EstimateListItem], int]:
    _require_staff(ctx)
    stmt = select(Estimate).where(Estimate.organization_id == ctx.org_id)
    if status:
        stmt = stmt.where(Estimate.status.in_(status))
    if request_id:
        stmt = stmt.where(Estimate.request_id == request_id)
    rows, total = paginate_rows(db, stmt.order_by(Estimate.created_at.desc(), Estimate.id), params)
    outs = build_out(db, ctx, [r[0] for r in rows])
    ids = {o.request_id for o in outs}
    briefs: dict[uuid.UUID, EstimateRequestBrief] = {}
    if ids:  # one batched query, no N+1
        for rid, number, title in db.execute(
            select(ServiceRequest.id, ServiceRequest.number, ServiceRequest.title).where(
                ServiceRequest.organization_id == ctx.org_id, ServiceRequest.id.in_(ids)
            )
        ):
            briefs[rid] = EstimateRequestBrief(id=rid, display_id=f"REQ-{number}", title=title)
    return [
        EstimateListItem(**o.model_dump(), request=briefs.get(o.request_id)) for o in outs
    ], total
