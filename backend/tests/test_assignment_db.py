"""DB-level guarantees of the assignments table (SCHED-03)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.models import Assignment
from app.models.enums import AssignmentStatus, RequestStatus
from tests.req_helpers import seed_request
from tests.sched_helpers import make_sched_world

T0 = datetime(2031, 3, 3, 10, 0, tzinfo=UTC)


def _row(sw, req, start, end, status=AssignmentStatus.ACTIVE, tech=None):
    return Assignment(
        organization_id=sw.w.org.id,
        request_id=req.id,
        technician_membership_id=(tech or sw.w.tech)[1].id,
        start_at=start,
        end_at=end,
        status=status,
        active=status == AssignmentStatus.ACTIVE,
        assigned_by_membership_id=sw.w.disp[1].id,
    )


def _req(db, sw):
    return seed_request(db, sw.w, status=RequestStatus.TRIAGED)


def test_overlapping_active_rows_rejected(db, sw):
    db.add(_row(sw, _req(db, sw), T0, T0 + timedelta(hours=2)))
    db.commit()
    db.add(_row(sw, _req(db, sw), T0 + timedelta(hours=1), T0 + timedelta(hours=3)))
    with pytest.raises(IntegrityError) as exc:
        db.commit()
    assert "ex_assignments_technician_no_overlap" in str(exc.value)
    db.rollback()


def test_adjacent_half_open_intervals_allowed(db, sw):
    db.add(_row(sw, _req(db, sw), T0, T0 + timedelta(hours=1)))  # 10:00-11:00
    db.add(_row(sw, _req(db, sw), T0 + timedelta(hours=1), T0 + timedelta(hours=2)))  # 11:00-12:00
    db.commit()


def test_other_technician_same_window_allowed(db, sw):
    db.add(_row(sw, _req(db, sw), T0, T0 + timedelta(hours=1)))
    db.add(_row(sw, _req(db, sw), T0, T0 + timedelta(hours=1), tech=sw.tech2))
    db.commit()


def test_inactive_rows_never_block(db, sw):
    db.add(_row(sw, _req(db, sw), T0, T0 + timedelta(hours=1), AssignmentStatus.DECLINED))
    db.add(_row(sw, _req(db, sw), T0, T0 + timedelta(hours=1), AssignmentStatus.COMPLETED))
    db.add(_row(sw, _req(db, sw), T0, T0 + timedelta(hours=1)))
    db.commit()


def test_one_active_assignment_per_request(db, sw):
    req = _req(db, sw)
    db.add(_row(sw, req, T0, T0 + timedelta(hours=1)))
    db.commit()
    db.add(_row(sw, req, T0 + timedelta(days=1), T0 + timedelta(days=1, hours=1), tech=sw.tech2))
    with pytest.raises(IntegrityError) as exc:
        db.commit()
    assert "uq_assignments_one_active_per_request" in str(exc.value)
    db.rollback()


def test_minimum_duration_and_active_flag_checks(db, sw):
    db.add(_row(sw, _req(db, sw), T0, T0 + timedelta(minutes=29)))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    bad = _row(sw, _req(db, sw), T0, T0 + timedelta(hours=1))
    bad.active = False  # ACTIVE status but active=false
    db.add(bad)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add(_row(sw, _req(db, sw), T0, T0 + timedelta(minutes=30)))  # exactly 30 is fine
    db.commit()


def test_assignment_rows_cannot_be_deleted(db, sw):
    a = _row(sw, _req(db, sw), T0, T0 + timedelta(hours=1))
    db.add(a)
    db.commit()
    with pytest.raises(DBAPIError):
        db.execute(text("DELETE FROM assignments WHERE id = :i"), {"i": a.id})
    db.rollback()


def test_cross_org_technician_rejected_by_composite_fk(db, sw):
    other = make_sched_world(db, "Org B")
    row = _row(sw, _req(db, sw), T0, T0 + timedelta(hours=1), tech=other.w.tech)
    db.add(row)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
