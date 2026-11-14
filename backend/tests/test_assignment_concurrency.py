"""SCHED-04 / E2E-02 / API-03: DB-backed race safety and idempotency."""

import threading
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models import Assignment, IdempotencyKey, RequestEvent, ServiceRequest
from app.services import assignments as assignments_svc
from tests.sched_helpers import API, S, assign, iso, local_slot, new_key, triaged

ITERATIONS = 5


def race(app, calls):
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


def assigner(req, tech, s, e, headers, extra=None):
    # resolve ids BEFORE the threads start: ORM instances are not thread safe
    url = f"{API}/requests/{req.id}/assignment"
    body = {"technician_membership_id": str(tech[1].id), "start_at": iso(s), "end_at": iso(e)}

    def call(c):
        return c.post(url, json=body, headers={**headers, **(extra or {})})

    return call


def untouched(db, req):
    """Loser invariants: still TRIAGED, no assignment row, no status/assignment events."""
    db.expire_all()
    assert db.get(ServiceRequest, req.id).status == S.TRIAGED
    assert (
        db.scalar(
            select(func.count()).select_from(Assignment).where(Assignment.request_id == req.id)
        )
        == 0
    )
    types = set(db.scalars(select(RequestEvent.type).where(RequestEvent.request_id == req.id)))
    assert not ({"STATUS_CHANGED", "ASSIGNED"} & types)


def test_concurrent_overlapping_assignments_exactly_one_wins(client, db, sw, hd):
    for i in range(ITERATIONS):
        a, b = triaged(db, sw.w), triaged(db, sw.w)
        s, e = local_slot(2 + i, 10)
        res = race(
            client.app,
            [
                assigner(a, sw.w.tech, s, e, hd["disp"]),
                assigner(
                    b, sw.w.tech, s + timedelta(minutes=30), e + timedelta(minutes=30), hd["admin"]
                ),
            ],
        )
        codes = sorted(r.status_code for r in res)
        assert codes[0] == 201 and codes[1] in (409, 422), [r.text for r in res]
        loser_resp = next(r for r in res if r.status_code != 201)
        assert loser_resp.json()["error"]["code"] in ("schedule_conflict", "technician_ineligible")
        loser = a if res[0].status_code != 201 else b
        winner = b if loser is a else a
        untouched(db, loser)
        db.expire_all()
        assert db.get(ServiceRequest, winner.id).status == S.SCHEDULED
        n = db.scalar(
            select(func.count())
            .select_from(Assignment)
            .where(
                Assignment.technician_membership_id == sw.w.tech[1].id,
                Assignment.start_at >= s - timedelta(hours=1),
                Assignment.start_at <= s + timedelta(hours=2),
            )
        )
        assert n == 1


def test_db_constraint_is_the_authority_clear_409_for_loser(client, db, sw, hd, monkeypatch):
    """Disable the application pre-check: the DB exclusion constraint alone must stop the loser."""
    monkeypatch.setattr(assignments_svc, "_require_eligible", lambda *a, **k: None)
    for i in range(ITERATIONS):
        a, b = triaged(db, sw.w), triaged(db, sw.w)
        s, e = local_slot(2 + i, 10)
        res = race(
            client.app,
            [
                assigner(a, sw.w.tech, s, e, hd["disp"]),
                assigner(b, sw.w.tech, s + timedelta(minutes=15), e, hd["admin"]),
            ],
        )
        assert sorted(r.status_code for r in res) == [201, 409], [r.text for r in res]
        err = next(r for r in res if r.status_code == 409).json()["error"]
        assert err["code"] == "schedule_conflict"
        assert err["details"]["technician_membership_id"] == str(sw.w.tech[1].id)
        loser = a if res[0].status_code == 409 else b
        untouched(db, loser)


def test_adjacent_windows_both_succeed_concurrently(client, db, sw, hd):
    a, b = triaged(db, sw.w), triaged(db, sw.w)
    s, e = local_slot(2, 10)
    res = race(
        client.app,
        [
            assigner(a, sw.w.tech, s, e, hd["disp"]),
            assigner(b, sw.w.tech, e, e + timedelta(hours=1), hd["admin"]),
        ],
    )
    assert [r.status_code for r in res] == [201, 201]


