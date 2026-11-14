import asyncio
import json
import socket
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import uvicorn
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import events as live
from app.core.config import get_settings
from app.core.security import hash_token
from app.db.session import build_engine, set_engine
from app.main import create_app
from app.models import MembershipRole, StreamTicket
from app.models.enums import RequestStatus
from app.services import stream as svc
from tests.factories import h
from tests.req_helpers import make_world, seed_request

API = "/api/v1"
R = MembershipRole


# ---- unit: subscriber filter -----------------------------------------------------------
def sub_of(role, org=None, mid=None):
    ident = svc.Identity(uuid.uuid4(), uuid.uuid4(), mid or uuid.uuid4(), org or uuid.uuid4(), role)
    return svc.Subscriber(ident.org_id, ident.membership_id, ident.role), ident


def ev(org, kind="request.changed", **kw):
    return {"org_id": str(org), "kind": kind, **kw}


def test_filter_staff_sees_all_org_events_but_only_own_notifications():
    s, _ = sub_of(R.DISPATCHER)
    assert svc.matches(s, ev(s.org_id, requester_membership_id=str(uuid.uuid4())))
    assert svc.matches(s, ev(s.org_id, "assignment.changed"))
    assert not svc.matches(s, ev(uuid.uuid4()))  # cross org
    assert not svc.matches(s, ev(s.org_id, "notification.created", recipient_membership_id="x"))
    assert svc.matches(
        s, ev(s.org_id, "notification.created", recipient_membership_id=str(s.membership_id))
    )
    a, _ = sub_of(R.ADMIN, org=s.org_id)
    assert svc.matches(a, ev(a.org_id))


def test_filter_requester_and_technician():
    r, _ = sub_of(R.REQUESTER)
    assert svc.matches(r, ev(r.org_id, requester_membership_id=str(r.membership_id)))
    assert not svc.matches(r, ev(r.org_id, requester_membership_id=str(uuid.uuid4())))
    assert not svc.matches(r, ev(r.org_id))
    assert not svc.matches(r, ev(uuid.uuid4(), requester_membership_id=str(r.membership_id)))
    t, _ = sub_of(R.TECHNICIAN)
    assert svc.matches(t, ev(t.org_id, technician_membership_ids=[str(t.membership_id), "z"]))
    assert not svc.matches(t, ev(t.org_id, technician_membership_ids=["z"]))
    assert not svc.matches(t, ev(t.org_id))
    assert not svc.matches(
        t, ev(t.org_id, "weird.kind", technician_membership_ids=[str(t.membership_id)])
    )


def test_filter_notification_recipient_only_and_client_view_strips_ids():
    t, _ = sub_of(R.TECHNICIAN)
    e = ev(
        t.org_id,
        "notification.created",
        recipient_membership_id=str(t.membership_id),
        notification_id="n1",
        request_id="r1",
        at="now",
    )
    assert svc.matches(t, e)
    assert svc.client_view(
        {**e, "technician_membership_ids": ["a"], "requester_membership_id": "b"}
    ) == {"kind": "notification.created", "request_id": "r1", "notification_id": "n1", "at": "now"}


def test_hub_dispatch_and_slow_consumer_dropped(monkeypatch):
    monkeypatch.setattr(get_settings(), "STREAM_QUEUE_SIZE", 2)

    async def run():
        hub = svc.Hub()
        _, i1 = sub_of(R.ADMIN)
        sub = hub.subscribe(i1)
        other_org = svc.Identity(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), R.ADMIN)
        hub.subscribe(other_org)
        e = ev(i1.org_id, request_id="r")
        assert hub.dispatch(e) == 1
        assert hub.dispatch(e) == 1
        assert hub.dispatch(e) == 1  # third overflows the 2-slot queue -> dropped
        assert sub.dropped and len(hub) == 1
        assert sub.queue.get_nowait() is None

    asyncio.run(run())


def test_payload_never_exceeds_notify_limit():
    big = {
        "org_id": "o",
        "kind": "request.changed",
        "technician_membership_ids": [str(uuid.uuid4())] * 400,
    }
    p = live.build_payload(big)
    assert len(p.encode()) < 8000 and json.loads(p)["truncated"] is True


# ---- ticket endpoint ---------------------------------------------------------------------
def test_ticket_requires_auth_and_org(client, hd):
    assert client.post(f"{API}/stream/ticket").status_code == 401
    bare = {"Authorization": hd["disp"]["Authorization"]}
    assert client.post(f"{API}/stream/ticket", headers=bare).status_code == 400
    r = client.post(f"{API}/stream/ticket", headers=hd["disp"])
    assert r.status_code == 200
    assert len(r.json()["ticket"]) >= 32 and r.json()["expires_at"]


