"""Smart Assign suggested slots (WEB-09) against real Postgres."""

import time as timer
from datetime import UTC, datetime, time, timedelta

import pytest
from sqlalchemy import delete

from app.models import (
    Assignment,
    MembershipRole,
    Skill,
    TechnicianAvailability,
    TechnicianSkill,
    TechnicianTimeOff,
)
from app.models.enums import Priority
from tests.factories import make_member
from tests.req_helpers import make_world, seed_request
from tests.sched_helpers import (
    API,
    TZ,
    S,
    assign,
    give_availability,
    give_skill,
    triaged,
)


@pytest.fixture(autouse=True)
def _no_rejected_suggestions(caplog):
    """The final eligibility.evaluate assertion must never reject a generated slot."""
    caplog.set_level("WARNING", logger="app.services.suggestions")
    yield
    assert not [r for r in caplog.records if "rejected by eligibility" in r.getMessage()]


def sug(client, hd, req, who="disp", **params):
    return client.get(f"{API}/requests/{req.id}/suggestions", params=params, headers=hd[who])


def set_avail(db, w, tech, weekdays, start=time(9, 0), end=time(18, 0)):
    db.execute(
        delete(TechnicianAvailability).where(TechnicianAvailability.membership_id == tech[1].id)
    )
    db.commit()
    if weekdays:
        give_availability(db, w.org, tech, start, end, weekdays)


def local(dt_iso: str) -> datetime:
    return datetime.fromisoformat(dt_iso).astimezone(TZ)


def future_monday(hour: int, minute: int, weeks_ahead_days: int = 8) -> datetime:
    """A Monday >= 8 local days from now at hour:minute (UTC instant)."""
    d = (datetime.now(TZ) + timedelta(days=weeks_ahead_days)).date()
    while d.weekday() != 0:
        d += timedelta(days=1)
    return datetime.combine(d, time(hour, minute), tzinfo=TZ).astimezone(UTC)


def at(base: datetime, days: int, hour: int, minute: int = 0) -> datetime:
    d = base.astimezone(TZ).date() + timedelta(days=days)
    return datetime.combine(d, time(hour, minute), tzinfo=TZ).astimezone(UTC)


@pytest.fixture
def one_tech(db, sw):
    """Only sw.w.tech is bookable (Mon-Fri 9-18); tech2 has no availability."""
    set_avail(db, sw.w, sw.w.tech, range(5))
    set_avail(db, sw.w, sw.tech2, [])
    return sw.w.tech


def patch_clock(monkeypatch, instant: datetime):
    monkeypatch.setattr("app.core.clock.now", lambda: instant)


def by_tech(body, tech):
    return [s for s in body["suggestions"] if s["technician"]["membership_id"] == str(tech[1].id)]


def test_earliest_slot_rounds_up_and_respects_tz(client, db, sw, hd, one_tech, monkeypatch):
    patch_clock(monkeypatch, future_monday(12, 7))
    r = sug(client, hd, triaged(db, sw.w))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["duration_minutes"] == 60  # category default
    s = body["suggestions"]
    assert [local(x["start_at"]).strftime("%a %H:%M") for x in s[:2]] == ["Mon 12:15", "Mon 13:15"]
    assert local(s[0]["end_at"]).strftime("%H:%M") == "13:15"
    assert len(s) == 2  # at most 2 per technician
    assert body["skipped"][0]["reason_codes"] == ["no_availability"]
    assert s[0]["reason"].startswith("Earliest free slot")


def test_weekend_time_off_and_busy_with_adjacency(client, db, sw, hd, one_tech, monkeypatch):
    friday_evening = at(future_monday(9, 0), -3, 17, 7)  # Friday before the Monday
    patch_clock(monkeypatch, friday_evening)
    mon = at(friday_evening, 3, 9)
    db.add(
        TechnicianTimeOff(
            organization_id=sw.w.org.id,
            membership_id=one_tech[1].id,
            start_at=mon,
            end_at=at(mon, 0, 10),
        )
    )
    db.commit()
    for h0, h1 in ((10, 11), (12, 13)):
        r = assign(client, hd, triaged(db, sw.w), one_tech, at(mon, 0, h0), at(mon, 0, h1))
        assert r.status_code == 201, r.text
    body = sug(client, hd, triaged(db, sw.w)).json()
    # Fri 17:15 + 60 min exceeds 18:00; weekend skipped; Mon 09-10 is time off, 10-11 and
    # 12-13 are booked: Mon 11:00 touches both bookings (adjacency allowed), next is 13:00.
    starts = [local(x["start_at"]).strftime("%a %H:%M") for x in body["suggestions"]]
    assert starts == ["Mon 11:00", "Mon 13:00"]


