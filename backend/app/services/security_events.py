import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.audit import sanitize
from app.models.identity import SecurityEvent


def record_security_event(
    db: Session,
    event_type: str,
    *,
    user_id: uuid.UUID | None = None,
    email_hash: str | None = None,
    ip: str | None = None,
    details: dict[str, Any] | None = None,
) -> SecurityEvent:
    """Never pass passwords, tokens or raw emails in ``details`` (secret keys are stripped)."""
    ev = SecurityEvent(
        event_type=event_type,
        user_id=user_id,
        email_hash=email_hash,
        ip=ip,
        details=sanitize(details) if details is not None else None,
    )
    db.add(ev)
    db.flush()
    return ev
