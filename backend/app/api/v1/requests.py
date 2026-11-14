import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, Query, Response, UploadFile
from fastapi.responses import FileResponse

from app.core.deps import CurrentCtx, DbDep
from app.core.pagination import Page, Pagination, make_page
from app.models.enums import FilePurpose, Priority, RequestStatus
from app.schemas.requests import (
    DuplicateIn,
    FileOut,
    NoteIn,
    NoteOut,
    ReasonIn,
    RequestCreate,
    RequestDetail,
    RequestListItem,
    RequestPatch,
    RequiredReasonIn,
    TimelineItem,
    TransitionIn,
    TriageIn,
)
from app.services import files as files_svc
from app.services import lifecycle
from app.services import notes as notes_svc
from app.services import requests as svc

router = APIRouter(tags=["requests"])
files_router = APIRouter(tags=["files"])

Sort = Literal["newest", "oldest", "priority", "due"]
SlaFilter = Literal["ON_TRACK", "AT_RISK", "OVERDUE", "PAUSED"]


@router.post("/requests", response_model=RequestDetail, status_code=201)
def create_request(body: RequestCreate, db: DbDep, ctx: CurrentCtx) -> RequestDetail:
    req = svc.create_request(db, ctx, body.model_dump())
    return svc.get_detail(db, ctx, req.id)


@router.get("/requests", response_model=Page[RequestListItem])
def list_requests(
    db: DbDep,
    ctx: CurrentCtx,
    params: Pagination,
    status: Annotated[list[RequestStatus] | None, Query()] = None,
    priority: Annotated[list[Priority] | None, Query()] = None,
    category_id: uuid.UUID | None = None,
    property_id: uuid.UUID | None = None,
    asset_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    sort: Sort = "newest",
    sla_state: Annotated[
        list[SlaFilter] | None,
        Query(description="Live SLA state (finished requests are excluded)."),
    ] = None,
    technician_id: Annotated[
        uuid.UUID | None,
        Query(description="Requests currently assigned (or completed) by this technician."),
    ] = None,
) -> dict:
    items, total = svc.list_requests(
        db,
        ctx,
        params,
        statuses=status or [],
        priorities=priority or [],
        category_id=category_id,
        property_id=property_id,
        asset_id=asset_id,
        q=q,
        created_from=created_from,
        created_to=created_to,
        sort=sort,
        technician_id=technician_id,
        sla_states=sla_state,
    )
    return make_page(items, total, params)


@router.get("/requests/{request_id}", response_model=RequestDetail)
def get_request(request_id: uuid.UUID, db: DbDep, ctx: CurrentCtx) -> RequestDetail:
    return svc.get_detail(db, ctx, request_id)


@router.patch("/requests/{request_id}", response_model=RequestDetail)
def patch_request(
    request_id: uuid.UUID, body: RequestPatch, db: DbDep, ctx: CurrentCtx
) -> RequestDetail:
    svc.update_request(db, ctx, request_id, body.model_dump(exclude_unset=True))
    return svc.get_detail(db, ctx, request_id)


@router.post("/requests/{request_id}/duplicate", response_model=RequestDetail)
def link_duplicate(
    request_id: uuid.UUID, body: DuplicateIn, db: DbDep, ctx: CurrentCtx
) -> RequestDetail:
    svc.link_duplicate(db, ctx, request_id, body.duplicate_of_id, body.reason)
    return svc.get_detail(db, ctx, request_id)


def _do(
    db: DbDep,
    ctx: CurrentCtx,
    request_id: uuid.UUID,
    to: RequestStatus,
    reason: str | None = None,
    note: str | None = None,
) -> RequestDetail:
    lifecycle.transition(db, ctx, request_id, to, reason=reason, note_body=note)
    return svc.get_detail(db, ctx, request_id)


