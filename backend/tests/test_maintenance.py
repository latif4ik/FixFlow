"""Preventive maintenance: recurrence math, plan API, idempotent generation, retirement."""

import threading
from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import cli
from app.models import MaintenancePlan, RequestEvent, ServiceRequest
from app.models.enums import Recurrence
from app.services import maintenance as svc
from app.services import maintenance_schedule as sched
from tests.factories import h, login
from tests.req_helpers import make_world
from tests.sched_helpers import API

W, M = Recurrence.WEEKLY, Recurrence.MONTHLY


# ---- pure recurrence ----
def test_weekly_occurrences():
    assert sched.occurrences_due(date(2026, 11, 1), W, None, date(2026, 11, 22)) == [
        date(2026, 11, 1),
        date(2026, 11, 8),
        date(2026, 11, 15),
        date(2026, 11, 22),
    ]
    assert sched.occurrences_due(date(2026, 11, 1), W, date(2026, 11, 8), date(2026, 11, 22)) == [
        date(2026, 11, 15),
        date(2026, 11, 22),
    ]
    assert sched.occurrences_due(date(2026, 11, 10), W, None, date(2026, 11, 9)) == []


def test_monthly_clamps_to_month_end_and_does_not_drift():
    got = sched.occurrences_due(date(2027, 1, 31), M, None, date(2027, 5, 31))
    assert got == [
        date(2027, 1, 31),
        date(2027, 2, 28),
        date(2027, 3, 31),
        date(2027, 4, 30),
        date(2027, 5, 31),
    ]


def test_monthly_leap_year_and_year_rollover():
    assert sched.nth_occurrence(date(2028, 1, 31), M, 1) == date(2028, 2, 29)
    assert sched.nth_occurrence(date(2026, 11, 15), M, 2) == date(2027, 1, 15)
    assert sched.nth_occurrence(date(2026, 12, 31), M, 12) == date(2027, 12, 31)


def test_next_occurrence_and_start_index_never_skips():
    first = date(2027, 1, 31)
    for after in (date(2027, 1, 31), date(2027, 2, 27), date(2027, 2, 28), date(2027, 3, 1)):
        nxt = sched.next_occurrence(first, M, after)
        assert nxt > after
    assert sched.next_occurrence(first, M, date(2027, 1, 31)) == date(2027, 2, 28)
    assert sched.next_occurrence(first, M, date(2027, 2, 28)) == date(2027, 3, 31)
    assert sched.next_occurrence(date(2026, 11, 1), W, None) == date(2026, 11, 1)
    assert sched.next_occurrence(date(2026, 11, 1), W, date(2026, 11, 8)) == date(2026, 11, 15)


def test_occurrence_cap_per_run():
    got = sched.occurrences_due(date(2000, 1, 1), W, None, date(2026, 1, 1), limit=10)
    assert len(got) == 10 and got[0] == date(2000, 1, 1)


# ---- API ----
def body(w, **over):
    b = {
        "asset_id": str(w.asset.id),
        "category_id": str(w.cat.id),
        "title": "Quarterly filter check",
        "description": "Inspect and replace the air handling unit filters as needed.",
        "priority": "NORMAL",
        "first_date": "2026-11-01",
        "recurrence": "WEEKLY",
    }
    b.update(over)
    return b


def mk(client, hd, w, **over):
    r = client.post(f"{API}/maintenance-plans", json=body(w, **over), headers=hd["disp"])
    assert r.status_code == 201, r.text
    return r.json()


def gen(client, hd, as_of, who="disp", **headers):
    return client.post(
        f"{API}/maintenance-plans/generate",
        json={"as_of": as_of},
        headers={**hd[who], **headers},
    )


def count_reqs(db, plan_id) -> int:
    return db.scalar(
        select(func.count()).select_from(ServiceRequest).where(ServiceRequest.plan_id == plan_id)
    )


