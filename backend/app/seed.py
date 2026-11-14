"""Deterministic, idempotent demo seed (``python -m app.cli seed``).

Every row uses a UUIDv5 derived from a stable name, and is created only if missing, so
re-running never duplicates or overwrites data. All demo passwords are the disposable
string below; never use this in production.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

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
    InventoryItem,
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
    NoteKind,
    NoteVisibility,
    Priority,
    RequestStatus,
    StockMovementKind,
)

DEMO_PASSWORD = "demo1234"  # noqa: S105 - disposable demo credential, documented
NAMESPACE = uuid.UUID("6f1f2c4e-8f0b-4a53-9c63-0f1f0c5e11a0")
SHARED_EMAIL = "shared@fixflow.demo"
R = MembershipRole


def uid(*parts: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, ":".join(parts))


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
        ),
        # requester2 has no grants (empty state). Property 0 is shared by requester1 + shared user.
        {0: ("requester1", "shared"), 1: ("requester1",), 2: ("shared",)},
    ),
    OrgSpec(
        "alatoo",
        "Ala-Too Repairs",
        "alatoo.demo",
        (
            ("Ala-Too Business Centre", "21 Manas Ave, Bishkek"),
            ("Orto-Sai Apartments", "3 Orto-Sai St, Bishkek"),
            ("Vostok Clinic", "40 Toktogul St, Bishkek"),
        ),
        {0: ("requester1", "requester2"), 1: ("requester1",), 2: ("requester2",)},
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
)
# request key -> technician key -> (item code, quantity): seeded material usage
USAGE = {
    "i": ("technician3", (("FILTER-HVAC-M", "2"),)),
    "k": ("technician1", (("SOCKET-16A", "1"), ("CABLE-2.5", "6.5"))),
    "l": ("technician2", (("VALVE-BALL-15", "1"), ("SEALANT-SIL", "1"))),
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
}
PEOPLE = (
    ("admin", "Admin", R.ADMIN),
    ("dispatcher", "Dispatcher", R.DISPATCHER),
    ("technician1", "Technician One", R.TECHNICIAN),
    ("technician2", "Technician Two", R.TECHNICIAN),
    ("technician3", "Technician Three", R.TECHNICIAN),
    ("requester1", "Requester One", R.REQUESTER),
    ("requester2", "Requester Two", R.REQUESTER),
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
        self.seed_inventory(org, spec, members)
        self.seed_estimates(org, spec, members)
        self.seed_notifications(org, spec, members)

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
        today = datetime.now(tz).date()

        def bday(offset: int) -> date:
            """Business day ``offset`` days from today (0 = today, or next Monday on weekends)."""
            d, step = today, (1 if offset > 0 else -1)
            for _ in range(abs(offset)):
                d += timedelta(days=step)
                while d.weekday() >= 5:
                    d += timedelta(days=step)
            while d.weekday() >= 5:
                d += timedelta(days=1)
            return d

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
                )
            items[code] = item
        for rkey, (tech_key, lines) in USAGE.items():
            req_id = uid("request", spec.key, rkey)
            if self.db.get(ServiceRequest, req_id) is None:
                continue
            tech = members[tech_key]
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
                )

    def _balance(self, item_id: uuid.UUID) -> Decimal:
        return self.db.execute(
            text("SELECT COALESCE(sum(delta), 0) FROM stock_movements WHERE item_id = :i"),
            {"i": item_id},
        ).scalar_one()

    def _movement(self, org, item, kind, delta, reason, actor, after, mid, usage_id=None) -> None:
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
        now = datetime.now(UTC)
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
            self._event(org, req, disp, "ESTIMATE_SUBMITTED", None, None, data)
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
                est.decided_at, est.decided_by_membership_id = now, req1.id
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

    def _new_request(self, org, spec, requester, rid, pidx, cat, title, prio) -> ServiceRequest:
        number = self.db.execute(
            text(
                "UPDATE organizations SET request_seq = request_seq + 1 "
                "WHERE id = :o RETURNING request_seq"
            ),
            {"o": org.id},
        ).scalar_one()
        req = self.ensure(
            ServiceRequest,
            rid,
            id=rid,
            organization_id=org.id,
            number=number,
            requester_membership_id=requester.id,
            created_by_membership_id=requester.id,
            property_id=uid("prop", spec.key, str(pidx)),
            category_id=uid("cat", spec.key, cat),
            title=title,
            description="Reported by the tenant; the problem needs a technician visit soon.",
            priority=prio,
            status=RequestStatus.SUBMITTED,
        )
        self._event(
            org,
            req,
            requester,
            "REQUEST_CREATED",
            None,
            RequestStatus.SUBMITTED,
            {"number": number},
        )
        return req

    def _event(self, org, req, actor, type_, frm, to, data) -> None:
        self.db.add(
            RequestEvent(
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

    def _note(self, org, req, author, visibility, kind, body) -> WorkNote:
        note = WorkNote(
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
        )
        return note


def seed(db: Session) -> list[tuple[str, str, str]]:
    s = Seeder(db)
    shared = s.user(SHARED_EMAIL, "Shared Demo User")
    for spec in ORGS:
        s.seed_org(spec, shared)
    db.commit()
    return s.credentials


def format_credentials(rows: list[tuple[str, str, str]]) -> str:
    width = max(len(r[0]) for r in rows)
    org_w = max(len(r[1]) for r in rows)
    lines = [f"{'EMAIL':<{width}}  {'ORGANIZATION':<{org_w}}  {'ROLE':<10}  PASSWORD"]
    lines += [f"{e:<{width}}  {o:<{org_w}}  {r:<10}  {DEMO_PASSWORD}" for e, o, r in rows]
    return "\n".join(lines)
