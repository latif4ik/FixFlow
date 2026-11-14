"""Assignment + technician lifecycle through the API (SCHED-03..07, LIFE-02..07, ROLE-03/05)."""

from datetime import timedelta

from sqlalchemy import func, select

from app.models import Assignment, AuditEvent, Membership, RequestEvent, ServiceRequest
from app.models.enums import AssignmentStatus as A
from tests.req_helpers import LONG_DESC, image_bytes, payload, seed_request, upload
from tests.sched_helpers import API, S, assign, iso, local_slot, triaged

NOTE = "Replaced the faulty valve and tested the flow."


def act(client, hd, who, req, action, **body):
    return client.post(f"{API}/requests/{req.id}/{action}", json=body, headers=hd[who])


def status_of(db, req):
    db.expire_all()
    return db.get(ServiceRequest, req.id).status


def rows(db, req):
    db.expire_all()
    return list(
        db.scalars(
            select(Assignment)
            .where(Assignment.request_id == req.id)
            .order_by(Assignment.created_at)
        )
    )


def put(client, hd, req, tech, s, e, who="disp", **extra):
    return client.put(
        f"{API}/requests/{req.id}/assignment",
        json={
            "technician_membership_id": str(tech[1].id),
            "start_at": iso(s),
            "end_at": iso(e),
            **extra,
        },
        headers=hd[who],
    )


# ---------------- E2E-01 backend part ----------------
def test_full_lifecycle_via_api(client, db, sw, hd):
    w = sw.w
    r = client.post(f"{API}/requests", json=payload(w), headers=hd["req1"])
    assert r.status_code == 201
    rid = r.json()["id"]
    assert (
        client.post(f"{API}/requests/{rid}/triage", json={}, headers=hd["disp"]).status_code == 200
    )
    s, e = local_slot(2, 10)
    cands = client.get(
        f"{API}/requests/{rid}/candidates",
        params={"start_at": iso(s), "end_at": iso(e)},
        headers=hd["disp"],
    ).json()
    assert {c["membership_id"] for c in cands if c["eligible"]} == {
        str(w.tech[1].id),
        str(sw.tech2[1].id),
    }

    class Ref:  # light request stand-in for helpers taking .id
        id = rid

    ref = Ref()
    r = assign(client, hd, ref, w.tech, s, e)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["request"]["status"] == "SCHEDULED" and body["assignment"]["status"] == "ACTIVE"
    assert body["assignment"]["technician"]["name"]
    # starting before accepting is a 409
    assert act(client, hd, "tech", ref, "start").status_code == 409
    assert act(client, hd, "tech", ref, "accept").status_code == 200
    d = act(client, hd, "tech", ref, "start").json()
    assert d["status"] == "IN_PROGRESS"
    n = client.post(
        f"{API}/requests/{rid}/notes", json={"body": "Found the leaking valve."}, headers=hd["tech"]
    )
    assert n.status_code == 201
    # completion guards: short note, then missing image
    assert act(client, hd, "tech", ref, "complete", note="too short").status_code == 422
    r = act(client, hd, "tech", ref, "complete", note=NOTE)
    assert r.status_code == 422
    assert "completion_images" in [x["field"] for x in r.json()["error"]["details"]]
    up = upload(client, hd["tech"], rid, image_bytes(), purpose="COMPLETION", name="done.png")
    assert up.status_code == 201, up.text
    done = act(client, hd, "tech", ref, "complete", note=NOTE)
    assert done.status_code == 200 and done.json()["status"] == "COMPLETED"
    assert done.json()["assignment"]["status"] == "COMPLETED"
    closed = client.post(f"{API}/requests/{rid}/close", json={}, headers=hd["req1"])
    assert closed.status_code == 200 and closed.json()["status"] == "CLOSED"

    tl = client.get(f"{API}/requests/{rid}/timeline?page_size=100", headers=hd["disp"]).json()[
        "items"
    ]
    seq = [
        i["to_status"] if i["type"] == "STATUS_CHANGED" else i["type"]
        for i in tl
        if i["type"] in ("REQUEST_CREATED", "STATUS_CHANGED", "ASSIGNED")
    ]
    assert seq == [
        "REQUEST_CREATED",
        "TRIAGED",
        "ASSIGNED",
        "SCHEDULED",
        "ACCEPTED",
        "IN_PROGRESS",
        "COMPLETED",
        "CLOSED",
    ]
    # requesters never see assignment internals in the timeline
    rt = client.get(f"{API}/requests/{rid}/timeline?page_size=100", headers=hd["req1"]).json()
    assert "ASSIGNED" not in {i["type"] for i in rt["items"]}
    # slot freed: another job can take the same window
    other = triaged(db, w)
    assert assign(client, hd, other, w.tech, s, e).status_code == 201
    hist = client.get(f"{API}/requests/{rid}/assignments", headers=hd["disp"]).json()
    assert [h["status"] for h in hist] == ["COMPLETED"]
    # technician keeps read access to completed job
    assert client.get(f"{API}/requests/{rid}", headers=hd["tech"]).status_code == 200


