import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import error_body
from app.db.session import get_db

router = APIRouter(prefix="/health", tags=["health"])
logger = logging.getLogger("app.health")


@router.get("/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", response_model=None)
def ready(db: Session = Depends(get_db)) -> dict[str, str] | JSONResponse:  # noqa: B008
    try:
        db.execute(text("SET LOCAL statement_timeout = '2000'"))
        db.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning("readiness check failed: %s", type(exc).__name__)
        return JSONResponse(
            error_body("not_ready", "Service is not ready.", {"database": "unavailable"}),
            status_code=503,
        )
    finally:
        db.rollback()
    return {"status": "ready", "database": "ok"}
