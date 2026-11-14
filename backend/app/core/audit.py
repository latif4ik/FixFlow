"""Audit trail writer. Always call inside the same transaction as the change."""

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from app.core.tenancy import Ctx
from app.models.audit import AuditEvent

SECRET_KEYS = frozenset(
    {"password", "password_hash", "token", "token_hash", "secret", "authorization", "api_key"}
)


def sanitize(value: Any) -> Any:
    """JSON-safe copy of ``value`` with secret-looking keys removed."""
    if isinstance(value, dict):
        return {str(k): sanitize(v) for k, v in value.items() if str(k).lower() not in SECRET_KEYS}
    if isinstance(value, list | tuple | set | frozenset):
        return [sanitize(v) for v in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, uuid.UUID | Decimal):
        return str(value)
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    return value


def record_audit(
    db: Session,
    ctx: Ctx,
    action: str,
    target_type: str,
    target_id: uuid.UUID | None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        organization_id=ctx.org_id,
        actor_membership_id=ctx.membership_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        before=sanitize(before) if before is not None else None,
        after=sanitize(after) if after is not None else None,
    )
    db.add(event)
    db.flush()
    return event
