import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.deps import AdminCtx, CurrentCtx, DbDep
from app.core.pagination import Page, Pagination, make_page
from app.models.enums import MembershipRole
from app.models.org import ServiceCategory, Skill
from app.schemas.org import (
    CategoryIn,
    CategoryOut,
    CategoryPatch,
    SkillIn,
    SkillOut,
)
from app.services import catalog as svc

router = APIRouter(tags=["catalog"])


def _cat_out(cat: ServiceCategory, skills: list[Skill]) -> CategoryOut:
    return CategoryOut.model_validate(
        {
            "id": cat.id,
            "name": cat.name,
            "description": cat.description,
            "default_duration_minutes": cat.default_duration_minutes,
            "is_enabled": cat.is_enabled,
            "created_at": cat.created_at,
            "updated_at": cat.updated_at,
            "required_skills": skills,
        },
        from_attributes=True,
    )


@router.get("/skills", response_model=Page[SkillOut])
def list_skills(db: DbDep, ctx: CurrentCtx, params: Pagination) -> dict:
    items, total = svc.list_skills(db, ctx, params)
    return make_page([SkillOut.model_validate(s) for s in items], total, params)


@router.post("/skills", response_model=SkillOut, status_code=201)
def create_skill(body: SkillIn, db: DbDep, ctx: AdminCtx) -> Skill:
    skill = svc.create_skill(db, ctx, body.name)
    db.commit()
    return skill


@router.patch("/skills/{skill_id}", response_model=SkillOut)
def patch_skill(skill_id: uuid.UUID, body: SkillIn, db: DbDep, ctx: AdminCtx) -> Skill:
    skill = svc.rename_skill(db, ctx, skill_id, body.name)
    db.commit()
    return skill


@router.get("/categories", response_model=Page[CategoryOut])
def list_categories(
    db: DbDep,
    ctx: CurrentCtx,
    params: Pagination,
    include_disabled: Annotated[
        bool, Query(description="Staff only; requesters always see enabled categories only.")
    ] = False,
) -> dict:
    only_enabled = ctx.role == MembershipRole.REQUESTER or not include_disabled
    rows, total = svc.list_categories(db, ctx, params, only_enabled)
    return make_page([_cat_out(c, s) for c, s in rows], total, params)


@router.post("/categories", response_model=CategoryOut, status_code=201)
def create_category(body: CategoryIn, db: DbDep, ctx: AdminCtx) -> CategoryOut:
    cat, skills = svc.create_category(db, ctx, body.model_dump())
    db.commit()
    return _cat_out(cat, skills)


@router.patch("/categories/{category_id}", response_model=CategoryOut)
def patch_category(
    category_id: uuid.UUID, body: CategoryPatch, db: DbDep, ctx: AdminCtx
) -> CategoryOut:
    cat, skills = svc.update_category(db, ctx, category_id, body.model_dump(exclude_unset=True))
    db.commit()
    return _cat_out(cat, skills)
