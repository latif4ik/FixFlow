"""Generic idempotency for retryable commands (API-03).

Usage (endpoint level)::

    outcome = run_idempotent(db, ctx, key, endpoint, payload, op)

``op()`` performs the effect WITHOUT committing and returns ``(status, json_body)``. The key
is claimed with ``INSERT ... ON CONFLICT DO NOTHING`` inside the same transaction as the
effect, and the response is stored in that transaction too, so effect + stored response
commit (or roll back) together:

* same key, same endpoint + payload  -> the stored response is replayed, nothing re-executed;
* same key, different endpoint/payload -> 409 ``idempotency_key_reused``;
* two concurrent requests with one key -> the second blocks on the first's uncommitted claim
  row (unique index), then replays its stored response. A failed first attempt rolls back its
  claim, so a retry simply executes.

Failed responses (errors) are not stored: the client can retry the same key.
"""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Header
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.errors import AppError, ValidationFailed
from app.core.tenancy import Ctx
from app.models.assignments import IdempotencyKey

MAX_KEY_LEN = 128

IdempotencyKeyHeader = Annotated[
    str | None,
    Header(
        alias="Idempotency-Key",
        description=(
            "Optional (1-128 chars). Retrying with the same key and payload replays the original "
            "response; the same key with a different payload returns 409 idempotency_key_reused."
        ),
    ),
]


@dataclass(frozen=True)
class Outcome:
    status: int
    body: Any
    replayed: bool


def payload_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def validate_key(key: str | None) -> str | None:
    if key is None:
        return None
    key = key.strip()
    if not 1 <= len(key) <= MAX_KEY_LEN:
        raise ValidationFailed(
            "Invalid Idempotency-Key.",
            [{"field": "Idempotency-Key", "message": f"must be 1-{MAX_KEY_LEN} characters"}],
        )
    return key


def _claim(db: Session, ctx: Ctx, key: str, endpoint: str, digest: str) -> Outcome | None:
    """Claim ``key`` (returns None: caller must execute) or return the stored response."""
    inserted = db.execute(
        pg_insert(IdempotencyKey)
        .values(
            organization_id=ctx.org_id,
            membership_id=ctx.membership_id,
            key=key,
            endpoint=endpoint,
            payload_hash=digest,
            response_status=0,
            response_body={},
        )
        .on_conflict_do_nothing(index_elements=["organization_id", "membership_id", "key"])
        .returning(IdempotencyKey.id)
    ).scalar()
    if inserted is not None:
        return None
    row = db.scalars(
        select(IdempotencyKey).where(
            IdempotencyKey.organization_id == ctx.org_id,
            IdempotencyKey.membership_id == ctx.membership_id,
            IdempotencyKey.key == key,
        )
    ).one()
    if row.endpoint != endpoint or row.payload_hash != digest:
        raise AppError(
            409,
            "idempotency_key_reused",
            "This Idempotency-Key was already used with a different request.",
        )
    return Outcome(row.response_status, row.response_body, True)


def run_idempotent(
    db: Session,
    ctx: Ctx,
    key: str | None,
    endpoint: str,
    payload: Any,
    op: Callable[[], tuple[int, Any]],
) -> Outcome:
    """Run ``op`` atomically (commit on success, rollback on any error), with optional replay."""
    key = validate_key(key)
    try:
        digest = payload_hash(payload)
        if key is not None:
            replay = _claim(db, ctx, key, endpoint, digest)
            if replay is not None:
                db.rollback()  # read-only path: end the transaction
                return replay
        status, body = op()
        if key is not None:
            db.execute(
                update(IdempotencyKey)
                .where(
                    IdempotencyKey.organization_id == ctx.org_id,
                    IdempotencyKey.membership_id == ctx.membership_id,
                    IdempotencyKey.key == key,
                )
                .values(response_status=status, response_body=body)
            )
        db.commit()
        return Outcome(status, body, False)
    except BaseException:
        db.rollback()
        raise