def test_different_technicians_same_window_both_succeed_concurrently(client, db, sw, hd):
    a, b = triaged(db, sw.w), triaged(db, sw.w)
    s, e = local_slot(2, 10)
    res = race(
        client.app,
        [assigner(a, sw.w.tech, s, e, hd["disp"]), assigner(b, sw.tech2, s, e, hd["admin"])],
    )
    assert [r.status_code for r in res] == [201, 201]


def test_concurrent_assign_of_same_request_one_wins(client, db, sw, hd):
    for i in range(ITERATIONS):
        req = triaged(db, sw.w)
        s, e = local_slot(2 + i, 10)
        res = race(
            client.app,
            [
                assigner(req, sw.w.tech, s, e, hd["disp"]),
                assigner(req, sw.tech2, s, e, hd["admin"]),
            ],
        )
        assert sorted(r.status_code for r in res) == [201, 409], [r.text for r in res]
        loser = next(r for r in res if r.status_code == 409).json()["error"]["code"]
        assert loser in ("invalid_transition", "conflict")
        db.expire_all()
        active = db.scalars(
            select(Assignment).where(Assignment.request_id == req.id, Assignment.active.is_(True))
        ).all()
        assert len(active) == 1
        assert len(db.scalars(select(Assignment).where(Assignment.request_id == req.id)).all()) == 1


# ---------------- idempotency ----------------
def count_assignments(db, req):
    db.expire_all()
    return db.scalar(
        select(func.count()).select_from(Assignment).where(Assignment.request_id == req.id)
    )


def count_events(db, req, type_):
    return db.scalar(
        select(func.count())
        .select_from(RequestEvent)
        .where(RequestEvent.request_id == req.id, RequestEvent.type == type_)
    )


def test_replay_returns_original_response_and_single_effect(client, db, sw, hd):
    req = triaged(db, sw.w)
    s, e = local_slot(2, 10)
    key = new_key()
    r1 = assign(client, hd, req, sw.w.tech, s, e, **{"Idempotency-Key": key})
    r2 = assign(client, hd, req, sw.w.tech, s, e, **{"Idempotency-Key": key})
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json() == r2.json()
    assert (
        r2.headers.get("Idempotent-Replayed") == "true" and "Idempotent-Replayed" not in r1.headers
    )
    assert count_assignments(db, req) == 1
    assert count_events(db, req, "ASSIGNED") == 1
    assert count_events(db, req, "STATUS_CHANGED") == 1
    # equivalent timestamp spelling is the same payload
    r3 = client.post(
        f"{API}/requests/{req.id}/assignment",
        json={
            "technician_membership_id": str(sw.w.tech[1].id),
            "start_at": s.astimezone().isoformat(),
            "end_at": e.isoformat().replace("+00:00", "Z"),
        },
        headers={**hd["disp"], "Idempotency-Key": key},
    )
    assert r3.status_code == 201 and r3.json() == r1.json()


def test_replay_survives_later_state_change(client, db, sw, hd):
    req = triaged(db, sw.w)
    s, e = local_slot(2, 10)
    key = new_key()
    r1 = assign(client, hd, req, sw.w.tech, s, e, **{"Idempotency-Key": key})
    client.post(
        f"{API}/requests/{req.id}/assignment/unassign",
        json={"reason": "Customer asked to postpone"},
        headers=hd["disp"],
    )
    r2 = assign(client, hd, req, sw.w.tech, s, e, **{"Idempotency-Key": key})
    assert r2.status_code == 201 and r2.json() == r1.json()
    assert count_assignments(db, req) == 1  # no second row; request is still TRIAGED
    db.expire_all()
    assert db.get(ServiceRequest, req.id).status == S.TRIAGED