def test_ticket_stored_hashed(client, db, hd):
    t = client.post(f"{API}/stream/ticket", headers=hd["disp"]).json()["ticket"]
    rows = db.query(StreamTicket).all()
    assert len(rows) == 1 and rows[0].token_hash == hash_token(t) and t not in rows[0].token_hash
    ttl = (rows[0].expires_at - rows[0].created_at).total_seconds()
    assert 55 <= ttl <= 65


def test_invalid_and_expired_ticket_401(client, db, hd):
    assert client.get(f"{API}/stream", params={"ticket": "nope-nope-nope"}).status_code == 401
    assert client.get(f"{API}/stream").status_code == 422
    t = client.post(f"{API}/stream/ticket", headers=hd["disp"]).json()["ticket"]
    db.execute(text("UPDATE stream_tickets SET expires_at = now() - interval '1 second'"))
    db.commit()
    r = client.get(f"{API}/stream", params={"ticket": t})
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"


def test_validate_ticket_rejects_deactivated_user_and_membership(client, db, sw, hd):
    w = sw.w
    t = client.post(f"{API}/stream/ticket", headers=hd["disp"]).json()["ticket"]
    assert svc.validate_ticket(t) is not None
    db.execute(text("UPDATE memberships SET is_active=false WHERE id=:i"), {"i": w.disp[1].id})
    db.commit()
    assert svc.validate_ticket(t) is None


# ---- integration against a real uvicorn server -------------------------------------------
class Live:
    def __init__(self, base, db_engine):
        self.base = base
        self.engine = db_engine


@pytest.fixture
def live_server(migrated_db, db_engine):
    set_engine(build_engine(migrated_db))
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    server = uvicorn.Server(
        uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning")
    )
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    assert server.started
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    th.join(10)
    set_engine(None)


class Reader:
    """Reads an SSE stream in a thread, collecting (event, data) pairs and comments."""

    def __init__(self, base, ticket):
        self.events: list[tuple[str, dict]] = []
        self.comments = 0
        self.lines: list[str] = []
        self.status = None
        self.error = None
        self.ended = threading.Event()
        self._cond = threading.Condition()
        self._t = threading.Thread(target=self._run, args=(base, ticket), daemon=True)
        self._t.start()

    def _run(self, base, ticket):
        try:
            with httpx.stream(
                "GET", f"{base}{API}/stream", params={"ticket": ticket}, timeout=30
            ) as r:
                self.status = r.status_code
                ev_name = None
                for line in r.iter_lines():
                    self.lines.append(line)
                    if line.startswith(":"):
                        self.comments += 1
                    elif line.startswith("event:"):
                        ev_name = line[6:].strip()
                    elif line.startswith("data:") and ev_name:
                        with self._cond:
                            self.events.append((ev_name, json.loads(line[5:])))
                            self._cond.notify_all()
        except Exception as exc:
            self.error = exc
        finally:
            self.ended.set()
            with self._cond:
                self._cond.notify_all()

    def wait_for(self, name, timeout=8, pred=lambda d: True):
        end = time.monotonic() + timeout
        with self._cond:
            while time.monotonic() < end:
                for n, d in self.events:
                    if n == name and pred(d):
                        return d
                self._cond.wait(0.2)
        return None

    def count(self, name):
        return sum(1 for n, _ in self.events if n == name)


