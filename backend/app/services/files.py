"""Evidence uploads (COMM-05/06, SEC-04): streamed, content-verified, atomically stored."""

import contextlib
import hashlib
import logging
import os
import re
import uuid
import warnings
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from PIL import Image, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.config import get_settings
from app.core.errors import AppError, Conflict, Forbidden, NotFound, ValidationFailed
from app.core.tenancy import Ctx
from app.models.enums import FilePurpose, RequestStatus
from app.models.requests import EvidenceFile, ServiceRequest
from app.services.notes import ensure_can_add_note
from app.services.request_access import (
    get_visible_request,
    is_assigned_technician,
    is_owner_requester,
    is_staff,
    visible_files_clause,
)
from app.services.request_events import add_event

logger = logging.getLogger("app.files")

MAX_DIMENSION = 8000
MAX_INTAKE_FILES = 3
CHUNK = 64 * 1024
# format -> (extension, mime)
FORMATS = {
    "JPEG": ("jpg", "image/jpeg"),
    "PNG": ("png", "image/png"),
    "WEBP": ("webp", "image/webp"),
}
# Pillow raises DecompressionBombError above 2x this and warns above 1x.
Image.MAX_IMAGE_PIXELS = MAX_DIMENSION * MAX_DIMENSION
_CMD_CONSTRAINT = "uq_evidence_files_org_client_command"


def upload_root() -> Path:
    return Path(get_settings().UPLOAD_DIR)


def sanitize_filename(name: str | None, ext: str) -> str:
    base = os.path.basename((name or "").replace("\\", "/"))
    base = re.sub(r"[^A-Za-z0-9._ -]", "_", base).strip(" .")
    base = re.sub(r"_{2,}", "_", base)[:255]
    return base or f"upload.{ext}"


def _bad(message: str, field: str = "file") -> ValidationFailed:
    return ValidationFailed("Invalid file.", [{"field": field, "message": message}])


def _stream_to_temp(src: BinaryIO, tmp: Path, max_bytes: int) -> tuple[int, str]:
    """Copy ``src`` into ``tmp`` while counting; abort as soon as the cap is exceeded."""
    size = 0
    digest = hashlib.sha256()
    with tmp.open("wb") as out:
        while chunk := src.read(CHUNK):
            size += len(chunk)
            if size > max_bytes:
                raise AppError(
                    413,
                    "payload_too_large",
                    "File is too large.",
                    {"max_bytes": max_bytes},
                )
            digest.update(chunk)
            out.write(chunk)
    return size, digest.hexdigest()