def test_same_key_different_payload_is_409(client, db, sw, hd):
    req = triaged(db, sw.w)
    s, e = local_slot(2, 10)
    key = new_key()
    assert assign(client, hd, req, sw.w.tech, s, e, **{"Idempotency-Key": key}).status_code == 201
    r = assign(
        client,
        hd,
        req,
        sw.w.tech,
        s + timedelta(hours=1),
        e + timedelta(hours=1),
        **{"Idempotency-Key": key},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "idempotency_key_reused"
    r = assign(client, hd, req, sw.tech2, s, e, **{"Idempotency-Key": key})
    assert r.json()["error"]["code"] == "idempotency_key_reused"
    # other endpoint, same key
    other = triaged(db, sw.w)
    r = assign(
        client,
        hd,
        other,
        sw.w.tech,
        s + timedelta(hours=3),
        e + timedelta(hours=3),
        **{"Idempotency-Key": key},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "idempotency_key_reused"
    assert count_assignments(db, req) == 1 and count_assignments(db, other) == 0


def test_failed_attempt_does_not_burn_the_key(client, db, sw, hd):
    req = triaged(db, sw.w)
    s, e = local_slot(2, 10)
    key = new_key()
    bad = assign(
        client, hd, req, sw.w.tech, s, s + timedelta(minutes=10), **{"Idempotency-Key": key}
    )
    assert bad.status_code == 422
    assert db.scalar(select(func.count()).select_from(IdempotencyKey)) == 0
    ok = assign(client, hd, req, sw.w.tech, s, e, **{"Idempotency-Key": key})
    assert ok.status_code == 201


def test_keys_are_scoped_per_user_and_validated(client, db, sw, hd):
    a, b = triaged(db, sw.w), triaged(db, sw.w)
    s, e = local_slot(2, 10)
    key = new_key()
    assert (
        assign(client, hd, a, sw.w.tech, s, e, who="disp", **{"Idempotency-Key": key}).status_code
        == 201
    )
    r = assign(client, hd, b, sw.tech2, s, e, who="admin", **{"Idempotency-Key": key})
    assert r.status_code == 201 and r.json()["assignment"]["request_id"] == str(b.id)
    r = assign(client, hd, triaged(db, sw.w), sw.w.tech, s, e, **{"Idempotency-Key": "k" * 129})
    assert r.status_code == 422
    r = assign(
        client,
        hd,
        triaged(db, sw.w),
        sw.w.tech,
        s + timedelta(hours=5),
        e + timedelta(hours=5),
        **{"Idempotency-Key": "k" * 128},
    )
    assert r.status_code == 201


def test_reschedule_and_unassign_are_idempotent_too(client, db, sw, hd):
    req = triaged(db, sw.w)
    s, e = local_slot(2, 10)
    assert assign(client, hd, req, sw.w.tech, s, e).status_code == 201
    s2, e2 = local_slot(3, 10)
    key = new_key()
    body = {"technician_membership_id": str(sw.tech2[1].id), "start_at": iso(s2), "end_at": iso(e2)}
    url = f"{API}/requests/{req.id}/assignment"
    r1 = client.put(url, json=body, headers={**hd["disp"], "Idempotency-Key": key})
    r2 = client.put(url, json=body, headers={**hd["disp"], "Idempotency-Key": key})
    assert r1.status_code == r2.status_code == 200 and r1.json() == r2.json()
    assert count_assignments(db, req) == 2
    assert count_events(db, req, "RESCHEDULED") == 1
    key2 = new_key()
    u = {"reason": "Customer asked to postpone"}
    un1 = client.post(f"{url}/unassign", json=u, headers={**hd["disp"], "Idempotency-Key": key2})
    un2 = client.post(f"{url}/unassign", json=u, headers={**hd["disp"], "Idempotency-Key": key2})
    assert un1.status_code == un2.status_code == 200 and un1.json() == un2.json()
    assert count_events(db, req, "UNASSIGNED") == 1


@pytest.mark.parametrize("round_", range(ITERATIONS))
def test_concurrent_same_key_produces_one_effect(client, db, sw, hd, round_):
    req = triaged(db, sw.w)
    s, e = local_slot(2 + round_, 10)
    key = new_key()
    res = race(
        client.app,
        [
            assigner(req, sw.w.tech, s, e, hd["disp"], {"Idempotency-Key": key}),
            assigner(req, sw.w.tech, s, e, hd["disp"], {"Idempotency-Key": key}),
        ],
    )
    assert [r.status_code for r in res] == [201, 201], [r.text for r in res]
    assert res[0].json() == res[1].json()
    assert count_assignments(db, req) == 1
    assert count_events(db, req, "ASSIGNED") == 1
    assert db.scalar(select(func.count()).select_from(IdempotencyKey)) == 1
