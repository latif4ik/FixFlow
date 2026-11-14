"""Request lifecycle engine (LIFE-01..09): one data-driven transition table.

``transition`` locks the request row, validates the (from, to) pair against TRANSITIONS,
checks the actor, runs guards, then applies the status, a STATUS_CHANGED request_event, an
audit event and (when text is supplied) an immutable note, all in ONE transaction.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.errors import AppError, Forbidden, ValidationFailed
from app.core.tenancy import Ctx
from app.models.enums import FilePurpose, NoteKind, NoteVisibility, RequestStatus
from app.models.requests import EvidenceFile, ServiceRequest
from app.services.notes import add_note_row
from app.services.request_access import (
    get_visible_request,
    is_assigned_technician,
    is_owner_requester,
    is_staff,
    validate_materials_for_completion,
)
from app.services.request_events import add_event

S = RequestStatus
Guard = Callable[[Session, Ctx, ServiceRequest, str], None]

MIN_REASON_LEN = 5
COMPLETION_NOTE_MIN = 20


@dataclass(frozen=True)
class Rule:
    """One way an actor may perform a (from, to) transition."""

    who: str  # "staff" | "owner_requester" | "assigned_technician"
    action: str  # stable action name exposed in allowed_actions
    reason_required: bool = False
    min_text_len: int = MIN_REASON_LEN
    note_kind: NoteKind = NoteKind.GENERAL
    note_visibility: NoteVisibility = NoteVisibility.PUBLIC
    # internal rules are reserved for services (assignment flows in Phase 2b), not the
    # generic transitions endpoint.
    internal: bool = False
    guards: tuple[Guard, ...] = field(default=())


def _completion_guard(db: Session, ctx: Ctx, request: ServiceRequest, text: str) -> None:
    n = db.scalar(
        select(func.count())
        .select_from(EvidenceFile)
        .where(
            EvidenceFile.organization_id == request.organization_id,
            EvidenceFile.request_id == request.id,
            EvidenceFile.purpose == FilePurpose.COMPLETION,
        )
    )
    if not n:
        raise ValidationFailed(
            "A completion image is required.",
            [{"field": "completion_images", "message": "Upload at least one completion image."}],
        )
    validate_materials_for_completion(db, request)  # HOOK (Phase 3)


_TRIAGE_RULE = Rule(
    "staff", "triage", note_kind=NoteKind.TRIAGE, note_visibility=NoteVisibility.INTERNAL
)

TRANSITIONS: dict[tuple[RequestStatus, RequestStatus], tuple[Rule, ...]] = {
    (S.SUBMITTED, S.TRIAGED): (_TRIAGE_RULE,),
    # Phase 2b: performed by the assignment service (internal=True) after creating the assignment.
    (S.TRIAGED, S.SCHEDULED): (Rule("staff", "schedule", internal=True),),
    (S.SCHEDULED, S.ACCEPTED): (Rule("assigned_technician", "accept"),),
    (S.SCHEDULED, S.TRIAGED): (
        Rule(
            "assigned_technician",
            "decline",
            True,
            internal=True,
            note_visibility=NoteVisibility.INTERNAL,
        ),
        Rule("staff", "unassign", True, internal=True, note_visibility=NoteVisibility.INTERNAL),
    ),
    (S.ACCEPTED, S.TRIAGED): (
        Rule(
            "assigned_technician",
            "decline",
            True,
            internal=True,
            note_visibility=NoteVisibility.INTERNAL,
        ),
        Rule("staff", "unassign", True, internal=True, note_visibility=NoteVisibility.INTERNAL),
    ),
    (S.ACCEPTED, S.IN_PROGRESS): (Rule("assigned_technician", "start"),),  # Phase 3: estimate gate
    (S.IN_PROGRESS, S.BLOCKED): (
        Rule("assigned_technician", "block", True, note_kind=NoteKind.BLOCKER),
    ),
    (S.BLOCKED, S.IN_PROGRESS): (
        Rule("assigned_technician", "resume", True, note_kind=NoteKind.RESOLUTION),
    ),
    (S.IN_PROGRESS, S.COMPLETED): (
        Rule(
            "assigned_technician",
            "complete",
            True,
            COMPLETION_NOTE_MIN,
            NoteKind.COMPLETION,
            guards=(_completion_guard,),
        ),
    ),
    (S.COMPLETED, S.CLOSED): (
        Rule("owner_requester", "close", note_kind=NoteKind.CLOSE),
        Rule("staff", "close", True, note_kind=NoteKind.CLOSE),
    ),
    (S.COMPLETED, S.REOPENED): (
        Rule("owner_requester", "reopen", True, note_kind=NoteKind.REWORK),
    ),
    (S.REOPENED, S.TRIAGED): (_TRIAGE_RULE,),
    (S.SUBMITTED, S.CANCELED): (
        Rule("owner_requester", "cancel", note_kind=NoteKind.CANCEL),
        Rule("staff", "cancel", True, note_kind=NoteKind.CANCEL),
    ),
    (S.TRIAGED, S.CANCELED): (Rule("staff", "cancel", True, note_kind=NoteKind.CANCEL),),
    (S.SCHEDULED, S.CANCELED): (Rule("staff", "cancel", True, note_kind=NoteKind.CANCEL),),
}

TERMINAL = frozenset({S.CLOSED, S.CANCELED})
_STAMP = {S.COMPLETED: "completed_at", S.CLOSED: "closed_at", S.CANCELED: "canceled_at"}


def _actor_matches(db: Session, ctx: Ctx, request: ServiceRequest, who: str) -> bool:
    if who == "staff":
        return is_staff(ctx)
    if who == "owner_requester":
        return is_owner_requester(ctx, request)
    if who == "assigned_technician":
        return is_assigned_technician(db, ctx, request)
    return False


def invalid_transition(frm: RequestStatus, to: RequestStatus, why: str | None = None) -> AppError:
    return AppError(
        409,
        "invalid_transition",
        why or f"A request cannot move from {frm.value} to {to.value}.",
        {"from": frm.value, "to": to.value},
    )


def allowed_actions(db: Session, ctx: Ctx, request: ServiceRequest) -> list[str]:
    """Actions ``ctx`` may take now, from the SAME table as ``transition`` (cheap guards only)."""
    actions: list[str] = []
    for (frm, _to), rules in TRANSITIONS.items():
        if frm != request.status:
            continue
        for rule in rules:
            if not rule.internal and _actor_matches(db, ctx, request, rule.who):
                if rule.action not in actions:
                    actions.append(rule.action)
                break
    if request.status not in TERMINAL:
        actions.append("add_note")
        if is_staff(ctx):
            actions += ["edit_priority_category", "link_duplicate"]
    if is_owner_requester(ctx, request) and request.status == S.SUBMITTED:
        actions.append("edit")
    return actions


def transition(
    db: Session,
    ctx: Ctx,
    request_id: uuid.UUID,
    to_status: RequestStatus,
    *,
    reason: str | None = None,
    note_body: str | None = None,
    extra: dict[str, Any] | None = None,
    internal: bool = False,
) -> ServiceRequest:
    """Apply one lifecycle transition atomically. Commits on success, rolls back on error."""
    try:
        request = _transition(db, ctx, request_id, to_status, reason, note_body, extra, internal)
        db.commit()
        return request
    except BaseException:
        db.rollback()
        raise


def _transition(
    db: Session,
    ctx: Ctx,
    request_id: uuid.UUID,
    to: RequestStatus,
    reason: str | None,
    note_body: str | None,
    extra: dict[str, Any] | None,
    internal: bool,
) -> ServiceRequest:
    request = get_visible_request(db, ctx, request_id, lock=True)
    frm = request.status
    rules = TRANSITIONS.get((frm, to))
    if frm in TERMINAL or rules is None:
        raise invalid_transition(frm, to)
    usable = [r for r in rules if internal or not r.internal]
    if not usable:
        raise invalid_transition(
            frm, to, f"{frm.value} -> {to.value} is only performed through the assignment flow."
        )
    rule = next((r for r in usable if _actor_matches(db, ctx, request, r.who)), None)
    if rule is None:
        raise Forbidden("You are not allowed to perform this transition.")

    text = (reason or note_body or "").strip()
    field_name = "note" if rule.min_text_len == COMPLETION_NOTE_MIN else "reason"
    if rule.reason_required and len(text) < rule.min_text_len:
        raise ValidationFailed(
            "A reason is required." if field_name == "reason" else "A completion note is required.",
            [
                {
                    "field": field_name,
                    "message": f"must be at least {rule.min_text_len} characters",
                }
            ],
        )
    for guard in rule.guards:
        guard(db, ctx, request, text)

    now = datetime.now(UTC)
    note_id: uuid.UUID | None = None
    if text:
        note = add_note_row(db, ctx, request, text, rule.note_visibility, rule.note_kind)
        note_id = note.id
        if to == S.COMPLETED:
            db.execute(
                update(EvidenceFile)
                .where(
                    EvidenceFile.organization_id == request.organization_id,
                    EvidenceFile.request_id == request.id,
                    EvidenceFile.purpose == FilePurpose.COMPLETION,
                    EvidenceFile.note_id.is_(None),
                )
                .values(note_id=note.id)
            )

    request.status = to
    request.status_changed_at = now
    if (col := _STAMP.get(to)) is not None:
        setattr(request, col, now)
    db.flush()

    data: dict[str, Any] = {"action": rule.action, **(extra or {})}
    if note_id is not None:
        data.update(note_id=note_id, note_visibility=rule.note_visibility.value)
    add_event(
        db, ctx, request, "STATUS_CHANGED", from_status=frm.value, to_status=to.value, data=data
    )
    record_audit(
        db,
        ctx,
        "request.status_change",
        "service_request",
        request.id,
        before={"status": frm.value},
        after={"status": to.value, "action": rule.action, "note_id": note_id},
    )
    return request
