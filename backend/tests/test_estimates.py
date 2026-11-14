"""EST-01..06, E2E-03: versioned approval-gated estimates."""

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.models import AuditEvent, Estimate, RequestEvent
from tests.factories import h, login, make_member, make_org
from tests.p3_helpers import (
    accepted_job,
    create_est,
    decide,
    est_body,
    make_item,
    submit_est,
)
from tests.req_helpers import make_world, seed_request
from tests.sched_helpers import API, S, triaged

# 90 min @ 500.00/h = 75000; 2 x 12050 = 24100; 1.5 x 333 = 499.5 -> 500 ; total 99600
EXPECTED_LABOR = 75000
EXPECTED_MATERIALS = 24100 + 500
EXPECTED_TOTAL = EXPECTED_LABOR + EXPECTED_MATERIALS


def test_create_draft_totals_stored_server_side(client, db, sw, hd):
    req = triaged(db, sw.w)
    r = create_est(client, hd, req)
    assert r.status_code == 201, r.text
    e = r.json()
    assert e["status"] == "DRAFT" and e["version"] == 1 and e["currency"] == "KGS"
    assert e["labor_cost_minor"] == EXPECTED_LABOR
    assert e["materials_total_minor"] == EXPECTED_MATERIALS
    assert e["total_minor"] == EXPECTED_TOTAL
    assert [ln["line_total_minor"] for ln in e["lines"]] == [24100, 500]
    assert e["created_by"]["membership_id"] == str(sw.w.disp[1].id)
    assert e["supersedes_id"] is None


def test_clients_cannot_set_totals(client, db, sw, hd):
    req = triaged(db, sw.w)
    for bad in (
        est_body(total_minor=1),
        est_body(labor_cost_minor=1),
        est_body(
            lines=[
                {"description": "x", "quantity": "1", "unit_price_minor": 1, "line_total_minor": 5}
            ]
        ),
    ):
        assert create_est(client, hd, req, **bad).status_code == 422


@pytest.mark.parametrize(
    "over",
    [
        {"labor_minutes": -1},
        {"labor_rate_minor": -5},
        {"lines": [{"description": "x", "quantity": "0", "unit_price_minor": 1}]},
        {"lines": [{"description": "x", "quantity": "-1", "unit_price_minor": 1}]},
        {"lines": [{"description": "x", "quantity": "1", "unit_price_minor": -1}]},
        {"lines": [{"description": "x", "quantity": "1.0001", "unit_price_minor": 1}]},
        {"lines": [{"description": "", "quantity": "1", "unit_price_minor": 1}]},
        {"lines": [{"description": "x", "quantity": "1"}]},  # no price, no item
    ],
)
def test_validation(client, db, sw, hd, over):
    req = triaged(db, sw.w)
    assert create_est(client, hd, req, **over).status_code == 422


def test_roles_and_states(client, db, sw, hd):
    req = triaged(db, sw.w)
    for who in ("tech", "req1"):
        assert create_est(client, hd, req, who=who).status_code == 403
    for st in (S.SUBMITTED, S.COMPLETED, S.CLOSED, S.CANCELED):
        other = seed_request(db, sw.w, status=st)
        assert create_est(client, hd, other).status_code == 409
    assert create_est(client, hd, req, who="admin").status_code == 201
    assert create_est(client, hd, req).status_code == 409  # one draft per request


def test_item_default_price_and_foreign_item(client, db, sw, hd):
    req = triaged(db, sw.w)
    item = make_item(db, sw.w.org, price=777)
    body = est_body(
        lines=[{"description": "Part", "quantity": "2", "inventory_item_id": str(item.id)}]
    )
    e = create_est(client, hd, req, **body).json()
    assert e["lines"][0]["unit_price_minor"] == 777 and e["lines"][0]["line_total_minor"] == 1554
    other = make_world(db, "Org B")
    foreign = make_item(db, other.org)
    body = est_body(
        lines=[{"description": "Part", "quantity": "1", "inventory_item_id": str(foreign.id)}]
    )
    assert (
        create_est(client, hd, seed_request(db, sw.w, status=S.TRIAGED), **body).status_code == 422
    )


