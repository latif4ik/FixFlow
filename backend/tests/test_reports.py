import uuid
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

import pytest

from app.models import (
    Assignment,
    Estimate,
    MaterialUsage,
    MembershipRole,
    TechnicianAvailability,
    TechnicianTimeOff,
)
from app.models.enums import AssignmentStatus, EstimateStatus, Priority, RequestStatus
from app.services import reports
from tests.factories import make_member
from tests.p3_helpers import make_item
from tests.req_helpers import make_category, make_world, seed_request
from tests.sla_helpers import at, set_now

API = "/api/v1/reports"
S = RequestStatus
D = 2  # report day: 2026-11-02 (Bishkek)


def local(day: int, hh: int, mm: int = 0) -> datetime:
    return at(day, hh, mm)


def get(client, hd, who, path, **params):
    return client.get(f"{API}{path}", params=params, headers=hd[who])


def _assign(db, w, req, tech, start, end, status=AssignmentStatus.COMPLETED):
    db.add(
        Assignment(
            organization_id=w.org.id,
            request_id=req.id,
            technician_membership_id=tech[1].id,
            start_at=start,
            end_at=end,
            status=status,
            active=status == AssignmentStatus.ACTIVE,
            assigned_by_membership_id=w.disp[1].id,
        )
    )
    db.commit()


# ---- access / validation ----------------------------------------------------------------
@pytest.mark.parametrize("path", ["/summary", "/daily", "/distribution?by=priority"])
def test_staff_only(client, hd, path):
    for who in ("admin", "disp"):
        assert client.get(f"{API}{path}", headers=hd[who]).status_code == 200
    for who in ("req1", "tech"):
        assert client.get(f"{API}{path}", headers=hd[who]).status_code == 403
    assert client.get(f"{API}{path}").status_code == 401


def test_range_validation(client, hd):
    r = get(client, hd, "disp", "/summary", **{"from": "2025-01-01", "to": "2026-01-02"})
    assert r.status_code == 422  # 367 days
    ok = get(client, hd, "disp", "/summary", **{"from": "2025-01-01", "to": "2025-12-31"})
    assert ok.status_code == 200  # 365 days
    leap = get(client, hd, "disp", "/summary", **{"from": "2024-01-01", "to": "2024-12-31"})
    assert leap.status_code == 200  # 366 days exactly
    bad = get(client, hd, "disp", "/summary", **{"from": "2026-02-02", "to": "2026-02-01"})
    assert bad.status_code == 422
    assert get(client, hd, "disp", "/daily", days=91).status_code == 422
    assert get(client, hd, "disp", "/daily", days=0).status_code == 422
    assert get(client, hd, "disp", "/distribution", by="nope").status_code == 422


def test_foreign_filters_404(client, db, hd, sw):
    other = make_world(db, "Other Org")
    r = get(client, hd, "disp", "/summary", category_id=str(other.cat.id))
    assert r.status_code == 404
    r = get(client, hd, "disp", "/summary", technician_id=str(other.tech[1].id))
    assert r.status_code == 404
    # a non-technician membership of the own org is not a valid technician filter either
    r = get(client, hd, "disp", "/summary", technician_id=str(sw.w.req1[1].id))
    assert r.status_code == 404


