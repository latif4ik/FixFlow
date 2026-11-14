"""Helpers for SLA / maintenance tests: patched clock and event-time rewriting."""

import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core import clock
from app.models import RequestEvent, ServiceRequest
from app.sla.service import recompute_sla

TZ = ZoneInfo("Asia/Bishkek")


def at(d: int, hh: int = 0, mm: int = 0, month: int = 11, year: int = 2026) -> datetime:
    """Local (Bishkek) instant as UTC; 2026-11-13 is a Friday, 2026-11-16 a Monday."""
    return datetime(year, month, d, hh, mm, tzinfo=TZ).astimezone(UTC)


def set_now(monkeypatch, t: datetime) -> None:
    monkeypatch.setattr(clock, "now", lambda: t)


def load(db: Session, request_id) -> ServiceRequest:
    rid = uuid.UUID(str(request_id))
    return db.scalars(
        select(ServiceRequest)
        .where(ServiceRequest.id == rid)
        .execution_options(populate_existing=True)
    ).one()


def _update_events(db: Session, where: str, params: dict) -> None:
    """request_events is append-only (trigger); tests need to place events at chosen instants."""
    trg = "trg_request_events_immutable"
    db.execute(text(f"ALTER TABLE request_events DISABLE TRIGGER {trg}"))
    db.execute(text(f"UPDATE request_events SET created_at = :t WHERE {where}"), params)
    db.execute(text(f"ALTER TABLE request_events ENABLE TRIGGER {trg}"))
    db.commit()
    db.expire_all()  # the session keeps no stale event rows


def set_event_time(
    db: Session, request_id, type_: str, t: datetime, nth: int = -1, to_status: str | None = None
) -> None:
    """Move one event of ``type_`` (the last by default) to ``t``, then re-derive the SLA cache."""
    rid = uuid.UUID(str(request_id))
    stmt = select(RequestEvent).where(RequestEvent.request_id == rid, RequestEvent.type == type_)
    if to_status is not None:
        stmt = stmt.where(RequestEvent.to_status == to_status)
    evs = list(db.scalars(stmt.order_by(RequestEvent.created_at, RequestEvent.id)))
    _update_events(db, "id = :i", {"t": t, "i": evs[nth].id})
    recompute_sla(db, load(db, rid))
    db.commit()


def backdate(db: Session, request_id, created: datetime) -> ServiceRequest:
    """Pretend the request was created at ``created`` (all events shift to that origin)."""
    rid = uuid.UUID(str(request_id))
    _update_events(db, "request_id = :r", {"t": created, "r": rid})
    req = load(db, rid)
    recompute_sla(db, req)
    db.commit()
    return req
