"""Deterministic, idempotent demo seed (``python -m app.cli seed``).

Every row uses a UUIDv5 derived from a stable name, and is created only if missing, so
re-running never duplicates or overwrites data. All demo passwords are the disposable
string below; never use this in production.
"""

import hashlib
import io
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import money
from app.core.audit import sanitize
from app.core.security import hash_password
from app.models import (
    Asset,
    Assignment,
    BusinessHour,
    CategoryRequiredSkill,
    Estimate,
    EstimateLine,
    EvidenceFile,
    Feedback,
    Holiday,
    InventoryItem,
    MaintenancePlan,
    MaterialUsage,
    Membership,
    MembershipRole,
    Notification,
    Organization,
    Property,
    PropertyAccess,
    RequestEvent,
    ServiceCategory,
    ServiceRequest,
    Skill,
    StockMovement,
    TechnicianAvailability,
    TechnicianProfile,
    TechnicianSkill,
    User,
    WorkNote,
)
from app.models.enums import (
    AssignmentStatus,
    EstimateStatus,
    FilePurpose,
    NoteKind,
    NoteVisibility,
    Priority,
    Recurrence,
    RequestStatus,
    StockMovementKind,
)
from app.services.files import upload_root
from app.sla.service import recompute_all

DEMO_PASSWORD = "demo1234"  # noqa: S105 - disposable demo credential, documented
NAMESPACE = uuid.UUID("6f1f2c4e-8f0b-4a53-9c63-0f1f0c5e11a0")
SHARED_EMAIL = "shared@fixflow.demo"
R = MembershipRole


def uid(*parts: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, ":".join(parts))


