"""Work notes (COMMN-01/02) with idempotent creation (API-03/04). Notes are immutable."""

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import Select, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.errors import AppError, Conflict, Forbidden, ValidationFailed
from app.core.pagination import PageParams, paginate_rows
from app.core.tenancy import Ctx
from app.models.enums import FilePurpose, MembershipRole, NoteKind, NoteVisibility, RequestStatus
from app.models.requests import EvidenceFile, ServiceRequest, WorkNote
from app.services.request_access import (
    get_visible_request,
    is_assigned_technician,
    is_owner_requester,
    is_staff,
)
from app.services.request_events import add_event

TERMINAL = frozenset({RequestStatus.CLOSED, RequestStatus.CANCELED})
USER_KINDS = frozenset({NoteKind.GENERAL, NoteKind.TRIAGE})
_CLIENT_CMD_CONSTRAINT = "uq_work_notes_org_client_command"


def ensure_can_add_note(db: Session, ctx: Ctx, request: ServiceRequest) -> None:
    """Role/ownership check + terminal-state check shared by notes and NOTE file uploads."""
    if not (
        is_staff(ctx)
        or is_owner_requester(ctx, request)
        or is_assigned_technician(db, ctx, request)
    ):
        raise Forbidden("You cannot add notes to this request.")
    if request.status in TERMINAL:
        raise Conflict(
            "Notes cannot be added to a closed or canceled request.",
            {"status": request.status.value},
        )