def test_edit_draft_then_immutable_after_submit(client, db, sw, hd):
    req = triaged(db, sw.w)
    e = create_est(client, hd, req).json()
    r = client.patch(f"{API}/estimates/{e['id']}", json={"labor_minutes": 60}, headers=hd["disp"])
    assert r.status_code == 200 and r.json()["labor_cost_minor"] == 50000
    assert r.json()["total_minor"] == 50000 + EXPECTED_MATERIALS
    r = client.put(
        f"{API}/estimates/{e['id']}/lines",
        json={"lines": [{"description": "Only", "quantity": "3", "unit_price_minor": 10}]},
        headers=hd["disp"],
    )
    assert r.status_code == 200 and r.json()["materials_total_minor"] == 30
    assert r.json()["total_minor"] == 50030
    assert (
        client.patch(
            f"{API}/estimates/{e['id']}", json={"total_minor": 1}, headers=hd["disp"]
        ).status_code
        == 422
    )
    sub = submit_est(client, hd, e["id"])
    assert sub["status"] == "AWAITING_APPROVAL" and sub["submitted_by"]["membership_id"]
    for call in (
        lambda: client.patch(f"{API}/estimates/{e['id']}", json={"notes": "x"}, headers=hd["disp"]),
        lambda: client.put(
            f"{API}/estimates/{e['id']}/lines", json={"lines": []}, headers=hd["disp"]
        ),
    ):
        r = call()
        assert r.status_code == 409 and r.json()["error"]["code"] == "estimate_immutable"
    again = client.post(f"{API}/estimates/{e['id']}/submit", headers=hd["disp"])
    assert again.status_code == 409 and again.json()["error"]["code"] == "estimate_not_draft"


def test_db_trigger_blocks_direct_mutation_after_submit(client, db, sw, hd):
    req = triaged(db, sw.w)
    e = create_est(client, hd, req).json()
    # while DRAFT, direct SQL edits are fine
    db.execute(text("UPDATE estimates SET notes='ok' WHERE id=:i"), {"i": e["id"]})
    db.commit()
    submit_est(client, hd, e["id"])
    for sql in (
        "UPDATE estimates SET total_minor = 1 WHERE id=:i",
        "UPDATE estimates SET labor_minutes = 1 WHERE id=:i",
        "UPDATE estimates SET notes = 'x' WHERE id=:i",
        "UPDATE estimate_lines SET quantity = 9 WHERE estimate_id=:i",
        "DELETE FROM estimate_lines WHERE estimate_id=:i",
        "DELETE FROM estimates WHERE id=:i",
        "INSERT INTO estimate_lines (id, organization_id, estimate_id, position, description,"
        " quantity, unit_price_minor, line_total_minor) SELECT gen_random_uuid(), organization_id,"
        " id, 99, 'sneak', 1, 1, 1 FROM estimates WHERE id=:i",
    ):
        with pytest.raises(DBAPIError):
            db.execute(text(sql), {"i": e["id"]})
        db.rollback()
    # status changes (workflow) are still allowed
    db.execute(text("UPDATE estimates SET status='SUPERSEDED' WHERE id=:i"), {"i": e["id"]})
    db.commit()


def test_revision_v2_supersedes_v1_on_submit(client, db, sw, hd):
    req = triaged(db, sw.w)
    v1 = create_est(client, hd, req).json()
    submit_est(client, hd, v1["id"])
    v2 = create_est(client, hd, req, labor_minutes=30).json()
    assert v2["version"] == 2 and v2["supersedes_id"] == v1["id"]
    # v1 stays pending until v2 is submitted
    assert (
        client.get(f"{API}/estimates/{v1['id']}", headers=hd["disp"]).json()["status"]
        == "AWAITING_APPROVAL"
    )
    submit_est(client, hd, v2["id"])
    hist = client.get(f"{API}/requests/{req.id}/estimates", headers=hd["disp"]).json()
    assert [(x["version"], x["status"]) for x in hist] == [
        (1, "SUPERSEDED"),
        (2, "AWAITING_APPROVAL"),
    ]
    # a decision on the superseded version is refused (EST-06)
    r = decide(client, hd["req1"], v1)
    assert r.status_code == 409 and r.json()["error"]["code"] == "estimate_not_pending"


