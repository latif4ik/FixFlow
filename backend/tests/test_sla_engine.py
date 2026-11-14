"""Pure SLA engine tests: events in, state out (no DB)."""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.models import RequestEvent, ServiceRequest
from app.models.enums import Priority, RequestStatus
from app.sla.calendar import BusinessCalendar
from app.sla.engine import compute_sla, stopped_state

TZ = ZoneInfo("Asia/Bishkek")
WEEK = {d: [(time(9), time(18))] for d in range(5)}


def at(d: int, hh: int = 0, mm: int = 0, ss: int = 0, month: int = 11) -> datetime:
    """Local Bishkek instant in 2026-<month>-<d> (Nov 13 = Friday, Nov 16 = Monday)."""
    return datetime(2026, month, d, hh, mm, ss, tzinfo=TZ).astimezone(UTC)


def cal(holidays=()) -> BusinessCalendar:
    return BusinessCalendar(TZ, WEEK, set(holidays))


def ev(type_: str, t: datetime, to_status: str | None = None, **data) -> RequestEvent:
    return RequestEvent(
        id=uuid.uuid4(), type=type_, created_at=t, to_status=to_status, data=data or None
    )


def req(priority=Priority.HIGH, status=RequestStatus.SUBMITTED, created=None) -> ServiceRequest:
    return ServiceRequest(
        priority=priority, status=status, created_at=created or at(13, 17), id=uuid.uuid4()
    )


def created(t: datetime, priority: Priority = Priority.HIGH) -> RequestEvent:
    return ev("REQUEST_CREATED", t, "SUBMITTED", priority=priority.value)


def status(t: datetime, to: str) -> RequestEvent:
    return ev("STATUS_CHANGED", t, to)


def test_friday_1700_high_due_monday_1600():
    st = compute_sla(req(), [created(at(13, 17))], cal(), at(13, 17))
    assert st.budget_minutes == 480 and st.due_at == at(16, 16)
    assert (st.consumed_minutes, st.remaining_minutes, st.state) == (0, 480, "ON_TRACK")
    assert not st.paused and not st.stopped and st.outcome is None


def test_monday_holiday_moves_due_to_tuesday():
    st = compute_sla(req(), [created(at(13, 17))], cal([date(2026, 11, 16)]), at(13, 17))
    assert st.due_at == at(17, 16)


def test_budgets_by_priority():
    for prio, minutes in ((Priority.HIGH, 480), (Priority.NORMAL, 1440), (Priority.LOW, 2880)):
        st = compute_sla(req(prio), [created(at(16, 9), prio)], cal(), at(16, 9))
        assert st.budget_minutes == minutes
    # NORMAL = 24 business hours from Mon 09:00 -> Wed 15:00
    st = compute_sla(req(Priority.NORMAL), [created(at(16, 9), Priority.NORMAL)], cal(), at(16, 9))
    assert st.due_at == at(18, 15)


def test_estimate_pause_shifts_due_by_exactly_paused_business_time():
    evs = [
        created(at(13, 17)),
        ev("ESTIMATE_SUBMITTED", at(16, 10)),
        ev("ESTIMATE_APPROVED", at(17, 10)),
    ]
    base = compute_sla(req(), evs[:1], cal(), at(16, 10)).due_at
    st = compute_sla(req(), evs, cal(), at(17, 10))
    assert base == at(16, 16)
    # consumed: Fri 1h + Mon 09-10 1h = 2h; resumes Tue 10:00 with 6h left
    assert st.consumed_minutes == 120 and st.remaining_minutes == 360
    assert st.due_at == at(17, 16)
    paused_business = cal().business_minutes_between(at(16, 10), at(17, 10))
    assert paused_business == 9 * 60
    assert base is not None and st.due_at is not None
    assert cal().business_minutes_between(base, st.due_at) == paused_business


def test_while_paused_no_due_and_no_consumption():
    evs = [created(at(16, 9)), ev("ESTIMATE_SUBMITTED", at(16, 10))]
    a = compute_sla(req(), evs, cal(), at(16, 12))
    b = compute_sla(req(), evs, cal(), at(20, 12))
    assert a.paused and a.due_at is None and a.at_risk_at is None
    assert a.consumed_minutes == b.consumed_minutes == 60
    assert b.remaining_minutes == 420 and b.state == "ON_TRACK"


