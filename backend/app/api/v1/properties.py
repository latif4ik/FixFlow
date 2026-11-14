import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.core.deps import CurrentCtx, DbDep, StaffCtx
from app.core.pagination import Page, Pagination, make_page
from app.models.assets import Asset, Property
from app.models.enums import AssetStatus
from app.schemas.assets import (
    AccessGrantIn,
    AccessOut,
    AssetIn,
    AssetOut,
    AssetPatch,
    PropertyIn,
    PropertyOut,
    PropertyPatch,
)
from app.services import properties as svc

router = APIRouter(tags=["properties"])
assets_router = APIRouter(tags=["assets"])

Q = Annotated[str | None, Query(max_length=100)]


@router.get("/properties", response_model=Page[PropertyOut])
def list_properties(
    db: DbDep, ctx: CurrentCtx, params: Pagination, q: Q = None, is_active: bool | None = None
) -> dict:
    items, total = svc.list_properties(db, ctx, params, q, is_active)
    return make_page([PropertyOut.model_validate(p) for p in items], total, params)


@router.post("/properties", response_model=PropertyOut, status_code=201)
def create_property(body: PropertyIn, db: DbDep, ctx: StaffCtx) -> Property:
    prop = svc.create_property(db, ctx, body.model_dump())
    db.commit()
    return prop


@router.get("/properties/{property_id}", response_model=PropertyOut)
def get_property(property_id: uuid.UUID, db: DbDep, ctx: CurrentCtx) -> Property:
    return svc.get_property(db, ctx, property_id)


@router.patch("/properties/{property_id}", response_model=PropertyOut)
def patch_property(
    property_id: uuid.UUID, body: PropertyPatch, db: DbDep, ctx: StaffCtx
) -> Property:
    prop = svc.update_property(db, ctx, property_id, body.model_dump(exclude_unset=True))
    db.commit()
    return prop


@router.get("/properties/{property_id}/access", response_model=Page[AccessOut])
def list_access(property_id: uuid.UUID, db: DbDep, ctx: StaffCtx, params: Pagination) -> dict:
    rows, total = svc.list_access(db, ctx, params, property_id)
    items = [
        AccessOut(
            membership_id=a.membership_id,
            full_name=u.full_name,
            email=u.email,
            granted_by_membership_id=a.granted_by_membership_id,
            created_at=a.created_at,
        )
        for a, u in rows
    ]
    return make_page(items, total, params)


@router.post("/properties/{property_id}/access", response_model=AccessOut, status_code=201)
def grant_access(
    property_id: uuid.UUID, body: AccessGrantIn, db: DbDep, ctx: StaffCtx
) -> AccessOut:
    a, u = svc.grant_access(db, ctx, property_id, body.membership_id)
    db.commit()
    return AccessOut(
        membership_id=a.membership_id,
        full_name=u.full_name,
        email=u.email,
        granted_by_membership_id=a.granted_by_membership_id,
        created_at=a.created_at,
    )


@router.delete("/properties/{property_id}/access/{membership_id}", status_code=204)
def revoke_access(
    property_id: uuid.UUID, membership_id: uuid.UUID, db: DbDep, ctx: StaffCtx
) -> Response:
    svc.revoke_access(db, ctx, property_id, membership_id)
    db.commit()
    return Response(status_code=204)


@assets_router.get("/assets", response_model=Page[AssetOut])
def list_assets(
    db: DbDep,
    ctx: CurrentCtx,
    params: Pagination,
    property_id: uuid.UUID | None = None,
    status: AssetStatus | None = None,
    q: Q = None,
) -> dict:
    items, total = svc.list_assets(db, ctx, params, property_id, status, q)
    return make_page([AssetOut.model_validate(a) for a in items], total, params)


@assets_router.post("/assets", response_model=AssetOut, status_code=201)
def create_asset(body: AssetIn, db: DbDep, ctx: StaffCtx) -> Asset:
    asset = svc.create_asset(db, ctx, body.model_dump())
    db.commit()
    return asset


@assets_router.get("/assets/{asset_id}", response_model=AssetOut)
def get_asset(asset_id: uuid.UUID, db: DbDep, ctx: CurrentCtx) -> Asset:
    return svc.get_asset(db, ctx, asset_id)


@assets_router.patch("/assets/{asset_id}", response_model=AssetOut)
def patch_asset(asset_id: uuid.UUID, body: AssetPatch, db: DbDep, ctx: StaffCtx) -> Asset:
    asset = svc.update_asset(db, ctx, asset_id, body.model_dump(exclude_unset=True))
    db.commit()
    return asset