def test_decision_approve_reject_rules(client, db, sw, hd):
    req = triaged(db, sw.w)
    e = create_est(client, hd, req).json()
    # a DRAFT is invisible to the requester
    assert client.get(f"{API}/estimates/{e['id']}", headers=hd["req1"]).status_code == 404
    assert decide(client, hd["req1"], e).status_code == 404
    e = submit_est(client, hd, e["id"])
    assert client.get(f"{API}/estimates/{e['id']}", headers=hd["req1"]).status_code == 200
    # other requester of the same org -> 404; staff -> 403; no reason on reject -> 422
    assert decide(client, hd["req2"], e).status_code == 404
    assert decide(client, hd["disp"], e).status_code == 403
    assert decide(client, hd["req1"], e, "REJECT").status_code == 422
    assert decide(client, hd["req1"], e, "REJECT", reason="no").status_code == 422
    assert decide(client, hd["req1"], {**e, "version": 7}).status_code == 409  # wrong version
    r = decide(client, hd["req1"], e, "REJECT", reason="Too expensive for this fix")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "REJECTED" and out["decision_reason"] == "Too expensive for this fix"
    assert out["decided_by"]["membership_id"] == str(sw.w.req1[1].id) and out["decided_at"]
    again = decide(client, hd["req1"], e)
    assert again.status_code == 409 and again.json()["error"]["code"] == "estimate_not_pending"
    assert again.json()["error"]["details"]["estimate_status"] == "REJECTED"


def test_technician_cannot_decide_and_sees_only_approved(client, db, sw, hd):
    req = accepted_job(client, db, sw, hd)
    e = submit_est(client, hd, create_est(client, hd, req).json()["id"])
    assert decide(client, hd["tech"], e).status_code in (403, 404)  # pending: hidden from techs
    assert client.get(f"{API}/estimates/{e['id']}", headers=hd["tech"]).status_code == 404
    assert client.get(f"{API}/requests/{req.id}/estimates", headers=hd["tech"]).json() == []
    assert decide(client, hd["tech2"], e).status_code == 404  # not assigned at all
    assert decide(client, hd["req1"], e).status_code == 200
    r = client.get(f"{API}/estimates/{e['id']}", headers=hd["tech"])
    assert r.status_code == 200 and r.json()["notes"] is None and r.json()["labor_minutes"] == 90
    assert len(r.json()["lines"]) == 2
    detail = client.get(f"{API}/requests/{req.id}", headers=hd["tech"]).json()
    assert (
        detail["estimate"]["status"] == "APPROVED"
        and detail["estimate"]["total_minor"] == EXPECTED_TOTAL
    )


def test_idempotent_decision_replay(client, db, sw, hd):
    req = triaged(db, sw.w)
    e = submit_est(client, hd, create_est(client, hd, req).json()["id"])
    key = {"Idempotency-Key": "dec-1"}
    r1 = client.post(
        f"{API}/estimates/{e['id']}/decision",
        json={"version": 1, "decision": "APPROVE"},
        headers={**hd["req1"], **key},
    )
    r2 = client.post(
        f"{API}/estimates/{e['id']}/decision",
        json={"version": 1, "decision": "APPROVE"},
        headers={**hd["req1"], **key},
    )
    assert r1.status_code == r2.status_code == 200
    assert r1.json() == r2.json() and r2.headers["Idempotent-Replayed"] == "true"
    r3 = client.post(
        f"{API}/estimates/{e['id']}/decision",
        json={"version": 1, "decision": "REJECT", "reason": "changed my mind"},
        headers={**hd["req1"], **key},
    )
    assert r3.status_code == 409 and r3.json()["error"]["code"] == "idempotency_key_reused"
    n = db.scalar(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "estimate.decide")
    )
    assert n == 1


def test_concurrent_decisions_exactly_one_wins(client, db, sw, hd):
    from tests.test_assignment_concurrency import race

    for _ in range(4):
        req = triaged(db, sw.w)
        e = submit_est(client, hd, create_est(client, hd, req).json()["id"])
        url = f"{API}/estimates/{e['id']}/decision"
        a = {"version": e["version"], "decision": "APPROVE"}
        b = {"version": e["version"], "decision": "REJECT", "reason": "I disagree with it"}
        res = race(
            client.app,
            [
                lambda c, a=a, url=url: c.post(url, json=a, headers=hd["req1"]),
                lambda c, b=b, url=url: c.post(url, json=b, headers=hd["req1"]),
            ],
        )
        assert sorted(r.status_code for r in res) == [200, 409], [r.text for r in res]
        loser = next(r for r in res if r.status_code == 409)
        assert loser.json()["error"]["code"] == "estimate_not_pending"
        db.expire_all()
        st = db.scalar(select(Estimate.status).where(Estimate.id == e["id"]))
        assert st.value == ("APPROVED" if res[0].status_code == 200 else "REJECTED")
        n = db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "estimate.decide", AuditEvent.target_id == e["id"])
        )
        assert n == 1
        evs = list(
            db.scalars(
                select(RequestEvent.type).where(
                    RequestEvent.request_id == req.id,
                    RequestEvent.type.in_(["ESTIMATE_APPROVED", "ESTIMATE_REJECTED"]),
                )
            )
        )
        assert len(evs) == 1


