"""Service requests: create, edit, triage metadata, duplicate links, list and detail."""

import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Select, case, or_, select, text
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.core.pagination import PageParams, paginate_rows
from app.core.tenancy import Ctx
from app.models.assets import Asset, Property, PropertyAccess
from app.models.enums import AssetStatus, MembershipRole, Priority, RequestStatus
from app.models.identity import Membership, User
from app.models.org import ServiceCategory
from app.models.requests import EvidenceFile, RequestEvent, ServiceRequest, WorkNote
from app.schemas.requests import (
    AssetBrief,
    CategoryBrief,
    DuplicateBrief,
    FileOut,
    NoteOut,
    OrgRef,
    PersonBrief,
    PropertyBrief,
    RequestDetail,
    RequestListItem,
    TimelineItem,
)
from app.services import lifecycle
from app.services.request_access import (
    get_visible_request,
    is_owner_requester,
    is_staff,
    visible_files_clause,
    visible_requests_stmt,
)
from app.services.request_events import EVENT_LABELS, STAFF_ONLY_EVENTS, add_event
from app.services.util import like_pattern

R = MembershipRole
NUMBER_RE = re.compile(r"^(?:REQ-)?(\d{1,9})$", re.IGNORECASE)
PRIORITY_RANK = case(
    (ServiceRequest.priority == Priority.HIGH, 0),
    (ServiceRequest.priority == Priority.NORMAL, 1),
    else_=2,
)
TERMINAL = lifecycle.TERMINAL


def display_id(number: int) -> str:
    return f"REQ-{number}"


def _field_error(field: str, message: str, summary: str = "Validation failed.") -> ValidationFailed:
    return ValidationFailed(summary, [{"field": field, "message": message}])


# ---- create ----------------------------------------------------------------------------
def _resolve_property(db: Session, ctx: Ctx, property_id: uuid.UUID) -> Property:
    """Same error for unknown, other-org and not-granted properties (no existence leak)."""
    stmt = select(Property).where(
        Property.organization_id == ctx.org_id,
        Property.id == property_id,
        Property.is_active.is_(True),
    )
    if ctx.role == R.REQUESTER:
        stmt = stmt.where(
            Property.id.in_(
                select(PropertyAccess.property_id).where(
                    PropertyAccess.organization_id == ctx.org_id,
                    PropertyAccess.membership_id == ctx.membership_id,
                )
            )
        )
    prop = db.scalars(stmt).first()
    if prop is None:
        raise _field_error("property_id", "Property is not available for requests.")
    return prop


def _resolve_asset(db: Session, ctx: Ctx, prop: Property, asset_id: uuid.UUID) -> Asset:
    asset = db.scalars(
        select(Asset).where(
            Asset.organization_id == ctx.org_id,
            Asset.id == asset_id,
            Asset.property_id == prop.id,
            Asset.status != AssetStatus.RETIRED,
        )
    ).first()
    if asset is None:
        raise _field_error("asset_id", "Asset is not available at the selected property.")
    return asset


def _resolve_category(db: Session, ctx: Ctx, category_id: uuid.UUID) -> ServiceCategory:
    cat = db.scalars(
        select(ServiceCategory).where(
            ServiceCategory.organization_id == ctx.org_id,
            ServiceCategory.id == category_id,
            ServiceCategory.is_enabled.is_(True),
        )
    ).first()
    if cat is None:
        raise _field_error("category_id", "Category is not available.")
    return cat


def create_request(db: Session, ctx: Ctx, data: dict[str, Any]) -> ServiceRequest:
    if ctx.role == R.TECHNICIAN:
        raise Forbidden("Technicians cannot create requests.")
    try:
        req = _create(db, ctx, data)
        db.commit()
        return req
    except BaseException:
        db.rollback()
        raise


