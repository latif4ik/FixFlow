import itertools
import threading
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, true

from app.models import AuditEvent, EvidenceFile, RequestEvent, ServiceRequest, WorkNote
from app.models.enums import FilePurpose, RequestStatus
from app.services import lifecycle
from app.services import request_access as access
from tests.factories import h, login
from tests.req_helpers import make_world, seed_request

API = "/api/v1"
S = RequestStatus
REASON = "A perfectly good reason for this."
COMPLETION_NOTE = "Replaced the faulty valve and tested the flow."


@pytest.fixture
def w(db):
    return make_world(db)


@pytest.fixture
def hd(client, w):
    return {
        k: h(login(client, getattr(w, k)[0]), w.org)
        for k in ("admin", "disp", "tech", "req1", "req2")
    }


@pytest.fixture
def assigned(monkeypatch, w):
    """Phase-2b stand-in: make w.tech the active technician of every request."""
    monkeypatch.setattr(
        access,
        "get_active_assignment",
        lambda db, req: SimpleNamespace(technician_membership_id=w.tech[1].id),
    )
    monkeypatch.setattr(access, "technician_visibility_filter", lambda ctx: true())


def add_completion_file(db, w, req) -> None:
    db.add(
        EvidenceFile(
            organization_id=w.org.id,
            request_id=req.id,
            uploaded_by_membership_id=w.tech[1].id,
            purpose=FilePurpose.COMPLETION,
            original_filename="done.png",
            storage_key=f"x/{uuid.uuid4()}.png",
            mime_type="image/png",
            size_bytes=1,
            width=1,
            height=1,
            sha256="0" * 64,
        )
    )
    db.commit()


def go(client, hd, who, req, to, **body):
    return client.post(
        f"{API}/requests/{req.id}/transitions",
        json={"to_status": to.value, **body},
        headers=hd[who],
    )


# (from, to, actor, body) - every listed, externally reachable transition for the right role.
ALLOWED = [
    (S.SUBMITTED, S.TRIAGED, "disp", {}),
    (S.SUBMITTED, S.TRIAGED, "admin", {"note": "looks fine"}),
    (S.SCHEDULED, S.ACCEPTED, "tech", {}),
    (S.ACCEPTED, S.IN_PROGRESS, "tech", {}),
    (S.IN_PROGRESS, S.BLOCKED, "tech", {"reason": REASON}),
    (S.BLOCKED, S.IN_PROGRESS, "tech", {"reason": REASON}),
    (S.IN_PROGRESS, S.COMPLETED, "tech", {"note": COMPLETION_NOTE}),
    (S.COMPLETED, S.CLOSED, "req1", {}),
    (S.COMPLETED, S.CLOSED, "disp", {"reason": REASON}),
    (S.COMPLETED, S.REOPENED, "req1", {"reason": REASON}),
    (S.REOPENED, S.TRIAGED, "disp", {}),
    (S.SUBMITTED, S.CANCELED, "req1", {}),
    (S.SUBMITTED, S.CANCELED, "disp", {"reason": REASON}),
    (S.TRIAGED, S.CANCELED, "admin", {"reason": REASON}),
    (S.SCHEDULED, S.CANCELED, "disp", {"reason": REASON}),
]
# Listed but reserved for the Phase 2b assignment service (internal rules).
INTERNAL = {(S.TRIAGED, S.SCHEDULED), (S.SCHEDULED, S.TRIAGED), (S.ACCEPTED, S.TRIAGED)}
LISTED = {(f, t) for f, t, _, _ in ALLOWED} | INTERNAL