def test_assignment_visible_in_detail_for_requester_without_contact_leak(client, db, sw, hd):
    req = triaged(db, sw.w)
    s, e = local_slot(2, 10)
    assert assign(client, hd, req, sw.w.tech, s, e).status_code == 201
    d = client.get(f"{API}/requests/{req.id}", headers=hd["req1"]).json()
    assert d["assignment"]["technician"]["name"] and d["appointment"]["start_at"]
    assert "email" not in str(d["assignment"]) and "phone" not in str(d["assignment"])
    assert "cancel" not in d["allowed_actions"]  # requesters cannot cancel once scheduled
    # actions by role
    dt = client.get(f"{API}/requests/{req.id}", headers=hd["tech"]).json()
    assert {"accept", "decline"} <= set(dt["allowed_actions"])
    assert not ({"assign", "unassign", "reschedule"} & set(dt["allowed_actions"]))
    ds = client.get(f"{API}/requests/{req.id}", headers=hd["disp"]).json()["allowed_actions"]
    assert {"unassign", "reschedule", "cancel"} <= set(ds) and "accept" not in ds
    t2 = client.get(f"{API}/requests/{req.id}", headers=hd["tech2"])
    assert t2.status_code == 404
    tri = triaged(db, sw.w)
    assert (
        "assign"
        in client.get(f"{API}/requests/{tri.id}", headers=hd["disp"]).json()["allowed_actions"]
    )


# ---------------- decline / unassign / reschedule ----------------
def test_decline_returns_to_triaged_and_preserves_history(client, db, sw, hd):
    req = triaged(db, sw.w)
    s, e = local_slot(2, 10)
    assert assign(client, hd, req, sw.w.tech, s, e).status_code == 201
    assert act(client, hd, "tech", req, "decline").status_code == 422  # reason required
    assert act(client, hd, "tech2", req, "decline", reason="not mine to decline").status_code == 404
    r = act(client, hd, "tech", req, "decline", reason="Vehicle broke down today")
    assert r.status_code == 200, r.text
    assert r.json()["assignment"]["status"] == "DECLINED"
    assert status_of(db, req) == S.TRIAGED
    (row,) = rows(db, req)
    assert row.status == A.DECLINED and row.active is False and row.released_at
    assert row.released_reason == "Vehicle broke down today"
    # technician lost visibility
    assert client.get(f"{API}/requests/{req.id}", headers=hd["tech"]).status_code == 404
    assert (
        client.get(f"{API}/me/assignments?scope=upcoming", headers=hd["tech"]).json()["total"] == 0
    )
    # slot freed -> reassign to another tech, even the same one for the same window
    assert assign(client, hd, req, sw.tech2, s, e).status_code == 201
    other = triaged(db, sw.w)
    assert assign(client, hd, other, sw.w.tech, s, e).status_code == 201
    hist = client.get(f"{API}/requests/{req.id}/assignments", headers=hd["disp"]).json()
    assert [h["status"] for h in hist] == ["DECLINED", "ACTIVE"]
    # technician history shows only own rows
    assert client.get(f"{API}/requests/{req.id}/assignments", headers=hd["tech"]).status_code == 404
    ev = db.scalars(select(RequestEvent.type).where(RequestEvent.request_id == req.id)).all()
    assert "DECLINED" in ev