def test_slot_is_inside_availability_for_long_duration(client, db, sw, hd, one_tech, monkeypatch):
    patch_clock(monkeypatch, future_monday(12, 7))
    body = sug(client, hd, triaged(db, sw.w), duration_minutes=240).json()
    s = body["suggestions"]
    assert local(s[0]["start_at"]).strftime("%a %H:%M") == "Mon 12:15"
    assert local(s[0]["end_at"]).strftime("%H:%M") == "16:15"
    assert local(s[1]["start_at"]).strftime("%a %H:%M") == "Tue 09:00"  # 16:15+4h > 18:00
    assert body["duration_minutes"] == 240


def test_ranking_workload_limit_and_two_per_tech(client, db, sw, hd):
    wd = (datetime.now(TZ) + timedelta(days=2)).weekday()
    for t in (sw.w.tech, sw.tech2):
        set_avail(db, sw.w, t, [wd])
    day2 = datetime.now(TZ) + timedelta(days=2)
    busy = assign(client, hd, triaged(db, sw.w), sw.w.tech, at(day2, 0, 14), at(day2, 0, 15))
    assert busy.status_code == 201, busy.text
    req = triaged(db, sw.w)
    body = sug(client, hd, req, limit=20).json()
    s = body["suggestions"]
    assert len(s) == 4  # 2 per technician
    assert s[0]["start_at"] == s[1]["start_at"]
    assert s[0]["technician"]["membership_id"] == str(sw.tech2[1].id)  # lighter workload first
    assert s[0]["workload_minutes_next_7_days"] == 0
    assert s[1]["workload_minutes_next_7_days"] == 60
    assert "lightest workload" in s[0]["reason"] and "lightest" not in s[1]["reason"]
    assert len(sug(client, hd, req, limit=3).json()["suggestions"]) == 3
    assert len(sug(client, hd, req, limit=1).json()["suggestions"]) == 1


def test_unskilled_inactive_and_unavailable_excluded(client, db, sw, hd, monkeypatch):
    patch_clock(monkeypatch, future_monday(8, 0))
    w = sw.w
    unskilled = make_member(db, w.org, MembershipRole.TECHNICIAN)
    give_availability(db, w.org, unskilled)
    inactive = make_member(db, w.org, MembershipRole.TECHNICIAN, active=False)
    give_skill(db, w.org, inactive, sw.skill)
    give_availability(db, w.org, inactive)
    no_avail = make_member(db, w.org, MembershipRole.TECHNICIAN)
    give_skill(db, w.org, no_avail, sw.skill)
    booked = make_member(db, w.org, MembershipRole.TECHNICIAN)
    give_skill(db, w.org, booked, sw.skill)
    give_availability(db, w.org, booked)
    start = future_monday(8, 0)
    db.add(
        TechnicianTimeOff(
            organization_id=w.org.id,
            membership_id=booked[1].id,
            start_at=start - timedelta(days=1),
            end_at=start + timedelta(days=60),
        )
    )
    db.commit()
    body = sug(client, hd, triaged(db, w), limit=20).json()
    ids = {s["technician"]["membership_id"] for s in body["suggestions"]}
    assert ids == {str(w.tech[1].id), str(sw.tech2[1].id)}
    assert body["unskilled_technicians"] == 1
    sk = {x["technician"]["membership_id"]: x["reason_codes"] for x in body["skipped"]}
    assert sk == {
        str(no_avail[1].id): ["no_availability"],
        str(booked[1].id): ["no_free_slot_in_horizon"],
    }


def test_reschedule_mode_excludes_own_assignment(client, db, sw, hd, one_tech, monkeypatch):
    base = future_monday(8, 0)
    patch_clock(monkeypatch, base)
    mon9 = at(base, 0, 9)
    own = triaged(db, sw.w)
    assert assign(client, hd, own, one_tech, mon9, mon9 + timedelta(hours=1)).status_code == 201
    other = triaged(db, sw.w)
    assert local(sug(client, hd, other).json()["suggestions"][0]["start_at"]).hour == 10
    r = sug(client, hd, own)
    assert r.status_code == 200
    assert local(r.json()["suggestions"][0]["start_at"]).strftime("%H:%M") == "09:00"
    # staff UI mechanism
    d = client.get(f"{API}/requests/{own.id}", headers=hd["disp"]).json()
    assert "suggest_assignment" in d["allowed_actions"]
    d = client.get(f"{API}/requests/{other.id}", headers=hd["disp"]).json()
    assert "suggest_assignment" in d["allowed_actions"]
    d = client.get(f"{API}/requests/{other.id}", headers=hd["req1"]).json()
    assert "suggest_assignment" not in d["allowed_actions"]