def test_create_validation_and_permissions(client, db, sw, hd):
    w = sw.w
    for who in ("req1", "tech"):
        r = client.post(f"{API}/maintenance-plans", json=body(w), headers=hd[who])
        assert r.status_code == 403
        assert client.get(f"{API}/maintenance-plans", headers=hd[who]).status_code == 403
    w.asset.status = "OUT_OF_SERVICE"
    db.commit()
    assert (
        client.post(f"{API}/maintenance-plans", json=body(w), headers=hd["disp"]).status_code == 422
    )
    w.asset.status = "RETIRED"
    db.commit()
    r = client.post(f"{API}/maintenance-plans", json=body(w), headers=hd["disp"])
    assert r.status_code == 422
    w.asset.status = "ACTIVE"
    w.cat.is_enabled = False
    db.commit()
    assert (
        client.post(f"{API}/maintenance-plans", json=body(w), headers=hd["disp"]).status_code == 422
    )
    w.cat.is_enabled = True
    db.commit()
    bad = client.post(f"{API}/maintenance-plans", json=body(w, title="abc"), headers=hd["disp"])
    assert bad.status_code == 422
    other = make_world(db, "Org B")
    r = client.post(
        f"{API}/maintenance-plans", json=body(w, asset_id=str(other.asset.id)), headers=hd["disp"]
    )
    assert r.status_code == 422


def test_generate_creates_traceable_requests_and_rerun_is_noop(client, db, sw, hd):
    w = sw.w
    plan = mk(client, hd, w, priority="HIGH")
    assert plan["next_occurrence"] == "2026-11-01" and plan["generated_total"] == 0
    r = gen(client, hd, "2026-11-15")
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["requests_created"] == 3 and rep["skipped_existing"] == 0
    pid = plan["id"]
    rows = list(
        db.scalars(
            select(ServiceRequest)
            .where(ServiceRequest.plan_id == pid)
            .order_by(ServiceRequest.occurrence_date)
        )
    )
    assert [r.occurrence_date for r in rows] == [date(2026, 11, d) for d in (1, 8, 15)]
    first = rows[0]
    assert first.requester_membership_id is None and first.created_by_membership_id is None
    assert first.asset_id == w.asset.id and first.property_id == w.prop.id
    assert first.status == "SUBMITTED" and first.title.endswith("(2026-11-01)")
    assert first.sla_budget_minutes == 480 and first.sla_due_at is not None
    ev = db.scalars(
        select(RequestEvent).where(
            RequestEvent.request_id == first.id, RequestEvent.type == "REQUEST_CREATED"
        )
    ).one()
    assert ev.data and ev.data["source"] == "maintenance" and ev.data["plan_id"] == pid
    assert ev.data["occurrence_date"] == "2026-11-01"
    # re-run: nothing new
    rep = gen(client, hd, "2026-11-15").json()
    assert rep["requests_created"] == 0 and rep["skipped_existing"] == 0
    assert count_reqs(db, pid) == 3
    # a later date only adds the new occurrence
    assert gen(client, hd, "2026-11-22").json()["requests_created"] == 1
    d = client.get(f"{API}/maintenance-plans/{pid}", headers=hd["disp"]).json()
    assert d["generated_total"] == 4 and d["next_occurrence"] == "2026-11-29"
    assert [g["occurrence_date"] for g in d["generated"]][:2] == ["2026-11-22", "2026-11-15"]
    assert d["last_generated_for"] == "2026-11-22"


def test_unique_constraint_backstop_skips_existing_occurrence(client, db, sw, hd):
    w = sw.w
    plan = mk(client, hd, w)
    assert gen(client, hd, "2026-11-08").json()["requests_created"] == 2
    p = db.get(MaintenancePlan, plan["id"])
    db.refresh(p)
    p.last_generated_for = None  # simulate a lost marker: only the DB constraint protects us
    db.commit()
    rep = gen(client, hd, "2026-11-08").json()
    assert rep["requests_created"] == 0 and rep["skipped_existing"] == 2
    assert count_reqs(db, plan["id"]) == 2
    dup = db.scalars(select(ServiceRequest).where(ServiceRequest.plan_id == plan["id"])).first()
    assert dup is not None
    clone = ServiceRequest(
        organization_id=dup.organization_id,
        number=999,
        property_id=dup.property_id,
        category_id=dup.category_id,
        title="x" * 6,
        description="y" * 25,
        plan_id=dup.plan_id,
        occurrence_date=dup.occurrence_date,
    )
    db.add(clone)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_plan_occurrence_check_constraint(db, sw):
    w = sw.w
    from tests.req_helpers import seed_request

    with pytest.raises(IntegrityError):
        seed_request(db, w, occurrence_date=date(2026, 11, 1))
    db.rollback()