def test_resubmission_while_pending_stays_paused_and_rejection_resumes():
    evs = [
        created(at(16, 9)),
        ev("ESTIMATE_SUBMITTED", at(16, 10)),
        ev("ESTIMATE_SUBMITTED", at(16, 11)),  # supersedes, no resume event in between
    ]
    st = compute_sla(req(), evs, cal(), at(16, 15))
    assert st.paused and st.consumed_minutes == 60 and st.due_at is None
    evs.append(ev("ESTIMATE_REJECTED", at(17, 9)))
    st = compute_sla(req(), evs, cal(), at(17, 10))
    assert not st.paused and st.consumed_minutes == 120 and st.due_at == at(17, 16)


def test_withdrawn_and_stray_resume_events():
    evs = [created(at(16, 9)), ev("ESTIMATE_APPROVED", at(16, 10))]  # resume when not paused
    st = compute_sla(req(), evs, cal(), at(16, 12))
    assert not st.paused and st.consumed_minutes == 180
    evs = [
        created(at(16, 9)),
        ev("ESTIMATE_SUBMITTED", at(16, 10)),
        ev("ESTIMATE_WITHDRAWN", at(16, 11)),
    ]
    st = compute_sla(req(), evs, cal(), at(16, 12))
    assert not st.paused and st.consumed_minutes == 120  # 09-10 and 11-12


def test_priority_normal_to_high_after_7_consumed_hours():
    r = req(Priority.HIGH)  # current priority after the change
    evs = [
        created(at(16, 9), Priority.NORMAL),
        ev("PRIORITY_CHANGED", at(16, 16), **{"from": "NORMAL", "to": "HIGH"}),
    ]
    st = compute_sla(r, evs, cal(), at(16, 16))
    assert st.budget_minutes == 480 and st.consumed_minutes == 420 and st.remaining_minutes == 60
    assert st.due_at == at(16, 17) and st.state == "AT_RISK"


def test_priority_high_to_low_recalculates_and_initial_from_change_event():
    # created event without priority data -> initial priority taken from the change's "from"
    evs = [
        ev("REQUEST_CREATED", at(16, 9), "SUBMITTED"),
        ev("PRIORITY_CHANGED", at(16, 16), **{"from": "HIGH", "to": "LOW"}),
    ]
    st = compute_sla(req(Priority.LOW), evs, cal(), at(16, 16))
    assert st.budget_minutes == 2880 and st.consumed_minutes == 420
    assert st.remaining_minutes == 2460 and st.state == "ON_TRACK"
    assert st.due_at == cal().add_business_minutes(at(16, 9), 2880)


def test_priority_change_when_already_overdue_gives_past_due():
    evs = [
        created(at(16, 9)),
        ev("PRIORITY_CHANGED", at(18, 9), **{"from": "HIGH", "to": "HIGH"}),
    ]
    st = compute_sla(req(), evs, cal(), at(18, 10))
    assert st.state == "OVERDUE" and st.due_at == at(16, 17)
    assert st.overdue_by_minutes == cal().business_minutes_between(at(16, 17), at(18, 10))


def test_at_risk_and_overdue_boundaries():
    r, evs = req(), [created(at(16, 9))]  # budget 480: at risk from 360 consumed = 15:00
    assert compute_sla(r, evs, cal(), at(16, 14, 59, 59)).state == "ON_TRACK"
    st = compute_sla(r, evs, cal(), at(16, 15))
    assert st.state == "AT_RISK" and st.remaining_minutes == 120 and st.at_risk_at == at(16, 15)
    assert compute_sla(r, evs, cal(), at(16, 17)).state == "AT_RISK"  # remaining == 0
    over = compute_sla(r, evs, cal(), at(16, 17, 0, 1))
    assert over.state == "OVERDUE" and over.overdue_by_minutes == 0
    over = compute_sla(r, evs, cal(), at(16, 17, 30))
    assert over.state == "OVERDUE" and over.overdue_by_minutes == 30
    assert over.remaining_minutes == -30 and over.due_at == at(16, 17)


def test_completed_freezes_outcome():
    evs = [created(at(16, 9)), status(at(16, 12), "COMPLETED")]
    r = req(status=RequestStatus.COMPLETED)
    a = compute_sla(r, evs, cal(), at(16, 13))
    b = compute_sla(r, evs, cal(), at(30, 13))
    assert a == b
    assert a.stopped and a.stopped_at == at(16, 12) and a.outcome == "MET"
    assert (a.consumed_minutes, a.remaining_minutes, a.state) == (180, 300, "ON_TRACK")
    assert a.due_at is None and not a.paused


