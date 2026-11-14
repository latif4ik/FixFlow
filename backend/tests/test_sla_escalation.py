"""Overdue escalation (SLA-06/07, E2E-07): once per request, concurrency-safe, org-scoped."""

import threading

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import cli
from app.models import Notification, RequestEvent
from app.services.escalation import escalate_overdue
from app.services.request_events import add_event
from tests.factories import h, login
from tests.req_helpers import make_world
from tests.sched_helpers import API
from tests.sla_helpers import at, backdate, load, set_now
from tests.test_sla_api import make_request

NOW = at(16, 10)  # Monday 10:00; HIGH requests created Fri 09:00 were due Fri 17:00


def overdue_count(db, org_id) -> int:
    return db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.organization_id == org_id, Notification.type == "OVERDUE_ESCALATION")
    )


def test_escalates_once_per_request_per_staff_recipient(client, db, sw, hd, monkeypatch):
    w = sw.w
    late = make_request(client, db, hd, w, at(13, 9), "HIGH")
    fresh = make_request(client, db, hd, w, at(16, 9), "HIGH")
    set_now(monkeypatch, NOW)
    assert escalate_overdue(db, NOW) == 1
    rows = list(db.scalars(select(Notification).where(Notification.type == "OVERDUE_ESCALATION")))
    # admin + dispatcher, nobody else; only the late request; one row each
    assert len(rows) == 2
    assert {r.recipient_membership_id for r in rows} == {w.admin[1].id, w.disp[1].id}
    assert {str(r.request_id) for r in rows} == {late}
    assert {r.dedupe_key for r in rows} == {f"overdue:{late}"}
    assert rows[0].data and rows[0].data["overdue_by_minutes"] == 120
    assert load(db, late).overdue_notified_at == NOW and load(db, fresh).overdue_notified_at is None
    events = db.scalars(select(RequestEvent).where(RequestEvent.type == "SLA_ESCALATED")).all()
    assert len(events) == 1 and str(events[0].request_id) == late
    # a second run (and a later one) creates nothing
    assert escalate_overdue(db, NOW) == 0
    assert (
        escalate_overdue(db, at(17, 12)) == 1
    )  # `fresh` became overdue meanwhile, `late` not again
    assert escalate_overdue(db, at(17, 12)) == 0
    assert overdue_count(db, w.org.id) == 4
    # visible via the API, once per request for the dispatcher
    r = client.get(f"{API}/notifications", headers=hd["disp"])
    types = [n["type"] for n in r.json()["items"]]
    assert types.count("OVERDUE_ESCALATION") == 2
    assert client.get(f"{API}/notifications", headers=hd["req1"]).json()["total"] == 0


def test_requester_timeline_hides_escalation(client, db, sw, hd):
    w = sw.w
    late = make_request(client, db, hd, w, at(13, 9), "HIGH")
    assert escalate_overdue(db, NOW) == 1
    staff = client.get(f"{API}/requests/{late}", headers=hd["disp"]).json()["timeline"]
    mine = client.get(f"{API}/requests/{late}", headers=hd["req1"]).json()["timeline"]
    assert "SLA_ESCALATED" in [t["type"] for t in staff]
    assert "SLA_ESCALATED" not in [t["type"] for t in mine]


def test_paused_request_not_escalated_until_resumed(client, db, sw, hd):
    w = sw.w
    rid = make_request(client, db, hd, w, at(13, 9), "HIGH")
    # pause at Friday 10:00 (consumed 1h) -> not overdue while the estimate is pending
    add_event(db, None, load(db, rid), "ESTIMATE_SUBMITTED", at=at(13, 10))
    db.commit()
    assert load(db, rid).sla_paused and load(db, rid).sla_due_at is None
    assert escalate_overdue(db, at(20, 12)) == 0
    assert overdue_count(db, w.org.id) == 0
    add_event(db, None, load(db, rid), "ESTIMATE_APPROVED", at=at(16, 9))
    db.commit()
    assert escalate_overdue(db, at(16, 12)) == 0  # 7h remaining at Mon 09:00 -> due Mon 16:00
    assert escalate_overdue(db, at(16, 16, 1)) == 1


def test_finished_requests_are_not_escalated(client, db, sw, hd):
    w = sw.w
    rid = make_request(client, db, hd, w, at(13, 9), "HIGH")
    r = client.post(
        f"{API}/requests/{rid}/cancel", json={"reason": "duplicate work"}, headers=hd["disp"]
    )
    assert r.status_code == 200, r.text
    assert escalate_overdue(db, at(30, 12)) == 0


