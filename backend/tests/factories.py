"""Small helpers that create rows directly through the ORM (committing)."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import (
    Asset,
    Membership,
    MembershipRole,
    Organization,
    Property,
    PropertyAccess,
    User,
)

PASSWORD = "password123"
_HASH = hash_password(PASSWORD)  # hash once: argon2 is deliberately slow

R = MembershipRole


def make_org(db: Session, name: str = "Org", tz: str = "Asia/Bishkek") -> Organization:
    org = Organization(
        name=name, slug=f"{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}", timezone=tz
    )
    db.add(org)
    db.commit()
    return org


def make_user(
    db: Session, email: str | None = None, active: bool = True, full_name: str = "Test User"
) -> User:
    email = email or f"user-{uuid.uuid4().hex[:8]}@example.test"
    user = User(email=email, full_name=full_name, password_hash=_HASH, is_active=active)
    db.add(user)
    db.commit()
    return user


def make_member(
    db: Session,
    org: Organization,
    role: MembershipRole,
    user: User | None = None,
    active: bool = True,
) -> tuple[User, Membership]:
    user = user or make_user(db, full_name=f"{role.value.title()} User")
    m = Membership(organization_id=org.id, user_id=user.id, role=role, is_active=active)
    db.add(m)
    db.commit()
    return user, m


def make_property(db: Session, org: Organization, name: str = "Prop") -> Property:
    p = Property(organization_id=org.id, name=name, address="1 Test St")
    db.add(p)
    db.commit()
    return p


def make_asset(db: Session, org: Organization, prop: Property, code: str = "A-1") -> Asset:
    a = Asset(
        organization_id=org.id,
        property_id=prop.id,
        code=code,
        name=f"Asset {code}",
        asset_type="HVAC",
    )
    db.add(a)
    db.commit()
    return a


def grant(db: Session, prop: Property, membership: Membership, by: Membership) -> None:
    db.add(
        PropertyAccess(
            organization_id=prop.organization_id,
            property_id=prop.id,
            membership_id=membership.id,
            granted_by_membership_id=by.id,
        )
    )
    db.commit()


def login(client: TestClient, user: User, password: str = PASSWORD) -> str:
    r = client.post("/api/v1/auth/login", json={"email": user.email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def h(token: str, org: Organization | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if org is not None:
        headers["X-Org-Id"] = str(org.id)
    return headers