# ---- summary ----------------------------------------------------------------------------
def test_summary_counts_and_money(client, db, hd, sw, monkeypatch):
    w = sw.w
    set_now(monkeypatch, local(10, 12))
    cat2 = make_category(db, w.org, "Plumbing")
    r1 = seed_request(db, w, status=S.SUBMITTED, created_at=local(2, 10))
    r2 = seed_request(db, w, status=S.TRIAGED, category_id=cat2.id, created_at=local(3, 10))
    r3 = seed_request(db, w, status=S.COMPLETED, completed_at=local(2, 15), created_at=local(1, 10))
    r4 = seed_request(db, w, status=S.CLOSED, completed_at=local(20, 9), created_at=local(1, 10))
    seed_request(db, w, status=S.CANCELED, created_at=local(1, 10))
    # overdue: running SLA past its due instant
    r1.sla_budget_minutes = 60
    r1.sla_due_at = local(10, 9)
    db.commit()
    # another org's data must never count
    other = make_world(db, "Other Org")
    seed_request(db, other, status=S.SUBMITTED, created_at=local(2, 10))

    # upcoming appointment (ACTIVE, starts within 7 days) and one beyond the window
    _assign(db, w, r2, w.tech, local(11, 10), local(11, 11), AssignmentStatus.ACTIVE)
    _assign(db, w, r3, sw.tech2, local(25, 10), local(25, 11), AssignmentStatus.ACTIVE)

    # approved estimates: counted by decided_at in range; draft/rejected/out-of-range excluded
    def est(req, version, status, total, decided):
        db.add(
            Estimate(
                organization_id=w.org.id,
                request_id=req.id,
                version=version,
                status=status,
                labor_minutes=60,
                labor_rate_minor=1000,
                labor_cost_minor=1000,
                materials_total_minor=total - 1000,
                total_minor=total,
                created_by_membership_id=w.disp[1].id,
                decided_at=decided,
            )
        )
        db.commit()

    est(r3, 1, EstimateStatus.APPROVED, 5000, local(2, 16))
    est(r4, 1, EstimateStatus.APPROVED, 7000, local(3, 16))
    est(r2, 1, EstimateStatus.REJECTED, 9000, local(3, 16))
    est(r1, 1, EstimateStatus.APPROVED, 20000, local(20, 16))
    item = make_item(db, w.org, price=300)
    for req, qty, when in ((r3, "2", local(2, 17)), (r2, "1", local(25, 17))):
        db.add(
            MaterialUsage(
                organization_id=w.org.id,
                request_id=req.id,
                item_id=item.id,
                technician_membership_id=w.tech[1].id,
                quantity=Decimal(qty),
                unit_cost_minor_snapshot=300,
                total_cost_minor=int(Decimal(qty) * 300),
                client_command_id=uuid.uuid4(),
                payload_hash="x",
                created_at=when,
            )
        )
    db.commit()

    r = get(client, hd, "disp", "/summary", **{"from": "2026-11-02", "to": "2026-11-05"})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["counts_by_status"]["SUBMITTED"] == 1
    assert b["counts_by_status"]["TRIAGED"] == 1
    assert b["counts_by_status"]["COMPLETED"] == 1
    assert b["counts_by_status"]["CLOSED"] == 1
    assert b["counts_by_status"]["CANCELED"] == 1
    assert sum(b["counts_by_status"].values()) == 5  # all statuses present, other org excluded
    assert set(b["counts_by_status"]) == {s.value for s in S}
    assert b["open_requests"] == 2
    assert b["overdue_requests"] == 1
    assert b["upcoming_appointments"] == 1
    assert b["completed_in_range"] == 1  # r3 only (r4 completed Nov 20)
    assert b["approved_estimates_total_minor"] == 12000
    assert "not collected revenue" in b["approved_estimates_label"]
    assert b["material_costs_total_minor"] == 600
    assert b["currency"] == "KGS"
    assert b["range"]["from_date"] == "2026-11-02" and b["range"]["to_date"] == "2026-11-05"

    # category filter
    c = get(client, hd, "disp", "/summary", category_id=str(cat2.id), **{"from": "2026-11-02"})
    cb = c.json()
    assert sum(cb["counts_by_status"].values()) == 1 and cb["counts_by_status"]["TRIAGED"] == 1
    assert cb["upcoming_appointments"] == 1
    assert cb["overdue_requests"] == 0
    # technician filter: only r2 is assigned (ACTIVE) to tech; r3's assignment is tech2's
    t = get(
        client, hd, "disp", "/summary", technician_id=str(w.tech[1].id), **{"from": "2026-11-02"}
    )
    tb = t.json()
    assert sum(tb["counts_by_status"].values()) == 1 and tb["counts_by_status"]["TRIAGED"] == 1
    assert tb["upcoming_appointments"] == 1
    assert [x["membership_id"] for x in tb["technician_utilization"]["per_technician"]] == [
        str(w.tech[1].id)
    ]


def test_summary_isolated_between_orgs(client, db, hd, sw):
    seed_request(db, sw.w, status=S.SUBMITTED)
    other = make_world(db, "Other Org")
    for _ in range(3):
        seed_request(db, other, status=S.SUBMITTED)
    b = get(client, hd, "disp", "/summary").json()
    assert b["counts_by_status"]["SUBMITTED"] == 1