@pytest.mark.parametrize(("frm", "to", "who", "body"), ALLOWED)
def test_allowed_transition(client, db, w, hd, assigned, frm, to, who, body):
    req = seed_request(db, w, status=frm)
    if to == S.COMPLETED:
        add_completion_file(db, w, req)
    r = go(client, hd, who, req, to, **body)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == to.value
    events = db.scalars(
        select(RequestEvent).where(
            RequestEvent.request_id == req.id, RequestEvent.type == "STATUS_CHANGED"
        )
    ).all()
    assert len(events) == 1
    ev = events[0]
    actor = getattr(w, who)[1]
    assert (ev.from_status, ev.to_status, ev.actor_membership_id) == (frm.value, to.value, actor.id)
    assert ev.created_at is not None
    audits = db.scalars(
        select(AuditEvent).where(
            AuditEvent.action == "request.status_change", AuditEvent.target_id == req.id
        )
    ).all()
    assert len(audits) == 1 and audits[0].before == {"status": frm.value}
    db.expire_all()
    fresh = db.get(ServiceRequest, req.id)
    assert fresh is not None and fresh.status == to


ALL_PAIRS = list(itertools.product(list(S), list(S)))


@pytest.mark.parametrize(("frm", "to"), [p for p in ALL_PAIRS if p not in LISTED])
def test_every_unlisted_pair_is_409(client, db, w, hd, assigned, frm, to):
    req = seed_request(db, w, status=frm)
    for who in ("admin", "tech"):
        r = go(client, hd, who, req, to, reason=REASON, note=COMPLETION_NOTE)
        assert r.status_code == 409, (who, r.text)
        assert r.json()["error"]["code"] == "invalid_transition"
    db.expire_all()
    fresh = db.get(ServiceRequest, req.id)
    assert fresh is not None and fresh.status == frm
    assert db.scalar(select(func.count()).select_from(RequestEvent)) == 0


@pytest.mark.parametrize(("frm", "to"), sorted(INTERNAL))
def test_assignment_only_transitions_not_via_generic_endpoint(client, db, w, hd, frm, to):
    req = seed_request(db, w, status=frm)
    r = go(client, hd, "disp", req, to, reason=REASON)
    assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_transition"


def test_internal_transitions_through_service(db, w, assigned):
    from app.core.tenancy import Ctx

    disp = Ctx(w.disp[0].id, w.org.id, w.disp[1].id, w.disp[1].role, "UTC")
    tech = Ctx(w.tech[0].id, w.org.id, w.tech[1].id, w.tech[1].role, "UTC")
    req = seed_request(db, w, status=S.TRIAGED)
    lifecycle.transition(db, disp, req.id, S.SCHEDULED, internal=True)
    lifecycle.transition(db, tech, req.id, S.ACCEPTED)
    with pytest.raises(Exception, match="reason is required"):
        lifecycle.transition(db, tech, req.id, S.TRIAGED, internal=True)
    lifecycle.transition(db, tech, req.id, S.TRIAGED, reason=REASON, internal=True)
    assert db.get(ServiceRequest, req.id).status == S.TRIAGED  # type: ignore[union-attr]


@pytest.mark.parametrize("terminal", [S.CLOSED, S.CANCELED])
def test_terminal_states_reject_everything(client, db, w, hd, assigned, terminal):
    req = seed_request(db, w, status=terminal)
    for to in S:
        for who in ("admin", "req1", "tech"):
            r = go(client, hd, who, req, to, reason=REASON, note=COMPLETION_NOTE)
            assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_transition"
    assert (
        client.patch(
            f"{API}/requests/{req.id}",
            json={"priority": "HIGH", "reason": REASON},
            headers=hd["disp"],
        ).status_code
        == 409
    )
    note = client.post(
        f"{API}/requests/{req.id}/notes", json={"body": "late note"}, headers=hd["disp"]
    )
    assert note.status_code == 409


def test_role_and_ownership_enforced(client, db, w, hd, assigned):
    sub = seed_request(db, w, status=S.SUBMITTED)
    assert go(client, hd, "req1", sub, S.TRIAGED).status_code == 403
    assert go(client, hd, "tech", sub, S.TRIAGED).status_code == 403
    # other requester cannot even see it
    assert go(client, hd, "req2", sub, S.CANCELED).status_code == 404
    done = seed_request(db, w, status=S.COMPLETED)
    assert go(client, hd, "disp", done, S.REOPENED, reason=REASON).status_code == 403
    assert go(client, hd, "req2", done, S.CLOSED).status_code == 404
    assert go(client, hd, "req1", done, S.CLOSED).status_code == 200
    prog = seed_request(db, w, status=S.IN_PROGRESS)
    assert go(client, hd, "disp", prog, S.BLOCKED, reason=REASON).status_code == 403