def _create(db: Session, ctx: Ctx, data: dict[str, Any]) -> ServiceRequest:
    prop = _resolve_property(db, ctx, data["property_id"])
    asset = _resolve_asset(db, ctx, prop, data["asset_id"]) if data.get("asset_id") else None
    cat = _resolve_category(db, ctx, data["category_id"])

    requester_id: uuid.UUID | None
    on_behalf = data.get("requester_membership_id")
    if ctx.role == R.REQUESTER:
        if on_behalf not in (None, ctx.membership_id):
            raise _field_error("requester_membership_id", "Not allowed.")
        requester_id = ctx.membership_id
    elif on_behalf is not None:
        ok = db.scalar(
            select(Membership.id).where(
                Membership.organization_id == ctx.org_id,
                Membership.id == on_behalf,
                Membership.role == R.REQUESTER,
                Membership.is_active.is_(True),
            )
        )
        if ok is None:
            raise _field_error("requester_membership_id", "Not an active requester in this org.")
        requester_id = on_behalf
    else:
        requester_id = None

    number = db.execute(
        text(
            "UPDATE organizations SET request_seq = request_seq + 1 "
            "WHERE id = :org RETURNING request_seq"
        ),
        {"org": ctx.org_id},
    ).scalar_one()
    req = ServiceRequest(
        organization_id=ctx.org_id,
        number=number,
        requester_membership_id=requester_id,
        created_by_membership_id=ctx.membership_id,
        property_id=prop.id,
        asset_id=asset.id if asset else None,
        category_id=cat.id,
        title=data["title"],
        description=data["description"],
        priority=data.get("priority") or Priority.NORMAL,
        status=RequestStatus.SUBMITTED,
        preferred_window_start=data.get("preferred_window_start"),
        preferred_window_end=data.get("preferred_window_end"),
    )
    db.add(req)
    db.flush()
    snapshot = {
        "number": number,
        "title": req.title,
        "property_id": prop.id,
        "asset_id": req.asset_id,
        "category_id": cat.id,
        "priority": req.priority.value,
        "requester_membership_id": requester_id,
    }
    add_event(db, ctx, req, "REQUEST_CREATED", to_status=req.status.value, data={"number": number})
    record_audit(db, ctx, "request.create", "service_request", req.id, after=snapshot)
    return req


# ---- update ----------------------------------------------------------------------------
def update_request(
    db: Session, ctx: Ctx, request_id: uuid.UUID, data: dict[str, Any]
) -> ServiceRequest:
    try:
        req = _update(db, ctx, request_id, data)
        db.commit()
        return req
    except BaseException:
        db.rollback()
        raise


def _update(db: Session, ctx: Ctx, request_id: uuid.UUID, data: dict[str, Any]) -> ServiceRequest:
    req = get_visible_request(db, ctx, request_id, lock=True)
    text_fields = {"title", "description", "preferred_window_start", "preferred_window_end"}
    triage_fields = {"priority", "category_id"}
    sent = set(data) - {"reason"}
    if is_owner_requester(ctx, req):
        if sent & triage_fields:
            raise Forbidden("Requesters cannot change priority or category.")
        if req.status != RequestStatus.SUBMITTED:
            raise Conflict(
                "Requests can only be edited while they are still submitted.",
                {"status": req.status.value},
            )
        _apply_text_edit(db, ctx, req, {k: data[k] for k in sent & text_fields})
    elif is_staff(ctx):
        if sent & text_fields:
            raise Forbidden("Only the requester can edit request details.")
        if req.status in TERMINAL:
            raise Conflict("Closed or canceled requests cannot be changed.")
        _apply_triage_edit(db, ctx, req, data)
    else:
        raise Forbidden("You cannot edit this request.")
    db.flush()
    return req


def _apply_text_edit(db: Session, ctx: Ctx, req: ServiceRequest, changes: dict[str, Any]) -> None:
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for k, v in changes.items():
        if getattr(req, k) != v:
            before[k] = getattr(req, k)
            after[k] = v
            setattr(req, k, v)
    start, end = req.preferred_window_start, req.preferred_window_end
    if (start is None) != (end is None) or (start and end and end <= start):
        raise _field_error(
            "preferred_window_start", "Preferred window needs a valid start and end."
        )
    if after:
        add_event(db, ctx, req, "REQUEST_UPDATED", data={"fields": sorted(after)})
        record_audit(db, ctx, "request.update", "service_request", req.id, before, after)