def payload_hash(
    request_id: uuid.UUID,
    body: str,
    visibility: NoteVisibility,
    kind: NoteKind,
    attachment_ids: list[uuid.UUID],
) -> str:
    canonical = json.dumps(
        {
            "request_id": str(request_id),
            "body": body,
            "visibility": visibility.value,
            "kind": kind.value,
            "attachment_ids": sorted(str(a) for a in attachment_ids),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def add_note_row(
    db: Session,
    ctx: Ctx,
    request: ServiceRequest,
    body: str,
    visibility: NoteVisibility,
    kind: NoteKind,
    *,
    client_command_id: uuid.UUID | None = None,
    phash: str | None = None,
) -> WorkNote:
    """Insert a note + its NOTE_ADDED event + audit (no commit; caller owns the transaction)."""
    note = WorkNote(
        organization_id=request.organization_id,
        request_id=request.id,
        author_membership_id=ctx.membership_id,
        visibility=visibility,
        kind=kind,
        body=body,
        client_command_id=client_command_id,
        payload_hash=phash,
    )
    db.add(note)
    db.flush()
    add_event(
        db,
        ctx,
        request,
        "NOTE_ADDED",
        data={"note_id": note.id, "visibility": visibility.value, "kind": kind.value},
    )
    record_audit(
        db,
        ctx,
        "request.note_add",
        "service_request",
        request.id,
        after={"note_id": note.id, "visibility": visibility.value, "kind": kind.value},
    )
    return note


def _validate_attachments(
    db: Session, ctx: Ctx, request: ServiceRequest, ids: list[uuid.UUID]
) -> list[uuid.UUID]:
    unique = list(dict.fromkeys(ids))
    if not unique:
        return []
    ok = set(
        db.scalars(
            select(EvidenceFile.id).where(
                EvidenceFile.organization_id == ctx.org_id,
                EvidenceFile.request_id == request.id,
                EvidenceFile.id.in_(unique),
                EvidenceFile.uploaded_by_membership_id == ctx.membership_id,
                EvidenceFile.purpose == FilePurpose.NOTE,
                EvidenceFile.note_id.is_(None),
            )
        )
    )
    if len(ok) != len(unique):
        raise ValidationFailed(
            "Invalid attachments.",
            [
                {
                    "field": "attachment_ids",
                    "message": "Attachments must be unlinked note files you uploaded here.",
                }
            ],
        )
    return unique


def _is_constraint(exc: IntegrityError, name: str) -> bool:
    return getattr(getattr(exc.orig, "diag", None), "constraint_name", None) == name


def create_note(
    db: Session,
    ctx: Ctx,
    request_id: uuid.UUID,
    body: str,
    visibility: NoteVisibility,
    kind: NoteKind = NoteKind.GENERAL,
    client_command_id: uuid.UUID | None = None,
    attachment_ids: list[uuid.UUID] | None = None,
) -> tuple[WorkNote, bool]:
    """Returns (note, created). ``created`` is False for an identical idempotent replay."""
    request = get_visible_request(db, ctx, request_id)
    ensure_can_add_note(db, ctx, request)
    if kind not in USER_KINDS or (kind == NoteKind.TRIAGE and not is_staff(ctx)):
        raise ValidationFailed(
            "Invalid note kind.", [{"field": "kind", "message": "kind is not allowed"}]
        )
    if visibility == NoteVisibility.INTERNAL and ctx.role == MembershipRole.REQUESTER:
        raise Forbidden("Requesters can only post public notes.")
    attachments = list(dict.fromkeys(attachment_ids or []))
    phash = payload_hash(request.id, body, visibility, kind, attachments)

    if client_command_id is not None:
        existing = _find_existing(db, ctx, client_command_id)
        if existing is not None:
            return _replay(existing, ctx, phash), False

    valid_ids = _validate_attachments(db, ctx, request, attachments)
    try:
        with db.begin_nested():
            note = add_note_row(
                db,
                ctx,
                request,
                body,
                visibility,
                kind,
                client_command_id=client_command_id,
                phash=phash if client_command_id else None,
            )
            if valid_ids:
                res = db.execute(
                    update(EvidenceFile)
                    .where(
                        EvidenceFile.organization_id == ctx.org_id,
                        EvidenceFile.id.in_(valid_ids),
                        EvidenceFile.note_id.is_(None),
                    )
                    .values(note_id=note.id)
                )
                if getattr(res, "rowcount", 0) != len(valid_ids):
                    raise ValidationFailed(
                        "Invalid attachments.",
                        [{"field": "attachment_ids", "message": "attachment already linked"}],
                    )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if client_command_id is not None and _is_constraint(exc, _CLIENT_CMD_CONSTRAINT):
            existing = _find_existing(db, ctx, client_command_id)
            if existing is not None:
                return _replay(existing, ctx, phash), False
        raise
    except AppError:
        db.rollback()
        raise
    return note, True


def _find_existing(db: Session, ctx: Ctx, client_command_id: uuid.UUID) -> WorkNote | None:
    return db.scalars(
        select(WorkNote).where(
            WorkNote.organization_id == ctx.org_id,
            WorkNote.client_command_id == client_command_id,
        )
    ).first()


def _replay(existing: WorkNote, ctx: Ctx, phash: str) -> WorkNote:
    if existing.payload_hash != phash or existing.author_membership_id != ctx.membership_id:
        raise AppError(
            409,
            "idempotency_key_reused",
            "This client_command_id was already used with a different payload.",
        )
    return existing


# ---- reading ---------------------------------------------------------------------------
def notes_stmt(ctx: Ctx, request_id: uuid.UUID) -> Select[Any]:
    stmt = select(WorkNote).where(
        WorkNote.organization_id == ctx.org_id, WorkNote.request_id == request_id
    )
    if ctx.role == MembershipRole.REQUESTER:
        stmt = stmt.where(WorkNote.visibility == NoteVisibility.PUBLIC)
    return stmt


def list_notes(
    db: Session, ctx: Ctx, request_id: uuid.UUID, params: PageParams
) -> tuple[list[WorkNote], int]:
    get_visible_request(db, ctx, request_id)
    rows, total = paginate_rows(
        db, notes_stmt(ctx, request_id).order_by(WorkNote.created_at, WorkNote.id), params
    )
    return [r[0] for r in rows], total
