"""Scheduling world: two skilled technicians available every day 09:00-18:00 Asia/Bishkek."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.models import (
    CategoryRequiredSkill,
    Skill,
    TechnicianAvailability,
    TechnicianSkill,
)
from app.models.enums import RequestStatus
from tests.factories import make_member
from tests.req_helpers import Org, make_world, seed_request

API = "/api/v1"
TZ = ZoneInfo("Asia/Bishkek")
S = RequestStatus
R_TECH = "TECHNICIAN"


def local_slot(day_offset: int, hour: int, minutes: int = 60, minute: int = 0):
    """(start, end) UTC for a future local day (relative to now) at hour:minute, given length."""
    base = (datetime.now(TZ) + timedelta(days=day_offset)).date()
    start = datetime.combine(base, time(hour, minute), tzinfo=TZ).astimezone(UTC)
    return start, start + timedelta(minutes=minutes)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


@dataclass
class SchedWorld:
    w: Org
    tech2: tuple[Any, Any]
    skill: Skill


def _m(membership):
    return membership[1] if isinstance(membership, tuple) else membership


def give_availability(db, org, membership, start=time(9, 0), end=time(18, 0), weekdays=range(7)):
    membership = _m(membership)
    for wd in weekdays:
        db.add(
            TechnicianAvailability(
                organization_id=org.id,
                membership_id=membership.id,
                weekday=wd,
                start_time=start,
                end_time=end,
            )
        )
    db.commit()


def give_skill(db, org, membership, skill):
    membership = _m(membership)
    db.add(TechnicianSkill(organization_id=org.id, membership_id=membership.id, skill_id=skill.id))
    db.commit()


def make_sched_world(db, name: str = "Org A") -> SchedWorld:
    w = make_world(db, name)
    skill = Skill(organization_id=w.org.id, name="hvac")
    db.add(skill)
    db.commit()
    db.add(CategoryRequiredSkill(organization_id=w.org.id, category_id=w.cat.id, skill_id=skill.id))
    db.commit()
    tech2 = make_member(
        db, w.org, __import__("app.models", fromlist=["MembershipRole"]).MembershipRole.TECHNICIAN
    )
    for _, m in (w.tech, tech2):
        give_skill(db, w.org, m, skill)
        give_availability(db, w.org, m)
    return SchedWorld(w, tech2, skill)


def triaged(db, w: Org, **over):
    return seed_request(db, w, status=S.TRIAGED, **over)


def assign(client, hd, req, tech, start, end, who="disp", **headers):
    return client.post(
        f"{API}/requests/{req.id}/assignment",
        json={
            "technician_membership_id": str(tech[1].id),
            "start_at": iso(start),
            "end_at": iso(end),
        },
        headers={**hd[who], **headers},
    )


def new_key() -> str:
    return uuid.uuid4().hex