def _bday(today: date, offset: int) -> date:
    """Business day ``offset`` days from ``today`` (0 = today, or next Monday on weekends)."""
    d, step = today, (1 if offset > 0 else -1)
    for _ in range(abs(offset)):
        d += timedelta(days=step)
        while d.weekday() >= 5:
            d += timedelta(days=step)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _local(tz: ZoneInfo, d: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(d, time(hour, minute), tzinfo=tz).astimezone(UTC)


def make_image(label: str, fmt: str) -> bytes:
    """Small deterministic PNG/JPEG: a solid colour derived from ``label`` plus simple shapes."""
    h = hashlib.sha256(label.encode()).digest()
    bg = (60 + h[0] % 120, 60 + h[1] % 120, 60 + h[2] % 120)
    img = Image.new("RGB", (320, 240), bg)
    d = ImageDraw.Draw(img)
    x0, y0 = 20 + h[3] % 60, 20 + h[4] % 50
    d.rectangle((x0, y0, x0 + 120, y0 + 80), fill=(240, 240, 240), outline=(20, 20, 20), width=3)
    d.ellipse((180 + h[5] % 40, 110 + h[6] % 40, 280, 210), fill=(h[7], h[8], h[9]))
    d.line((10, 230, 310, 10 + h[10] % 40), fill=(255, 255, 255), width=4)
    buf = io.BytesIO()
    if fmt == "JPEG":
        img.save(buf, format="JPEG", quality=80)
    else:
        img.save(buf, format="PNG")
    return buf.getvalue()


@dataclass(frozen=True)
class Bulk:
    """One extra seeded request (see ``Seeder.seed_history``)."""

    key: str
    pidx: int
    asset_n: int | None
    category: str
    title: str
    priority: Priority
    final: RequestStatus
    tech: str | None = None  # technician key; None = unassigned
    day: int = 0  # business-day offset of the assignment slot (negative = past)
    hour: int = 13
    minutes: int = 60
    who: str = "requester1"
    created_day: int | None = None  # business-day offset of creation; default = day - 1
    rating: int | None = None
    comment: str | None = None
    intake: int = 0  # number of INTAKE images
    completion_image: bool = False  # COMPLETION image on finished jobs


_S, _P = RequestStatus, Priority
# 12 finished jobs spread over the previous ~14 days (+ the same asset several times), then
# open / future / canceled / reopened requests. All slots are inside business hours (09-18).
BULK: tuple[Bulk, ...] = (
    Bulk(
        "h01",
        0,
        1,
        "HVAC",
        "Replace fan belt on the rooftop AC",
        _P.HIGH,
        _S.CLOSED,
        "technician3",
        -1,
        16,
        90,
        "requester1",
        rating=5,
        comment="Fast and tidy.",
        completion_image=True,
    ),
    Bulk(
        "h02",
        1,
        None,
        "Plumbing",
        "Repair leaking pipe joint in the basement",
        _P.HIGH,
        _S.COMPLETED,
        "technician2",
        -2,
        13,
        120,
        "requester1",
        rating=4,
        comment="Fixed, small mess left behind.",
        intake=1,
        completion_image=True,
    ),
    Bulk(
        "h03",
        0,
        None,
        "Electrical",
        "Replace faulty breaker in panel B",
        _P.NORMAL,
        _S.CLOSED,
        "technician1",
        -3,
        13,
        90,
        "requester1",
        rating=3,
        completion_image=True,
    ),
    Bulk(
        "h04",
        3,
        1,
        "HVAC",
        "Clean condenser coils",
        _P.NORMAL,
        _S.CLOSED,
        "technician3",
        -3,
        16,
        60,
        "requester3",
        rating=5,
        completion_image=True,
    ),
    Bulk(
        "h05",
        3,
        None,
        "General maintenance",
        "Adjust the sticking lobby door",
        _P.LOW,
        _S.COMPLETED,
        "technician4",
        -4,
        13,
        60,
        "requester3",
        completion_image=True,
    ),
    Bulk(
        "h06",
        4,
        2,
        "General maintenance",
        "Annual boiler inspection",
        _P.NORMAL,
        _S.CLOSED,
        "technician4",
        -4,
        15,
        90,
        "requester3",
        rating=4,
        comment="Report was clear.",
    ),
    Bulk(
        "h07",
        1,
        1,
        "HVAC",
        "Rooftop AC compressor noise",
        _P.HIGH,
        _S.COMPLETED,
        "technician3",
        -5,
        16,
        120,
        "requester1",
        rating=2,
        comment="Noise returned later.",
        intake=2,
        completion_image=True,
    ),
    Bulk(
        "h08",
        0,
        1,
        "HVAC",
        "Rooftop AC thermostat recalibration",
        _P.NORMAL,
        _S.CLOSED,
        "technician3",
        -7,
        16,
        60,
        "requester1",
        rating=5,
        completion_image=True,
    ),
    Bulk(
        "h09",
        5,
        None,
        "Electrical",
        "Install emergency exit lighting",
        _P.HIGH,
        _S.CLOSED,
        "technician1",
        -6,
        13,
        120,
        "requester3",
        rating=4,
        completion_image=True,
    ),
    Bulk(
        "h10",
        4,
        None,
        "Plumbing",
        "Replace washroom tap",
        _P.LOW,
        _S.COMPLETED,
        "technician2",
        -8,
        13,
        60,
        "requester3",
    ),
    Bulk(
        "h11",
        1,
        None,
        "Electrical",
        "Rewire the break-room outlets",
        _P.NORMAL,
        _S.CLOSED,
        "technician1",
        -9,
        13,
        120,
        "requester1",
        rating=3,
        comment="Took longer than planned.",
    ),
    Bulk(
        "h12",
        5,
        2,
        "General maintenance",
        "Boiler pressure valve replacement",
        _P.HIGH,
        _S.CLOSED,
        "technician4",
        -10,
        13,
        120,
        "requester3",
        rating=5,
        completion_image=True,
    ),
    Bulk(
        "o01",
        3,
        None,
        "Electrical",
        "Flickering lights in room 12",
        _P.NORMAL,
        _S.SUBMITTED,
        who="requester3",
        created_day=-1,
        intake=1,
    ),
    Bulk(
        "o02",
        4,
        None,
        "Plumbing",
        "Toilet keeps running",
        _P.LOW,
        _S.SUBMITTED,
        who="requester3",
        created_day=-2,
    ),
    Bulk(
        "o03",
        1,
        None,
        "HVAC",
        "No heating in the east wing",
        _P.HIGH,
        _S.SUBMITTED,
        who="requester1",
        created_day=-1,
        intake=2,
    ),
    Bulk(
        "o04",
        5,
        None,
        "General maintenance",
        "Broken window latch",
        _P.NORMAL,
        _S.SUBMITTED,
        who="requester3",
        created_day=-3,
    ),
    Bulk(
        "o05",
        0,
        None,
        "Plumbing",
        "Low water pressure on the 3rd floor",
        _P.HIGH,
        _S.TRIAGED,
        who="requester1",
        created_day=-2,
    ),
    Bulk(
        "o06",
        3,
        2,
        "General maintenance",
        "Boiler making a knocking noise",
        _P.NORMAL,
        _S.TRIAGED,
        who="requester3",
        created_day=-4,
    ),
    Bulk(
        "o07",
        5,
        None,
        "Electrical",
        "Replace parking-lot floodlights",
        _P.LOW,
        _S.TRIAGED,
        who="requester3",
        created_day=-5,
    ),
    Bulk(
        "o08",
        4,
        None,
        "Electrical",
        "Install new sockets in office 4",
        _P.NORMAL,
        _S.SCHEDULED,
        "technician1",
        4,
        11,
        90,
        "requester3",
        created_day=-1,
    ),
    Bulk(
        "o09",
        1,
        2,
        "General maintenance",
        "Boiler gasket replacement",
        _P.HIGH,
        _S.SCHEDULED,
        "technician4",
        2,
        10,
        120,
        "requester1",
        created_day=-1,
    ),
    Bulk(
        "o10",
        3,
        1,
        "HVAC",
        "Quarterly AC service",
        _P.NORMAL,
        _S.ACCEPTED,
        "technician3",
        5,
        10,
        120,
        "requester3",
        created_day=-1,
    ),
    Bulk(
        "o11",
        0,
        None,
        "Plumbing",
        "Replace the kitchen mixer tap",
        _P.NORMAL,
        _S.IN_PROGRESS,
        "technician2",
        0,
        9,
        120,
        "requester1",
        created_day=-1,
        intake=1,
    ),
    Bulk(
        "o12",
        5,
        None,
        "Electrical",
        "Duplicate: floodlight request",
        _P.LOW,
        _S.CANCELED,
        who="requester3",
        created_day=-5,
    ),
    Bulk(
        "o13",
        1,
        None,
        "General maintenance",
        "Resolved by the tenant",
        _P.LOW,
        _S.CANCELED,
        who="requester1",
        created_day=-6,
    ),
    Bulk(
        "o14",
        4,
        None,
        "Plumbing",
        "Washroom tap still dripping",
        _P.NORMAL,
        _S.REOPENED,
        "technician2",
        -3,
        15,
        60,
        "requester3",
        created_day=-4,
    ),
)


@dataclass(frozen=True)
class OrgSpec:
    key: str
    name: str
    domain: str
    properties: tuple[tuple[str, str], ...]
    # property index -> requester keys granted access
    grants: dict[int, tuple[str, ...]]


ORGS = (
    OrgSpec(
        "northwind",
        "Northwind Facilities",
        "northwind.demo",
        (
            ("Northwind HQ Tower", "12 Chuy Ave, Bishkek"),
            ("Riverside Mall", "88 Sovetskaya St, Bishkek"),
            ("Eastside Warehouse", "5 Industrial Rd, Bishkek"),
            ("Parkview Residences", "17 Gorky St, Bishkek"),
            ("Dordoi Logistics Hub", "2 Dordoi Rd, Bishkek"),
            ("Central Library Annex", "9 Erkindik Blvd, Bishkek"),
        ),
        # requester2 has no grants (empty state). Property 0 is shared by requester1 + shared user.
        {
            0: ("requester1", "shared"),
            1: ("requester1",),
            2: ("shared",),
            3: ("requester3",),
            4: ("requester3",),
            5: ("requester3",),
        },
    ),
    OrgSpec(
        "alatoo",
        "Ala-Too Repairs",
        "alatoo.demo",
        (
            ("Ala-Too Business Centre", "21 Manas Ave, Bishkek"),
            ("Orto-Sai Apartments", "3 Orto-Sai St, Bishkek"),
            ("Vostok Clinic", "40 Toktogul St, Bishkek"),
            ("Chui Plaza Offices", "100 Chui Ave, Bishkek"),
            ("Ak-Orgo Cold Storage", "7 Ak-Orgo Rd, Bishkek"),
            ("Jal Community Centre", "55 Jal St, Bishkek"),
        ),
        {
            0: ("requester1", "requester2"),
            1: ("requester1",),
            2: ("requester2",),
            3: ("requester3",),
            4: ("requester3",),
            5: ("requester3",),
        },
    ),
)

# (code, name, unit, final stock, reorder threshold, unit price in tyiyn)
INVENTORY = (
    ("PIPE-CU-15", "Copper pipe 15 mm", "m", "48", "20", 45000),
    ("VALVE-BALL-15", 'Ball valve 1/2"', "pcs", "14", "5", 38000),
    ("FILTER-HVAC-M", "Chiller air filter (M)", "pcs", "6", "4", 125000),
    ("BREAKER-16A", "Circuit breaker 16 A", "pcs", "22", "8", 21000),
    ("SOCKET-16A", "Wall socket 16 A", "pcs", "34", "10", 8500),
    ("CABLE-2.5", "Copper cable 2.5 mm2", "m", "293.5", "100", 6200),
    ("LED-BULB-12W", "LED bulb 12 W", "pcs", "3", "12", 4500),  # low stock
    ("HINGE-HD", "Heavy-duty door hinge", "pcs", "8", "4", 12000),
    ("SEALANT-SIL", "Silicone sealant tube", "tube", "2", "3", 9500),  # race demo item
    ("THERMOSTAT-DGT", "Digital thermostat", "pcs", "5", "2", 95000),
    ("PAINT-WHT-5L", "White interior paint 5 L", "can", "9", "3", 68000),
    ("BATTERY-9V", "9 V battery (smoke detector)", "pcs", "40", "15", 3500),
)
# (key, asset code suffix, category, title, priority, recurrence, first_date offset in days from
# the first seed run, enabled). Org -> plans. SEED-03: some already due, one disabled.
PLANS = {
    "northwind": (
        (
            "hvac-weekly",
            "P1-01",
            "HVAC",
            "Weekly rooftop AC filter check",
            Priority.NORMAL,
            Recurrence.WEEKLY,
            -14,
            True,
        ),
        (
            "boiler-monthly",
            "P2-02",
            "General maintenance",
            "Monthly boiler safety inspection",
            Priority.HIGH,
            Recurrence.MONTHLY,
            10,
            True,
        ),
    ),
    "alatoo": (
        (
            "hvac-monthly",
            "P1-01",
            "HVAC",
            "Monthly chiller service",
            Priority.NORMAL,
            Recurrence.MONTHLY,
            -5,
            True,
        ),
        (
            "boiler-weekly-off",
            "P2-02",
            "General maintenance",
            "Weekly boiler pressure log",
            Priority.LOW,
            Recurrence.WEEKLY,
            -30,
            False,
        ),
    ),
}

# request key -> technician key -> (item code, quantity): seeded material usage
USAGE = {
    "i": ("technician3", (("FILTER-HVAC-M", "2"),)),
    "k": ("technician1", (("SOCKET-16A", "1"), ("CABLE-2.5", "6.5"))),
    "l": ("technician2", (("VALVE-BALL-15", "1"), ("SEALANT-SIL", "1"))),
    # history jobs (seed_history)
    "h02": ("technician2", (("PIPE-CU-15", "2.5"), ("VALVE-BALL-15", "1"))),
    "h03": ("technician1", (("BREAKER-16A", "1"),)),
    "h07": ("technician3", (("FILTER-HVAC-M", "1"),)),
    "h09": ("technician1", (("LED-BULB-12W", "4"), ("CABLE-2.5", "12"))),
    "h11": ("technician1", (("SOCKET-16A", "3"), ("CABLE-2.5", "20"))),
    "h12": ("technician4", (("THERMOSTAT-DGT", "1"), ("HINGE-HD", "1"))),
}

SKILLS = ("electrical", "plumbing", "hvac", "general")
CATEGORIES = (
    ("Electrical", "Wiring, outlets, lighting", 60, ("electrical",)),
    ("Plumbing", "Leaks, drains, fixtures", 60, ("plumbing",)),
    ("HVAC", "Heating, ventilation, cooling", 90, ("hvac",)),
    ("General maintenance", "Doors, locks, minor repairs", 30, ("general",)),
)
TECH_SKILLS = {
    "technician1": ("electrical", "general"),
    "technician2": ("plumbing", "general"),
    "technician3": ("hvac", "general"),
    "technician4": ("electrical", "plumbing", "general"),
}
PEOPLE = (
    ("admin", "Admin", R.ADMIN),
    ("dispatcher", "Dispatcher", R.DISPATCHER),
    ("technician1", "Technician One", R.TECHNICIAN),
    ("technician2", "Technician Two", R.TECHNICIAN),
    ("technician3", "Technician Three", R.TECHNICIAN),
    ("technician4", "Technician Four", R.TECHNICIAN),
    ("requester1", "Requester One", R.REQUESTER),
    ("requester2", "Requester Two", R.REQUESTER),
    ("requester3", "Requester Three", R.REQUESTER),
)


class Seeder:
    def __init__(self, db: Session) -> None:
        self.db = db
        self._pw_hash: str | None = None
        self.credentials: list[tuple[str, str, str]] = []  # (email, org, role)

    def ensure(self, model: Any, pk: Any, **fields: Any) -> Any:
        obj = self.db.get(model, pk)
        if obj is None:
            obj = model(**fields)
            self.db.add(obj)
            self.db.flush()
        return obj

    def _anchor(self, org: Organization) -> date:
        """Single time anchor of the seed: the org-local date the organization row was created.

        Stored with the data, so a re-run on a later day derives identical timestamps."""
        return org.created_at.astimezone(ZoneInfo(org.timezone)).date()

    def password_hash(self) -> str:
        if self._pw_hash is None:
            self._pw_hash = hash_password(DEMO_PASSWORD)
        return self._pw_hash

    def user(self, email: str, full_name: str) -> User:
        return self.ensure(
            User,
            uid("user", email),
            id=uid("user", email),
            email=email,
            full_name=full_name,
            password_hash=self.password_hash(),
        )

    def membership(self, org: Organization, user: User, role: MembershipRole) -> Membership:
        m = self.ensure(
            Membership,
            uid("membership", org.slug, user.email),
            id=uid("membership", org.slug, user.email),
            organization_id=org.id,
            user_id=user.id,
            role=role,
        )
        self.credentials.append((user.email, org.name, role.value))
        if role == R.TECHNICIAN:
            self.ensure(
                TechnicianProfile,
                m.id,
                membership_id=m.id,
                organization_id=org.id,
            )
        return m

    def seed_org(self, spec: OrgSpec, shared_user: User) -> None:
        org = self.ensure(
            Organization,
            uid("org", spec.key),
            id=uid("org", spec.key),
            name=spec.name,
            slug=spec.key,
            timezone="Asia/Bishkek",
        )
        for weekday in range(5):
            self.ensure(
                BusinessHour,
                uid("bh", spec.key, str(weekday)),
                id=uid("bh", spec.key, str(weekday)),
                organization_id=org.id,
                weekday=weekday,
                open_time=time(9, 0),
                close_time=time(18, 0),
            )
        skills = {
            n: self.ensure(
                Skill,
                uid("skill", spec.key, n),
                id=uid("skill", spec.key, n),
                organization_id=org.id,
                name=n,
            )
            for n in SKILLS
        }
        for name, desc, minutes, req in CATEGORIES:
            cat = self.ensure(
                ServiceCategory,
                uid("cat", spec.key, name),
                id=uid("cat", spec.key, name),
                organization_id=org.id,
                name=name,
                description=desc,
                default_duration_minutes=minutes,
            )
            for s in req:
                self.ensure(
                    CategoryRequiredSkill,
                    (cat.id, skills[s].id),
                    organization_id=org.id,
                    category_id=cat.id,
                    skill_id=skills[s].id,
                )

        members: dict[str, Membership] = {}
        for key, label, role in PEOPLE:
            email = f"{key}@{spec.domain}"
            user = self.user(email, f"{label} ({spec.name})")
            members[key] = self.membership(org, user, role)
        # The shared account: REQUESTER in the first org, DISPATCHER in the second.
        shared_role = R.REQUESTER if spec.key == ORGS[0].key else R.DISPATCHER
        members["shared"] = self.membership(org, shared_user, shared_role)

        for key, skill_names in TECH_SKILLS.items():
            mid = members[key].id
            for s in skill_names:
                self.ensure(
                    TechnicianSkill,
                    (mid, skills[s].id),
                    organization_id=org.id,
                    membership_id=mid,
                    skill_id=skills[s].id,
                )
            for weekday in range(5):
                self.ensure(
                    TechnicianAvailability,
                    uid("avail", spec.key, key, str(weekday)),
                    id=uid("avail", spec.key, key, str(weekday)),
                    organization_id=org.id,
                    membership_id=mid,
                    weekday=weekday,
                    start_time=time(9, 0),
                    end_time=time(18, 0),
                )

        prefix = spec.key[:2].upper()
        for idx, (pname, address) in enumerate(spec.properties):
            prop = self.ensure(
                Property,
                uid("prop", spec.key, str(idx)),
                id=uid("prop", spec.key, str(idx)),
                organization_id=org.id,
                name=pname,
                address=address,
                contact_instructions="Check in at the front desk.",
            )
            for n, (atype, aname) in enumerate(
                (("HVAC unit", "Rooftop AC"), ("Boiler", "Main boiler"))
            ):
                code = f"{prefix}-P{idx + 1}-{n + 1:02d}"
                self.ensure(
                    Asset,
                    uid("asset", spec.key, code),
                    id=uid("asset", spec.key, code),
                    organization_id=org.id,
                    property_id=prop.id,
                    code=code,
                    name=f"{aname} ({pname})",
                    asset_type=atype,
                    serial_number=f"SN-{prefix}{idx + 1}{n + 1}",
                    installed_on=date(2022, 1, 1 + n),
                )
            for who in spec.grants.get(idx, ()):
                mid = members[who].id
                self.ensure(
                    PropertyAccess,
                    (prop.id, mid),
                    organization_id=org.id,
                    property_id=prop.id,
                    membership_id=mid,
                    granted_by_membership_id=members["admin"].id,
                )
        self.seed_requests(org, spec, members)
        self.seed_jobs(org, spec, members)
        self.seed_history(org, spec, members)
        self.seed_files_feedback(org, spec, members)
        self.seed_inventory(org, spec, members)
        self.seed_estimates(org, spec, members)
        self.seed_notifications(org, spec, members)
        self.seed_sla(org, spec, members)

    def seed_requests(
        self, org: Organization, spec: OrgSpec, members: dict[str, Membership]
    ) -> None:
        """~6 requests per org across SUBMITTED / TRIAGED / CANCELED / REOPENED (no files)."""
        S, P, N = RequestStatus, Priority, NoteKind
        req1, disp, tech = members["requester1"], members["dispatcher"], members["technician1"]
        prefix = spec.key[:2].upper()
        # (key, property idx, asset n or None, category, title, priority, final status)
        rows = (
            ("a", 0, 1, "HVAC", "Rooftop AC not cooling", P.HIGH, S.SUBMITTED),
            ("b", 1, None, "Plumbing", "Leaking tap in the staff kitchen", P.NORMAL, S.SUBMITTED),
            ("c", 0, None, "Electrical", "Flickering lights in the lobby", P.NORMAL, S.TRIAGED),
            ("d", 1, 2, "General maintenance", "Boiler room door will not lock", P.LOW, S.TRIAGED),
            (
                "e",
                0,
                None,
                "General maintenance",
                "Duplicate: lobby light report",
                P.LOW,
                S.CANCELED,
            ),
            ("f", 0, 1, "HVAC", "Thermostat reading is wrong", P.NORMAL, S.REOPENED),
        )
        desc = (
            "Reported by the tenant; the problem has persisted for several days and needs a visit."
        )
        for key, pidx, asset_n, cat, title, prio, final in rows:
            rid = uid("request", spec.key, key)
            if self.db.get(ServiceRequest, rid) is not None:
                continue
            number = self.db.execute(
                text(
                    "UPDATE organizations SET request_seq = request_seq + 1 "
                    "WHERE id = :o RETURNING request_seq"
                ),
                {"o": org.id},
            ).scalar_one()
            asset_id = (
                uid("asset", spec.key, f"{prefix}-P{pidx + 1}-{asset_n:02d}") if asset_n else None
            )
            req = self.ensure(
                ServiceRequest,
                rid,
                id=rid,
                organization_id=org.id,
                number=number,
                requester_membership_id=req1.id,
                created_by_membership_id=req1.id,
                property_id=uid("prop", spec.key, str(pidx)),
                asset_id=asset_id,
                category_id=uid("cat", spec.key, cat),
                title=title,
                description=desc,
                priority=prio,
                status=S.SUBMITTED,
            )
            self._event(org, req, req1, "REQUEST_CREATED", None, S.SUBMITTED, {"number": number})
            chain: list[tuple[RequestStatus, Membership]] = []
            if final in (S.TRIAGED, S.REOPENED):
                chain.append((S.TRIAGED, disp))
            if final == S.REOPENED:
                chain += [
                    (S.SCHEDULED, disp),
                    (S.ACCEPTED, tech),
                    (S.IN_PROGRESS, tech),
                    (S.COMPLETED, tech),
                    (S.REOPENED, req1),
                ]
            if final == S.CANCELED:
                chain.append((S.CANCELED, req1))
            current = S.SUBMITTED
            for to, actor in chain:
                note = None
                if to == S.TRIAGED:
                    note = self._note(
                        org,
                        req,
                        disp,
                        NoteVisibility.INTERNAL,
                        N.TRIAGE,
                        "Needs a technician visit.",
                    )
                elif to == S.CANCELED:
                    note = self._note(
                        org,
                        req,
                        req1,
                        NoteVisibility.PUBLIC,
                        N.CANCEL,
                        "Reported twice, cancel this one.",
                    )
                elif to == S.REOPENED:
                    note = self._note(
                        org,
                        req,
                        req1,
                        NoteVisibility.PUBLIC,
                        N.REWORK,
                        "The reading is still wrong.",
                    )
                self._event(
                    org,
                    req,
                    actor,
                    "STATUS_CHANGED",
                    current,
                    to,
                    {"note_id": note.id} if note else None,
                )
                current = to
            req.status = final
            if final == S.CANCELED:
                req.canceled_at = req.created_at
            if final == S.REOPENED:
                req.completed_at = req.created_at
            if final == S.SUBMITTED and key == "a":
                self._note(
                    org,
                    req,
                    req1,
                    NoteVisibility.PUBLIC,
                    N.GENERAL,
                    "The unit is on the roof, access via the east stairs.",
                )
                self._note(
                    org,
                    req,
                    disp,
                    NoteVisibility.INTERNAL,
                    N.GENERAL,
                    "Check warranty before dispatching a contractor.",
                )
            self.db.flush()

    # ---- scheduled / in-flight / finished jobs with assignments (Phase 2b) ----------------
    def seed_jobs(self, org: Organization, spec: OrgSpec, members: dict[str, Membership]) -> None:
        """Requests in SCHEDULED, ACCEPTED, IN_PROGRESS, BLOCKED, COMPLETED and CLOSED with
        matching assignments + request_events, plus the SEED-02 collision candidate.

        Slots are anchored to the local date of the FIRST seed run (rows are skipped on re-runs,
        so they never move): future business days for SCHEDULED/ACCEPTED, previous business
        days for COMPLETED/CLOSED. Rows are inserted directly (like the rest of the seed), so
        seeded completions deliberately bypass the completion-image guard (no files seeded).
        All inserts respect the assignments exclusion constraint (no overlaps per technician).
        """
        S, P, N, A = RequestStatus, Priority, NoteKind, AssignmentStatus
        tz = ZoneInfo(org.timezone)
        today = self._anchor(org)

        def bday(offset: int) -> date:
            return _bday(today, offset)

        def slot(d: date, hour: int, minutes: int, minute: int = 0) -> tuple[datetime, datetime]:
            start = datetime.combine(d, time(hour, minute), tzinfo=tz).astimezone(UTC)
            return start, start + timedelta(minutes=minutes)

        disp, req1 = members["dispatcher"], members["requester1"]
        labels = {k: f"{label} ({spec.name})" for k, label, _ in PEOPLE}
        # (key, property idx, category, title, priority, final status, tech, slot, extra)
        jobs = (
            (
                "g",
                0,
                "Electrical",
                "Replace burnt-out corridor lights",
                P.NORMAL,
                S.SCHEDULED,
                "technician1",
                slot(bday(1), 10, 60),
                {},
            ),
            (
                "h",
                1,
                "Plumbing",
                "Fix dripping tap in the kitchen",
                P.NORMAL,
                S.ACCEPTED,
                "technician2",
                slot(bday(2), 14, 90),
                {},
            ),
            (
                "i",
                0,
                "HVAC",
                "Service the lobby air handler",
                P.HIGH,
                S.IN_PROGRESS,
                "technician3",
                slot(bday(0), 9, 120),
                {},
            ),
            (
                "j",
                1,
                "General maintenance",
                "Repair the stuck service door",
                P.LOW,
                S.BLOCKED,
                "technician1",
                slot(bday(0), 14, 60),
                {"blocker": "Waiting for a replacement hinge."},
            ),
            (
                "k",
                0,
                "Electrical",
                "Install socket in the meeting room",
                P.NORMAL,
                S.COMPLETED,
                "technician1",
                slot(bday(-1), 10, 120),
                {"completion": "Installed and tested the new socket; breaker labelled."},
            ),
            (
                "l",
                1,
                "Plumbing",
                "Unblock the washroom drain",
                P.NORMAL,
                S.CLOSED,
                "technician2",
                slot(bday(-1), 10, 60),
                {"completion": "Cleared the drain and flushed the line; no further leaks."},
            ),
            # Active booking that the collision candidate (m) overlaps.
            (
                "n",
                0,
                "HVAC",
                "Replace chiller filters",
                P.NORMAL,
                S.SCHEDULED,
                "technician3",
                slot(bday(3), 13, 120),
                {},
            ),
        )
        for key, pidx, cat, title, prio, final, tech_key, window, extra in jobs:
            rid = uid("request", spec.key, key)
            if self.db.get(ServiceRequest, rid) is not None:
                continue
            req = self._new_request(org, spec, req1, rid, pidx, cat, title, prio)
            tech = members[tech_key]
            start, end = window
            reached = {
                S.SCHEDULED: [S.SCHEDULED],
                S.ACCEPTED: [S.SCHEDULED, S.ACCEPTED],
                S.IN_PROGRESS: [S.SCHEDULED, S.ACCEPTED, S.IN_PROGRESS],
                S.BLOCKED: [S.SCHEDULED, S.ACCEPTED, S.IN_PROGRESS, S.BLOCKED],
                S.COMPLETED: [S.SCHEDULED, S.ACCEPTED, S.IN_PROGRESS, S.COMPLETED],
                S.CLOSED: [S.SCHEDULED, S.ACCEPTED, S.IN_PROGRESS, S.COMPLETED, S.CLOSED],
            }[final]
            current = S.SUBMITTED
            aid = uid("assignment", spec.key, key)
            done = final in (S.COMPLETED, S.CLOSED)
            for to in [S.TRIAGED, *reached]:
                actor = {
                    S.TRIAGED: disp,
                    S.SCHEDULED: disp,
                    S.CLOSED: req1,
                }.get(to, tech)
                note = None
                if to == S.TRIAGED:
                    note = self._note(
                        org,
                        req,
                        disp,
                        NoteVisibility.INTERNAL,
                        N.TRIAGE,
                        "Needs a technician visit.",
                    )
                elif to == S.BLOCKED:
                    note = self._note(
                        org, req, tech, NoteVisibility.PUBLIC, N.BLOCKER, extra["blocker"]
                    )
                elif to == S.COMPLETED:
                    note = self._note(
                        org, req, tech, NoteVisibility.PUBLIC, N.COMPLETION, extra["completion"]
                    )
                elif to == S.CLOSED:
                    note = self._note(
                        org, req, req1, NoteVisibility.PUBLIC, N.CLOSE, "Confirmed, thank you."
                    )
                data: dict[str, Any] = {"note_id": note.id} if note else {}
                if to == S.SCHEDULED:
                    self.db.add(
                        Assignment(
                            id=aid,
                            organization_id=org.id,
                            request_id=req.id,
                            technician_membership_id=tech.id,
                            start_at=start,
                            end_at=end,
                            status=A.COMPLETED if done else A.ACTIVE,
                            active=not done,
                            assigned_by_membership_id=disp.id,
                        )
                    )
                    self.db.flush()
                    self._event(
                        org,
                        req,
                        disp,
                        "ASSIGNED",
                        None,
                        None,
                        {
                            "assignment_id": str(aid),
                            "technician": {"membership_id": str(tech.id), "name": labels[tech_key]},
                            "start_at": start.isoformat(),
                            "end_at": end.isoformat(),
                            "reason": None,
                        },
                    )
                    data["assignment_id"] = aid
                self._event(org, req, actor, "STATUS_CHANGED", current, to, data or None)
                current = to
            req.status = final
            if done:
                req.completed_at = end
            if final == S.CLOSED:
                req.closed_at = end
            self.db.flush()

        # Technician-completed history for the seeded reopened request "f" (HVAC -> tech3).
        f_id, f_aid = uid("request", spec.key, "f"), uid("assignment", spec.key, "f")
        if self.db.get(ServiceRequest, f_id) is not None and self.db.get(Assignment, f_aid) is None:
            start, end = slot(bday(-2), 14, 60)
            self.db.add(
                Assignment(
                    id=f_aid,
                    organization_id=org.id,
                    request_id=f_id,
                    technician_membership_id=members["technician3"].id,
                    start_at=start,
                    end_at=end,
                    status=A.COMPLETED,
                    active=False,
                    assigned_by_membership_id=disp.id,
                )
            )
            self.db.flush()

        # SEED-02 collision candidate: a TRIAGED HVAC request (only technician3 has the hvac
        # skill) whose preferred window overlaps technician3's active booking "n" (13:00-15:00
        # on the 3rd business day): assigning technician3 in that window is rejected.
        m_id = uid("request", spec.key, "m")
        if self.db.get(ServiceRequest, m_id) is None:
            pref_start, pref_end = slot(bday(3), 14, 90)
            req = self._new_request(
                org, spec, req1, m_id, 0, "HVAC", "Chiller noise in the server room", P.HIGH
            )
            req.preferred_window_start, req.preferred_window_end = pref_start, pref_end
            note = self._note(
                org, req, disp, NoteVisibility.INTERNAL, N.TRIAGE, "Collision demo: needs hvac."
            )
            self._event(
                org,
                req,
                disp,
                "STATUS_CHANGED",
                RequestStatus.SUBMITTED,
                RequestStatus.TRIAGED,
                {"note_id": note.id},
            )
            req.status = RequestStatus.TRIAGED
            self.db.flush()

    # ---- extra history / pipeline requests, files, feedback (Phase 3d) ---------------------
    def seed_history(
        self, org: Organization, spec: OrgSpec, members: dict[str, Membership]
    ) -> None:
        """BULK requests: finished jobs over the last ~14 days (assignments in business hours,
        completion images, feedback), plus open / future / canceled / reopened ones.

        Everything is timestamped from the org anchor date (see ``_anchor``) and inserted row by
        row like the rest of the seed, skipped when the deterministic id already exists."""
        S, N = RequestStatus, NoteKind
        tz = ZoneInfo(org.timezone)
        today = self._anchor(org)
        disp = members["dispatcher"]
        prefix = spec.key[:2].upper()
        ladder = [S.TRIAGED, S.SCHEDULED, S.ACCEPTED, S.IN_PROGRESS, S.COMPLETED]
        for idx, b in enumerate(BULK):
            rid = uid("request", spec.key, b.key)
            if self.db.get(ServiceRequest, rid) is not None:
                continue
            requester = members[b.who]
            tech = members[b.tech] if b.tech else None
            created_off = b.created_day if b.created_day is not None else b.day - 1
            t0 = _local(tz, _bday(today, created_off), 9 + idx % 6, (idx * 7) % 60)
            w0 = w1 = t0  # no slot for unassigned requests
            if tech is not None:
                w0 = _local(tz, _bday(today, b.day), b.hour)
                w1 = w0 + timedelta(minutes=b.minutes)
            asset_id = (
                uid("asset", spec.key, f"{prefix}-P{b.pidx + 1}-{b.asset_n:02d}")
                if b.asset_n
                else None
            )
            req = self._new_request(
                org, spec, requester, rid, b.pidx, b.category, b.title, b.priority,
                at=t0, asset_id=asset_id,
            )  # fmt: skip
            times = {
                S.TRIAGED: t0 + timedelta(minutes=25),
                S.SCHEDULED: t0 + timedelta(minutes=50),
                S.ACCEPTED: t0 + timedelta(minutes=120),
                S.IN_PROGRESS: w0,
                S.COMPLETED: w1,
            }
            steps: list[tuple[RequestStatus, Membership, datetime]] = []
            if b.final == S.CANCELED:
                steps.append((S.CANCELED, requester, t0 + timedelta(hours=3)))
            else:
                last = S.COMPLETED if b.final in (S.CLOSED, S.REOPENED) else b.final
                if b.final != S.SUBMITTED:
                    for st in ladder[: ladder.index(last) + 1]:
                        actor = disp if st in (S.TRIAGED, S.SCHEDULED) or tech is None else tech
                        steps.append((st, actor, times[st]))
                if b.final == S.CLOSED:
                    steps.append((S.CLOSED, requester, w1 + timedelta(minutes=90)))
                if b.final == S.REOPENED:
                    steps.append((S.REOPENED, requester, w1 + timedelta(hours=20)))
            current = S.SUBMITTED
            aid = uid("assignment", spec.key, b.key)
            done = b.final in (S.COMPLETED, S.CLOSED, S.REOPENED)
            for to, actor, at in steps:
                note = None
                if to == S.TRIAGED:
                    note = self._note(
                        org, req, disp, NoteVisibility.INTERNAL, N.TRIAGE,
                        "Needs a technician visit.", at,
                    )  # fmt: skip
                elif to == S.COMPLETED:
                    note = self._note(
                        org, req, actor, NoteVisibility.PUBLIC, N.COMPLETION,
                        "Work finished, tested and the area cleaned up.", at,
                    )  # fmt: skip
                elif to == S.CLOSED:
                    note = self._note(
                        org, req, actor, NoteVisibility.PUBLIC, N.CLOSE, "Confirmed, thank you.", at
                    )
                elif to == S.REOPENED:
                    note = self._note(
                        org, req, actor, NoteVisibility.PUBLIC, N.REWORK,
                        "The problem is back, please check again.", at,
                    )  # fmt: skip
                elif to == S.CANCELED:
                    note = self._note(
                        org, req, actor, NoteVisibility.PUBLIC, N.CANCEL,
                        "No longer needed, cancel this one.", at,
                    )  # fmt: skip
                data: dict[str, Any] = {"note_id": note.id} if note else {}
                if to == S.SCHEDULED:
                    if tech is None:
                        raise RuntimeError("scheduled seed row needs a technician and a slot")
                    self.db.add(
                        Assignment(
                            id=aid,
                            organization_id=org.id,
                            request_id=req.id,
                            technician_membership_id=tech.id,
                            start_at=w0,
                            end_at=w1,
                            status=AssignmentStatus.COMPLETED if done else AssignmentStatus.ACTIVE,
                            active=not done,
                            assigned_by_membership_id=disp.id,
                            created_at=at,
                        )
                    )
                    self.db.flush()
                    self._event(
                        org, req, disp, "ASSIGNED", None, None,
                        {
                            "assignment_id": str(aid),
                            "technician": {
                                "membership_id": str(tech.id),
                                "name": f"Technician ({spec.name})",
                            },
                            "start_at": w0.isoformat(),
                            "end_at": w1.isoformat(),
                            "reason": None,
                        },
                        at=at,
                    )  # fmt: skip
                    data["assignment_id"] = aid
                self._event(org, req, actor, "STATUS_CHANGED", current, to, data or None, at=at)
                current = to
                req.completed_at = at if to == S.COMPLETED else req.completed_at
                if to == S.CLOSED:
                    req.closed_at = at
                if to == S.CANCELED:
                    req.canceled_at = at
                req.status_changed_at = at
                req.updated_at = at
            req.status = b.final
            self.db.flush()
            for n in range(b.intake):
                self._evidence(
                    org, req, requester, FilePurpose.INTAKE, n, t0 + timedelta(minutes=2 + n)
                )
            if done and b.completion_image and tech is not None:
                self._evidence(
                    org, req, tech, FilePurpose.COMPLETION, 0, w1 - timedelta(minutes=10)
                )
            if b.rating is not None and req.completed_at is not None:
                end = req.closed_at or req.completed_at
                self._feedback(org, req, requester, b.rating, b.comment, end + timedelta(hours=2))

    def _evidence(
        self,
        org: Organization,
        req: ServiceRequest,
        uploader: Membership,
        purpose: FilePurpose,
        n: int,
        at: datetime,
    ) -> EvidenceFile:
        """Create (or heal) one evidence file: real PNG/JPEG bytes at the same storage key
        layout the upload endpoint uses (``<org>/<YYYY>/<MM>/<file id>.<ext>``)."""
        fid = uid("file", org.slug, str(req.id), purpose.value, str(n))
        label = f"{org.slug}:{req.number}:{purpose.value}:{n}"
        row = self.db.get(EvidenceFile, fid)
        if row is None:
            fmt, ext, mime = ("JPEG", "jpg", "image/jpeg") if n % 2 else ("PNG", "png", "image/png")
            data = make_image(label, fmt)
            key = f"{org.id}/{at:%Y}/{at:%m}/{fid}.{ext}"
            row = EvidenceFile(
                id=fid,
                organization_id=org.id,
                request_id=req.id,
                uploaded_by_membership_id=uploader.id,
                purpose=purpose,
                original_filename=f"{purpose.value.lower()}-{req.number}-{n + 1}.{ext}",
                storage_key=key,
                mime_type=mime,
                size_bytes=len(data),
                width=320,
                height=240,
                sha256=hashlib.sha256(data).hexdigest(),
                created_at=at,
            )
            self.db.add(row)
            self.db.flush()
            self._event(
                org, req, uploader, "FILE_UPLOADED", None, None,
                {"file_id": str(fid), "purpose": purpose.value, "mime_type": mime},
                at=at,
            )  # fmt: skip
        path = upload_root() / row.storage_key
        if not path.exists():  # also heals a wiped upload directory on re-run
            fmt = "JPEG" if row.mime_type == "image/jpeg" else "PNG"
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".part")
            tmp.write_bytes(make_image(label, fmt))
            os.replace(tmp, path)
        return row

    def _feedback(
        self,
        org: Organization,
        req: ServiceRequest,
        requester: Membership,
        rating: int,
        comment: str | None,
        at: datetime,
    ) -> None:
        fid = uid("feedback", org.slug, str(req.id))
        if self.db.get(Feedback, fid) is not None:
            return
        self.db.add(
            Feedback(
                id=fid,
                organization_id=org.id,
                request_id=req.id,
                requester_membership_id=requester.id,
                rating=rating,
                comment=comment,
                created_at=at,
            )
        )
        self.db.flush()
        self._event(
            org, req, requester, "FEEDBACK_SUBMITTED", None, None, {"rating": rating}, at=at
        )

    def seed_files_feedback(
        self, org: Organization, spec: OrgSpec, members: dict[str, Membership]
    ) -> None:
        """Images and feedback for the Phase 2 requests: intake on "a", completion on "k"/"l"."""
        rq = members["requester1"]

        def get(key: str) -> ServiceRequest | None:
            return self.db.get(ServiceRequest, uid("request", spec.key, key))

        a = get("a")
        if a is not None:
            self._evidence(org, a, rq, FilePurpose.INTAKE, 0, a.created_at + timedelta(minutes=2))
        for key, tech_key, rating, comment in (
            ("k", "technician1", 5, "Socket works, thanks."),
            ("l", "technician2", 4, None),
        ):
            req = get(key)
            if req is None or req.completed_at is None:
                continue
            self._evidence(
                org, req, members[tech_key], FilePurpose.COMPLETION, 0,
                req.completed_at - timedelta(minutes=10),
            )  # fmt: skip
            at = (req.closed_at or req.completed_at) + timedelta(hours=1)
            self._feedback(org, req, rq, rating, comment, at)

    # ---- inventory + material usage (Phase 3a) ------------------------------------------
    def seed_inventory(
        self, org: Organization, spec: OrgSpec, members: dict[str, Membership]
    ) -> None:
        """10 items per org. The ledger starts with an ADDITION of (final stock + seeded usage)
        and one CONSUMPTION per usage row, so stock and movements always agree."""
        from app.services.inventory import _usage_hash

        admin = members["admin"]
        used: dict[str, Decimal] = {}
        for _, (_, lines) in USAGE.items():
            for code, qty in lines:
                used[code] = used.get(code, Decimal(0)) + Decimal(qty)
        items: dict[str, InventoryItem] = {}
        for code, name, unit, final, threshold, price in INVENTORY:
            iid = uid("item", spec.key, code)
            item = self.db.get(InventoryItem, iid)
            if item is None:
                initial = Decimal(final) + used.get(code, Decimal(0))
                item = InventoryItem(
                    id=iid,
                    organization_id=org.id,
                    code=code,
                    name=name,
                    unit=unit,
                    stock_quantity=Decimal(final),
                    reorder_threshold=Decimal(threshold),
                    unit_price_minor=price,
                )
                self.db.add(item)
                self.db.flush()
                self._movement(
                    org,
                    item,
                    StockMovementKind.ADDITION,
                    initial,
                    "Initial stock (seed)",
                    admin,
                    initial,
                    uid("mv", spec.key, code, "initial"),
                    None,
                    _local(ZoneInfo(org.timezone), self._anchor(org) - timedelta(days=21), 8),
                )
            items[code] = item
        for rkey, (tech_key, lines) in USAGE.items():
            req_id = uid("request", spec.key, rkey)
            if self.db.get(ServiceRequest, req_id) is None:
                continue
            tech = members[tech_key]
            req_row = self.db.get(ServiceRequest, req_id)
            done_at = req_row.completed_at if req_row else None
            used_at = done_at - timedelta(minutes=20) if done_at else None
            stamp = {"created_at": used_at} if used_at else {}
            for code, qty_s in lines:
                cmd = uid("usage", spec.key, rkey, code)
                if self.db.scalar(text("SELECT 1 FROM material_usage WHERE id = :i"), {"i": cmd}):
                    continue
                item, qty = items[code], Decimal(qty_s)
                total = money.line_total_minor(qty, item.unit_price_minor)
                self.db.add(
                    MaterialUsage(
                        id=cmd,
                        organization_id=org.id,
                        request_id=req_id,
                        item_id=item.id,
                        technician_membership_id=tech.id,
                        quantity=qty,
                        unit_cost_minor_snapshot=item.unit_price_minor,
                        total_cost_minor=total,
                        client_command_id=cmd,
                        payload_hash=_usage_hash(req_id, item.id, qty),
                        **stamp,
                    )
                )
                self.db.flush()
                # initial stock included this usage, so the ledger running balance is exact
                running = self._balance(item.id) - qty
                self._movement(
                    org,
                    item,
                    StockMovementKind.CONSUMPTION,
                    -qty,
                    "Used on a seeded job",
                    tech,
                    running,
                    uid("mv", spec.key, rkey, code),
                    cmd,
                    used_at,
                )

    def _balance(self, item_id: uuid.UUID) -> Decimal:
        return self.db.execute(
            text("SELECT COALESCE(sum(delta), 0) FROM stock_movements WHERE item_id = :i"),
            {"i": item_id},
        ).scalar_one()

    def _movement(
        self, org, item, kind, delta, reason, actor, after, mid, usage_id=None, at=None
    ) -> None:
        self.db.add(
            StockMovement(
                id=mid,
                organization_id=org.id,
                item_id=item.id,
                kind=kind,
                delta=delta,
                reason=reason,
                actor_membership_id=actor.id,
                material_usage_id=usage_id,
                stock_after=after,
                **({"created_at": at} if at else {}),
            )
        )
        self.db.flush()

    # ---- estimates (Phase 3a) -------------------------------------------------------------
    def _estimate(
        self,
        org: Organization,
        spec: OrgSpec,
        members: dict[str, Membership],
        req_key: str,
        version: int,
        final: EstimateStatus,
        labor_minutes: int,
        rate: int,
        lines: tuple[tuple[str, str, int], ...],
        supersedes: Estimate | None = None,
        notes: str | None = None,
        reason: str | None = None,
        at: datetime | None = None,
    ) -> Estimate | None:
        """Insert one estimate version (DRAFT first so its lines can be written, then moved to
        ``final`` via status-only updates) with totals computed by the money helpers."""
        eid = uid("estimate", spec.key, req_key, str(version))
        if self.db.get(Estimate, eid) is not None:
            return None
        req = self.db.get(ServiceRequest, uid("request", spec.key, req_key))
        if req is None:
            return None
        disp, req1 = members["dispatcher"], members["requester1"]
        labor = money.labor_cost_minor(labor_minutes, rate)
        line_rows = [(d, Decimal(q), p, money.line_total_minor(Decimal(q), p)) for d, q, p in lines]
        materials = sum(r[3] for r in line_rows)
        now = at or datetime.now(UTC)
        decided_at = now + timedelta(hours=1) if at else now
        est = Estimate(
            id=eid,
            organization_id=org.id,
            request_id=req.id,
            version=version,
            status=EstimateStatus.DRAFT,
            supersedes_id=supersedes.id if supersedes else None,
            labor_minutes=labor_minutes,
            labor_rate_minor=rate,
            labor_cost_minor=labor,
            materials_total_minor=materials,
            total_minor=labor + materials,
            currency=money.CURRENCY,
            notes=notes,
            created_by_membership_id=disp.id,
        )
        self.db.add(est)
        self.db.flush()
        for pos, (d, q, p, t) in enumerate(line_rows, start=1):
            self.db.add(
                EstimateLine(
                    organization_id=org.id,
                    estimate_id=eid,
                    position=pos,
                    description=d,
                    quantity=q,
                    unit_price_minor=p,
                    line_total_minor=t,
                )
            )
        self.db.flush()
        if final != EstimateStatus.DRAFT:
            est.submitted_at, est.submitted_by_membership_id = now, disp.id
            data = {
                "estimate_id": str(eid),
                "version": version,
                "total_minor": est.total_minor,
                "superseded": [],
            }
            est.status = EstimateStatus.AWAITING_APPROVAL
            self.db.flush()
            self._event(org, req, disp, "ESTIMATE_SUBMITTED", None, None, data, at=now)
            if final in (
                EstimateStatus.APPROVED,
                EstimateStatus.REJECTED,
                EstimateStatus.SUPERSEDED,
            ):
                # SUPERSEDED here means "rejected, then replaced by the next version"
                decided = (
                    EstimateStatus.APPROVED
                    if final == EstimateStatus.APPROVED
                    else EstimateStatus.REJECTED
                )
                est.status = decided
                est.decided_at, est.decided_by_membership_id = decided_at, req1.id
                est.decision_reason = reason
                self.db.flush()
                self._event(
                    org,
                    req,
                    req1,
                    f"ESTIMATE_{decided.value}",
                    None,
                    None,
                    {"estimate_id": str(eid), "version": version, "reason": reason},
                    at=decided_at,
                )
            if final == EstimateStatus.SUPERSEDED:
                est.status = EstimateStatus.SUPERSEDED
            self.db.flush()
        return est

    def seed_estimates(
        self, org: Organization, spec: OrgSpec, members: dict[str, Membership]
    ) -> None:
        ES = EstimateStatus
        # c (TRIAGED): a DRAFT being prepared
        self._estimate(
            org,
            spec,
            members,
            "c",
            1,
            ES.DRAFT,
            60,
            50000,
            (("Ballast", "2", 7800), ("Wire", "3.5", 6200)),
            notes="Draft, not yet sent.",
        )
        # h (ACCEPTED): AWAITING_APPROVAL, so the technician's "start" is blocked (EST-04 demo)
        self._estimate(
            org,
            spec,
            members,
            "h",
            1,
            ES.AWAITING_APPROVAL,
            90,
            50000,
            (("Tap cartridge", "1", 24500), ("Sealing tape", "2", 1950)),
            notes="Includes replacing the cartridge.",
        )
        # i (IN_PROGRESS): APPROVED
        self._estimate(
            org,
            spec,
            members,
            "i",
            1,
            ES.APPROVED,
            120,
            55000,
            (("Chiller air filter (M)", "2", 125000),),
        )
        # j (BLOCKED): v1 rejected and replaced by an approved v2
        v1 = self._estimate(
            org,
            spec,
            members,
            "j",
            1,
            ES.SUPERSEDED,
            120,
            60000,
            (("Hinge set", "2", 12000), ("Door closer", "1", 48000)),
            reason="Too expensive; please reduce the scope.",
        )
        self._estimate(
            org,
            spec,
            members,
            "j",
            2,
            ES.APPROVED,
            60,
            60000,
            (("Hinge set", "2", 12000),),
            supersedes=v1,
            notes="Scope reduced after v1.",
        )
        # History: approved estimates dated within the last 30 days (REPORT revenue figures)
        approved = (
            ("h02", 120, 50000, (("Copper pipe 15 mm", "2.5", 45000), ("Ball valve", "1", 38000))),
            ("h07", 120, 55000, (("Chiller air filter (M)", "1", 125000),)),
            ("h12", 120, 60000, (("Digital thermostat", "1", 95000), ("Hinge", "1", 12000))),
        )
        for rkey, minutes, rate, lines in approved:
            req = self.db.get(ServiceRequest, uid("request", spec.key, rkey))
            if req is not None:
                self._estimate(
                    org,
                    spec,
                    members,
                    rkey,
                    1,
                    ES.APPROVED,
                    minutes,
                    rate,
                    lines,
                    at=req.created_at + timedelta(hours=3),
                )
        o06 = self.db.get(ServiceRequest, uid("request", spec.key, "o06"))
        if o06 is not None:
            self._estimate(
                org,
                spec,
                members,
                "o06",
                1,
                ES.REJECTED,
                180,
                60000,
                (("Boiler pump", "1", 210000),),
                reason="Too expensive; get a second quote.",
                at=o06.created_at + timedelta(hours=5),
            )
        self.db.flush()

    # ---- notifications (Phase 3a) ---------------------------------------------------------
    def seed_notifications(
        self, org: Organization, spec: OrgSpec, members: dict[str, Membership]
    ) -> None:
        def req_of(key: str) -> ServiceRequest | None:
            return self.db.get(ServiceRequest, uid("request", spec.key, key))

        now = datetime.now(UTC)
        # (key, recipient, type, title, body, request key, read?)
        rows = (
            (
                "assigned-h",
                "technician2",
                "ASSIGNMENT_CREATED",
                "New job assigned",
                "Fix dripping tap in the kitchen was assigned to you.",
                "h",
                False,
            ),
            (
                "assigned-g",
                "technician1",
                "ASSIGNMENT_CREATED",
                "New job assigned",
                "Replace burnt-out corridor lights was assigned to you.",
                "g",
                True,
            ),
            (
                "est-h",
                "requester1",
                "ESTIMATE_SUBMITTED",
                "Estimate awaiting your approval",
                "Estimate v1 for 'Fix dripping tap in the kitchen' needs your decision.",
                "h",
                False,
            ),
            (
                "done-k-req",
                "requester1",
                "JOB_COMPLETED",
                "Job completed",
                "Work on 'Install socket in the meeting room' was completed.",
                "k",
                True,
            ),
            (
                "done-k-disp",
                "dispatcher",
                "JOB_COMPLETED",
                "Job completed",
                "Work on 'Install socket in the meeting room' was completed.",
                "k",
                False,
            ),
            (
                "done-k-admin",
                "admin",
                "JOB_COMPLETED",
                "Job completed",
                "Work on 'Install socket in the meeting room' was completed.",
                "k",
                True,
            ),
            (
                "est-j",
                "dispatcher",
                "ESTIMATE_DECIDED",
                "Estimate approved",
                "Estimate v2 for 'Repair the stuck service door' was approved.",
                "j",
                False,
            ),
            (
                "rework-f",
                "dispatcher",
                "REWORK_REQUESTED",
                "Rework requested",
                "The requester reopened 'Thermostat reading is wrong' for rework.",
                "f",
                False,
            ),
        )
        for key, who, type_, title, body, rkey, read in rows:
            nid = uid("notification", spec.key, key)
            req = req_of(rkey)
            if req is None or self.db.get(Notification, nid) is not None:
                continue
            self.db.add(
                Notification(
                    id=nid,
                    organization_id=org.id,
                    recipient_membership_id=members[who].id,
                    type=type_,
                    title=title,
                    body=body,
                    request_id=req.id,
                    data={"seed": True},
                    read_at=now if read else None,
                    dedupe_key=f"seed:{key}",
                )
            )
        self.db.flush()

    def seed_sla(self, org: Organization, spec: OrgSpec, members: dict[str, Membership]) -> None:
        """SLA-01 holiday, SEED-02 overdue job (not yet escalated) and SEED-03 plans.

        Dates are anchored to the local date of the FIRST seed run (rows are skipped on re-runs)."""
        tz = ZoneInfo(org.timezone)
        today = self._anchor(org)
        holiday_id = uid("holiday", spec.key)
        if self.db.get(Holiday, holiday_id) is None:
            self.db.add(
                Holiday(
                    id=holiday_id,
                    organization_id=org.id,
                    date=today + timedelta(days=45),
                    name="Demo public holiday",
                )
            )
            self.db.flush()

        rid = uid("request", spec.key, "overdue")
        if self.db.get(ServiceRequest, rid) is None:
            # HIGH = 8 business hours; created 3 business days ago at 09:00 local -> long overdue.
            d, back = today, 3
            while back:
                d -= timedelta(days=1)
                if d.weekday() < 5:
                    back -= 1
            created = datetime.combine(d, time(9, 0), tzinfo=tz).astimezone(UTC)
            req = self._new_request(
                org,
                spec,
                members["requester1"],
                rid,
                0,
                "HVAC",
                "Server room cooling failed (overdue demo)",
                Priority.HIGH,
                at=created,
            )
            req.asset_id = uid("asset", spec.key, f"{spec.key[:2].upper()}-P1-01")
            self.db.flush()

        for key, asset_suffix, cat, title, prio, rec, offset, enabled in PLANS[spec.key]:
            pid = uid("plan", spec.key, key)
            if self.db.get(MaintenancePlan, pid) is not None:
                continue
            self.db.add(
                MaintenancePlan(
                    id=pid,
                    organization_id=org.id,
                    asset_id=uid("asset", spec.key, f"{spec.key[:2].upper()}-{asset_suffix}"),
                    category_id=uid("cat", spec.key, cat),
                    title=title,
                    description="Routine preventive maintenance as per the manufacturer schedule.",
                    priority=prio,
                    first_date=today + timedelta(days=offset),
                    recurrence=rec,
                    is_enabled=enabled,
                    created_by_membership_id=members["admin"].id,
                )
            )
        self.db.flush()

    def _new_request(
        self,
        org,
        spec,
        requester,
        rid,
        pidx,
        cat,
        title,
        prio,
        at=None,
        asset_id=None,
    ) -> ServiceRequest:
        number = self.db.execute(
            text(
                "UPDATE organizations SET request_seq = request_seq + 1 "
                "WHERE id = :o RETURNING request_seq"
            ),
            {"o": org.id},
        ).scalar_one()
        stamps = {"created_at": at, "updated_at": at, "status_changed_at": at} if at else {}
        req = self.ensure(
            ServiceRequest,
            rid,
            id=rid,
            organization_id=org.id,
            number=number,
            requester_membership_id=requester.id,
            created_by_membership_id=requester.id,
            property_id=uid("prop", spec.key, str(pidx)),
            asset_id=asset_id,
            category_id=uid("cat", spec.key, cat),
            title=title,
            description="Reported by the tenant; the problem needs a technician visit soon.",
            priority=prio,
            status=RequestStatus.SUBMITTED,
            **stamps,
        )
        self._event(
            org,
            req,
            requester,
            "REQUEST_CREATED",
            None,
            RequestStatus.SUBMITTED,
            {"number": number, "priority": prio.value},
            at=at,
        )
        return req

    def _event(self, org, req, actor, type_, frm, to, data, at=None) -> None:
        self.db.add(
            RequestEvent(
                **({"created_at": at} if at is not None else {}),
                organization_id=org.id,
                request_id=req.id,
                type=type_,
                actor_membership_id=actor.id,
                from_status=frm.value if frm else None,
                to_status=to.value if to else None,
                data=sanitize(data) if data else None,
            )
        )
        self.db.flush()

    def _note(self, org, req, author, visibility, kind, body, at=None) -> WorkNote:
        note = WorkNote(
            **({"created_at": at} if at is not None else {}),
            organization_id=org.id,
            request_id=req.id,
            author_membership_id=author.id,
            visibility=visibility,
            kind=kind,
            body=body,
        )
        self.db.add(note)
        self.db.flush()
        self._event(
            org,
            req,
            author,
            "NOTE_ADDED",
            None,
            None,
            {"note_id": str(note.id), "visibility": visibility.value, "kind": kind.value},
            at=at,
        )
        return note