def test_cannot_decline_after_start(client, db, sw, hd):
    req = triaged(db, sw.w)
    s, e = local_slot(2, 10)
    assign(client, hd, req, sw.w.tech, s, e)
    act(client, hd, "tech", req, "accept")
    act(client, hd, "tech", req, "start")
    r = act(client, hd, "tech", req, "decline", reason="changed my mind")
    assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_transition"


def test_unassign_requires_reason_and_keeps_row(client, db, sw, hd):
    req = triaged(db, sw.w)
    s, e = local_slot(2, 10)
    assign(client, hd, req, sw.w.tech, s, e)
    url = f"{API}/requests/{req.id}/assignment/unassign"
    assert client.post(url, json={}, headers=hd["disp"]).status_code == 422
    assert client.post(url, json={"reason": "no"}, headers=hd["disp"]).status_code == 422
    assert client.post(url, json={"reason": "valid reason"}, headers=hd["tech"]).status_code == 403
    r = client.post(url, json={"reason": "Customer asked to postpone"}, headers=hd["disp"])
    assert r.status_code == 200, r.text
    assert (
        r.json()["assignment"]["status"] == "UNASSIGNED"
        and r.json()["request"]["status"] == "TRIAGED"
    )
    assert [x.status for x in rows(db, req)] == [A.UNASSIGNED]
    # unassigning again is a clean 409
    assert client.post(url, json={"reason": "valid reason"}, headers=hd["disp"]).status_code == 409


def test_reschedule_from_accepted_requires_reaccept(client, db, sw, hd):
    req = triaged(db, sw.w)
    s, e = local_slot(2, 10)
    assign(client, hd, req, sw.w.tech, s, e)
    act(client, hd, "tech", req, "accept")
    assert status_of(db, req) == S.ACCEPTED
    s2, e2 = local_slot(3, 14)
    r = put(client, hd, req, sw.w.tech, s2, e2, reason="Customer moved the visit")
    assert r.status_code == 200, r.text
    assert r.json()["request"]["status"] == "SCHEDULED"
    old, new = rows(db, req)
    assert (old.status, old.active) == (A.RESCHEDULED, False)
    assert (new.status, new.active, new.start_at) == (A.ACTIVE, True, s2)
    assert act(client, hd, "tech", req, "start").status_code == 409  # must accept again
    assert act(client, hd, "tech", req, "accept").status_code == 200
    sc = db.scalars(
        select(RequestEvent).where(
            RequestEvent.request_id == req.id, RequestEvent.type == "STATUS_CHANGED"
        )
    ).all()
    assert [x.to_status for x in sc] == [
        "SCHEDULED",
        "ACCEPTED",
        "TRIAGED",
        "SCHEDULED",
        "ACCEPTED",
    ]
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "assignment.rescheduled")
        )
        == 1
    )


def test_reschedule_into_own_old_slot_and_to_other_tech(client, db, sw, hd):
    req = triaged(db, sw.w)
    s, e = local_slot(2, 10)
    assign(client, hd, req, sw.w.tech, s, e)
    # same technician, partially overlapping their OWN old slot: must not conflict with it
    assert (
        put(
            client, hd, req, sw.w.tech, s + timedelta(minutes=30), e + timedelta(minutes=30)
        ).status_code
        == 200
    )
    # reassign to the other technician
    r = put(client, hd, req, sw.tech2, s, e)
    assert r.status_code == 200
    assert r.json()["assignment"]["technician"]["membership_id"] == str(sw.tech2[1].id)
    assert [x.status for x in rows(db, req)] == [A.RESCHEDULED, A.RESCHEDULED, A.ACTIVE]
    # former technician no longer sees the job
    assert client.get(f"{API}/requests/{req.id}", headers=hd["tech"]).status_code == 404


