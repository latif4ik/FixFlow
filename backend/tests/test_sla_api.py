"""SLA through the API: detail block, list filters / sort, calendar changes, recompute hooks."""

from datetime import UTC, datetime

from app.services.request_events import add_event
from tests.req_helpers import payload
from tests.sched_helpers import API
from tests.sla_helpers import at, backdate, load, set_event_time, set_now


def make_request(client, db, hd, w, created, priority="NORMAL", who="disp"):
    r = client.post(
        f"{API}/requests",
        json=payload(w, priority=priority, requester_membership_id=str(w.req1[1].id)),
        headers=hd[who],
    )
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    backdate(db, rid, created)
    return rid


def get(client, hd, rid, who="disp"):
    r = client.get(f"{API}/requests/{rid}", headers=hd[who])
    assert r.status_code == 200, r.text
    return r.json()


def test_detail_sla_friday_evening_high_due_monday(client, db, sw, hd, monkeypatch):
    w = sw.w
    rid = make_request(client, db, hd, w, at(13, 17), "HIGH")
    set_now(monkeypatch, at(13, 17, 30))
    sla = get(client, hd, rid)["sla"]
    assert sla["budget_minutes"] == 480 and sla["consumed_minutes"] == 30
    assert sla["remaining_minutes"] == 450 and sla["state"] == "ON_TRACK"
    assert sla["due_at"] == at(16, 16).isoformat().replace("+00:00", "Z")
    assert sla["paused"] is False and sla["outcome"] is None and sla["overdue_by_minutes"] == 0
    # requesters see their own SLA too
    assert get(client, hd, rid, "req1")["sla"]["due_at"] == sla["due_at"]
    set_now(monkeypatch, at(16, 17, 45))
    sla = get(client, hd, rid)["sla"]
    assert sla["state"] == "OVERDUE" and sla["overdue_by_minutes"] == 105
    assert sla["remaining_minutes"] < 0


def test_priority_change_audits_and_recalculates(client, db, sw, hd, monkeypatch):
    w = sw.w
    rid = make_request(client, db, hd, w, at(16, 9), "NORMAL")
    set_now(monkeypatch, at(16, 16))
    assert get(client, hd, rid)["sla"]["remaining_minutes"] == 1440 - 420
    r = client.patch(
        f"{API}/requests/{rid}",
        json={"priority": "HIGH", "reason": "Water damage"},
        headers=hd["disp"],
    )
    assert r.status_code == 200, r.text
    # the PATCH happened "now" in real time; place its event at the patched instant
    set_event_time(db, rid, "PRIORITY_CHANGED", at(16, 16))
    sla = get(client, hd, rid)["sla"]
    assert sla["budget_minutes"] == 480 and sla["consumed_minutes"] == 420
    assert sla["remaining_minutes"] == 60 and sla["state"] == "AT_RISK"
    assert sla["due_at"] == at(16, 17).isoformat().replace("+00:00", "Z")
    types = [t["type"] for t in get(client, hd, rid)["timeline"]]
    assert "PRIORITY_CHANGED" in types
    assert load(db, rid).sla_budget_minutes == 480  # cache updated in the same transaction


def test_list_filters_and_due_sort(client, db, sw, hd, monkeypatch):
    w = sw.w
    on_track = make_request(client, db, hd, w, at(16, 9), "NORMAL")
    at_risk = make_request(client, db, hd, w, at(16, 9), "HIGH")
    overdue = make_request(client, db, hd, w, at(13, 9), "HIGH")
    paused = make_request(client, db, hd, w, at(16, 9), "HIGH")
    done = make_request(client, db, hd, w, at(13, 9), "HIGH")
    r = client.post(
        f"{API}/requests/{done}/cancel", json={"reason": "no longer needed"}, headers=hd["disp"]
    )
    assert r.status_code == 200, r.text
    set_event_time(db, done, "STATUS_CHANGED", at(13, 10), to_status="CANCELED")
    add_event(db, None, load(db, paused), "ESTIMATE_SUBMITTED", at=at(16, 10))
    db.commit()
    set_now(monkeypatch, at(16, 16))

    def ids(**params):
        r = client.get(f"{API}/requests", params={"page_size": 50, **params}, headers=hd["disp"])
        assert r.status_code == 200, r.text
        return [i["id"] for i in r.json()["items"]]

    assert ids(sla_state="OVERDUE") == [overdue]
    assert ids(sla_state="AT_RISK") == [at_risk]
    assert ids(sla_state="ON_TRACK") == [on_track]
    assert ids(sla_state="PAUSED") == [paused]
    assert set(ids(sla_state=["OVERDUE", "PAUSED"])) == {overdue, paused}
    # finished requests never show up in live-state filters
    assert done not in ids(sla_state="OVERDUE") + ids(sla_state="ON_TRACK") + ids(
        sla_state="AT_RISK"
    )
    ordered = ids(sort="due")
    assert ordered[:3] == [overdue, at_risk, on_track]
    assert set(ordered[3:]) == {paused, done}
    items = {
        i["id"]: i
        for i in client.get(f"{API}/requests?page_size=50", headers=hd["disp"]).json()["items"]
    }
    assert items[overdue]["sla_state"] == "OVERDUE" and items[overdue]["sla_due_at"]
    assert items[paused]["sla_state"] == "PAUSED" and items[paused]["sla_due_at"] is None
    assert items[done]["sla_state"] == "ON_TRACK"  # canceled after 1h: historical state
    bad = client.get(f"{API}/requests?sla_state=NOPE", headers=hd["disp"])
    assert bad.status_code == 422


