"""Properties, assets and requester property access (ASSET-01..03)."""

import uuid
from typing import Any

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.core.pagination import PageParams, paginate_rows
from app.core.tenancy import Ctx, get_or_404
from app.models.assets import Asset, Property, PropertyAccess
from app.models.enums import AssetStatus, MembershipRole
from app.models.identity import Membership, User
from app.services.util import like_pattern

R = MembershipRole


def _deny_technician(ctx: Ctx) -> None:
    if ctx.role == R.TECHNICIAN:
        raise Forbidden("Technicians cannot browse properties or assets here.")


def granted_property_ids(ctx: Ctx):
    return select(PropertyAccess.property_id).where(
        PropertyAccess.organization_id == ctx.org_id,
        PropertyAccess.membership_id == ctx.membership_id,
    )


def _prop_snapshot(p: Property) -> dict[str, Any]:
    return {
        "name": p.name,
        "address": p.address,
        "contact_instructions": p.contact_instructions,
        "is_active": p.is_active,
    }


# ---- properties ----
def list_properties(
    db: Session, ctx: Ctx, params: PageParams, q: str | None, is_active: bool | None
) -> tuple[list[Property], int]:
    _deny_technician(ctx)
    stmt: Select[Any] = select(Property).where(Property.organization_id == ctx.org_id)
    if ctx.role == R.REQUESTER:
        stmt = stmt.where(Property.id.in_(granted_property_ids(ctx)), Property.is_active.is_(True))
    elif is_active is not None:
        stmt = stmt.where(Property.is_active.is_(is_active))
    if q:
        pat = like_pattern(q)
        stmt = stmt.where(
            or_(Property.name.ilike(pat, escape="\\"), Property.address.ilike(pat, escape="\\"))
        )
    rows, total = paginate_rows(db, stmt.order_by(Property.name, Property.id), params)
    return [r[0] for r in rows], total


def get_property(db: Session, ctx: Ctx, property_id: uuid.UUID) -> Property:
    """Requester: only granted properties; anything else is the same 404."""
    _deny_technician(ctx)
    prop = get_or_404(db, Property, property_id, ctx, "Property")
    if ctx.role == R.REQUESTER:
        granted = db.scalar(
            select(PropertyAccess.property_id).where(
                PropertyAccess.organization_id == ctx.org_id,
                PropertyAccess.property_id == property_id,
                PropertyAccess.membership_id == ctx.membership_id,
            )
        )
        if granted is None or not prop.is_active:
            raise NotFound("Property not found.")
    return prop


def create_property(db: Session, ctx: Ctx, data: dict[str, Any]) -> Property:
    prop = Property(organization_id=ctx.org_id, **data)
    db.add(prop)
    db.flush()
    record_audit(db, ctx, "property.created", "property", prop.id, None, _prop_snapshot(prop))
    return prop


def update_property(
    db: Session, ctx: Ctx, property_id: uuid.UUID, data: dict[str, Any]
) -> Property:
    prop = get_or_404(db, Property, property_id, ctx, "Property")
    before = _prop_snapshot(prop)
    for k, v in data.items():
        if k == "contact_instructions" or v is not None:
            setattr(prop, k, v)
    db.flush()
    after = _prop_snapshot(prop)
    if before != after:
        action = "property.updated"
        if before["is_active"] != after["is_active"]:
            action = "property.restored" if after["is_active"] else "property.archived"
        record_audit(db, ctx, action, "property", prop.id, before, after)
    return prop


# ---- access ----
def list_access(
    db: Session, ctx: Ctx, params: PageParams, property_id: uuid.UUID
) -> tuple[list[Any], int]:
    get_or_404(db, Property, property_id, ctx, "Property")
    stmt = (
        select(PropertyAccess, User)
        .join(Membership, Membership.id == PropertyAccess.membership_id)
        .join(User, User.id == Membership.user_id)
        .where(
            PropertyAccess.organization_id == ctx.org_id, PropertyAccess.property_id == property_id
        )
        .order_by(User.full_name, PropertyAccess.membership_id)
    )
    return paginate_rows(db, stmt, params)


def grant_access(
    db: Session, ctx: Ctx, property_id: uuid.UUID, membership_id: uuid.UUID
) -> tuple[PropertyAccess, User]:
    get_or_404(db, Property, property_id, ctx, "Property")
    row = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == ctx.org_id, Membership.id == membership_id)
    ).first()
    if row is None or row[0].role != R.REQUESTER:
        raise ValidationFailed(
            "Access can only be granted to a requester membership of this organization.",
            [{"field": "membership_id", "message": "must be a REQUESTER membership in this org"}],
        )
    if db.get(PropertyAccess, (property_id, membership_id)) is not None:
        raise Conflict("Access has already been granted.", {"fields": ["membership_id"]})
    access = PropertyAccess(
        organization_id=ctx.org_id,
        property_id=property_id,
        membership_id=membership_id,
        granted_by_membership_id=ctx.membership_id,
    )
    db.add(access)
    db.flush()
    db.refresh(access)
    record_audit(
        db,
        ctx,
        "property_access.granted",
        "property",
        property_id,
        None,
        {"membership_id": membership_id, "email": row[1].email},
    )
    return access, row[1]