def test_concurrent_escalation_runs_notify_exactly_once(client, db, db_engine, sw, hd):
    w = sw.w
    ids = [make_request(client, db, hd, w, at(13, 9), "HIGH") for _ in range(6)]
    barrier = threading.Barrier(2)
    results: list[int] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            with Session(db_engine, expire_on_commit=False) as s:
                barrier.wait(timeout=10)
                results.append(escalate_overdue(s, NOW))
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert not errors, errors
    assert sum(results) == 6  # every request claimed by exactly one worker
    assert overdue_count(db, w.org.id) == 6 * 2
    per_request = db.execute(
        select(Notification.request_id, func.count())
        .where(Notification.type == "OVERDUE_ESCALATION")
        .group_by(Notification.request_id)
    ).all()
    assert len(per_request) == 6 and {n for _, n in per_request} == {2}
    assert {str(r) for r, _ in per_request} == set(ids)
    assert escalate_overdue(db, NOW) == 0


def test_endpoint_is_admin_only_and_scoped_to_caller_org(client, db, sw, hd):
    w = sw.w
    other = make_world(db, "Org B")
    hb = {"admin": h(login(client, other.admin[0]), other.org)}
    a = make_request(client, db, hd, w, at(13, 9), "HIGH")
    r = client.post(
        f"{API}/requests",
        json={
            "title": "Other org outage",
            "description": "The generator in the basement does not start at all.",
            "category_id": str(other.cat.id),
            "property_id": str(other.prop.id),
            "priority": "HIGH",
            "requester_membership_id": str(other.req1[1].id),
        },
        headers=hb["admin"],
    )
    assert r.status_code == 201, r.text
    b = r.json()["id"]
    backdate(db, b, at(13, 9))
    assert client.post(f"{API}/admin/sla/escalate", headers=hd["disp"]).status_code == 403
    assert client.post(f"{API}/admin/sla/escalate", headers=hd["req1"]).status_code == 403
    # the endpoint uses the real clock: both requests are long overdue by now
    r = client.post(f"{API}/admin/sla/escalate", headers=hd["admin"])
    assert r.status_code == 200 and r.json() == {"escalated": 1}
    assert load(db, a).overdue_notified_at is not None
    assert load(db, b).overdue_notified_at is None  # other org untouched
    assert client.post(f"{API}/admin/sla/escalate", headers=hd["admin"]).json() == {"escalated": 0}
    assert overdue_count(db, other.org.id) == 0
    assert escalate_overdue(db) == 1  # the all-orgs run (CLI path) picks up org B
    assert overdue_count(db, other.org.id) == 2


def test_dashboard_overdue_queue(client, db, sw, hd, monkeypatch):
    w = sw.w
    older = make_request(client, db, hd, w, at(11, 9), "HIGH")  # due Wed 17:00
    newer = make_request(client, db, hd, w, at(13, 9), "HIGH")  # due Fri 17:00
    make_request(client, db, hd, w, at(16, 9), "HIGH")  # not overdue yet
    paused = make_request(client, db, hd, w, at(11, 9), "HIGH")
    add_event(db, None, load(db, paused), "ESTIMATE_SUBMITTED", at=at(11, 10))
    db.commit()
    set_now(monkeypatch, NOW)
    r = client.get(f"{API}/dashboard/overdue", headers=hd["disp"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 2
    assert [i["id"] for i in body["items"]] == [older, newer]  # most overdue first
    assert body["items"][0]["overdue_by_minutes"] > body["items"][1]["overdue_by_minutes"] > 0
    assert body["items"][0]["escalated_at"] is None
    escalate_overdue(db, NOW)
    body = client.get(f"{API}/dashboard/overdue?page_size=1", headers=hd["admin"]).json()
    assert body["count"] == 2 and len(body["items"]) == 1 and body["items"][0]["escalated_at"]
    assert client.get(f"{API}/dashboard/overdue", headers=hd["req1"]).status_code == 403
    assert client.get(f"{API}/dashboard/overdue", headers=hd["tech"]).status_code == 403
    other = make_world(db, "Org B")
    hb = h(login(client, other.admin[0]), other.org)
    empty = client.get(f"{API}/dashboard/overdue", headers=hb).json()
    assert empty["count"] == 0 and empty["items"] == []


def test_cli_sla_escalate_prints_count_and_is_idempotent(client, db, sw, hd, capsys):
    w = sw.w
    make_request(client, db, hd, w, at(13, 9), "HIGH")
    assert cli.main(["sla-escalate", "--now", NOW.isoformat()]) == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] == "1"
    assert cli.main(["sla-escalate", "--now", NOW.isoformat()]) == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] == "0"
    assert cli.main(["sla-recompute"]) == 0
    assert int(capsys.readouterr().out.strip().splitlines()[-1]) >= 1
