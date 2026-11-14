"""Live updates over Server-Sent Events (API-06, WEB-08, SEC-07).

Architecture
------------
* Writers call ``app.core.events.publish`` INSIDE their DB transaction (``pg_notify``), so a
  NOTIFY exists only if the change committed.
* Every worker process keeps ONE ``LISTEN fixflow_events`` connection (``run_listener``,
  started from the app lifespan, reconnecting with exponential backoff) and fans the events out
  to its own in-process subscribers (``Hub``). Postgres is the only cross-worker channel, so any
  worker can serve any stream.
* Clients obtain a 60 s ticket (``POST /stream/ticket``, Bearer + X-Org-Id) and open
  ``GET /stream?ticket=...`` (EventSource cannot send headers). A ticket may be reused until it
  expires so the browser's automatic reconnect works; after that, fetch a new ticket.

Protocol: first ``event: ready`` (``{membership_id, org_id}``); then ``event: <kind>`` with a
monotonic ``id`` and a tiny JSON body (``kind``, ``request_id``, ``notification_id``, ``at``)
that never contains request content; ``: ping`` comments every ``STREAM_HEARTBEAT_SECONDS``;
``event: resync`` after the server's listener reconnected (events may have been missed);
``event: closed`` right before the server ends the stream (revoked session/membership, slow
consumer). Session and membership are re-validated every ``STREAM_REVALIDATE_SECONDS``.
Delivery is a hint, not a log: clients MUST refetch canonical state on every (re)connect and
on ``resync``, and treat events only as "something changed, invalidate".
"""

import asyncio
import contextlib
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core import events as live
from app.core.config import get_settings
from app.core.security import hash_token, new_token
from app.core.tenancy import Ctx
from app.db.session import SessionLocal, get_engine
from app.models.enums import MembershipRole
from app.models.feedback import StreamTicket
from app.models.identity import Membership, Organization, User
from app.models.identity import Session as AuthSession

logger = logging.getLogger("app.stream")
R = MembershipRole
STAFF = frozenset({R.ADMIN, R.DISPATCHER})
# Only these keys ever reach a client.
CLIENT_KEYS = ("kind", "request_id", "notification_id", "at")


# ---- tickets ---------------------------------------------------------------------------
def issue_ticket(db: Session, ctx: Ctx, session_id: uuid.UUID) -> tuple[str, datetime]:
    ttl = get_settings().STREAM_TICKET_TTL_SECONDS
    now = datetime.now(UTC)
    token = new_token()
    expires = now + timedelta(seconds=ttl)
    db.add(
        StreamTicket(
            token_hash=hash_token(token),
            user_id=ctx.user_id,
            session_id=session_id,
            membership_id=ctx.membership_id,
            organization_id=ctx.org_id,
            expires_at=expires,
        )
    )
    # Housekeeping: tickets are useless the moment they expire.
    db.execute(delete(StreamTicket).where(StreamTicket.expires_at < now - timedelta(hours=1)))
    db.commit()
    return token, expires


@dataclass(frozen=True)
class Identity:
    user_id: uuid.UUID
    session_id: uuid.UUID
    membership_id: uuid.UUID
    org_id: uuid.UUID
    role: MembershipRole


def _identity_of(
    db: Session,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    membership_id: uuid.UUID,
    org_id: uuid.UUID,
) -> Identity | None:
    """Current identity if the session, user, org and membership are all still valid."""
    now = datetime.now(UTC)
    sess = db.get(AuthSession, session_id)
    if sess is None or sess.revoked_at is not None or sess.expires_at <= now:
        return None
    user = db.get(User, user_id)
    if user is None or not user.is_active or sess.user_id != user_id:
        return None
    row = db.execute(
        select(Membership.role)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(
            Membership.id == membership_id,
            Membership.organization_id == org_id,
            Membership.user_id == user_id,
            Membership.is_active.is_(True),
            Organization.is_active.is_(True),
        )
    ).first()
    if row is None:
        return None
    return Identity(user_id, session_id, membership_id, org_id, row[0])


def validate_ticket(token: str) -> Identity | None:
    """Sync (run in a worker thread): the identity behind an unexpired ticket, else None."""
    with SessionLocal() as db:
        t = db.scalars(
            select(StreamTicket).where(StreamTicket.token_hash == hash_token(token))
        ).first()
        if t is None or t.expires_at <= datetime.now(UTC):
            return None
        return _identity_of(db, t.user_id, t.session_id, t.membership_id, t.organization_id)


def revalidate(identity: Identity) -> Identity | None:
    """Sync (run in a worker thread): re-check session + membership; None when revoked."""
    with SessionLocal() as db:
        return _identity_of(
            db, identity.user_id, identity.session_id, identity.membership_id, identity.org_id
        )


# ---- in-process fan-out ----------------------------------------------------------------
@dataclass(eq=False)
class Subscriber:
    org_id: uuid.UUID
    membership_id: uuid.UUID
    role: MembershipRole
    queue: asyncio.Queue[tuple[str, dict[str, Any]] | None] = field(
        default_factory=lambda: asyncio.Queue(maxsize=get_settings().STREAM_QUEUE_SIZE)
    )
    dropped: bool = False