def test_reschedule_into_overlap_with_other_job_is_rejected_atomically(client, db, sw, hd):
    a, b = triaged(db, sw.w), triaged(db, sw.w)
    sa, ea = local_slot(2, 10)
    sb, eb = local_slot(2, 14)
    assign(client, hd, a, sw.w.tech, sa, ea)
    assign(client, hd, b, sw.w.tech, sb, eb)
    r = put(client, hd, b, sw.w.tech, sa + timedelta(minutes=30), ea + timedelta(minutes=30))
    assert r.status_code == 422 and r.json()["error"]["code"] == "technician_ineligible"
    assert r.json()["error"]["details"]["reasons"][0]["code"] == "overlap"
    # nothing changed for b
    assert status_of(db, b) == S.SCHEDULED
    assert [(x.status, x.start_at) for x in rows(db, b)] == [(A.ACTIVE, sb)]


def test_reschedule_only_before_work_begins(client, db, sw, hd):
    req = triaged(db, sw.w)
    s, e = local_slot(2, 10)
    assign(client, hd, req, sw.w.tech, s, e)
    act(client, hd, "tech", req, "accept")
    act(client, hd, "tech", req, "start")
    s2, e2 = local_slot(3, 10)
    assert put(client, hd, req, sw.w.tech, s2, e2).status_code == 409
    assert (
        client.post(
            f"{API}/requests/{req.id}/assignment/unassign",
            json={"reason": "valid reason"},
            headers=hd["disp"],
        ).status_code
        == 409
    )


def test_block_and_resume(client, db, sw, hd):
    req = triaged(db, sw.w)
    s, e = local_slot(2, 10)
    assign(client, hd, req, sw.w.tech, s, e)
    act(client, hd, "tech", req, "accept")
    act(client, hd, "tech", req, "start")
    assert act(client, hd, "tech", req, "block").status_code == 422
    assert (
        act(client, hd, "tech", req, "block", reason="Waiting for part").json()["status"]
        == "BLOCKED"
    )
    # BLOCKED still reserves the slot
    other = triaged(db, sw.w)
    assert assign(client, hd, other, sw.w.tech, s, e).status_code == 422
    assert act(client, hd, "tech", req, "resume").status_code == 422
    r = act(client, hd, "tech", req, "resume", note="Part arrived")
    assert r.status_code == 200 and r.json()["status"] == "IN_PROGRESS"


# ---------------- permissions ----------------
def test_permissions(client, db, sw, hd):
    req = triaged(db, sw.w)
    s, e = local_slot(2, 10)
    for who in ("req1", "tech", "req2"):
        assert assign(client, hd, req, sw.w.tech, s, e, who=who).status_code == 403
    assert assign(client, hd, req, sw.w.tech, s, e, who="admin").status_code == 201
    # other technician: cannot see/accept someone else's job
    assert act(client, hd, "tech2", req, "accept").status_code == 404
    assert client.get(f"{API}/requests/{req.id}", headers=hd["tech2"]).status_code == 404
    # requester cannot act as technician
    assert act(client, hd, "req1", req, "accept").status_code == 403
    assert act(client, hd, "disp", req, "accept").status_code == 403
    assert client.get(f"{API}/requests/{req.id}/assignments", headers=hd["req1"]).status_code == 403
    assert client.get(f"{API}/me/assignments", headers=hd["disp"]).status_code == 403
    assert (
        client.get(
            f"{API}/schedule", params={"from": iso(s), "to": iso(e)}, headers=hd["tech"]
        ).status_code
        == 403
    )
    # generic transitions endpoint cannot do internal transitions
    for to in ("SCHEDULED", "TRIAGED"):
        r = client.post(
            f"{API}/requests/{req.id}/transitions",
            json={"to_status": to, "reason": "valid reason"},
            headers=hd["disp"],
        )
        assert r.status_code == 409, (to, r.text)
    tri = triaged(db, sw.w)
    r = client.post(
        f"{API}/requests/{tri.id}/transitions", json={"to_status": "SCHEDULED"}, headers=hd["disp"]
    )
    assert r.status_code == 409
    assert [x.status for x in rows(db, tri)] == []


