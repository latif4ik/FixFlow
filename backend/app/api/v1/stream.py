"""Live updates (Server-Sent Events). See ``app.services.stream`` for the full contract."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.core.deps import CurrentCtx, DbDep, SessionUserDep
from app.core.errors import Unauthorized
from app.services import stream as svc

router = APIRouter(tags=["stream"])


class TicketOut(BaseModel):
    ticket: str
    expires_at: datetime


@router.post("/stream/ticket", response_model=TicketOut)
def create_ticket(db: DbDep, ctx: CurrentCtx, su: SessionUserDep) -> TicketOut:
    """Mint a short-lived (60 s) opaque ticket for GET /stream. Needs Bearer + X-Org-Id."""
    token, expires = svc.issue_ticket(db, ctx, su.session.id)
    return TicketOut(ticket=token, expires_at=expires)


@router.get("/stream")
async def stream(request: Request, ticket: Annotated[str, Query(min_length=8, max_length=200)]):
    """``text/event-stream`` of change signals for the ticket's membership.

    The ticket may be reused until it expires (browser auto-reconnect); afterwards request a new
    one. Always refetch canonical state when (re)connecting and on ``resync``.
    """
    identity = await run_in_threadpool(svc.validate_ticket, ticket)
    if identity is None:
        raise Unauthorized("Invalid or expired stream ticket.")
    return StreamingResponse(
        svc.event_stream(request.app.state.hub, identity),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