def matches(sub: Subscriber, event: dict[str, Any]) -> bool:
    """May ``sub`` see ``event``? (never crosses organizations)"""
    if event.get("org_id") != str(sub.org_id):
        return False
    kind = event.get("kind")
    me = str(sub.membership_id)
    if kind == live.NOTIFICATION_CREATED:  # personal: only the recipient, whatever the role
        return event.get("recipient_membership_id") == me
    if kind not in (live.REQUEST_CHANGED, live.ASSIGNMENT_CHANGED):
        return False
    if sub.role in STAFF:
        return True
    if sub.role == R.REQUESTER:
        return event.get("requester_membership_id") == me
    if sub.role == R.TECHNICIAN:
        return me in (event.get("technician_membership_ids") or [])
    return False


def client_view(event: dict[str, Any]) -> dict[str, Any]:
    return {k: event[k] for k in CLIENT_KEYS if k in event}


class Hub:
    def __init__(self) -> None:
        self._subs: set[Subscriber] = set()

    def __len__(self) -> int:
        return len(self._subs)

    def subscribe(self, identity: Identity) -> Subscriber:
        sub = Subscriber(identity.org_id, identity.membership_id, identity.role)
        self._subs.add(sub)
        return sub

    def unsubscribe(self, sub: Subscriber) -> None:
        self._subs.discard(sub)

    def _deliver(self, sub: Subscriber, item: tuple[str, dict[str, Any]]) -> None:
        try:
            sub.queue.put_nowait(item)
        except asyncio.QueueFull:
            # Slow consumer: drop it rather than grow without bound (it reconnects + refetches).
            sub.dropped = True
            self._subs.discard(sub)
            while not sub.queue.empty():
                sub.queue.get_nowait()
            sub.queue.put_nowait(None)

    def dispatch(self, event: dict[str, Any]) -> int:
        n = 0
        for sub in list(self._subs):
            if matches(sub, event):
                self._deliver(sub, (str(event.get("kind")), client_view(event)))
                n += 1
        return n

    def resync_all(self) -> None:
        for sub in list(self._subs):
            self._deliver(sub, ("resync", {"reason": "listener_reconnected"}))


# ---- LISTEN connection (one per worker) --------------------------------------------------
def listener_dsn() -> str:
    return get_engine().url.set(drivername="postgresql").render_as_string(hide_password=False)


async def run_listener(hub: Hub, dsn: str | None = None, *, max_backoff: float = 30.0) -> None:
    """Forever: LISTEN and dispatch; on any connection failure back off and reconnect."""
    backoff = 0.5
    first = True
    while True:
        try:
            conninfo = dsn or listener_dsn()
            async with await psycopg.AsyncConnection.connect(
                conninfo,
                autocommit=True,
                connect_timeout=5,
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=3,
            ) as conn:
                await conn.execute(f"LISTEN {live.CHANNEL}")
                backoff = 0.5
                if not first:
                    hub.resync_all()  # events may have been lost while we were away
                first = False
                logger.info("stream listener connected")
                async for notify in conn.notifies():
                    try:
                        event = json.loads(notify.payload)
                    except ValueError:
                        continue
                    if isinstance(event, dict):
                        hub.dispatch(event)
            logger.warning("stream listener connection ended; reconnecting")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("stream listener error (%s); retrying in %.1fs", exc, backoff)
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, max_backoff)


class ListenerHandle:
    """Owns the background listener task (created by the app lifespan)."""

    def __init__(self, hub: Hub) -> None:
        self.hub = hub
        self.task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self.task = asyncio.create_task(run_listener(self.hub), name="fixflow-stream-listener")

    async def stop(self) -> None:
        if self.task is not None:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self.task


# ---- the stream ------------------------------------------------------------------------
_last_id = 0


def next_event_id() -> int:
    """Monotonic per process (microsecond clock, bumped on ties)."""
    global _last_id
    _last_id = max(_last_id + 1, time.time_ns() // 1000)
    return _last_id


def format_event(event: str, data: dict[str, Any], event_id: int | None = None) -> str:
    out = f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n"
    if event_id is not None:
        out += f"id: {event_id}\n"
    return out + "\n"


async def event_stream(hub: Hub, identity: Identity) -> AsyncIterator[str]:
    from starlette.concurrency import run_in_threadpool

    settings = get_settings()
    sub = hub.subscribe(identity)
    try:
        yield format_event(
            "ready",
            {"membership_id": str(identity.membership_id), "org_id": str(identity.org_id)},
        )
        loop = asyncio.get_running_loop()
        next_ping = loop.time() + settings.STREAM_HEARTBEAT_SECONDS
        next_check = loop.time() + settings.STREAM_REVALIDATE_SECONDS
        while True:
            now = loop.time()
            if now >= next_check:
                next_check = now + settings.STREAM_REVALIDATE_SECONDS
                try:
                    current = await run_in_threadpool(revalidate, identity)
                except Exception as exc:  # DB down: keep the stream (heartbeats) until it is back
                    logger.warning("stream revalidation skipped: %s", exc)
                else:
                    if current is None:
                        yield format_event("closed", {"reason": "session_revoked"})
                        return
                    sub.role = current.role
            if now >= next_ping:
                next_ping = now + settings.STREAM_HEARTBEAT_SECONDS
                yield ": ping\n\n"
            wait = max(0.0, min(next_ping, next_check) - loop.time())
            try:
                item = await asyncio.wait_for(sub.queue.get(), timeout=wait)
            except TimeoutError:
                continue
            if item is None:
                yield format_event("closed", {"reason": "slow_consumer"})
                return
            kind, data = item
            yield format_event(kind, data, next_event_id())
    finally:
        hub.unsubscribe(sub)