# ---- utilization (hand computed) ---------------------------------------------------------
def test_utilization_hand_computed(client, db, hd, sw):
    w = sw.w
    tech3 = make_member(db, w.org, MembershipRole.TECHNICIAN, active=False)
    for _, m in (tech3,):
        for wd in range(7):
            db.add(
                TechnicianAvailability(
                    organization_id=w.org.id,
                    membership_id=m.id,
                    weekday=wd,
                    start_time=time(9),
                    end_time=time(18),
                )
            )
    # tech2: an extra availability interval overlapping 09-18 must not be double counted
    for wd in range(7):
        db.add(
            TechnicianAvailability(
                organization_id=w.org.id,
                membership_id=sw.tech2[1].id,
                weekday=wd,
                start_time=time(12),
                end_time=time(15),
            )
        )
    db.commit()
    # tech: time off Nov 2 12:00-14:00 local (-120)
    db.add(
        TechnicianTimeOff(
            organization_id=w.org.id,
            membership_id=w.tech[1].id,
            start_at=local(2, 12),
            end_at=local(2, 14),
        )
    )
    db.commit()
    req = seed_request(db, w, status=S.COMPLETED)
    # tech: 120 min inside + one straddling the range start (Nov 1 23:00 -> Nov 2 01:00 => 60
    # counted) + a DECLINED one (ignored)
    _assign(db, w, req, w.tech, local(2, 10), local(2, 12))
    _assign(db, w, req, w.tech, local(1, 23), local(2, 1))
    _assign(db, w, req, w.tech, local(3, 10), local(3, 11), AssignmentStatus.DECLINED)
    # tech2: overlapping COMPLETED assignments merge: 09-12 + 11-13 => 240 min
    _assign(db, w, req, sw.tech2, local(3, 9), local(3, 12))
    _assign(db, w, req, sw.tech2, local(3, 11), local(3, 13))
    # inactive technician: heavy load that must be ignored
    _assign(db, w, req, tech3, local(2, 9), local(2, 18))

    u = get(client, hd, "disp", "/summary", **{"from": "2026-11-02", "to": "2026-11-03"}).json()[
        "technician_utilization"
    ]
    per = {p["membership_id"]: p for p in u["per_technician"]}
    assert set(per) == {str(w.tech[1].id), str(sw.tech2[1].id)}  # inactive excluded
    t1, t2 = per[str(w.tech[1].id)], per[str(sw.tech2[1].id)]
    assert (t1["planned_minutes"], t1["available_minutes"]) == (180, 960)  # 2*540 - 120
    assert (t2["planned_minutes"], t2["available_minutes"]) == (240, 1080)
    assert (u["planned_minutes"], u["available_minutes"]) == (420, 2040)
    assert u["percent"] == 20.6 and u["percent_capped"] == 20.6
    assert t1["percent"] == 18.8
    assert "overlapping" in u["explanation"].lower() and "time off" in u["explanation"]


def test_utilization_over_100_capped_and_zero_division(client, db, hd, sw):
    w = sw.w
    narrow = make_member(db, w.org, MembershipRole.TECHNICIAN)
    # available only on Mondays 09-10 (2026-11-02 is a Monday): 60 min in the 2-day range
    db.add(
        TechnicianAvailability(
            organization_id=w.org.id,
            membership_id=narrow[1].id,
            weekday=0,
            start_time=time(9),
            end_time=time(10),
        )
    )
    db.commit()
    req = seed_request(db, w, status=S.COMPLETED)
    _assign(db, w, req, narrow, local(3, 9), local(3, 11))  # Tuesday: outside availability
    p = {"from": "2026-11-02", "to": "2026-11-03", "technician_id": str(narrow[1].id)}
    u = get(client, hd, "disp", "/summary", **p).json()["technician_utilization"]
    assert (u["planned_minutes"], u["available_minutes"]) == (120, 60)
    assert u["percent"] == 200.0 and u["percent_capped"] == 100.0
    # a Tuesday-only range: nothing available -> null, not an error
    p = {"from": "2026-11-03", "to": "2026-11-03", "technician_id": str(narrow[1].id)}
    u = get(client, hd, "disp", "/summary", **p).json()["technician_utilization"]
    assert u["available_minutes"] == 0 and u["percent"] is None and u["percent_capped"] is None