def test_completed_late_is_breached_and_closed_keeps_it():
    evs = [created(at(16, 9)), status(at(18, 9), "COMPLETED")]  # 18h consumed on 8h
    st = compute_sla(req(status=RequestStatus.COMPLETED), evs, cal(), at(25, 9))
    assert st.outcome == "BREACHED" and st.state == "OVERDUE" and st.consumed_minutes == 1080
    evs.append(status(at(19, 9), "CLOSED"))
    closed = compute_sla(req(status=RequestStatus.CLOSED), evs, cal(), at(25, 9))
    assert closed == st or (closed.outcome, closed.consumed_minutes) == ("BREACHED", 1080)
    assert closed.stopped_at == at(18, 9)


def test_reopened_resumes_clock_with_carried_consumption():
    evs = [
        created(at(16, 9)),
        status(at(16, 12), "COMPLETED"),
        status(at(17, 9), "REOPENED"),
    ]
    r = req(status=RequestStatus.REOPENED)
    st = compute_sla(r, evs, cal(), at(17, 10))
    assert not st.stopped and st.outcome is None
    assert st.consumed_minutes == 240 and st.remaining_minutes == 240
    assert st.due_at == at(17, 14)  # 5h of budget left at Tue 09:00
    done = [*evs, status(at(17, 15), "COMPLETED")]
    st2 = compute_sla(req(status=RequestStatus.COMPLETED), done, cal(), at(30, 9))
    assert st2.stopped and st2.outcome == "BREACHED" and st2.consumed_minutes == 540


def test_canceled_retains_outcome_even_when_paused_at_cancel():
    evs = [created(at(16, 9)), status(at(16, 10), "CANCELED")]
    st = compute_sla(req(status=RequestStatus.CANCELED), evs, cal(), at(20, 9))
    assert st.stopped and st.outcome == "MET" and st.consumed_minutes == 60
    evs = [
        created(at(16, 9)),
        ev("ESTIMATE_SUBMITTED", at(16, 10)),
        status(at(16, 11), "CANCELED"),
    ]
    st = compute_sla(req(status=RequestStatus.CANCELED), evs, cal(), at(20, 9))
    assert st.stopped and not st.paused and st.consumed_minutes == 60


def test_priority_change_after_stop_does_not_change_outcome():
    evs = [
        created(at(16, 9)),
        status(at(18, 9), "COMPLETED"),  # 18h on a HIGH (8h) budget: BREACHED
        ev("PRIORITY_CHANGED", at(18, 10), **{"from": "HIGH", "to": "LOW"}),
    ]
    st = compute_sla(req(Priority.LOW, RequestStatus.COMPLETED), evs, cal(), at(19, 9))
    assert st.outcome == "BREACHED" and st.budget_minutes == 480


def test_request_without_events_falls_back_to_created_at():
    r = req(Priority.NORMAL, created=at(16, 9))
    st = compute_sla(r, [], cal(), at(16, 10))
    assert st.consumed_minutes == 60 and st.budget_minutes == 1440
    r = req(Priority.NORMAL, RequestStatus.COMPLETED, created=at(16, 9))
    r.completed_at = at(16, 11)
    st = compute_sla(r, [], cal(), at(30, 10))
    assert st.stopped and st.consumed_minutes == 120 and st.outcome == "MET"


def test_no_business_hours_gives_no_due():
    c = BusinessCalendar(TZ, {}, set())
    st = compute_sla(req(), [created(at(16, 9))], c, at(17, 9))
    assert st.due_at is None and st.at_risk_at is None and st.consumed_minutes == 0
    assert st.state == "ON_TRACK"


def test_stopped_state_helper_matches_engine():
    for consumed in (0, 359, 360, 479, 480):
        evs = [created(at(16, 9)), status(at(16, 9) + timedelta(minutes=consumed), "COMPLETED")]
        # keep the consumption inside business hours: 9..17 on Monday is enough for <= 480
        st = compute_sla(req(status=RequestStatus.COMPLETED), evs, cal(), at(30, 9))
        assert st.state == stopped_state(480, st.consumed_minutes, st.outcome or "")