def _ticket(base, headers):
    r = httpx.post(f"{base}{API}/stream/ticket", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["ticket"]


def _world(db, base):
    from tests.sched_helpers import make_sched_world

    sw = make_sched_world(db)
    w = sw.w

    def hdr(m):
        r = httpx.post(
            f"{base}{API}/auth/login", json={"email": m[0].email, "password": "password123"}
        )
        return h(r.json()["token"], w.org)

    return sw, {k: hdr(getattr(w, k)) for k in ("admin", "disp", "req1", "req2", "tech")}


def test_live_stream_delivers_status_change_to_right_subscribers(live_server, db):
    base = live_server
    sw, hd = _world(db, base)
    w = sw.w
    req = seed_request(db, w, status=RequestStatus.SUBMITTED)  # owned by req1
    disp = Reader(base, _ticket(base, hd["disp"]))
    own = Reader(base, _ticket(base, hd["req1"]))
    other = Reader(base, _ticket(base, hd["req2"]))
    tech = Reader(base, _ticket(base, hd["tech"]))
    for r in (disp, own, other, tech):
        d = r.wait_for("ready")
        assert d is not None and d["org_id"] == str(w.org.id)
    assert disp.wait_for("ready")["membership_id"] == str(w.disp[1].id)
    assert disp.status == 200

    r = httpx.post(f"{base}{API}/requests/{req.id}/triage", json={}, headers=hd["disp"])
    assert r.status_code == 200, r.text
    got = disp.wait_for("request.changed", pred=lambda d: d["request_id"] == str(req.id))
    assert got is not None and set(got) <= {"kind", "request_id", "notification_id", "at"}
    assert own.wait_for("request.changed", pred=lambda d: d["request_id"] == str(req.id))
    time.sleep(1.0)
    assert other.count("request.changed") == 0  # requester of ANOTHER request
    assert tech.count("request.changed") == 0  # unassigned technician


def test_live_notification_goes_to_recipient_only(live_server, db):
    base = live_server
    sw, hd = _world(db, base)
    w = sw.w
    req = seed_request(db, w, status=RequestStatus.COMPLETED)
    admin = Reader(base, _ticket(base, hd["admin"]))
    disp = Reader(base, _ticket(base, hd["disp"]))
    req1 = Reader(base, _ticket(base, hd["req1"]))
    for r in (admin, disp, req1):
        assert r.wait_for("ready")
    r = httpx.post(
        f"{base}{API}/requests/{req.id}/feedback", json={"rating": 5}, headers=hd["req1"]
    )
    assert r.status_code == 201, r.text
    assert admin.wait_for("notification.created")
    assert disp.wait_for("notification.created")
    assert admin.wait_for("request.changed")
    time.sleep(0.8)
    assert req1.count("notification.created") == 0  # actor excluded from staff notification


def test_rolled_back_publish_delivers_nothing_commit_does(live_server, db, db_engine):
    base = live_server
    sw, hd = _world(db, base)
    w = sw.w
    disp = Reader(base, _ticket(base, hd["disp"]))
    assert disp.wait_for("ready")
    rid = uuid.uuid4()
    ev_ = {"org_id": w.org.id, "kind": "request.changed", "request_id": rid}
    with Session(db_engine) as s:
        live.publish(s, ev_)
        s.rollback()
    time.sleep(1.0)
    assert disp.count("request.changed") == 0
    with Session(db_engine) as s:
        live.publish(s, ev_)
        s.commit()
    assert disp.wait_for("request.changed", pred=lambda d: d["request_id"] == str(rid))


def test_cross_org_events_never_delivered(live_server, db, db_engine):
    base = live_server
    _, hd = _world(db, base)
    other = make_world(db, "Other Org")
    disp = Reader(base, _ticket(base, hd["disp"]))
    assert disp.wait_for("ready")
    with Session(db_engine) as s:
        live.publish(
            s, {"org_id": other.org.id, "kind": "request.changed", "request_id": uuid.uuid4()}
        )
        s.commit()
    time.sleep(1.0)
    assert disp.count("request.changed") == 0


def test_heartbeat_and_ticket_reuse(live_server, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "STREAM_HEARTBEAT_SECONDS", 0.3)
    base = live_server
    _, hd = _world(db, base)
    t = _ticket(base, hd["disp"])
    a = Reader(base, t)
    assert a.wait_for("ready")
    time.sleep(1.2)
    assert a.comments >= 2 and ": ping" in a.lines
    b = Reader(base, t)  # same ticket again (browser auto-reconnect)
    assert b.wait_for("ready")


def test_stream_closed_when_membership_deactivated(live_server, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "STREAM_REVALIDATE_SECONDS", 0.5)
    base = live_server
    sw, hd = _world(db, base)
    r = Reader(base, _ticket(base, hd["disp"]))
    assert r.wait_for("ready")
    db.execute(text("UPDATE memberships SET is_active=false WHERE id=:i"), {"i": sw.w.disp[1].id})
    db.commit()
    assert r.wait_for("closed", timeout=6) == {"reason": "session_revoked"}
    assert r.ended.wait(5)


def test_stream_closed_when_session_revoked(live_server, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "STREAM_REVALIDATE_SECONDS", 0.5)
    base = live_server
    _, hd = _world(db, base)
    r = Reader(base, _ticket(base, hd["req1"]))
    assert r.wait_for("ready")
    db.execute(text("UPDATE sessions SET revoked_at = :t"), {"t": datetime.now(UTC) + timedelta(0)})
    db.commit()
    assert r.wait_for("closed", timeout=6)


def test_listener_reconnects_after_connection_killed(live_server, db, db_engine):
    base = live_server
    sw, hd = _world(db, base)
    r = Reader(base, _ticket(base, hd["disp"]))
    assert r.wait_for("ready")
    with db_engine.connect() as c:
        c.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE query LIKE 'LISTEN%' AND pid <> pg_backend_pid()"
            )
        )
        c.commit()
    assert r.wait_for("resync", timeout=10)
    rid = uuid.uuid4()
    with Session(db_engine) as s:
        live.publish(s, {"org_id": sw.w.org.id, "kind": "request.changed", "request_id": rid})
        s.commit()
    assert r.wait_for("request.changed", pred=lambda d: d["request_id"] == str(rid))