def revoke_access(db: Session, ctx: Ctx, property_id: uuid.UUID, membership_id: uuid.UUID) -> None:
    access = db.scalars(
        select(PropertyAccess).where(
            PropertyAccess.organization_id == ctx.org_id,
            PropertyAccess.property_id == property_id,
            PropertyAccess.membership_id == membership_id,
        )
    ).first()
    if access is None:
        raise NotFound("Access grant not found.")
    db.delete(access)
    db.flush()
    record_audit(
        db,
        ctx,
        "property_access.revoked",
        "property",
        property_id,
        {"membership_id": membership_id},
        None,
    )


# ---- assets ----
def _asset_snapshot(a: Asset) -> dict[str, Any]:
    return {
        "property_id": a.property_id,
        "code": a.code,
        "name": a.name,
        "asset_type": a.asset_type,
        "serial_number": a.serial_number,
        "installed_on": a.installed_on,
        "status": a.status,
        "notes": a.notes,
    }


def _check_property(db: Session, ctx: Ctx, property_id: uuid.UUID) -> None:
    ok = db.scalar(
        select(Property.id).where(
            Property.organization_id == ctx.org_id, Property.id == property_id
        )
    )
    if ok is None:
        raise ValidationFailed(
            "Unknown property.",
            [{"field": "property_id", "message": "property does not exist in this organization"}],
        )


def list_assets(
    db: Session,
    ctx: Ctx,
    params: PageParams,
    property_id: uuid.UUID | None,
    status: AssetStatus | None,
    q: str | None,
) -> tuple[list[Asset], int]:
    _deny_technician(ctx)
    stmt: Select[Any] = select(Asset).where(Asset.organization_id == ctx.org_id)
    if ctx.role == R.REQUESTER:
        stmt = stmt.where(Asset.property_id.in_(granted_property_ids(ctx)))
    if property_id is not None:
        stmt = stmt.where(Asset.property_id == property_id)
    if status is not None:
        stmt = stmt.where(Asset.status == status)
    if q:
        pat = like_pattern(q)
        stmt = stmt.where(
            or_(
                Asset.name.ilike(pat, escape="\\"),
                Asset.code.ilike(pat, escape="\\"),
                Asset.serial_number.ilike(pat, escape="\\"),
            )
        )
    rows, total = paginate_rows(db, stmt.order_by(Asset.code, Asset.id), params)
    return [r[0] for r in rows], total


def get_asset(db: Session, ctx: Ctx, asset_id: uuid.UUID) -> Asset:
    _deny_technician(ctx)
    asset = get_or_404(db, Asset, asset_id, ctx, "Asset")
    if ctx.role == R.REQUESTER:
        granted = db.scalar(
            select(PropertyAccess.property_id).where(
                PropertyAccess.organization_id == ctx.org_id,
                PropertyAccess.property_id == asset.property_id,
                PropertyAccess.membership_id == ctx.membership_id,
            )
        )
        if granted is None:
            raise NotFound("Asset not found.")
    return asset


def create_asset(db: Session, ctx: Ctx, data: dict[str, Any]) -> Asset:
    _check_property(db, ctx, data["property_id"])
    asset = Asset(organization_id=ctx.org_id, **data)
    db.add(asset)
    db.flush()
    db.refresh(asset)
    record_audit(db, ctx, "asset.created", "asset", asset.id, None, _asset_snapshot(asset))
    return asset


def update_asset(db: Session, ctx: Ctx, asset_id: uuid.UUID, data: dict[str, Any]) -> Asset:
    asset = get_or_404(db, Asset, asset_id, ctx, "Asset")
    if data.get("property_id") is not None:
        _check_property(db, ctx, data["property_id"])
    before = _asset_snapshot(asset)
    nullable = {"serial_number", "installed_on", "notes"}
    for k, v in data.items():
        if k in nullable or v is not None:
            setattr(asset, k, v)
    db.flush()
    db.refresh(asset)
    after = _asset_snapshot(asset)
    if before != after:
        action = "asset.updated"
        if before["status"] != after["status"] and after["status"] == AssetStatus.RETIRED:
            action = "asset.retired"
        record_audit(db, ctx, action, "asset", asset.id, before, after)
    return asset