def test_every_suggestion_is_accepted_and_taken_slot_disappears(client, db, sw, hd):
    wd = [(datetime.now(TZ) + timedelta(days=d)).weekday() for d in (1, 2)]
    for t in (sw.w.tech, sw.tech2):
        set_avail(db, sw.w, t, wd)
    top = sug(client, hd, triaged(db, sw.w), limit=20).json()["suggestions"]
    assert len(top) == 4
    for sgn in top:  # each one is accepted by the real guarded endpoint
        req = triaged(db, sw.w)
        r = client.post(
            f"{API}/requests/{req.id}/assignment",
            json={
                "technician_membership_id": sgn["technician"]["membership_id"],
                "start_at": sgn["start_at"],
                "end_at": sgn["end_at"],
            },
            headers=hd["disp"],
        )
        assert r.status_code == 201, r.text
        r = client.post(
            f"{API}/requests/{req.id}/assignment/unassign",
            json={"reason": "Testing suggestions again."},
            headers=hd["disp"],
        )
        assert r.status_code == 200, r.text
    # take the top one for real, then ask again for another request
    first = top[0]
    req = triaged(db, sw.w)
    assert (
        client.post(
            f"{API}/requests/{req.id}/assignment",
            json={
                "technician_membership_id": first["technician"]["membership_id"],
                "start_at": first["start_at"],
                "end_at": first["end_at"],
            },
            headers=hd["disp"],
        ).status_code
        == 201
    )
    again = sug(client, hd, triaged(db, sw.w), limit=20).json()["suggestions"]
    ts, te = (datetime.fromisoformat(first[k]) for k in ("start_at", "end_at"))
    for s in again:
        if s["technician"]["membership_id"] == first["technician"]["membership_id"]:
            assert (
                datetime.fromisoformat(s["end_at"]) <= ts
                or datetime.fromisoformat(s["start_at"]) >= te
            )


def test_slot_ends_after_due_flag(client, db, sw, hd, one_tech, monkeypatch):
    base = future_monday(12, 7)
    patch_clock(monkeypatch, base)
    late = seed_request(
        db, sw.w, status=S.TRIAGED, priority=Priority.HIGH, sla_due_at=at(base, 0, 12, 30)
    )
    ok = seed_request(
        db, sw.w, status=S.TRIAGED, priority=Priority.HIGH, sla_due_at=at(base, 1, 18)
    )
    none = triaged(db, sw.w)
    a = sug(client, hd, late).json()["suggestions"][0]
    assert a["sla"]["slot_ends_after_due"] is True and "ends after SLA due" in a["reason"]
    assert datetime.fromisoformat(a["sla"]["due_at"]) == at(base, 0, 12, 30)
    b = sug(client, hd, ok).json()["suggestions"][0]
    assert b["sla"]["slot_ends_after_due"] is False
    c = sug(client, hd, none).json()["suggestions"][0]
    assert c["sla"] == {"due_at": None, "slot_ends_after_due": False}


def test_permissions_state_and_validation(client, db, sw, hd):
    req = triaged(db, sw.w)
    for who in ("req1", "tech"):
        assert sug(client, hd, req, who=who).status_code == 403
    assert sug(client, hd, req, who="admin").status_code == 200
    other = make_world(db, "Org B")
    foreign = seed_request(db, other, status=S.TRIAGED)
    assert sug(client, hd, foreign).status_code == 404
    for st in (S.SUBMITTED, S.IN_PROGRESS, S.COMPLETED, S.CANCELED):
        r = sug(client, hd, seed_request(db, sw.w, status=st))
        assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_state", r.text
    for bad in (
        {"horizon_days": 0},
        {"horizon_days": 32},
        {"limit": 0},
        {"limit": 21},
        {"duration_minutes": 15},
        {"duration_minutes": 721},
        {"duration_minutes": 50},
    ):
        assert sug(client, hd, req, **bad).status_code == 422, bad
    assert sug(client, hd, req, horizon_days=31, duration_minutes=720, limit=20).status_code == 200