def test_estimate_pause_via_api_and_resume(client, db, sw, hd, monkeypatch):
    from tests.p3_helpers import accepted_job, create_est, decide, submit_est

    req = accepted_job(client, db, sw, hd)
    rid = str(req.id)
    # give the seeded request its SLA events: created Mon 09:00 HIGH
    add_event(db, None, load(db, rid), "REQUEST_CREATED", at=at(16, 9), data={"priority": "HIGH"})
    db.commit()
    est = create_est(client, hd, req).json()
    submit_est(client, hd, est["id"])
    set_event_time(db, rid, "ESTIMATE_SUBMITTED", at(16, 10))
    set_now(monkeypatch, at(17, 12))
    sla = get(client, hd, rid)["sla"]
    assert sla["paused"] is True and sla["due_at"] is None and sla["consumed_minutes"] == 60
    assert client.get(f"{API}/requests?sla_state=PAUSED", headers=hd["disp"]).json()["total"] == 1
    r = decide(client, hd["req1"], est, "APPROVE")
    assert r.status_code == 200, r.text
    set_event_time(db, rid, "ESTIMATE_APPROVED", at(17, 10))
    sla = get(client, hd, rid)["sla"]
    assert sla["paused"] is False and sla["consumed_minutes"] == 180
    assert sla["remaining_minutes"] == 300
    assert sla["due_at"] == at(17, 17).isoformat().replace("+00:00", "Z")


def test_business_hours_and_holiday_changes_recompute_open_requests(
    client, db, sw, hd, monkeypatch
):
    w = sw.w
    rid = make_request(client, db, hd, w, at(13, 17), "HIGH")
    set_now(monkeypatch, at(13, 17, 30))
    due = lambda: client.get(f"{API}/requests/{rid}", headers=hd["disp"]).json()["sla"]["due_at"]  # noqa: E731
    iso = lambda t: t.isoformat().replace("+00:00", "Z")  # noqa: E731
    assert due() == iso(at(16, 16))
    h = client.post(
        f"{API}/org/holidays", json={"date": "2026-11-16", "name": "Day off"}, headers=hd["admin"]
    )
    assert h.status_code == 201, h.text
    assert due() == iso(at(17, 16))
    assert load(db, rid).sla_due_at == at(17, 16)  # persisted cache moved too
    assert (
        client.delete(f"{API}/org/holidays/{h.json()['id']}", headers=hd["admin"]).status_code
        == 204
    )
    assert due() == iso(at(16, 16))
    # Saturday becomes a working day: Fri 17-18 (1h) + Sat 09-16 (7h)
    iv = [{"weekday": d, "open_time": "09:00:00", "close_time": "18:00:00"} for d in range(6)]
    r = client.put(f"{API}/org/business-hours", json={"intervals": iv}, headers=hd["admin"])
    assert r.status_code == 200, r.text
    assert due() == iso(at(14, 16))
    # time zone change is a calendar change too (UTC+6 -> UTC: 17:00 Bishkek is 11:00 UTC)
    r = client.patch(f"{API}/org", json={"timezone": "America/New_York"}, headers=hd["admin"])
    assert r.status_code == 200, r.text
    # created Fri 17:00 Bishkek = 06:00 New York (closed) -> 8h from Fri 09:00 EST = 17:00 EST
    assert load(db, rid).sla_due_at == datetime(2026, 11, 13, 22, 0, tzinfo=UTC)


def test_completion_freezes_cache_and_reopen_restarts(client, db, sw, hd, monkeypatch):
    from tests.p3_helpers import add_completion_file, in_progress_job

    w = sw.w
    req = in_progress_job(client, db, sw, hd)
    rid = str(req.id)
    add_event(db, None, load(db, rid), "REQUEST_CREATED", at=at(16, 9), data={"priority": "HIGH"})
    db.commit()
    add_completion_file(db, w.org, req, w.tech[1])
    r = client.post(
        f"{API}/requests/{rid}/complete",
        json={"note": "Replaced the faulty compressor relay and tested."},
        headers=hd["tech"],
    )
    assert r.status_code == 200, r.text
    set_event_time(db, rid, "STATUS_CHANGED", at(16, 12), to_status="COMPLETED")
    row = load(db, rid)
    assert row.sla_outcome == "MET" and row.sla_stopped_at == at(16, 12)
    assert row.sla_due_at is None and row.sla_consumed_minutes == 180
    set_now(monkeypatch, at(30, 12))
    sla = get(client, hd, rid)["sla"]
    assert sla["stopped"] and sla["outcome"] == "MET" and sla["state"] == "ON_TRACK"
    assert sla["consumed_minutes"] == 180
    # rework: requester reopens -> clock restarts (carry-over of consumed time)
    r = client.post(
        f"{API}/requests/{rid}/reopen", json={"reason": "Still leaking"}, headers=hd["req1"]
    )
    assert r.status_code == 200, r.text
    set_event_time(db, rid, "STATUS_CHANGED", at(17, 9), to_status="REOPENED")
    row = load(db, rid)
    assert row.sla_stopped_at is None and row.sla_outcome is None
    assert row.sla_due_at == at(17, 14)
