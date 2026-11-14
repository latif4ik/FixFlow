import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ValidationFailed
from app.core.tenancy import Ctx
from app.models.org import Skill


def like_pattern(q: str) -> str:
    """Substring pattern for ILIKE with wildcards escaped (use ``escape='\\\\'``)."""
    escaped = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def validate_skill_ids(
    db: Session, ctx: Ctx, ids: Iterable[uuid.UUID], field: str
) -> list[uuid.UUID]:
    """Return de-duplicated ids, 422 if any skill is missing from the caller's org."""
    unique = list(dict.fromkeys(ids))
    if not unique:
        return []
    found = set(
        db.scalars(
            select(Skill.id).where(Skill.organization_id == ctx.org_id, Skill.id.in_(unique))
        )
    )
    missing = [str(i) for i in unique if i not in found]
    if missing:
        raise ValidationFailed(
            "Unknown skill ids.", [{"field": field, "message": f"unknown skill(s): {missing}"}]
        )
    return unique