def test_concurrent_generate_creates_each_occurrence_once(client, db, db_engine, sw, hd):
    w = sw.w
    plans = [mk(client, hd, w, title=f"Plan number {i}") for i in range(3)]
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            with Session(db_engine, expire_on_commit=False) as s:
                barrier.wait(timeout=10)
                svc.generate(s, w.org.id, date(2026, 11, 29))
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    ts = [threading.Thread(target=worker) for _ in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=60)
    assert not errors, errors
    for p in plans:
        assert count_reqs(db, p["id"]) == 5  # Nov 1, 8, 15, 22, 29
    dupes = db.execute(
        select(ServiceRequest.plan_id, ServiceRequest.occurrence_date, func.count())
        .where(ServiceRequest.plan_id.is_not(None))
        .group_by(ServiceRequest.plan_id, ServiceRequest.occurrence_date)
        .having(func.count() > 1)
    ).all()
    assert dupes == []
    numbers = list(db.scalars(select(ServiceRequest.number)))
    assert len(numbers) == len(set(numbers)) == 15


def test_idempotency_key_replays_generation(client, db, sw, hd):
    plan = mk(client, hd, sw.w)
    a = gen(client, hd, "2026-11-08", **{"Idempotency-Key": "k1"})
    b = gen(client, hd, "2026-11-08", **{"Idempotency-Key": "k1"})
    assert a.status_code == b.status_code == 200
    assert a.json() == b.json() and b.headers.get("Idempotent-Replayed") == "true"
    assert a.json()["requests_created"] == 2 and count_reqs(db, plan["id"]) == 2
    c = gen(client, hd, "2026-11-15", **{"Idempotency-Key": "k1"})
    assert c.status_code == 409


def test_disable_stops_generation_but_keeps_requests(client, db, sw, hd):
    plan = mk(client, hd, sw.w)
    gen(client, hd, "2026-11-08")
    r = client.patch(
        f"{API}/maintenance-plans/{plan['id']}", json={"is_enabled": False}, headers=hd["disp"]
    )
    assert r.status_code == 200 and r.json()["is_enabled"] is False
    assert r.json()["next_occurrence"] is None
    assert gen(client, hd, "2026-12-31").json()["requests_created"] == 0
    assert count_reqs(db, plan["id"]) == 2
    client.patch(
        f"{API}/maintenance-plans/{plan['id']}", json={"is_enabled": True}, headers=hd["disp"]
    )
    assert gen(client, hd, "2026-11-15").json()["requests_created"] == 1


def test_changing_schedule_does_not_regenerate_old_dates(client, db, sw, hd):
    plan = mk(client, hd, sw.w)
    gen(client, hd, "2026-11-15")  # Nov 1, 8, 15
    r = client.patch(
        f"{API}/maintenance-plans/{plan['id']}", json={"recurrence": "MONTHLY"}, headers=hd["disp"]
    )
    assert r.status_code == 200 and r.json()["last_generated_for"] == "2026-11-15"
    assert gen(client, hd, "2026-11-30").json()["requests_created"] == 0
    assert gen(client, hd, "2026-12-01").json()["requests_created"] == 1
    assert count_reqs(db, plan["id"]) == 4
    r = client.patch(
        f"{API}/maintenance-plans/{plan['id']}",
        json={"first_date": "2026-10-01", "title": "Renamed plan title"},
        headers=hd["disp"],
    )
    assert r.status_code == 200
    assert gen(client, hd, "2026-12-01").json()["requests_created"] == 0