def test_decision_vs_new_submission_race_never_approves_wrong_version(client, db, sw, hd):
    from tests.test_assignment_concurrency import race

    for _ in range(3):
        req = triaged(db, sw.w)
        v1 = submit_est(client, hd, create_est(client, hd, req).json()["id"])
        v2 = create_est(client, hd, req, labor_minutes=10).json()
        res = race(
            client.app,
            [
                lambda c, v1=v1: c.post(
                    f"{API}/estimates/{v1['id']}/decision",
                    json={"version": 1, "decision": "APPROVE"},
                    headers=hd["req1"],
                ),
                lambda c, v2=v2: c.post(f"{API}/estimates/{v2['id']}/submit", headers=hd["disp"]),
            ],
        )
        assert res[1].status_code == 200
        db.expire_all()
        s = {
            e.version: e.status.value
            for e in db.scalars(select(Estimate).where(Estimate.request_id == req.id))
        }
        assert s[2] == "AWAITING_APPROVAL" and s[1] == "SUPERSEDED"  # approval never leaks to v2


def test_e2e_03_start_gate_full_flow(client, db, sw, hd):
    req = accepted_job(client, db, sw, hd)
    start = lambda: client.post(f"{API}/requests/{req.id}/start", headers=hd["tech"])  # noqa: E731
    v1 = submit_est(client, hd, create_est(client, hd, req).json()["id"])
    detail = client.get(f"{API}/requests/{req.id}", headers=hd["tech"]).json()
    assert "start" not in detail["allowed_actions"] and detail["estimate"] is None
    r = start()
    assert r.status_code == 409 and r.json()["error"]["code"] == "estimate_not_approved"
    assert r.json()["error"]["details"]["estimate_status"] == "AWAITING_APPROVAL"
    mine = client.get(f"{API}/me/assignments", headers=hd["tech"]).json()["items"][0]
    assert (
        mine["estimate_status"] == "AWAITING_APPROVAL" and "approve" in mine["start_blocked_reason"]
    )
    assert "start" not in mine["allowed_actions"]
    # requester rejects -> still blocked
    assert (
        decide(client, hd["req1"], v1, "REJECT", reason="Please lower the labor").status_code == 200
    )
    r = start()
    assert r.status_code == 409 and r.json()["error"]["details"]["estimate_status"] == "REJECTED"
    mine = client.get(f"{API}/me/assignments", headers=hd["tech"]).json()["items"][0]
    assert mine["estimate_status"] == "REJECTED" and "rejected" in mine["start_blocked_reason"]
    # dispatcher revises
    v2 = create_est(client, hd, req, labor_minutes=45).json()
    assert v2["version"] == 2 and v2["supersedes_id"] == v1["id"]
    v2 = submit_est(client, hd, v2["id"])
    assert start().status_code == 409
    assert decide(client, hd["req1"], v2).status_code == 200
    r = start()
    assert r.status_code == 200 and r.json()["status"] == "IN_PROGRESS"
    # history: versions, actors, totals
    hist = client.get(f"{API}/requests/{req.id}/estimates", headers=hd["disp"]).json()
    assert [(x["version"], x["status"]) for x in hist] == [(1, "SUPERSEDED"), (2, "APPROVED")]
    assert hist[0]["decision_reason"] == "Please lower the labor"
    assert hist[0]["decided_by"]["membership_id"] == str(sw.w.req1[1].id)
    assert hist[1]["decided_by"]["membership_id"] == str(sw.w.req1[1].id)
    assert hist[1]["total_minor"] == 37500 + EXPECTED_MATERIALS
    assert hist[1]["submitted_by"]["membership_id"] == str(sw.w.disp[1].id)
    types = [
        t["type"]
        for t in client.get(f"{API}/requests/{req.id}", headers=hd["req1"]).json()["timeline"]
    ]
    for t in ("ESTIMATE_SUBMITTED", "ESTIMATE_REJECTED", "ESTIMATE_APPROVED"):
        assert t in types
    # request detail for requester shows the current estimate; materials hidden
    d = client.get(f"{API}/requests/{req.id}", headers=hd["req1"]).json()
    assert (
        d["estimate"]["version"] == 2
        and d["estimate"]["currency"] == "KGS"
        and d["materials"] == []
    )