def _apply_triage_edit(db: Session, ctx: Ctx, req: ServiceRequest, data: dict[str, Any]) -> None:
    changes: list[tuple[str, str, Any, Any]] = []
    if "priority" in data and data["priority"] is not None and data["priority"] != req.priority:
        changes.append(("PRIORITY_CHANGED", "priority", req.priority.value, data["priority"].value))
    new_cat = data.get("category_id")
    if new_cat is not None and new_cat != req.category_id:
        _resolve_category(db, ctx, new_cat)
        changes.append(("CATEGORY_CHANGED", "category_id", req.category_id, new_cat))
    if not changes:
        return
    reason = (data.get("reason") or "").strip()
    if not reason:
        raise _field_error("reason", "A reason (5-500 characters) is required for this change.")
    for event_type, col, old, new in changes:
        setattr(req, col, Priority(new) if col == "priority" else new)
        add_event(db, ctx, req, event_type, data={"from": old, "to": new, "reason": reason})
        record_audit(
            db,
            ctx,
            f"request.{col.removesuffix('_id')}_change",
            "service_request",
            req.id,
            before={col: old},
            after={col: new, "reason": reason},
        )


def link_duplicate(
    db: Session, ctx: Ctx, request_id: uuid.UUID, duplicate_of_id: uuid.UUID, reason: str
) -> ServiceRequest:
    if not is_staff(ctx):
        raise Forbidden("Only dispatchers and admins can link related requests.")
    try:
        req = get_visible_request(db, ctx, request_id, lock=True)
        if duplicate_of_id == req.id:
            raise _field_error("duplicate_of_id", "A request cannot be related to itself.")
        other = db.scalars(
            select(ServiceRequest).where(
                ServiceRequest.organization_id == ctx.org_id, ServiceRequest.id == duplicate_of_id
            )
        ).first()
        if other is None:
            raise _field_error("duplicate_of_id", "Related request not found.")
        if other.duplicate_of_id == req.id:
            raise _field_error("duplicate_of_id", "That request is already linked to this one.")
        if req.status in TERMINAL:
            raise Conflict("Closed or canceled requests cannot be changed.")
        before = {"duplicate_of_id": req.duplicate_of_id}
        req.duplicate_of_id = other.id
        db.flush()
        add_event(
            db,
            ctx,
            req,
            "DUPLICATE_LINKED",
            data={
                "duplicate_of_id": other.id,
                "duplicate_of_number": other.number,
                "reason": reason,
            },
        )
        record_audit(
            db,
            ctx,
            "request.duplicate_link",
            "service_request",
            req.id,
            before,
            {"duplicate_of_id": other.id, "reason": reason},
        )
        db.commit()
        return req
    except BaseException:
        db.rollback()
        raise


# ---- list ------------------------------------------------------------------------------
def list_requests(
    db: Session,
    ctx: Ctx,
    params: PageParams,
    *,
    statuses: list[RequestStatus],
    priorities: list[Priority],
    category_id: uuid.UUID | None,
    property_id: uuid.UUID | None,
    asset_id: uuid.UUID | None,
    q: str | None,
    created_from: datetime | None,
    created_to: datetime | None,
    sort: str,
) -> tuple[list[RequestListItem], int]:
    # TODO(Phase 2b/3): technician, SLA state filters and the "due" sort need assignments/SLA.
    stmt = _list_base(ctx)
    if statuses:
        stmt = stmt.where(ServiceRequest.status.in_(statuses))
    if priorities:
        stmt = stmt.where(ServiceRequest.priority.in_(priorities))
    if category_id:
        stmt = stmt.where(ServiceRequest.category_id == category_id)
    if property_id:
        stmt = stmt.where(ServiceRequest.property_id == property_id)
    if asset_id:
        stmt = stmt.where(ServiceRequest.asset_id == asset_id)
    if created_from:
        stmt = stmt.where(ServiceRequest.created_at >= created_from)
    if created_to:
        stmt = stmt.where(ServiceRequest.created_at <= created_to)
    if q and q.strip():
        m = NUMBER_RE.match(q.strip())
        if m:
            stmt = stmt.where(ServiceRequest.number == int(m.group(1)))
        else:
            pat = like_pattern(q)
            stmt = stmt.where(
                or_(
                    ServiceRequest.title.ilike(pat, escape="\\"),
                    Property.name.ilike(pat, escape="\\"),
                    Property.address.ilike(pat, escape="\\"),
                )
            )
    order = {
        "newest": (ServiceRequest.created_at.desc(), ServiceRequest.id),
        "oldest": (ServiceRequest.created_at.asc(), ServiceRequest.id),
        "priority": (PRIORITY_RANK, ServiceRequest.created_at.desc(), ServiceRequest.id),
    }[sort]
    rows, total = paginate_rows(db, stmt.order_by(*order), params)
    return [_list_item(*r) for r in rows], total


