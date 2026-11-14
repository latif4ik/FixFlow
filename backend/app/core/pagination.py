from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Query
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings

_settings = get_settings()


@dataclass(frozen=True)
class PageParams:
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def page_params(
    page: Annotated[int, Query(ge=1, le=1_000_000, description="1-based page number.")] = 1,
    page_size: Annotated[
        int,
        Query(
            ge=1,
            le=_settings.MAX_PAGE_SIZE,
            description=f"Items per page (max {_settings.MAX_PAGE_SIZE}).",
        ),
    ] = _settings.DEFAULT_PAGE_SIZE,
) -> PageParams:
    return PageParams(page=page, page_size=page_size)


Pagination = Annotated[PageParams, Depends(page_params)]


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int


def paginate_rows(
    db: Session, stmt: Select[Any] | Any, params: PageParams
) -> tuple[list[Any], int]:
    """Run ``stmt`` with LIMIT/OFFSET and return (rows, total). ``stmt`` must be ordered."""
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = list(db.execute(stmt.limit(params.page_size).offset(params.offset)).all())
    return rows, total


def make_page(items: list[Any], total: int, params: PageParams) -> dict[str, Any]:
    return {"items": items, "total": total, "page": params.page, "page_size": params.page_size}