@router.post("/requests/{request_id}/triage", response_model=RequestDetail)
def triage(request_id: uuid.UUID, body: TriageIn, db: DbDep, ctx: CurrentCtx) -> RequestDetail:
    return _do(db, ctx, request_id, RequestStatus.TRIAGED, note=body.note)


@router.post("/requests/{request_id}/cancel", response_model=RequestDetail)
def cancel(request_id: uuid.UUID, body: ReasonIn, db: DbDep, ctx: CurrentCtx) -> RequestDetail:
    return _do(db, ctx, request_id, RequestStatus.CANCELED, reason=body.reason)


@router.post("/requests/{request_id}/close", response_model=RequestDetail)
def close(request_id: uuid.UUID, body: ReasonIn, db: DbDep, ctx: CurrentCtx) -> RequestDetail:
    return _do(db, ctx, request_id, RequestStatus.CLOSED, reason=body.reason)


@router.post("/requests/{request_id}/reopen", response_model=RequestDetail)
def reopen(
    request_id: uuid.UUID, body: RequiredReasonIn, db: DbDep, ctx: CurrentCtx
) -> RequestDetail:
    return _do(db, ctx, request_id, RequestStatus.REOPENED, reason=body.reason)


@router.post("/requests/{request_id}/transitions", response_model=RequestDetail)
def generic_transition(
    request_id: uuid.UUID, body: TransitionIn, db: DbDep, ctx: CurrentCtx
) -> RequestDetail:
    return _do(db, ctx, request_id, body.to_status, reason=body.reason, note=body.note)


@router.get("/requests/{request_id}/timeline", response_model=Page[TimelineItem])
def timeline(request_id: uuid.UUID, db: DbDep, ctx: CurrentCtx, params: Pagination) -> dict:
    items, total = svc.list_timeline(db, ctx, request_id, params)
    return make_page(items, total, params)


@router.post("/requests/{request_id}/notes", response_model=NoteOut)
def create_note(
    request_id: uuid.UUID, body: NoteIn, response: Response, db: DbDep, ctx: CurrentCtx
) -> NoteOut:
    note, created = notes_svc.create_note(
        db,
        ctx,
        request_id,
        body.body,
        body.visibility,
        body.kind,
        body.client_command_id,
        body.attachment_ids,
    )
    response.status_code = 201 if created else 200
    files = [f for f in svc.visible_files(db, ctx, request_id) if f.note_id == note.id]
    return svc.build_notes(db, ctx, [note], files)[0]


@router.get("/requests/{request_id}/notes", response_model=Page[NoteOut])
def list_notes(request_id: uuid.UUID, db: DbDep, ctx: CurrentCtx, params: Pagination) -> dict:
    notes, total = notes_svc.list_notes(db, ctx, request_id, params)
    files = svc.visible_files(db, ctx, request_id)
    return make_page(svc.build_notes(db, ctx, notes, files), total, params)


@router.post("/requests/{request_id}/files", response_model=FileOut, status_code=201)
def upload_file(
    request_id: uuid.UUID,
    response: Response,
    db: DbDep,
    ctx: CurrentCtx,
    file: Annotated[UploadFile, File()],
    purpose: Annotated[FilePurpose, Form()],
    client_command_id: Annotated[uuid.UUID | None, Form()] = None,
    client_index: Annotated[int | None, Form(ge=0, le=32000)] = None,
) -> FileOut:
    row, created = files_svc.upload_file(
        db, ctx, request_id, purpose, file.file, file.filename, client_command_id, client_index
    )
    if not created:
        response.status_code = 200
    return svc.file_out(row)


@files_router.get("/files/{file_id}")
def download_file(file_id: uuid.UUID, db: DbDep, ctx: CurrentCtx) -> FileResponse:
    f, path = files_svc.get_file_for_download(db, ctx, file_id)
    return FileResponse(
        path,
        media_type=f.mime_type,
        headers={
            "Content-Disposition": f'inline; filename="{f.original_filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
