"""Pure SLA engine (SLA-02..05): derives the SLA state ONLY from a request's events.

Model: a request owns a *clock* that runs (consuming business time) except while paused or
stopped. The state machine over time-ordered events:

* ``REQUEST_CREATED``  starts the clock (fallback: ``request.created_at`` if the event is missing).
* ``ESTIMATE_SUBMITTED``  pauses it. ``ESTIMATE_APPROVED`` / ``_REJECTED`` / ``_WITHDRAWN`` resume
  it (a no-op when not paused). A resubmission while one is pending emits only another
  SUBMITTED, so the clock simply stays paused: pause is active iff the latest estimate event
  is ``ESTIMATE_SUBMITTED``.
* ``PRIORITY_CHANGED``  replaces the TOTAL budget (HIGH 480 / NORMAL 1440 / LOW 2880 business
  minutes); consumed time carries over, so remaining = new budget - already consumed.
* ``STATUS_CHANGED`` to COMPLETED or CANCELED  stops the clock and freezes the outcome
  (MET if consumed <= budget else BREACHED). CLOSED keeps the frozen outcome.
* ``STATUS_CHANGED`` to REOPENED  restarts the clock. DECISION: rework time counts, i.e.
  consumed time carries over from before the completion and the clock keeps running against
  the (current) total budget, so a reopened request can immediately be overdue.

Time is tracked exactly (``timedelta``); minute figures are floored, except ``remaining`` /
``overdue_by`` which are floored on the absolute value. OVERDUE is strict (remaining < 0).
AT_RISK is remaining <= 25 % of the budget (inclusive). ``at_risk_at`` is the instant the
remaining time reached 25 % and is kept after it has passed (the list filter needs it).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from app.models.enums import Priority, RequestStatus
from app.models.requests import RequestEvent, ServiceRequest
from app.sla.calendar import ZERO, BusinessCalendar

BUDGET_MINUTES: dict[Priority, int] = {
    Priority.HIGH: 8 * 60,
    Priority.NORMAL: 24 * 60,
    Priority.LOW: 48 * 60,
}
AT_RISK_DIVISOR = 4  # remaining <= budget / 4

ON_TRACK, AT_RISK, OVERDUE = "ON_TRACK", "AT_RISK", "OVERDUE"
MET, BREACHED = "MET", "BREACHED"

ESTIMATE_PAUSE = "ESTIMATE_SUBMITTED"
ESTIMATE_RESUME = frozenset({"ESTIMATE_APPROVED", "ESTIMATE_REJECTED", "ESTIMATE_WITHDRAWN"})
SLA_EVENT_TYPES = frozenset(
    {"REQUEST_CREATED", "PRIORITY_CHANGED", ESTIMATE_PAUSE, *ESTIMATE_RESUME, "STATUS_CHANGED"}
)
_STOPPING = {RequestStatus.COMPLETED.value, RequestStatus.CANCELED.value}
_STOP_STATUSES = (RequestStatus.COMPLETED, RequestStatus.CLOSED, RequestStatus.CANCELED)


def budget_for(priority: Priority | str) -> int:
    return BUDGET_MINUTES[Priority(priority)]


def is_sla_event(type_: str, to_status: str | None) -> bool:
    """Whether an event can change the SLA state (the recompute trigger set)."""
    if type_ == "STATUS_CHANGED":
        return to_status in (*_STOPPING, RequestStatus.REOPENED.value)
    return type_ in SLA_EVENT_TYPES


@dataclass(frozen=True)
class SlaState:
    budget_minutes: int
    consumed_minutes: int
    remaining_minutes: int  # negative while overdue
    overdue_by_minutes: int  # 0 unless overdue
    paused: bool
    stopped: bool
    stopped_at: datetime | None
    due_at: datetime | None  # None while paused, stopped or without business hours
    at_risk_at: datetime | None
    state: str  # ON_TRACK | AT_RISK | OVERDUE (stopped: the state at the stop instant)
    outcome: str | None  # MET | BREACHED once stopped


def classify(remaining: timedelta, budget: timedelta) -> str:
    if remaining < ZERO:
        return OVERDUE
    return AT_RISK if remaining <= budget / AT_RISK_DIVISOR else ON_TRACK


def stopped_state(budget_minutes: int, consumed_minutes: int, outcome: str) -> str:
    """State at the stop instant from persisted integers (same result as ``compute_sla``)."""
    if outcome == BREACHED:
        return OVERDUE
    return (
        AT_RISK
        if consumed_minutes * AT_RISK_DIVISOR >= (AT_RISK_DIVISOR - 1) * budget_minutes
        else ON_TRACK
    )


def _instant_at(
    cal: BusinessCalendar,
    segments: Sequence[tuple[datetime, datetime]],
    open_start: datetime | None,
    target: timedelta,
) -> datetime | None:
    """Instant at which cumulative business time over the running segments reaches ``target``."""
    cum = ZERO
    for s, e in segments:
        d = cal.business_time_between(s, e)
        if cum + d >= target:
            return cal.add_business_time(s, target - cum)
        cum += d
    if open_start is None:
        return None
    return cal.add_business_time(open_start, target - cum)


def _initial_priority(request: ServiceRequest, events: Sequence[RequestEvent]) -> Priority:
    for ev in events:
        data: dict[str, Any] = ev.data or {}
        if ev.type == "REQUEST_CREATED" and data.get("priority"):
            return Priority(data["priority"])
        if ev.type == "PRIORITY_CHANGED" and data.get("from"):
            return Priority(data["from"])
    return request.priority


def _mins(td: timedelta) -> int:
    return int(td // timedelta(minutes=1))


def compute_sla(
    request: ServiceRequest,
    events: Sequence[RequestEvent],
    calendar: BusinessCalendar,
    now: datetime,
) -> SlaState:
    evs = sorted(events, key=lambda e: e.created_at)  # stable: ties keep the given order
    created = next((e for e in evs if e.type == "REQUEST_CREATED"), None)
    start = created.created_at if created is not None else request.created_at
    budget = budget_for(_initial_priority(request, evs))

    stopped_at: datetime | None = None
    frozen: tuple[int, timedelta] | None = None  # (budget, consumed) at the stop instant
    est_paused = False
    segments: list[tuple[datetime, datetime]] = []
    open_start: datetime | None = start

    def consumed_closed() -> timedelta:
        return sum((calendar.business_time_between(s, e) for s, e in segments), ZERO)

    def settle(t: datetime) -> None:
        nonlocal open_start
        running = stopped_at is None and not est_paused
        if open_start is not None and not running:
            segments.append((open_start, t))
            open_start = None
        elif open_start is None and running:
            open_start = t

    for ev in evs:
        if ev is created:
            continue
        t = ev.created_at
        data: dict[str, Any] = ev.data or {}
        if ev.type == "PRIORITY_CHANGED" and data.get("to"):
            budget = budget_for(data["to"])
        elif ev.type == ESTIMATE_PAUSE:
            est_paused = True
        elif ev.type in ESTIMATE_RESUME:
            est_paused = False
        elif ev.type == "STATUS_CHANGED":
            if ev.to_status in _STOPPING and stopped_at is None:
                stopped_at = t
                settle(t)
                frozen = (budget, consumed_closed())
            elif ev.to_status == RequestStatus.REOPENED.value and stopped_at is not None:
                stopped_at, frozen = None, None
        settle(t)

    if stopped_at is None and request.status in _STOP_STATUSES:
        # Row set directly without lifecycle events (tests / legacy data): stop at its stamp.
        stopped_at = (
            request.completed_at
            or request.closed_at
            or request.canceled_at
            or request.status_changed_at
            or now
        )
        stopped_at = max(stopped_at, start)
        settle(stopped_at)
        frozen = (budget, consumed_closed())

    if stopped_at is not None and frozen is not None:
        f_budget, f_consumed = frozen
        budget_td = timedelta(minutes=f_budget)
        outcome = MET if f_consumed <= budget_td else BREACHED
        consumed_min = _mins(f_consumed)
        return SlaState(
            budget_minutes=f_budget,
            consumed_minutes=consumed_min,
            remaining_minutes=f_budget - consumed_min,
            overdue_by_minutes=0,
            paused=False,
            stopped=True,
            stopped_at=stopped_at,
            due_at=None,
            at_risk_at=None,
            state=stopped_state(f_budget, consumed_min, outcome),
            outcome=outcome,
        )

    budget_td = timedelta(minutes=budget)
    consumed = consumed_closed()
    if open_start is not None:
        consumed += calendar.business_time_between(open_start, now)
    remaining = budget_td - consumed
    paused = est_paused
    due_at = at_risk_at = None
    if not paused:
        due_at = _instant_at(calendar, segments, open_start, budget_td)
        at_risk_at = _instant_at(
            calendar,
            segments,
            open_start,
            budget_td - budget_td / AT_RISK_DIVISOR,
        )
    over = -remaining if remaining < ZERO else ZERO
    return SlaState(
        budget_minutes=budget,
        consumed_minutes=_mins(consumed),
        remaining_minutes=_mins(remaining) if remaining >= ZERO else -_mins(over),
        overdue_by_minutes=_mins(over),
        paused=paused,
        stopped=False,
        stopped_at=None,
        due_at=due_at,
        at_risk_at=at_risk_at,
        state=classify(remaining, budget_td),
        outcome=None,
    )