def seed(db: Session) -> list[tuple[str, str, str]]:
    s = Seeder(db)
    shared = s.user(SHARED_EMAIL, "Shared Demo User")
    for spec in ORGS:
        s.seed_org(spec, shared)
    recompute_all(db)  # SLA cache of every seeded request, derived from its events
    db.commit()
    return s.credentials


SUMMARY_ENTITIES = (
    ("requesters", "memberships WHERE role = 'REQUESTER'"),
    ("dispatchers", "memberships WHERE role = 'DISPATCHER'"),
    ("admins", "memberships WHERE role = 'ADMIN'"),
    ("technicians", "memberships WHERE role = 'TECHNICIAN'"),
    ("properties", "properties"),
    ("assets", "assets"),
    ("service categories", "service_categories"),
    ("inventory items", "inventory_items"),
    ("low-stock items", "inventory_items WHERE stock_quantity <= reorder_threshold"),
    ("service requests", "service_requests"),
    ("assignments", "assignments"),
    ("estimates", "estimates"),
    ("attachments", "evidence_files"),
    ("feedback", "feedback"),
    ("material usage", "material_usage"),
    ("maintenance plans", "maintenance_plans"),
)


def summary(db: Session) -> dict[str, dict[str, int]]:
    """Counts per entity per organization (name -> entity -> count)."""
    out: dict[str, dict[str, int]] = {}
    for org_id, name in db.execute(text("SELECT id, name FROM organizations ORDER BY name")).all():
        out[name] = {
            label: db.execute(
                text(
                    f"SELECT count(*) FROM {frm}"  # noqa: S608 - constant table list
                    + (" AND" if "WHERE" in frm else " WHERE")
                    + " organization_id = :o"
                ),
                {"o": org_id},
            ).scalar_one()
            for label, frm in SUMMARY_ENTITIES
        }
    return out


def format_summary(data: dict[str, dict[str, int]]) -> str:
    orgs = list(data)
    labels = [lbl for lbl, _ in SUMMARY_ENTITIES]
    w = max(len(x) for x in labels)
    lines = [f"{'ENTITY':<{w}}  " + "  ".join(f"{o:>22}" for o in orgs) + "  " + f"{'TOTAL':>6}"]
    for lbl in labels:
        vals = [data[o][lbl] for o in orgs]
        lines.append(f"{lbl:<{w}}  " + "  ".join(f"{v:>22}" for v in vals) + f"  {sum(vals):>6}")
    return "\n".join(lines)


def format_credentials(rows: list[tuple[str, str, str]]) -> str:
    width = max(len(r[0]) for r in rows)
    org_w = max(len(r[1]) for r in rows)
    lines = [f"{'EMAIL':<{width}}  {'ORGANIZATION':<{org_w}}  {'ROLE':<10}  PASSWORD"]
    lines += [f"{e:<{width}}  {o:<{org_w}}  {r:<10}  {DEMO_PASSWORD}" for e, o, r in rows]
    return "\n".join(lines)