def test_other_org_staff_gets_404(client, db, sw, hd):
    from tests.factories import h, login
    from tests.sched_helpers import make_sched_world

    other = make_sched_world(db, "Org B")
    ho = h(login(client, other.w.disp[0]), other.w.org)
    req = triaged(db, sw.w)
    s, e = local_slot(2, 10)
    assert client.get(f"{API}/requests/{req.id}/candidates", headers=ho).status_code == 404
    r = client.post(
        f"{API}/requests/{req.id}/assignment",
        json={
            "technician_membership_id": str(other.w.tech[1].id),
            "start_at": iso(s),
            "end_at": iso(e),
        },
        headers=ho,
    )
    assert r.status_code == 404
    # cross-org technician id for own request: ineligible, not a leak
    r = assign(client, hd, req, other.w.tech, s, e)
    assert r.status_code == 422 and r.json()["error"]["details"]["reasons"][0]["code"] == "inactive"


def test_deactivated_technician_gets_no_new_assignments_history_kept(client, db, sw, hd):
    done = triaged(db, sw.w)
    s, e = local_slot(2, 10)
    assign(client, hd, done, sw.w.tech, s, e)
    db.get(Membership, sw.w.tech[1].id).is_active = False
    db.commit()
    req = triaged(db, sw.w)
    s2, e2 = local_slot(3, 10)
    r = assign(client, hd, req, sw.w.tech, s2, e2)
    assert r.status_code == 422 and r.json()["error"]["details"]["reasons"][0]["code"] == "inactive"
    assert [x.status for x in rows(db, done)] == [A.ACTIVE]  # existing rows untouched


def test_past_and_short_windows_rejected(client, db, sw, hd):
    req = triaged(db, sw.w)
    s, e = local_slot(-1, 10)
    r = assign(client, hd, req, sw.w.tech, s, e)
    assert r.status_code == 422
    assert "in_past" in [x["code"] for x in r.json()["error"]["details"]["reasons"]]
    s, _ = local_slot(2, 10)
    r = assign(client, hd, req, sw.w.tech, s, s + timedelta(minutes=29))
    assert [x["code"] for x in r.json()["error"]["details"]["reasons"]] == ["invalid_window"]
    r = client.post(
        f"{API}/requests/{req.id}/assignment",
        json={
            "technician_membership_id": str(sw.w.tech[1].id),
            "start_at": "2031-01-01T10:00:00",
            "end_at": "2031-01-01T11:00:00",
        },
        headers=hd["disp"],
    )
    assert r.status_code == 422  # naive datetimes are rejected
    assert assign(client, hd, req, sw.w.tech, s, s + timedelta(minutes=30)).status_code == 201


def test_assign_requires_triaged(client, db, sw, hd):
    s, e = local_slot(2, 10)
    for st in (S.SUBMITTED, S.SCHEDULED, S.COMPLETED):
        req = seed_request(db, sw.w, status=st)
        r = assign(client, hd, req, sw.w.tech, s, e)
        assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_transition"


# ---------------- cancel releases ----------------
def test_cancel_from_scheduled_releases_assignment(client, db, sw, hd):
    req = triaged(db, sw.w)
    s, e = local_slot(2, 10)
    assign(client, hd, req, sw.w.tech, s, e)
    r = act(client, hd, "disp", req, "cancel", reason="Tenant moved out of the building")
    assert r.status_code == 200 and r.json()["status"] == "CANCELED"
    (row,) = rows(db, req)
    assert row.status == A.CANCELED and row.active is False
    other = triaged(db, sw.w)
    assert assign(client, hd, other, sw.w.tech, s, e).status_code == 201


