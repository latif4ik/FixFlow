"""SCHED-01/02/05: eligibility reasons, availability (org timezone), candidate list."""

from datetime import UTC, datetime, time, timedelta

import pytest
from sqlalchemy import delete

from app.core.tenancy import Ctx
from app.models import (
    Membership,
    MembershipRole,
    Skill,
    TechnicianAvailability,
    TechnicianSkill,
    TechnicianTimeOff,
)
from app.services import eligibility
from tests.factories import make_member
from tests.sched_helpers import (  # noqa: F401
    API,
    S,
    assign,
    give_availability,
    give_skill,
    iso,
    local_slot,
    make_sched_world,
    triaged,
)


def codes(res):
    return [r.code for r in res.reasons]


@pytest.fixture
def ctx(sw):
    return Ctx(
        user_id=sw.w.disp[0].id,
        org_id=sw.w.org.id,
        membership_id=sw.w.disp[1].id,
        role=MembershipRole.DISPATCHER,
        timezone="Asia/Bishkek",
    )


def ev(db, ctx, sw, req, tech, start, end, **kw):
    kw.setdefault("for_new", True)
    return eligibility.evaluate(db, ctx, req, tech[1].id, start, end, **kw)


def test_eligible_happy_path(db, ctx, sw):
    req = triaged(db, sw.w)
    s, e = local_slot(2, 10)
    res = ev(db, ctx, sw, req, sw.w.tech, s, e)
    assert res.eligible and res.reasons == []


def test_missing_skills_lists_all_missing(db, ctx, sw):
    extra = Skill(organization_id=sw.w.org.id, name="electrical")
    db.add(extra)
    db.commit()
    from app.models import CategoryRequiredSkill

    db.add(
        CategoryRequiredSkill(
            organization_id=sw.w.org.id, category_id=sw.w.cat.id, skill_id=extra.id
        )
    )
    db.commit()
    req = triaged(db, sw.w)
    s, e = local_slot(2, 10)
    res = ev(db, ctx, sw, req, sw.w.tech, s, e)  # has hvac, lacks electrical (ALL required)
    assert codes(res) == ["missing_skills"]
    assert res.reasons[0].details["skills"] == ["electrical"]
    give_skill(db, sw.w.org, sw.w.tech, extra)
    assert ev(db, ctx, sw, req, sw.w.tech, s, e).eligible


def test_org_timezone_availability_bishkek_is_utc_plus_six(db, ctx, sw):
    """09:00-18:00 Asia/Bishkek == 03:00-12:00 UTC."""
    req = triaged(db, sw.w)
    day = (datetime.now(UTC) + timedelta(days=3)).date()
    mk = lambda h, m=0: datetime(day.year, day.month, day.day, h, m, tzinfo=UTC)  # noqa: E731
    assert ev(db, ctx, sw, req, sw.w.tech, mk(3), mk(4)).eligible  # 09:00 local
    assert ev(db, ctx, sw, req, sw.w.tech, mk(11), mk(12)).eligible  # ends 18:00 local
    assert codes(ev(db, ctx, sw, req, sw.w.tech, mk(2, 30), mk(3, 30))) == [
        "outside_availability"
    ]  # starts 08:30 local
    assert codes(ev(db, ctx, sw, req, sw.w.tech, mk(11, 30), mk(12, 30))) == [
        "outside_availability"
    ]  # ends 18:30 local
    # 10:00-11:00 UTC is 16:00-17:00 local: inside; but a naive UTC reading (10:00-11:00) would
    # also be inside, so assert an UTC-evening window that is only outside in local time.
    assert codes(ev(db, ctx, sw, req, sw.w.tech, mk(13), mk(14))) == ["outside_availability"]


def test_availability_must_be_inside_one_interval(db, ctx, sw):
    db.execute(
        delete(TechnicianAvailability).where(
            TechnicianAvailability.membership_id == sw.w.tech[1].id
        )
    )
    db.commit()
    give_availability(db, sw.w.org, sw.w.tech, time(9, 0), time(12, 0))
    give_availability(db, sw.w.org, sw.w.tech, time(13, 0), time(17, 0))
    req = triaged(db, sw.w)
    s, e = local_slot(2, 11, 120)  # 11:00-13:00 spans the gap
    assert codes(ev(db, ctx, sw, req, sw.w.tech, s, e)) == ["outside_availability"]
    s, e = local_slot(2, 13, 60)
    assert ev(db, ctx, sw, req, sw.w.tech, s, e).eligible


