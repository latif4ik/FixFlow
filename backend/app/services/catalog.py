"""Skills and service categories."""

import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.audit import record_audit
from app.core.pagination import PageParams, paginate_rows
from app.core.tenancy import Ctx, get_or_404
from app.models.org import CategoryRequiredSkill, ServiceCategory, Skill
from app.services.util import validate_skill_ids


# ---- skills ----
def list_skills(db: Session, ctx: Ctx, params: PageParams) -> tuple[list[Skill], int]:
    stmt = select(Skill).where(Skill.organization_id == ctx.org_id).order_by(Skill.name, Skill.id)
    rows, total = paginate_rows(db, stmt, params)
    return [r[0] for r in rows], total


def create_skill(db: Session, ctx: Ctx, name: str) -> Skill:
    skill = Skill(organization_id=ctx.org_id, name=name)
    db.add(skill)
    db.flush()
    record_audit(db, ctx, "skill.created", "skill", skill.id, None, {"name": name})
    return skill


def rename_skill(db: Session, ctx: Ctx, skill_id: uuid.UUID, name: str) -> Skill:
    skill = get_or_404(db, Skill, skill_id, ctx, "Skill")
    before = {"name": skill.name}
    skill.name = name
    db.flush()
    if before["name"] != name:
        record_audit(db, ctx, "skill.updated", "skill", skill.id, before, {"name": name})
    return skill


# ---- categories ----
def _cat_snapshot(c: ServiceCategory, skill_ids: list[uuid.UUID]) -> dict[str, Any]:
    return {
        "name": c.name,
        "description": c.description,
        "default_duration_minutes": c.default_duration_minutes,
        "is_enabled": c.is_enabled,
        "required_skill_ids": sorted(str(i) for i in skill_ids),
    }


def category_skills(
    db: Session, ctx: Ctx, category_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[Skill]]:
    out: dict[uuid.UUID, list[Skill]] = defaultdict(list)
    if not category_ids:
        return out
    rows = db.execute(
        select(CategoryRequiredSkill.category_id, Skill)
        .join(Skill, Skill.id == CategoryRequiredSkill.skill_id)
        .where(
            CategoryRequiredSkill.organization_id == ctx.org_id,
            CategoryRequiredSkill.category_id.in_(category_ids),
        )
        .order_by(Skill.name)
    ).all()
    for cid, skill in rows:
        out[cid].append(skill)
    return out


def list_categories(
    db: Session, ctx: Ctx, params: PageParams, only_enabled: bool
) -> tuple[list[tuple[ServiceCategory, list[Skill]]], int]:
    stmt = select(ServiceCategory).where(ServiceCategory.organization_id == ctx.org_id)
    if only_enabled:
        stmt = stmt.where(ServiceCategory.is_enabled.is_(True))
    stmt = stmt.order_by(ServiceCategory.name, ServiceCategory.id)
    rows, total = paginate_rows(db, stmt, params)
    cats = [r[0] for r in rows]
    skills = category_skills(db, ctx, [c.id for c in cats])
    return [(c, skills.get(c.id, [])) for c in cats], total


def _set_required_skills(
    db: Session, ctx: Ctx, category_id: uuid.UUID, ids: list[uuid.UUID]
) -> None:
    db.execute(
        delete(CategoryRequiredSkill).where(
            CategoryRequiredSkill.organization_id == ctx.org_id,
            CategoryRequiredSkill.category_id == category_id,
        )
    )
    for sid in ids:
        db.add(
            CategoryRequiredSkill(organization_id=ctx.org_id, category_id=category_id, skill_id=sid)
        )
    db.flush()


def get_category(
    db: Session, ctx: Ctx, category_id: uuid.UUID
) -> tuple[ServiceCategory, list[Skill]]:
    cat = get_or_404(db, ServiceCategory, category_id, ctx, "Category")
    return cat, category_skills(db, ctx, [cat.id]).get(cat.id, [])


def create_category(
    db: Session, ctx: Ctx, data: dict[str, Any]
) -> tuple[ServiceCategory, list[Skill]]:
    skill_ids = validate_skill_ids(
        db, ctx, data.pop("required_skill_ids", []), "required_skill_ids"
    )
    cat = ServiceCategory(organization_id=ctx.org_id, **data)
    db.add(cat)
    db.flush()
    _set_required_skills(db, ctx, cat.id, skill_ids)
    record_audit(
        db, ctx, "category.created", "category", cat.id, None, _cat_snapshot(cat, skill_ids)
    )
    return get_category(db, ctx, cat.id)


def update_category(
    db: Session, ctx: Ctx, category_id: uuid.UUID, data: dict[str, Any]
) -> tuple[ServiceCategory, list[Skill]]:
    cat, current = get_category(db, ctx, category_id)
    current_ids = [s.id for s in current]
    before = _cat_snapshot(cat, current_ids)
    new_ids = current_ids
    if "required_skill_ids" in data:
        raw = data.pop("required_skill_ids")
        if raw is not None:
            new_ids = validate_skill_ids(db, ctx, raw, "required_skill_ids")
            _set_required_skills(db, ctx, cat.id, new_ids)
    for k, v in data.items():
        if k == "description" or v is not None:
            setattr(cat, k, v)
    db.flush()
    after = _cat_snapshot(cat, new_ids)
    if before != after:
        action = "category.updated"
        if before["is_enabled"] != after["is_enabled"]:
            action = "category.enabled" if after["is_enabled"] else "category.disabled"
        record_audit(db, ctx, action, "category", cat.id, before, after)
    return get_category(db, ctx, cat.id)
