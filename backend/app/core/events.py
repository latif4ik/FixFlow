"""Transactional publishing of live-update events (API-06).

``publish`` runs ``SELECT pg_notify('fixflow_events', payload)`` on the CALLER's session, so
PostgreSQL delivers the NOTIFY only if (and when) the surrounding transaction commits, and
silently drops it on rollback (also on rollback to a savepoint). That gives "publish after
commit" without any outbox. Payloads never carry request content: clients refetch.
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

CHANNEL = "fixflow_events"
MAX_PAYLOAD_BYTES = 7500  # NOTIFY limit is 8000 bytes

REQUEST_CHANGED = "request.changed"
NOTIFICATION_CREATED = "notification.created"
ASSIGNMENT_CHANGED = "assignment.changed"
KINDS = frozenset({REQUEST_CHANGED, NOTIFICATION_CREATED, ASSIGNMENT_CHANGED})


def _jsonable(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list | tuple | set | frozenset):
        return [_jsonable(v) for v in value]
    return value


def build_payload(event: dict[str, Any]) -> str:
    data = {k: _jsonable(v) for k, v in event.items() if v is not None}
    data.setdefault("at", datetime.now(UTC).isoformat())
    payload = json.dumps(data, separators=(",", ":"))
    if len(payload.encode()) > MAX_PAYLOAD_BYTES:
        # Never exceed the NOTIFY limit: drop the (optional) technician list; clients refetch.
        data.pop("technician_membership_ids", None)
        data["truncated"] = True
        payload = json.dumps(data, separators=(",", ":"))
    return payload


def publish(db: Session, event: dict[str, Any]) -> None:
    """Queue ``event`` (needs ``org_id`` and ``kind``) for delivery at commit time."""
    if "org_id" not in event or event.get("kind") not in KINDS:
        raise ValueError("event needs org_id and a known kind")
    db.execute(
        text("SELECT pg_notify(:channel, :payload)"),
        {"channel": CHANNEL, "payload": build_payload(event)},
    )
