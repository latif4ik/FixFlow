"""In-app notifications of the calling membership only (COMM-03/04)."""

import uuid

from fastapi import APIRouter

from app.core.deps import CurrentCtx, DbDep
from app.core.pagination import Page, Pagination, make_page
from app.schemas.notifications import MarkedRead, NotificationOut, UnreadCount
from app.services import notifications as svc

router = APIRouter(tags=["notifications"])


@router.get("/notifications", response_model=Page[NotificationOut])
def list_notifications(
    db: DbDep, ctx: CurrentCtx, params: Pagination, unread_only: bool = False
) -> dict:
    rows, total = svc.list_notifications(db, ctx, params, unread_only)
    return make_page(
        [NotificationOut.model_validate(r, from_attributes=True) for r in rows], total, params
    )


@router.get("/notifications/unread-count", response_model=UnreadCount)
def unread_count(db: DbDep, ctx: CurrentCtx) -> UnreadCount:
    return UnreadCount(unread=svc.unread_count(db, ctx))


@router.post("/notifications/read-all", response_model=MarkedRead)
def read_all(db: DbDep, ctx: CurrentCtx) -> MarkedRead:
    return MarkedRead(marked=svc.mark_all_read(db, ctx))


@router.post("/notifications/{notification_id}/read", response_model=NotificationOut)
def read_one(notification_id: uuid.UUID, db: DbDep, ctx: CurrentCtx) -> NotificationOut:
    return NotificationOut.model_validate(
        svc.mark_read(db, ctx, notification_id), from_attributes=True
    )