def _list_base(ctx: Ctx) -> Any:
    return (
        select(ServiceRequest, Property, ServiceCategory, Asset, User.full_name)
        .join(
            Property,
            (Property.organization_id == ServiceRequest.organization_id)
            & (Property.id == ServiceRequest.property_id),
        )
        .join(
            ServiceCategory,
            (ServiceCategory.organization_id == ServiceRequest.organization_id)
            & (ServiceCategory.id == ServiceRequest.category_id),
        )
        .outerjoin(
            Asset,
            (Asset.organization_id == ServiceRequest.organization_id)
            & (Asset.id == ServiceRequest.asset_id),
        )
        .outerjoin(
            Membership,
            (Membership.organization_id == ServiceRequest.organization_id)
            & (Membership.id == ServiceRequest.requester_membership_id),
        )
        .outerjoin(User, User.id == Membership.user_id)
        .where(_visible_clause(ctx))
    )


def _visible_clause(ctx: Ctx) -> Any:
    return ServiceRequest.id.in_(visible_requests_stmt(ctx).with_only_columns(ServiceRequest.id))


def _list_item(
    req: ServiceRequest,
    prop: Property,
    cat: ServiceCategory,
    asset: Asset | None,
    requester_name: str | None,
) -> RequestListItem:
    return RequestListItem(
        id=req.id,
        number=req.number,
        display_id=display_id(req.number),
        title=req.title,
        status=req.status,
        priority=req.priority,
        category=CategoryBrief.model_validate(cat),
        property=PropertyBrief.model_validate(prop),
        asset=AssetBrief.model_validate(asset) if asset else None,
        requester=(
            PersonBrief(membership_id=req.requester_membership_id, name=requester_name or "")
            if req.requester_membership_id
            else None
        ),
        created_at=req.created_at,
        updated_at=req.updated_at,
    )


# ---- detail ----------------------------------------------------------------------------
def _names(db: Session, ctx: Ctx, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    rows = db.execute(
        select(Membership.id, User.full_name)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == ctx.org_id, Membership.id.in_(ids))
    ).all()
    return {r[0]: r[1] for r in rows}


def _person(names: dict[uuid.UUID, str], mid: uuid.UUID | None) -> PersonBrief | None:
    return PersonBrief(membership_id=mid, name=names.get(mid, "")) if mid else None


def file_out(f: EvidenceFile) -> FileOut:
    return FileOut(
        id=f.id,
        purpose=f.purpose,
        note_id=f.note_id,
        original_filename=f.original_filename,
        mime_type=f.mime_type,
        size_bytes=f.size_bytes,
        width=f.width,
        height=f.height,
        uploaded_by_membership_id=f.uploaded_by_membership_id,
        created_at=f.created_at,
        url=f"/api/v1/files/{f.id}",
    )


def visible_files(db: Session, ctx: Ctx, request_id: uuid.UUID) -> list[EvidenceFile]:
    return list(
        db.scalars(
            select(EvidenceFile)
            .where(EvidenceFile.request_id == request_id, visible_files_clause(ctx))
            .order_by(EvidenceFile.created_at, EvidenceFile.id)
        )
    )


def build_notes(
    db: Session, ctx: Ctx, notes: list[WorkNote], files: list[EvidenceFile]
) -> list[NoteOut]:
    names = _names(db, ctx, {n.author_membership_id for n in notes})
    by_note: dict[uuid.UUID, list[FileOut]] = {}
    for f in files:
        if f.note_id:
            by_note.setdefault(f.note_id, []).append(file_out(f))
    return [
        NoteOut(
            id=n.id,
            request_id=n.request_id,
            author=_person(names, n.author_membership_id),
            visibility=n.visibility,
            kind=n.kind,
            body=n.body,
            created_at=n.created_at,
            attachments=by_note.get(n.id, []),
        )
        for n in notes
    ]