def test_window_crossing_local_midnight_is_outside(db, ctx, sw):
    db.execute(
        delete(TechnicianAvailability).where(
            TechnicianAvailability.membership_id == sw.w.tech[1].id
        )
    )
    db.commit()
    give_availability(db, sw.w.org, sw.w.tech, time(0, 0), time(23, 59, 59))
    req = triaged(db, sw.w)
    s, e = local_slot(2, 23, 60, 30)  # 23:30 -> 00:30 next local day
    assert codes(ev(db, ctx, sw, req, sw.w.tech, s, e)) == ["outside_availability"]


def test_weekday_without_availability(db, ctx, sw):
    s, e = local_slot(2, 10)
    wd = s.astimezone(__import__("zoneinfo").ZoneInfo("Asia/Bishkek")).weekday()
    db.execute(
        delete(TechnicianAvailability).where(
            TechnicianAvailability.membership_id == sw.w.tech[1].id,
            TechnicianAvailability.weekday == wd,
        )
    )
    db.commit()
    assert codes(ev(db, ctx, sw, triaged(db, sw.w), sw.w.tech, s, e)) == ["outside_availability"]


def test_time_off_blocks(db, ctx, sw):
    s, e = local_slot(2, 10)
    off = TechnicianTimeOff(
        organization_id=sw.w.org.id,
        membership_id=sw.w.tech[1].id,
        start_at=s + timedelta(minutes=30),
        end_at=s + timedelta(hours=5),
    )
    db.add(off)
    db.commit()
    res = ev(db, ctx, sw, triaged(db, sw.w), sw.w.tech, s, e)
    assert codes(res) == ["time_off"] and res.reasons[0].details["time_off_id"] == str(off.id)
    # adjacent (ends exactly when time off starts) is fine
    assert ev(
        db,
        ctx,
        sw,
        triaged(db, sw.w),
        sw.w.tech,
        s - timedelta(minutes=30),
        s + timedelta(minutes=30),
    ).eligible


def test_in_past_only_for_new(db, ctx, sw):
    req = triaged(db, sw.w)
    s = datetime.now(UTC) - timedelta(hours=2)
    e = s + timedelta(hours=1)
    assert "in_past" in codes(ev(db, ctx, sw, req, sw.w.tech, s, e))
    assert "in_past" not in codes(ev(db, ctx, sw, req, sw.w.tech, s, e, for_new=False))


def test_invalid_window_and_30_minute_minimum(db, ctx, sw):
    req = triaged(db, sw.w)
    s, _ = local_slot(2, 10)
    assert codes(ev(db, ctx, sw, req, sw.w.tech, s, s)) == ["invalid_window"]
    assert codes(ev(db, ctx, sw, req, sw.w.tech, s, s - timedelta(hours=1))) == ["invalid_window"]
    assert codes(ev(db, ctx, sw, req, sw.w.tech, s, s + timedelta(minutes=29))) == [
        "invalid_window"
    ]
    assert ev(db, ctx, sw, req, sw.w.tech, s, s + timedelta(minutes=30)).eligible


def test_inactive_and_non_technician(db, ctx, sw):
    req = triaged(db, sw.w)
    s, e = local_slot(2, 10)
    m = db.get(Membership, sw.w.tech[1].id)
    m.is_active = False
    db.commit()
    assert codes(ev(db, ctx, sw, req, sw.w.tech, s, e)) == ["inactive"]
    assert codes(ev(db, ctx, sw, req, sw.w.req1, s, e)) == ["inactive"]


