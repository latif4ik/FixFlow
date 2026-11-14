"""COMM-03/04: in-app notifications are wired to the events and scoped to the recipient + org."""

from sqlalchemy import func, select

from app.models import MembershipRole, Notification
from app.services import notifications as svc
from tests.factories import h, login, make_member, make_org
from tests.p3_helpers import (
    accepted_job,
    add_completion_file,
    create_est,
    decide,
    in_progress_job,
    submit_est,
)
from tests.req_helpers import make_world
from tests.sched_helpers import API, assign, iso, local_slot, triaged


def mine(client, headers, **params):
    r = client.get(f"{API}/notifications", headers=headers, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def types(client, headers):
    return [n["type"] for n in mine(client, headers)["items"]]


def unread(client, headers):
    return client.get(f"{API}/notifications/unread-count", headers=headers).json()["unread"]


def test_assignment_events_notify_technician(client, db, sw, hd):
    req = triaged(db, sw.w)
    s, e = local_slot(5, 10)
    assert assign(client, hd, req, sw.w.tech, s, e).status_code == 201
    assert types(client, hd["tech"]) == ["ASSIGNMENT_CREATED"]
    n = mine(client, hd["tech"])["items"][0]
    assert n["request_id"] == str(req.id) and n["read_at"] is None and n["data"]["assignment_id"]
    assert types(client, hd["disp"]) == [] and types(client, hd["req1"]) == []  # actor/others: none
    # reschedule to the other technician: new tech told, old tech told it was removed
    s2, e2 = local_slot(6, 11)
    r = client.put(
        f"{API}/requests/{req.id}/assignment",
        json={
            "technician_membership_id": str(sw.tech2[1].id),
            "start_at": iso(s2),
            "end_at": iso(e2),
            "reason": "Moved",
        },
        headers=hd["disp"],
    )
    assert r.status_code == 200, r.text
    assert types(client, hd["tech2"]) == ["ASSIGNMENT_RESCHEDULED"]
    assert types(client, hd["tech"]) == ["ASSIGNMENT_REMOVED", "ASSIGNMENT_CREATED"]
    # same technician, new time: RESCHEDULED only
    s3, e3 = local_slot(7, 11)
    r = client.put(
        f"{API}/requests/{req.id}/assignment",
        json={
            "technician_membership_id": str(sw.tech2[1].id),
            "start_at": iso(s3),
            "end_at": iso(e3),
        },
        headers=hd["admin"],
    )
    assert r.status_code == 200
    assert types(client, hd["tech2"]) == ["ASSIGNMENT_RESCHEDULED", "ASSIGNMENT_RESCHEDULED"]
    # unassign
    r = client.post(
        f"{API}/requests/{req.id}/assignment/unassign",
        json={"reason": "Customer postponed"},
        headers=hd["disp"],
    )
    assert r.status_code == 200
    assert types(client, hd["tech2"])[0] == "ASSIGNMENT_REMOVED"


def test_decline_notifies_staff_not_actor(client, db, sw, hd):
    req = triaged(db, sw.w)
    s, e = local_slot(5, 10)
    assign(client, hd, req, sw.w.tech, s, e)
    r = client.post(
        f"{API}/requests/{req.id}/decline", json={"reason": "Sick today"}, headers=hd["tech"]
    )
    assert r.status_code == 200
    for who in ("admin", "disp"):
        got = mine(client, hd[who])["items"]
        assert [n["type"] for n in got] == ["ASSIGNMENT_DECLINED"] and "Sick today" in got[0][
            "body"
        ]
    assert types(client, hd["tech"]) == ["ASSIGNMENT_CREATED"]  # no self-notification
    assert types(client, hd["req1"]) == []


def test_estimate_events_notify_requester_then_staff(client, db, sw, hd):
    req = triaged(db, sw.w)
    e = submit_est(client, hd, create_est(client, hd, req).json()["id"])
    got = mine(client, hd["req1"])["items"]
    assert [n["type"] for n in got] == ["ESTIMATE_SUBMITTED"] and got[0]["data"]["version"] == 1
    assert types(client, hd["req2"]) == [] and types(client, hd["disp"]) == []
    assert decide(client, hd["req1"], e, "REJECT", reason="Too pricey for me").status_code == 200
    for who in ("admin", "disp"):
        got = mine(client, hd[who])["items"]
        assert [n["type"] for n in got] == ["ESTIMATE_DECIDED"]
        assert got[0]["data"]["decision"] == "REJECTED"


def test_completion_and_rework_notifications(client, db, sw, hd):
    req = in_progress_job(client, db, sw, hd)
    add_completion_file(db, sw.w.org, req, sw.w.tech[1])
    r = client.post(
        f"{API}/requests/{req.id}/complete",
        json={"note": "Fixed the leak and tested."},
        headers=hd["tech"],
    )
    assert r.status_code == 200
    assert types(client, hd["req1"]) == ["JOB_COMPLETED"]
    assert types(client, hd["admin"]) == ["JOB_COMPLETED"] and types(client, hd["disp"]) == [
        "JOB_COMPLETED"
    ]
    assert "JOB_COMPLETED" not in types(client, hd["tech"])  # actor excluded
    assert types(client, hd["req2"]) == []
    r = client.post(
        f"{API}/requests/{req.id}/reopen",
        json={"reason": "Still leaking a bit"},
        headers=hd["req1"],
    )
    assert r.status_code == 200, r.text
    assert types(client, hd["admin"])[0] == "REWORK_REQUESTED"
    assert types(client, hd["disp"])[0] == "REWORK_REQUESTED"
    assert "REWORK_REQUESTED" not in types(client, hd["req1"])


def test_unread_count_mark_read_read_all_and_pagination(client, db, sw, hd):
    for i in range(3):
        req = triaged(db, sw.w)
        s, e = local_slot(5 + i, 10)
        assign(client, hd, req, sw.w.tech, s, e)
    assert unread(client, hd["tech"]) == 3
    page = mine(client, hd["tech"], page_size=2)
    assert page["total"] == 3 and len(page["items"]) == 2
    times = [n["created_at"] for n in mine(client, hd["tech"])["items"]]
    assert times == sorted(times, reverse=True)  # newest first
    first = page["items"][0]["id"]
    r = client.post(f"{API}/notifications/{first}/read", headers=hd["tech"])
    assert r.status_code == 200 and r.json()["read_at"]
    r2 = client.post(f"{API}/notifications/{first}/read", headers=hd["tech"])  # idempotent
    assert r2.json()["read_at"] == r.json()["read_at"]
    assert unread(client, hd["tech"]) == 2
    assert mine(client, hd["tech"], unread_only="true")["total"] == 2
    r = client.post(f"{API}/notifications/read-all", headers=hd["tech"])
    assert r.json()["marked"] == 2 and unread(client, hd["tech"]) == 0
    assert mine(client, hd["tech"], unread_only="true")["total"] == 0
    assert mine(client, hd["tech"])["total"] == 3
    assert client.post(f"{API}/notifications/read-all", headers=hd["tech"]).json()["marked"] == 0


def test_cannot_read_or_enumerate_others_notifications(client, db, sw, hd):
    req = triaged(db, sw.w)
    s, e = local_slot(5, 10)
    assign(client, hd, req, sw.w.tech, s, e)
    nid = mine(client, hd["tech"])["items"][0]["id"]
    for who in ("tech2", "disp", "admin", "req1"):
        assert client.post(f"{API}/notifications/{nid}/read", headers=hd[who]).status_code == 404
        assert mine(client, hd[who])["total"] == 0
    # read-all by someone else never touches it
    client.post(f"{API}/notifications/read-all", headers=hd["tech2"])
    assert unread(client, hd["tech"]) == 1
    # other org
    other = make_world(db, "Org B")
    ho = h(login(client, other.admin[0]), other.org)
    assert client.post(f"{API}/notifications/{nid}/read", headers=ho).status_code == 404
    assert client.post(f"{API}/notifications/{nid}/read", headers={}).status_code in (400, 401)
    assert (
        client.post(
            f"{API}/notifications/00000000-0000-0000-0000-000000000000/read", headers=hd["tech"]
        ).status_code
        == 404
    )


def test_org_scoping_same_user_two_orgs(client, db, sw, hd):
    req = triaged(db, sw.w)
    s, e = local_slot(5, 10)
    assign(client, hd, req, sw.w.tech, s, e)
    org_b = make_org(db, "Org B3")
    _, m_b = make_member(db, org_b, MembershipRole.TECHNICIAN, user=sw.w.tech[0])
    tok = login(client, sw.w.tech[0])
    in_a, in_b = h(tok, sw.w.org), h(tok, org_b)
    assert unread(client, in_a) == 1 and unread(client, in_b) == 0
    assert mine(client, in_b)["total"] == 0
    nid = mine(client, in_a)["items"][0]["id"]
    assert client.post(f"{API}/notifications/{nid}/read", headers=in_b).status_code == 404
    # a notification created for the org-B membership is invisible in org A
    svc.notify(db, org_b.id, [m_b.id], "TEST", "hi", "there")
    db.commit()
    assert unread(client, in_b) == 1 and unread(client, in_a) == 1


def test_notify_dedupe_and_recipient_rules(db, sw):
    org = sw.w.org
    tech = sw.w.tech[1].id
    assert svc.notify(db, org.id, [tech, tech, None], "T", "t", "b", dedupe_key="k1") == 1
    assert svc.notify(db, org.id, [tech], "T", "t", "b", dedupe_key="k1") == 0  # deduped
    assert svc.notify(db, org.id, [tech], "T", "t", "b", exclude=tech) == 0
    db.commit()
    assert db.scalar(select(func.count()).select_from(Notification)) == 1
    staff = set(svc.staff_recipients(db, org.id))
    assert staff == {sw.w.admin[1].id, sw.w.disp[1].id}
    # unknown membership id (other org's member) is rejected by the composite FK
    other = make_world(db, "Org X")
    import pytest
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        svc.notify(db, org.id, [other.tech[1].id], "T", "t", "b")
    db.rollback()


def test_accepted_job_fixture_notifications_isolated(client, db, sw, hd):
    accepted_job(client, db, sw, hd)
    assert unread(client, hd["tech"]) == 1  # the assignment