def timeline_stmt(ctx: Ctx, request_id: uuid.UUID) -> Select[Any]:
    stmt = select(RequestEvent).where(
        RequestEvent.organization_id == ctx.org_id, RequestEvent.request_id == request_id
    )
    if ctx.role == R.REQUESTER:
        stmt = stmt.where(
            RequestEvent.type.notin_(STAFF_ONLY_EVENTS),
            # internal notes / not-yet-public files never show up for requesters
            or_(
                RequestEvent.type.notin_(["NOTE_ADDED", "FILE_UPLOADED"]),
                RequestEvent.data["visibility"].astext == "PUBLIC",
                RequestEvent.actor_membership_id == ctx.membership_id,
                RequestEvent.data["purpose"].astext.in_(["INTAKE", "COMPLETION"]),
            ),
        )
    return stmt.order_by(RequestEvent.created_at, RequestEvent.id)


def build_timeline(db: Session, ctx: Ctx, events: list[RequestEvent]) -> list[TimelineItem]:
    names = _names(db, ctx, {e.actor_membership_id for e in events if e.actor_membership_id})
    items = []
    for e in events:
        data = dict(e.data) if e.data else None
        if data and ctx.role == R.REQUESTER and data.get("note_visibility") == "INTERNAL":
            data.pop("note_id", None)
        items.append(
            TimelineItem(
                id=e.id,
                type=e.type,
                label=EVENT_LABELS.get(e.type, e.type),
                actor=_person(names, e.actor_membership_id),
                from_status=e.from_status,
                to_status=e.to_status,
                data=data,
                created_at=e.created_at,
            )
        )
    return items


def list_timeline(
    db: Session, ctx: Ctx, request_id: uuid.UUID, params: PageParams
) -> tuple[list[TimelineItem], int]:
    get_visible_request(db, ctx, request_id)
    rows, total = paginate_rows(db, timeline_stmt(ctx, request_id), params)
    return build_timeline(db, ctx, [r[0] for r in rows]), total


def get_detail(db: Session, ctx: Ctx, request_id: uuid.UUID) -> RequestDetail:
    from app.models.identity import Organization
    from app.services.notes import notes_stmt

    req = get_visible_request(db, ctx, request_id)
    prop = db.get(Property, req.property_id)
    cat = db.get(ServiceCategory, req.category_id)
    if prop is None or cat is None:  # impossible given composite FKs
        raise NotFound("Request not found.")
    asset = db.get(Asset, req.asset_id) if req.asset_id else None
    org = db.get(Organization, ctx.org_id)
    if org is None:
        raise NotFound("Request not found.")
    dup = None
    if req.duplicate_of_id:
        d = db.get(ServiceRequest, req.duplicate_of_id)
        if d is not None and d.organization_id == ctx.org_id:
            dup = DuplicateBrief(
                id=d.id, number=d.number, display_id=display_id(d.number), title=d.title
            )
    files = visible_files(db, ctx, req.id)
    notes = list(db.scalars(notes_stmt(ctx, req.id).order_by(WorkNote.created_at, WorkNote.id)))
    events = list(db.scalars(timeline_stmt(ctx, req.id)))
    names = _names(
        db, ctx, {i for i in (req.requester_membership_id, req.created_by_membership_id) if i}
    )
    base = _list_item(
        req,
        prop,
        cat,
        asset,
        names.get(req.requester_membership_id) if req.requester_membership_id else None,
    )
    return RequestDetail(
        **base.model_dump(),
        description=req.description,
        organization=OrgRef(id=org.id, name=org.name),
        created_by=_person(names, req.created_by_membership_id),
        preferred_window_start=req.preferred_window_start,
        preferred_window_end=req.preferred_window_end,
        duplicate_of=dup,
        status_changed_at=req.status_changed_at,
        completed_at=req.completed_at,
        closed_at=req.closed_at,
        canceled_at=req.canceled_at,
        notes=build_notes(db, ctx, notes, files),
        files=[file_out(f) for f in files],
        timeline=build_timeline(db, ctx, events),
        allowed_actions=lifecycle.allowed_actions(db, ctx, req),
    )