def test_pure_interval_helpers():
    a = datetime(2026, 1, 1, 9, tzinfo=UTC)

    def h(n):
        return a + timedelta(hours=n)

    assert reports.merge_intervals([(h(0), h(3)), (h(2), h(5)), (h(6), h(7))]) == [
        (h(0), h(5)),
        (h(6), h(7)),
    ]
    assert reports.subtract_intervals([(h(0), h(10))], [(h(2), h(3)), (h(8), h(12))]) == [
        (h(0), h(2)),
        (h(3), h(8)),
    ]
    assert reports.minutes([(h(0), h(1)), (h(2), h(2) + timedelta(minutes=30))]) == 90


# ---- date boundaries in org tz ------------------------------------------------------------
def test_org_timezone_boundaries(client, db, hd, sw):
    w = sw.w
    # 23:30 local on Nov 2 = 17:30 UTC (same UTC day); 00:10 local Nov 3 = 18:10 UTC Nov 2
    seed_request(db, w, created_at=local(2, 23, 30), priority=Priority.HIGH)
    seed_request(db, w, created_at=local(3, 0, 10), priority=Priority.LOW)
    # 05:30 local Nov 3 = 23:30 UTC Nov 2: UTC date says Nov 2, local date says Nov 3
    seed_request(db, w, created_at=local(3, 5, 30), priority=Priority.LOW)

    def dist(d1, d2):
        r = get(client, hd, "disp", "/distribution", by="priority", **{"from": d1, "to": d2})
        return {i["key"]: i["count"] for i in r.json()}

    assert dist("2026-11-02", "2026-11-02") == {"HIGH": 1, "NORMAL": 0, "LOW": 0}
    assert dist("2026-11-03", "2026-11-03") == {"HIGH": 0, "NORMAL": 0, "LOW": 2}
    assert dist("2026-11-02", "2026-11-03") == {"HIGH": 1, "NORMAL": 0, "LOW": 2}
    r = get(client, hd, "disp", "/summary", **{"from": "2026-11-02", "to": "2026-11-02"}).json()
    assert r["range"]["start_at"] == local(2, 0).isoformat().replace("+00:00", "Z")
    assert r["range"]["end_at"] == local(3, 0).isoformat().replace("+00:00", "Z")


# ---- daily ---------------------------------------------------------------------------------
def test_daily_fills_zero_days_and_uses_local_dates(client, db, hd, sw, monkeypatch):
    w = sw.w
    set_now(monkeypatch, local(10, 12))
    seed_request(db, w, created_at=local(8, 23, 30))
    seed_request(db, w, created_at=local(9, 0, 10), status=S.COMPLETED, completed_at=local(9, 23))
    seed_request(db, w, created_at=local(9, 8))
    seed_request(db, w, created_at=local(5, 8))  # outside a 3-day window
    other = make_world(db, "Other Org")
    seed_request(db, other, created_at=local(9, 8))
    rows = get(client, hd, "disp", "/daily", days=3).json()
    assert rows == [
        {"date": "2026-11-08", "new_requests": 1, "completed_requests": 0},
        {"date": "2026-11-09", "new_requests": 2, "completed_requests": 1},
        {"date": "2026-11-10", "new_requests": 0, "completed_requests": 0},
    ]
    default = get(client, hd, "disp", "/daily").json()
    assert len(default) == 14 and default[-1]["date"] == "2026-11-10"
    assert default[0]["date"] == "2026-10-28"


# ---- distribution --------------------------------------------------------------------------
def test_distribution_by_priority_and_category(client, db, hd, sw):
    w = sw.w
    cat2 = make_category(db, w.org, "Plumbing")
    make_category(db, w.org, "Disabled", enabled=False)
    seed_request(db, w, created_at=local(2, 9), priority=Priority.HIGH)
    seed_request(db, w, created_at=local(2, 9), priority=Priority.HIGH, category_id=cat2.id)
    seed_request(db, w, created_at=local(2, 9), priority=Priority.NORMAL)
    seed_request(db, w, created_at=local(20, 9), priority=Priority.LOW)  # out of range
    p = {"from": "2026-11-02", "to": "2026-11-04"}
    pri = get(client, hd, "disp", "/distribution", by="priority", **p).json()
    assert pri == [
        {"key": "HIGH", "label": "High", "count": 2},
        {"key": "NORMAL", "label": "Normal", "count": 1},
        {"key": "LOW", "label": "Low", "count": 0},
    ]
    cat = get(client, hd, "disp", "/distribution", by="category", **p).json()
    assert [(c["label"], c["count"]) for c in cat] == [("HVAC", 2), ("Plumbing", 1)]
    assert cat[0]["key"] == str(w.cat.id)