def test_performance_eight_technicians_fourteen_days(client, db, sw, hd):
    w = sw.w
    techs = [w.tech, sw.tech2]
    for _ in range(6):
        t = make_member(db, w.org, MembershipRole.TECHNICIAN)
        give_skill(db, w.org, t, sw.skill)
        give_availability(db, w.org, t)
        techs.append(t)
    skill_rows = db.query(TechnicianSkill).count()
    assert skill_rows >= 8 and db.query(Skill).count() >= 1
    for i, t in enumerate(techs):  # a few busy intervals each
        for d in range(1, 6):
            s = datetime.now(TZ) + timedelta(days=d)
            r = assign(client, hd, triaged(db, w), t, at(s, 0, 9 + i % 3), at(s, 0, 10 + i % 3))
            assert r.status_code == 201, r.text
    req = triaged(db, w)
    t0 = timer.perf_counter()
    r = sug(client, hd, req, horizon_days=14, limit=20)
    elapsed = timer.perf_counter() - t0
    assert r.status_code == 200 and len(r.json()["suggestions"]) == 16
    assert elapsed < 3.0, elapsed
    assert db.query(Assignment).count() >= 40


def win(base: datetime, h0: int, h1: int, days: int = 0) -> dict[str, str]:
    return {
        "from": at(base, days, h0).isoformat().replace("+00:00", "Z"),
        "to": at(base, days, h1).isoformat().replace("+00:00", "Z"),
    }


def test_window_params_respected_and_later_than_global_earliest(
    client, db, sw, hd, one_tech, monkeypatch
):
    """The REQ-14 bug: free 15:00-18:00 must be found inside a 14:00-18:00 window."""
    base = future_monday(9, 0)
    patch_clock(monkeypatch, at(base, -3, 17, 7))
    day = at(base, 1, 9)  # Tuesday
    for h0, h1 in ((9, 12), (12, 15)):  # busy 09-15; adjacency keeps 15:00 usable
        r = assign(client, hd, triaged(db, sw.w), one_tech, at(day, 0, h0), at(day, 0, h1))
        assert r.status_code == 201, r.text
    req = triaged(db, sw.w)
    global_first = sug(client, hd, req).json()["suggestions"][0]
    assert (
        local(global_first["start_at"]).strftime("%a %H:%M") == "Mon 09:00"
    )  # unwindowed search starts Monday
    body = sug(client, hd, req, duration_minutes=60, limit=20, **win(day, 14, 18)).json()
    starts = [local(x["start_at"]).strftime("%H:%M") for x in body["suggestions"]]
    assert starts[0] == "15:00"
    for x in body["suggestions"]:  # strictly inside the window, ends by 18:00
        assert at(day, 0, 14) <= datetime.fromisoformat(x["start_at"])
        assert datetime.fromisoformat(x["end_at"]) <= at(day, 0, 18)
    assert body["horizon"]["to"].startswith(at(day, 0, 18).strftime("%Y-%m-%dT%H:%M"))


def test_window_in_the_past_is_clipped_to_now_and_tight_window_is_empty(
    client, db, sw, hd, one_tech, monkeypatch
):
    base = future_monday(9, 0)
    patch_clock(monkeypatch, at(base, 0, 12, 7))
    req = triaged(db, sw.w)
    body = sug(client, hd, req, **win(base, 9, 15)).json()
    assert local(body["suggestions"][0]["start_at"]).strftime("%H:%M") == "12:15"
    assert local(body["horizon"]["from"]).strftime("%H:%M") == "12:15"
    # 60 min needed, only 45 left in the window
    tight = sug(client, hd, req, **win(base, 12, 13)).json()
    assert tight["suggestions"] == []


def test_window_validation_422(client, db, sw, hd, one_tech):
    req = triaged(db, sw.w)
    t = datetime(2030, 1, 7, 8, 0, tzinfo=UTC)
    iso = lambda d: d.isoformat().replace("+00:00", "Z")  # noqa: E731
    cases = [
        {"from": iso(t), "to": iso(t)},
        {"from": iso(t), "to": iso(t - timedelta(hours=1))},
        {"from": iso(t), "to": iso(t + timedelta(days=31, minutes=1))},
        {"to": iso(t)},  # far future relative to now: > 31 days
    ]
    for bad in cases:
        r = sug(client, hd, req, **bad)
        assert r.status_code == 422, bad
    ok = sug(client, hd, req, **{"from": iso(t), "to": iso(t + timedelta(days=31))})
    assert ok.status_code == 200