def test_technician_unavailable_without_assignment(client, db, w, hd):
    req = seed_request(db, w, status=S.SCHEDULED)
    assert go(client, hd, "tech", req, S.ACCEPTED).status_code == 404  # not visible yet
    assert go(client, hd, "disp", req, S.ACCEPTED).status_code == 403


def test_reason_rules(client, db, w, hd, assigned):
    def fail(who, frm, to, field, **body):
        req = seed_request(db, w, status=frm)
        r = go(client, hd, who, req, to, **body)
        assert r.status_code == 422, r.text
        assert field in [d["field"] for d in r.json()["error"]["details"]]
        db.expire_all()
        fresh = db.get(ServiceRequest, req.id)
        assert fresh is not None and fresh.status == frm

    fail("disp", S.TRIAGED, S.CANCELED, "reason")
    fail("disp", S.TRIAGED, S.CANCELED, "reason", reason="no")
    fail("req1", S.COMPLETED, S.REOPENED, "reason")
    fail("disp", S.COMPLETED, S.CLOSED, "reason")
    fail("disp", S.SUBMITTED, S.CANCELED, "reason")
    fail("tech", S.IN_PROGRESS, S.BLOCKED, "reason")
    fail("tech", S.BLOCKED, S.IN_PROGRESS, "reason")
    fail("tech", S.IN_PROGRESS, S.COMPLETED, "note", note="too short")


def test_completion_needs_valid_image(client, db, w, hd, assigned):
    req = seed_request(db, w, status=S.IN_PROGRESS)
    r = go(client, hd, "tech", req, S.COMPLETED, note=COMPLETION_NOTE)
    assert r.status_code == 422
    assert "completion_images" in [d["field"] for d in r.json()["error"]["details"]]
    add_completion_file(db, w, req)
    assert go(client, hd, "tech", req, S.COMPLETED, note=COMPLETION_NOTE).status_code == 200
    db.expire_all()
    f = db.scalars(select(EvidenceFile).where(EvidenceFile.request_id == req.id)).one()
    assert f.note_id is not None  # linked to the completion note


def test_materials_hook_blocks_completion(client, db, w, hd, assigned, monkeypatch):
    from app.core.errors import ValidationFailed

    def boom(db_, req):
        raise ValidationFailed("bad materials", [{"field": "materials", "message": "invalid"}])

    monkeypatch.setattr(lifecycle, "validate_materials_for_completion", boom)
    req = seed_request(db, w, status=S.IN_PROGRESS)
    add_completion_file(db, w, req)
    assert go(client, hd, "tech", req, S.COMPLETED, note=COMPLETION_NOTE).status_code == 422


def test_specific_endpoints_and_notes(client, db, w, hd):
    req = seed_request(db, w, status=S.SUBMITTED)
    r = client.post(
        f"{API}/requests/{req.id}/cancel", json={"reason": "Fixed it myself"}, headers=hd["req1"]
    )
    assert r.status_code == 200 and r.json()["status"] == "CANCELED" and r.json()["canceled_at"]
    note = db.scalars(select(WorkNote).where(WorkNote.request_id == req.id)).one()
    assert (note.kind.value, note.visibility.value) == ("CANCEL", "PUBLIC")
    done = seed_request(db, w, status=S.COMPLETED)
    assert (
        client.post(f"{API}/requests/{done.id}/reopen", json={}, headers=hd["req1"]).status_code
        == 422
    )
    r = client.post(
        f"{API}/requests/{done.id}/reopen", json={"reason": "Still leaking"}, headers=hd["req1"]
    )
    assert r.json()["status"] == "REOPENED"
    r = client.post(f"{API}/requests/{done.id}/triage", json={}, headers=hd["disp"])
    assert r.json()["status"] == "TRIAGED"
    done2 = seed_request(db, w, status=S.COMPLETED)
    r = client.post(f"{API}/requests/{done2.id}/close", json={}, headers=hd["req1"])
    assert r.json()["status"] == "CLOSED" and r.json()["closed_at"]
    assert r.json()["allowed_actions"] == []