def inspect_image(path: Path) -> tuple[str, int, int]:
    """Verify the real content; returns (format, width, height) or raises 422."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as img:
                fmt = img.format
                img.verify()
            with Image.open(path) as img2:
                width, height = img2.size
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise _bad("Image dimensions are too large.") from None
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, EOFError):
        raise _bad("File is not a valid JPEG, PNG or WebP image.") from None
    if fmt not in FORMATS:
        raise _bad("Only JPEG, PNG and WebP images are accepted.")
    if width < 1 or height < 1 or width > MAX_DIMENSION or height > MAX_DIMENSION:
        raise _bad(f"Image dimensions must be at most {MAX_DIMENSION}x{MAX_DIMENSION} pixels.")
    return str(fmt), width, height


def _check_permission(db: Session, ctx: Ctx, request: ServiceRequest, purpose: FilePurpose) -> None:
    if purpose == FilePurpose.INTAKE:
        if not (is_staff(ctx) or is_owner_requester(ctx, request)):
            raise Forbidden("You cannot upload intake images to this request.")
        if request.status != RequestStatus.SUBMITTED:
            raise Conflict(
                "Intake images can only be added while the request is submitted.",
                {"status": request.status.value},
            )
    elif purpose == FilePurpose.NOTE:
        ensure_can_add_note(db, ctx, request)
    else:  # COMPLETION: assigned technician only, while IN_PROGRESS (staff may not)
        if not is_assigned_technician(db, ctx, request):
            raise Forbidden("Only the assigned technician can upload completion evidence.")
        if request.status != RequestStatus.IN_PROGRESS:
            raise Conflict(
                "Completion images can only be added while the work is in progress.",
                {"status": request.status.value},
            )


def upload_file(
    db: Session,
    ctx: Ctx,
    request_id: uuid.UUID,
    purpose: FilePurpose,
    src: BinaryIO,
    original_filename: str | None,
    client_command_id: uuid.UUID | None = None,
    client_index: int | None = None,
) -> tuple[EvidenceFile, bool]:
    """Returns (row, created). ``created`` is False for an identical idempotent replay."""
    settings = get_settings()
    request = get_visible_request(db, ctx, request_id)
    if client_command_id is None:
        _check_permission(db, ctx, request, purpose)  # cheap early reject before streaming
    # With a client_command_id the permission/status check for a NEW upload happens only after
    # the replay lookup: a retried upload after a status change must return the original row.
    index = (client_index or 0) if client_command_id is not None else None

    tmp_dir = upload_root() / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp = tmp_dir / f"{uuid.uuid4().hex}.part"
    final: Path | None = None
    try:
        size, sha = _stream_to_temp(src, tmp, settings.MAX_UPLOAD_BYTES)
        if size == 0:
            raise _bad("File is empty.")
        fmt, width, height = inspect_image(tmp)
        ext, mime = FORMATS[fmt]

        if client_command_id is not None:
            existing = _find_existing(db, ctx, client_command_id, index)
            if existing is not None:
                return _replay(existing, ctx, request, sha, purpose), False
            _check_permission(db, ctx, request, purpose)

        # Lock the request row so the status check + INTAKE count cannot race.
        locked = get_visible_request(db, ctx, request_id, lock=True)
        _check_permission(db, ctx, locked, purpose)
        if purpose == FilePurpose.INTAKE:
            count = db.scalar(
                select(func.count())
                .select_from(EvidenceFile)
                .where(
                    EvidenceFile.organization_id == ctx.org_id,
                    EvidenceFile.request_id == locked.id,
                    EvidenceFile.purpose == FilePurpose.INTAKE,
                )
            )
            if (count or 0) >= MAX_INTAKE_FILES:
                raise Conflict(f"At most {MAX_INTAKE_FILES} intake images are allowed.")

        now = datetime.now(UTC)
        file_id = uuid.uuid4()
        key = f"{ctx.org_id}/{now:%Y}/{now:%m}/{file_id}.{ext}"
        final = upload_root() / key
        final.parent.mkdir(parents=True, exist_ok=True)
        os.replace(tmp, final)

        row = EvidenceFile(
            id=file_id,
            organization_id=ctx.org_id,
            request_id=locked.id,
            uploaded_by_membership_id=ctx.membership_id,
            purpose=purpose,
            original_filename=sanitize_filename(original_filename, ext),
            storage_key=key,
            mime_type=mime,
            size_bytes=size,
            width=width,
            height=height,
            sha256=sha,
            client_command_id=client_command_id,
            client_index=index,
        )
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
        except IntegrityError as exc:
            if _constraint(exc) == _CMD_CONSTRAINT and client_command_id is not None:
                _discard(final)
                final = None
                db.rollback()
                existing = _find_existing(db, ctx, client_command_id, index)
                if existing is not None:
                    return _replay(existing, ctx, request, sha, purpose), False
            raise
        add_event(
            db,
            ctx,
            locked,
            "FILE_UPLOADED",
            data={"file_id": row.id, "purpose": purpose.value, "mime_type": mime},
        )
        record_audit(
            db,
            ctx,
            "request.file_upload",
            "service_request",
            locked.id,
            after={"file_id": row.id, "purpose": purpose.value, "sha256": sha, "size": size},
        )
        db.commit()
        final = None  # committed: keep the file
        return row, True
    except BaseException:
        db.rollback()
        raise
    finally:
        _discard(tmp)
        if final is not None:
            _discard(final)


def _constraint(exc: IntegrityError) -> str | None:
    return getattr(getattr(exc.orig, "diag", None), "constraint_name", None)


def _discard(path: Path) -> None:
    with contextlib.suppress(OSError):
        path.unlink()


def _find_existing(
    db: Session, ctx: Ctx, client_command_id: uuid.UUID, index: int | None
) -> EvidenceFile | None:
    return db.scalars(
        select(EvidenceFile).where(
            EvidenceFile.organization_id == ctx.org_id,
            EvidenceFile.client_command_id == client_command_id,
            EvidenceFile.client_index == index,
        )
    ).first()


def _replay(
    existing: EvidenceFile,
    ctx: Ctx,
    request: ServiceRequest,
    sha: str,
    purpose: FilePurpose,
) -> EvidenceFile:
    if (
        existing.uploaded_by_membership_id != ctx.membership_id
        or existing.request_id != request.id
        or existing.sha256 != sha
        or existing.purpose != purpose
    ):
        raise AppError(
            409,
            "idempotency_key_reused",
            "This client_command_id was already used with a different upload.",
        )
    return existing


# ---- download --------------------------------------------------------------------------
def get_file_for_download(db: Session, ctx: Ctx, file_id: uuid.UUID) -> tuple[EvidenceFile, Path]:
    f = db.scalars(
        select(EvidenceFile).where(
            EvidenceFile.id == file_id,
            visible_files_clause(ctx),
        )
    ).first()
    if f is None:
        raise NotFound("File not found.")
    get_visible_request(db, ctx, f.request_id)  # 404 if the request is not visible
    root = upload_root().resolve()
    path = (root / f.storage_key).resolve()
    if root not in path.parents or not path.is_file():
        logger.error("evidence file missing on disk", extra={"file_id": str(f.id)})
        raise NotFound("File not found.")
    return f, path
