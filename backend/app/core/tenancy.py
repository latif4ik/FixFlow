"""Org-scoped query helpers. Cross-org access always looks like "not found"."""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.models.enums import MembershipRole


@dataclass(frozen=True)
class Ctx:
    user_id: uuid.UUID
    org_id: uuid.UUID
    membership_id: uuid.UUID
    role: MembershipRole
    timezone: str


def scoped(stmt: Select[Any], model: Any, ctx: Ctx) -> Select[Any]:
    """Restrict a SELECT to the caller's organization."""
    return stmt.where(model.organization_id == ctx.org_id)


def get_or_404(
    db: Session, model: Any, obj_id: uuid.UUID, ctx: Ctx, what: str | None = None
) -> Any:
    """Fetch ``model`` by id inside the caller's org, else raise NotFound."""
    obj = db.scalars(scoped(select(model), model, ctx).where(model.id == obj_id)).first()
    if obj is None:
        raise NotFound(f"{what or model.__name__} not found.")
    return obj