# ---------------- listing, /me, schedule ----------------
def test_requests_list_technician_filter(client, db, sw, hd):
    a, b = triaged(db, sw.w), triaged(db, sw.w)
    s, e = local_slot(2, 10)
    assign(client, hd, a, sw.w.tech, s, e)
    assign(client, hd, b, sw.tech2, s, e)
    r = client.get(
        f"{API}/requests", params={"technician_id": str(sw.w.tech[1].id)}, headers=hd["disp"]
    )
    assert [i["id"] for i in r.json()["items"]] == [str(a.id)]
    # technician sees only their own list
    mine = client.get(f"{API}/requests", headers=hd["tech2"]).json()
    assert [i["id"] for i in mine["items"]] == [str(b.id)]


def test_me_assignments_scopes_and_payload(client, db, sw, hd):
    w = sw.w
    reqs = [triaged(db, w, title=f"Job {i}") for i in range(4)]
    for i, r in enumerate(reqs):
        s, e = local_slot(2 + i, 10)
        assert assign(client, hd, r, w.tech, s, e).status_code == 201
    act(client, hd, "tech", reqs[1], "accept")
    act(client, hd, "tech", reqs[2], "accept")
    act(client, hd, "tech", reqs[2], "start")
    act(client, hd, "tech", reqs[3], "accept")
    act(client, hd, "tech", reqs[3], "start")
    act(client, hd, "tech", reqs[3], "block", reason="Waiting for access")
    up = upload(client, hd["tech"], str(reqs[2].id), image_bytes(), purpose="COMPLETION")
    assert up.status_code == 201
    assert act(client, hd, "tech", reqs[2], "complete", note=NOTE).status_code == 200

    def scope(name):
        r = client.get(f"{API}/me/assignments?scope={name}", headers=hd["tech"])
        assert r.status_code == 200, r.text
        return r.json()

    up_ = scope("upcoming")
    assert [i["request"]["title"] for i in up_["items"]] == ["Job 0", "Job 1"]
    assert up_["total"] == 2 and up_["page"] == 1
    assert [i["request"]["title"] for i in scope("active")["items"]] == ["Job 3"]
    hist = scope("history")["items"]
    assert [i["request"]["title"] for i in hist] == ["Job 2"]
    item = up_["items"][0]
    assert set(item) == {
        "assignment_id",
        "request",
        "appointment",
        "assignment_status",
        "allowed_actions",
        "estimate_status",
        "start_blocked_reason",
    }
    assert item["estimate_status"] is None and item["start_blocked_reason"] is None
    rq = item["request"]
    assert rq["display_id"].startswith("REQ-") and rq["property"]["address"] == "1 Test St"
    assert set(rq["property"]) == {"name", "address", "contact_instructions"}
    assert (
        rq["requester_name"] and rq["category"]["name"] == "HVAC" and rq["description"] == LONG_DESC
    )
    assert "email" not in str(rq) and "phone" not in str(rq)
    assert item["appointment"]["start_at"] and item["assignment_status"] == "ACTIVE"
    assert {"accept", "decline"} <= set(item["allowed_actions"])
    assert scope("active")["items"][0]["allowed_actions"][:1] == ["resume"]
    # default scope + pagination + bad scope
    assert client.get(f"{API}/me/assignments?page_size=1", headers=hd["tech"]).json()["total"] == 2
    assert client.get(f"{API}/me/assignments?scope=nope", headers=hd["tech"]).status_code == 422
    # tech2 sees nothing of tech's jobs
    assert client.get(f"{API}/me/assignments", headers=hd["tech2"]).json()["total"] == 0


