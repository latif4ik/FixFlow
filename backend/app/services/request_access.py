"""Request visibility + the Phase 2b/3 hooks (assignment lookup, materials validation).

Everything that decides "can this caller see / act on this request" lives here so the
list, detail, notes, files and lifecycle code share one definition.
"""

import uuid
from typing import Any

from sqlalchemy import Select, false, select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.core.tenancy import Ctx
from app.models.enums import MembershipRole
from app.models.requests import ServiceRequest

R = MembershipRole


# ---- hooks filled in by later phases ---------------------------------------------------
def get_active_assignment(db: Session, request: ServiceRequest) -> Any | None:
    """HOOK (Phase 2b): the active assignment of ``request`` or None.

    The returned object must expose ``technician_membership_id``. Until assignments
    exist nobody is "the assigned technician", so technician actions are unavailable.
    """
    return None


def technician_visibility_filter(ctx: Ctx) -> Any:
    """HOOK (Phase 2b): SQL clause limiting ServiceRequest rows to a technician's own.

    Phase 2b replaces this with ``ServiceRequest.id IN (active assignments of ctx)``.
    """
    return false()


def validate_materials_for_completion(db: Session, request: ServiceRequest) -> None:
    """HOOK (Phase 3): raise a 422 AppError when recorded materials are invalid."""
    return None


# ---- visibility ------------------------------------------------------------------------
def visible_requests_stmt(ctx: Ctx) -> Select[Any]:
    """SELECT ServiceRequest limited to what ``ctx`` may see (always org-scoped)."""
    stmt = select(ServiceRequest).where(ServiceRequest.organization_id == ctx.org_id)
    if ctx.role in (R.ADMIN, R.DISPATCHER):
        return stmt
    if ctx.role == R.REQUESTER:
        return stmt.where(ServiceRequest.requester_membership_id == ctx.membership_id)
    return stmt.where(technician_visibility_filter(ctx))


def get_visible_request(
    db: Session, ctx: Ctx, request_id: uuid.UUID, *, lock: bool = False
) -> ServiceRequest:
    """Fetch a request the caller may see, else 404 (never reveals other-org/other-user rows)."""
    stmt = visible_requests_stmt(ctx).where(ServiceRequest.id == request_id)
    if lock:
        stmt = stmt.with_for_update(of=ServiceRequest).execution_options(populate_existing=True)
    req = db.scalars(stmt).first()
    if req is None:
        raise NotFound("Request not found.")
    return req


# ---- actor predicates ------------------------------------------------------------------
def is_staff(ctx: Ctx) -> bool:
    return ctx.role in (R.ADMIN, R.DISPATCHER)


def is_owner_requester(ctx: Ctx, request: ServiceRequest) -> bool:
    return ctx.role == R.REQUESTER and request.requester_membership_id == ctx.membership_id


def is_assigned_technician(db: Session, ctx: Ctx, request: ServiceRequest) -> bool:
    if ctx.role != R.TECHNICIAN:
        return False
    assignment = get_active_assignment(db, request)
    return (
        assignment is not None
        and getattr(assignment, "technician_membership_id", None) == ctx.membership_id
    )


def visible_files_clause(ctx: Ctx) -> Any:
    """Extra WHERE for EvidenceFile rows of a request the caller can already see.

    Requesters never see files tied to INTERNAL notes (or not-yet-linked staff note files).
    """
    from sqlalchemy import or_

    from app.models.enums import FilePurpose, NoteVisibility
    from app.models.requests import EvidenceFile, WorkNote

    if ctx.role != R.REQUESTER:
        return EvidenceFile.organization_id == ctx.org_id
    public_notes = select(WorkNote.id).where(
        WorkNote.organization_id == ctx.org_id, WorkNote.visibility == NoteVisibility.PUBLIC
    )
    return (EvidenceFile.organization_id == ctx.org_id) & or_(
        EvidenceFile.uploaded_by_membership_id == ctx.membership_id,
        EvidenceFile.purpose.in_([FilePurpose.INTAKE, FilePurpose.COMPLETION]),
        EvidenceFile.note_id.in_(public_notes),
    )
