"""Deterministic, idempotent demo seed (``python -m app.cli seed``).

Every row uses a UUIDv5 derived from a stable name, and is created only if missing, so
re-running never duplicates or overwrites data. All demo passwords are the disposable
string below; never use this in production.
"""

import uuid
from dataclasses import dataclass
from datetime import date, time
from typing import Any

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import (
    Asset,
    BusinessHour,
    CategoryRequiredSkill,
    Membership,
    MembershipRole,
    Organization,
    Property,
    PropertyAccess,
    ServiceCategory,
    Skill,
    TechnicianAvailability,
    TechnicianProfile,
    TechnicianSkill,
    User,
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