def test_overlap_reports_conflicting_assignment_and_adjacent_ok(client, db, sw, hd, ctx):
    s, e = local_slot(2, 10)
    first = triaged(db, sw.w)
    assert assign(client, hd, first, sw.w.tech, s, e).status_code == 201
    other = triaged(db, sw.w)
    res = ev(db, ctx, sw, other, sw.w.tech, s + timedelta(minutes=30), e + timedelta(minutes=30))
    assert codes(res) == ["overlap"]
    clash = res.reasons[0].details["assignments"][0]
    assert clash["request_number"] == first.number
    assert ev(db, ctx, sw, other, sw.w.tech, e, e + timedelta(hours=1)).eligible  # 11:00 start ok
    assert ev(db, ctx, sw, other, sw.w.tech, s - timedelta(hours=1), s).eligible  # 09:00-10:00 ok


def test_candidates_ordering_reasons_and_workload(client, db, sw, hd, ctx):
    lone = make_member(db, sw.w.org, MembershipRole.TECHNICIAN)  # no skills at all
    give_availability(db, sw.w.org, lone[1])
    s, e = local_slot(2, 10)
    busy = triaged(db, sw.w)
    assert assign(client, hd, busy, sw.w.tech, s, e).status_code == 201
    req = triaged(db, sw.w)
    # no window: only skills/inactive evaluated, availability flag null
    r = client.get(f"{API}/requests/{req.id}/candidates", headers=hd["disp"])
    assert r.status_code == 200
    data = r.json()
    assert [c["available"] for c in data] == [None, None, None]
    by = {c["membership_id"]: c for c in data}
    assert by[str(lone[1].id)]["eligible"] is False
    assert by[str(lone[1].id)]["reasons"][0]["code"] == "missing_skills"
    assert data[-1]["membership_id"] == str(lone[1].id)  # ineligible sorted last
    # with window: tech overlaps, tech2 is free -> tech2 first (eligible), then tech (overlap)
    r = client.get(
        f"{API}/requests/{req.id}/candidates",
        params={"start_at": iso(s), "end_at": iso(e)},
        headers=hd["disp"],
    )
    data = r.json()
    # eligible first, then fewest planned minutes: tech2 (ok), lone (0 min, no skills), tech (60)
    assert [c["membership_id"] for c in data] == [
        str(sw.tech2[1].id),
        str(lone[1].id),
        str(sw.w.tech[1].id),
    ]
    assert data[0]["eligible"] and data[0]["available"] is True
    busy_c = data[2]
    assert busy_c["eligible"] is False and busy_c["available"] is False
    assert [x["code"] for x in busy_c["reasons"]] == ["overlap"]
    assert busy_c["workload"]["active_assignments"] == 1
    assert busy_c["workload"]["planned_minutes_next_7_days"] == 60
    assert data[0]["workload"] == {"active_assignments": 0, "planned_minutes_next_7_days": 0}


def test_candidates_staff_only_and_window_pair(client, db, sw, hd):
    req = triaged(db, sw.w)
    for who in ("req1", "tech"):
        assert client.get(f"{API}/requests/{req.id}/candidates", headers=hd[who]).status_code == 403
    s, _ = local_slot(2, 10)
    r = client.get(
        f"{API}/requests/{req.id}/candidates", params={"start_at": iso(s)}, headers=hd["disp"]
    )
    assert r.status_code == 422


def test_candidates_exclude_deactivated_technicians(client, db, sw, hd):
    req = triaged(db, sw.w)
    db.get(Membership, sw.tech2[1].id).is_active = False
    db.commit()
    data = client.get(f"{API}/requests/{req.id}/candidates", headers=hd["disp"]).json()
    assert [c["membership_id"] for c in data] == [str(sw.w.tech[1].id)]


def test_assign_rejects_ineligible_with_422_reasons(client, db, sw, hd):
    s, e = local_slot(2, 10)
    req = triaged(db, sw.w)
    db.execute(delete(TechnicianSkill).where(TechnicianSkill.membership_id == sw.w.tech[1].id))
    db.commit()
    r = assign(client, hd, req, sw.w.tech, s, e)
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "technician_ineligible"
    assert err["details"]["reasons"][0]["code"] == "missing_skills"
    db.expire_all()
    assert db.get(type(req), req.id).status == S.TRIAGED