def test_schedule_shape_range_limit_and_conflict_flag(client, db, sw, hd):
    from datetime import time

    from sqlalchemy import delete

    from app.models import TechnicianAvailability, TechnicianTimeOff

    w = sw.w
    a, b = triaged(db, w), triaged(db, w)
    s, e = local_slot(2, 10)
    assign(client, hd, a, w.tech, s, e)
    s2, e2 = local_slot(3, 10)
    assign(client, hd, b, w.tech, s2, e2)
    frm, to = local_slot(0, 0)[0], local_slot(7, 0)[0]
    r = client.get(f"{API}/schedule", params={"from": iso(frm), "to": iso(to)}, headers=hd["disp"])
    assert r.status_code == 200, r.text
    data = r.json()
    assert set(data) == {"range", "technicians"} and data["range"]["timezone"] == "Asia/Bishkek"
    assert set(data["range"]) == {"from", "to", "timezone"}
    techs = {t["membership_id"]: t for t in data["technicians"]}
    assert set(techs) == {str(w.tech[1].id), str(sw.tech2[1].id)}
    t = techs[str(w.tech[1].id)]
    assert len(t["assignments"]) == 2 and not any(x["conflict"] for x in t["assignments"])
    assert t["assignments"][0]["display_id"] == f"REQ-{a.number}"
    assert set(t["assignments"][0]) >= {
        "assignment_id",
        "request_id",
        "title",
        "priority",
        "request_status",
        "start_at",
        "end_at",
        "conflict",
    }
    assert len(t["availability"]) >= 7  # one interval per local day in the week
    assert t["availability"][0]["end_at"] > t["availability"][0]["start_at"]
    one = client.get(
        f"{API}/schedule",
        params={"from": iso(frm), "to": iso(to), "technician_id": str(sw.tech2[1].id)},
        headers=hd["disp"],
    ).json()
    assert [x["membership_id"] for x in one["technicians"]] == [str(sw.tech2[1].id)]
    # one-day view
    day = client.get(
        f"{API}/schedule",
        params={"from": iso(s - timedelta(hours=2)), "to": iso(s + timedelta(hours=14))},
        headers=hd["disp"],
    ).json()
    mine = next(x for x in day["technicians"] if x["membership_id"] == str(w.tech[1].id))
    assert len(mine["assignments"]) == 1
    # limits
    assert (
        client.get(
            f"{API}/schedule",
            params={"from": iso(frm), "to": iso(frm + timedelta(days=32))},
            headers=hd["disp"],
        ).status_code
        == 422
    )
    assert (
        client.get(
            f"{API}/schedule",
            params={"from": iso(frm), "to": iso(frm + timedelta(days=31))},
            headers=hd["disp"],
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"{API}/schedule", params={"from": iso(to), "to": iso(frm)}, headers=hd["disp"]
        ).status_code
        == 422
    )
    assert (
        client.get(
            f"{API}/schedule",
            params={"from": iso(frm), "to": iso(to), "technician_id": str(w.req1[1].id)},
            headers=hd["disp"],
        ).status_code
        == 404
    )
    # availability later edited to exclude assignment a -> conflict flag; time off flags b
    db.execute(
        delete(TechnicianAvailability).where(TechnicianAvailability.membership_id == w.tech[1].id)
    )
    db.commit()
    db.add(
        TechnicianTimeOff(
            organization_id=w.org.id, membership_id=w.tech[1].id, start_at=s2, end_at=e2
        )
    )
    from tests.sched_helpers import give_availability

    give_availability(db, w.org, w.tech, time(14, 0), time(18, 0))
    r = client.get(
        f"{API}/schedule",
        params={"from": iso(frm), "to": iso(to), "technician_id": str(w.tech[1].id)},
        headers=hd["disp"],
    ).json()
    t = r["technicians"][0]
    flags = {x["display_id"]: (x["conflict"], x["conflict_reasons"]) for x in t["assignments"]}
    assert flags[f"REQ-{a.number}"] == (True, ["outside_availability"])
    assert flags[f"REQ-{b.number}"][0] is True and "time_off" in flags[f"REQ-{b.number}"][1]
    assert len(t["time_off"]) == 1