def test_allowed_actions_follow_engine(client, db, w, hd):
    req = seed_request(db, w, status=S.SUBMITTED)

    def d(who):
        return client.get(f"{API}/requests/{req.id}", headers=hd[who]).json()["allowed_actions"]

    assert {"triage", "cancel", "add_note"} <= set(d("disp"))
    assert set(d("req1")) == {"cancel", "add_note", "edit"}
    done = seed_request(db, w, status=S.COMPLETED)
    acts = client.get(f"{API}/requests/{done.id}", headers=hd["req1"]).json()["allowed_actions"]
    assert {"close", "reopen"} <= set(acts)


def test_failed_audit_rolls_everything_back(client, db, w, hd, monkeypatch):
    req = seed_request(db, w, status=S.SUBMITTED)

    def boom(*a, **k):
        raise RuntimeError("audit down")

    monkeypatch.setattr(lifecycle, "record_audit", boom)
    r = client.post(
        f"{API}/requests/{req.id}/triage", json={"note": "internal triage"}, headers=hd["disp"]
    )
    assert r.status_code == 500 and r.json()["error"]["code"] == "internal_error"
    db.expire_all()
    fresh = db.get(ServiceRequest, req.id)
    assert fresh is not None and fresh.status == S.SUBMITTED
    assert db.scalar(select(func.count()).select_from(RequestEvent)) == 0
    assert db.scalar(select(func.count()).select_from(WorkNote)) == 0


# ---------------- concurrency ----------------
def _race(app, calls):
    barrier = threading.Barrier(len(calls))
    results: list = [None] * len(calls)

    def run(i, fn):
        with TestClient(app) as c:
            barrier.wait()
            results[i] = fn(c)

    threads = [threading.Thread(target=run, args=(i, f)) for i, f in enumerate(calls)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    return results


def _poster(req, action, headers):
    def call(c):
        return c.post(f"{API}/requests/{req.id}/{action}", json={}, headers=headers)

    return call


def test_concurrent_double_triage_exactly_one_wins(client, db, w, hd):
    for _ in range(4):
        req = seed_request(db, w, status=S.SUBMITTED)
        res = _race(
            client.app, [_poster(req, "triage", hd["disp"]), _poster(req, "triage", hd["admin"])]
        )
        assert sorted(r.status_code for r in res) == [200, 409], [r.text for r in res]
        assert (
            next(r for r in res if r.status_code == 409).json()["error"]["code"]
            == "invalid_transition"
        )
        n = db.scalar(
            select(func.count())
            .select_from(RequestEvent)
            .where(RequestEvent.request_id == req.id, RequestEvent.type == "STATUS_CHANGED")
        )
        assert n == 1


def test_concurrent_cancel_vs_triage_is_consistent(client, db, w, hd):
    for _ in range(4):
        req = seed_request(db, w, status=S.SUBMITTED)
        c_res, t_res = _race(
            client.app, [_poster(req, "cancel", hd["req1"]), _poster(req, "triage", hd["disp"])]
        )
        # Exactly one wins; the loser is rejected (409 stale state, or 403 once it is TRIAGED).
        assert sorted([c_res.status_code == 200, t_res.status_code == 200]) == [False, True]
        loser = t_res if c_res.status_code == 200 else c_res
        assert loser.status_code in (403, 409)
        db.expire_all()
        fresh = db.get(ServiceRequest, req.id)
        assert fresh is not None
        assert fresh.status == (S.CANCELED if c_res.status_code == 200 else S.TRIAGED)
        evs = db.scalars(
            select(RequestEvent).where(
                RequestEvent.request_id == req.id, RequestEvent.type == "STATUS_CHANGED"
            )
        ).all()
        assert len(evs) == 1 and evs[0].to_status == fresh.status.value