def test_withdraw_rejected_opens_gate_and_no_estimate_means_open(client, db, sw, hd):
    req = accepted_job(client, db, sw, hd)
    v1 = submit_est(client, hd, create_est(client, hd, req).json()["id"])
    decide(client, hd["req1"], v1, "REJECT", reason="No thanks, too much")
    assert client.post(f"{API}/requests/{req.id}/start", headers=hd["tech"]).status_code == 409
    # only staff withdraw; reason required
    assert (
        client.post(
            f"{API}/estimates/{v1['id']}/withdraw",
            json={"reason": "withdrawn ok"},
            headers=hd["tech"],
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"{API}/estimates/{v1['id']}/withdraw", json={"reason": "x"}, headers=hd["disp"]
        ).status_code
        == 422
    )
    r = client.post(
        f"{API}/estimates/{v1['id']}/withdraw",
        json={"reason": "Customer declined work"},
        headers=hd["disp"],
    )
    assert r.status_code == 200 and r.json()["status"] == "SUPERSEDED"
    assert r.json()["withdrawn_by"]["membership_id"] == str(sw.w.disp[1].id)
    again = client.post(
        f"{API}/estimates/{v1['id']}/withdraw",
        json={"reason": "Customer declined work"},
        headers=hd["disp"],
    )
    assert again.status_code == 409
    assert client.post(f"{API}/requests/{req.id}/start", headers=hd["tech"]).status_code == 200
    # never-estimated job starts freely
    req2 = accepted_job(client, db, sw, hd)
    assert client.post(f"{API}/requests/{req2.id}/start", headers=hd["tech"]).status_code == 200


def test_withdraw_pending_resumes_and_draft_does_not_gate(client, db, sw, hd):
    req = accepted_job(client, db, sw, hd)
    create_est(client, hd, req)  # an unsent DRAFT never blocks
    d = client.get(f"{API}/requests/{req.id}", headers=hd["disp"]).json()
    assert d["estimate"]["status"] == "DRAFT"
    e = client.get(f"{API}/requests/{req.id}/estimates", headers=hd["disp"]).json()[0]
    submit_est(client, hd, e["id"])
    r = client.post(
        f"{API}/estimates/{e['id']}/withdraw",
        json={"reason": "Sent by mistake"},
        headers=hd["disp"],
    )
    assert r.status_code == 200
    types = [
        t["type"]
        for t in client.get(f"{API}/requests/{req.id}", headers=hd["disp"]).json()["timeline"]
    ]
    assert "ESTIMATE_WITHDRAWN" in types
    assert client.post(f"{API}/requests/{req.id}/start", headers=hd["tech"]).status_code == 200


def test_staff_list_and_cross_org_denial(client, db, sw, hd):
    req = triaged(db, sw.w)
    e = create_est(client, hd, req).json()
    submit_est(client, hd, e["id"])
    lst = client.get(
        f"{API}/estimates?status=AWAITING_APPROVAL&request_id={req.id}", headers=hd["admin"]
    ).json()
    assert lst["total"] == 1 and lst["items"][0]["id"] == e["id"]
    assert client.get(f"{API}/estimates", headers=hd["req1"]).status_code == 403
    assert client.get(f"{API}/estimates", headers=hd["tech"]).status_code == 403
    # other organization's staff
    other = make_world(db, "Org B")
    ho = h(login(client, other.admin[0]), other.org)
    assert client.get(f"{API}/estimates/{e['id']}", headers=ho).status_code == 404
    assert client.get(f"{API}/requests/{req.id}/estimates", headers=ho).status_code == 404
    assert (
        client.patch(f"{API}/estimates/{e['id']}", json={"notes": "x"}, headers=ho).status_code
        == 404
    )
    assert (
        client.post(
            f"{API}/estimates/{e['id']}/withdraw", json={"reason": "hack attempt"}, headers=ho
        ).status_code
        == 404
    )
    assert client.get(f"{API}/estimates", headers=ho).json()["total"] == 0


def test_same_user_second_org_cannot_touch_estimate(client, db, sw, hd):
    """A user who is staff in org B (via X-Org-Id) cannot reach org A's estimate by id."""
    req = triaged(db, sw.w)
    e = create_est(client, hd, req).json()
    org_b = make_org(db, "Org B2")
    user, _ = make_member(
        db, org_b, __import__("app.models", fromlist=["x"]).MembershipRole.ADMIN, user=sw.w.admin[0]
    )
    ho = h(login(client, user), org_b)
    assert client.get(f"{API}/estimates/{e['id']}", headers=ho).status_code == 404
