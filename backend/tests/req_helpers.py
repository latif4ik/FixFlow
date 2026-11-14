"""Shared world + helpers for request/lifecycle/notes/files tests."""

import io
import uuid
from dataclasses import dataclass
from typing import Any

from PIL import Image
from sqlalchemy.orm import Session

from app.models import (
    Asset,
    Membership,
    MembershipRole,
    Organization,
    Property,
    ServiceCategory,
    ServiceRequest,
)
from app.models.enums import AssetStatus, RequestStatus
from tests.factories import grant, make_asset, make_member, make_org, make_property

R = MembershipRole
LONG_DESC = "The air conditioner in the lobby is leaking water onto the floor."


@dataclass
class Org:
    org: Organization
    admin: tuple[Any, Membership]
    disp: tuple[Any, Membership]
    tech: tuple[Any, Membership]
    req1: tuple[Any, Membership]
    req2: tuple[Any, Membership]
    prop: Property  # granted to req1
    hidden: Property  # granted to nobody
    asset: Asset  # in prop
    other_asset: Asset  # in hidden
    cat: ServiceCategory


def make_category(db: Session, org: Organization, name: str = "HVAC", enabled: bool = True):
    c = ServiceCategory(
        organization_id=org.id, name=name, default_duration_minutes=60, is_enabled=enabled
    )
    db.add(c)
    db.commit()
    return c


def make_world(db: Session, name: str = "Org A") -> Org:
    org = make_org(db, name)
    admin = make_member(db, org, R.ADMIN)
    disp = make_member(db, org, R.DISPATCHER)
    tech = make_member(db, org, R.TECHNICIAN)
    req1 = make_member(db, org, R.REQUESTER)
    req2 = make_member(db, org, R.REQUESTER)
    prop = make_property(db, org, f"{name} Tower")
    hidden = make_property(db, org, f"{name} Hidden")
    asset = make_asset(db, org, prop, "A-1")
    other_asset = make_asset(db, org, hidden, "H-1")
    grant(db, prop, req1[1], admin[1])
    return Org(
        org, admin, disp, tech, req1, req2, prop, hidden, asset, other_asset, make_category(db, org)
    )


def payload(w: Org, **over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "title": "Lobby AC leaking",
        "description": LONG_DESC,
        "category_id": str(w.cat.id),
        "property_id": str(w.prop.id),
    }
    body.update(over)
    return body


def retire(db: Session, asset: Asset) -> None:
    asset.status = AssetStatus.RETIRED
    db.commit()


def seed_request(
    db: Session,
    w: Org,
    status: RequestStatus = RequestStatus.SUBMITTED,
    requester: Membership | None = None,
    title: str = "Seeded request",
    **over: Any,
) -> ServiceRequest:
    """Insert a request directly (bypasses the engine) so tests can start in any state."""
    from sqlalchemy import text

    number = db.execute(
        text(
            "UPDATE organizations SET request_seq = request_seq + 1 "
            "WHERE id=:o RETURNING request_seq"
        ),
        {"o": w.org.id},
    ).scalar_one()
    fields: dict[str, Any] = {
        "organization_id": w.org.id,
        "number": number,
        "requester_membership_id": (requester or w.req1[1]).id,
        "created_by_membership_id": (requester or w.req1[1]).id,
        "property_id": w.prop.id,
        "category_id": w.cat.id,
        "title": title,
        "description": LONG_DESC,
        "status": status,
    }
    fields.update(over)
    req = ServiceRequest(**fields)
    db.add(req)
    db.commit()
    return req


def image_bytes(fmt: str = "PNG", size: tuple[int, int] = (20, 20)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buf, format=fmt)
    return buf.getvalue()


def upload(client, hd, request_id, data: bytes, purpose="INTAKE", name="photo.png", **form):
    return client.post(
        f"/api/v1/requests/{request_id}/files",
        headers=hd,
        files={"file": (name, data, "image/png")},
        data={"purpose": purpose, **{k: str(v) for k, v in form.items()}},
    )


def new_id() -> str:
    return str(uuid.uuid4())