def test_retiring_asset_disables_plans_and_blocks_generation(client, db, sw, hd):
    w = sw.w
    plan = mk(client, hd, w)
    gen(client, hd, "2026-11-01")
    r = client.patch(f"{API}/assets/{w.asset.id}", json={"status": "RETIRED"}, headers=hd["disp"])
    assert r.status_code == 200, r.text
    d = client.get(f"{API}/maintenance-plans/{plan['id']}", headers=hd["disp"]).json()
    assert d["is_enabled"] is False and d["next_occurrence"] is None
    assert gen(client, hd, "2026-12-31").json()["requests_created"] == 0
    assert count_reqs(db, plan["id"]) == 1
    r = client.patch(
        f"{API}/maintenance-plans/{plan['id']}", json={"is_enabled": True}, headers=hd["disp"]
    )
    assert r.status_code == 422
    assert (
        client.post(f"{API}/maintenance-plans", json=body(w), headers=hd["disp"]).status_code == 422
    )
    audit = client.get(f"{API}/audit?page_size=100", headers=hd["admin"])
    assert audit.status_code == 200, audit.text
    actions = [e["action"] for e in audit.json()["items"]]
    assert "maintenance_plan.disabled" in actions and "asset.retired" in actions


def test_generated_request_follows_normal_lifecycle_and_visibility(client, db, sw, hd):
    plan = mk(client, hd, sw.w)
    gen(client, hd, "2026-11-01")
    rid = str(
        db.scalars(select(ServiceRequest.id).where(ServiceRequest.plan_id == plan["id"])).one()
    )
    detail = client.get(f"{API}/requests/{rid}", headers=hd["disp"]).json()
    assert detail["plan_id"] == plan["id"] and detail["occurrence_date"] == "2026-11-01"
    assert detail["requester"] is None and detail["sla"]["budget_minutes"] == 1440
    r = client.post(f"{API}/requests/{rid}/triage", json={}, headers=hd["disp"])
    assert r.status_code == 200 and r.json()["status"] == "TRIAGED"
    assert client.get(f"{API}/requests/{rid}", headers=hd["req1"]).status_code == 404
    assert client.get(f"{API}/requests/{rid}", headers=hd["tech"]).status_code == 404
    items = client.get(f"{API}/requests?page_size=50", headers=hd["req1"]).json()["items"]
    assert rid not in [i["id"] for i in items]


def test_org_isolation_and_org_scoped_generation(client, db, sw, hd):
    w = sw.w
    other = make_world(db, "Org B")
    hb = {"admin": h(login(client, other.admin[0]), other.org)}
    plan = mk(client, hd, w)
    pb = client.post(f"{API}/maintenance-plans", json=body(other), headers=hb["admin"])
    assert pb.status_code == 201, pb.text
    assert (
        client.get(f"{API}/maintenance-plans/{plan['id']}", headers=hb["admin"]).status_code == 404
    )
    r = client.patch(
        f"{API}/maintenance-plans/{plan['id']}", json={"is_enabled": False}, headers=hb["admin"]
    )
    assert r.status_code == 404
    listed = client.get(f"{API}/maintenance-plans", headers=hb["admin"]).json()
    assert listed["total"] == 1 and listed["items"][0]["id"] == pb.json()["id"]
    assert gen(client, hd, "2026-11-08").json()["requests_created"] == 2
    assert count_reqs(db, pb.json()["id"]) == 0  # endpoint only touches the caller's org
    with Session(db.get_bind()) as s:
        rep = svc.generate(s, other.org.id, date(2026, 11, 8))
    assert rep.requests_created == 2


def test_cli_generate_maintenance(client, db, sw, hd, capsys):
    plan = mk(client, hd, sw.w)
    args = ["generate-maintenance", "--as-of", "2026-11-08", "--org", str(sw.w.org.id)]
    assert cli.main(args) == 0
    assert "created=2" in capsys.readouterr().out
    assert cli.main(args) == 0
    assert "created=0" in capsys.readouterr().out
    assert count_reqs(db, plan["id"]) == 2
