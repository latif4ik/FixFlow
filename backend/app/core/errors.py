import logging
import re
from http import HTTPStatus
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_var

logger = logging.getLogger("app.errors")


def error_body(
    code: str, message: str, details: Any = None, request_id: str | None = None
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "request_id": request_id or request_id_var.get(),
        }
    }


def _rid(request: Request) -> str | None:
    """Request id from the contextvar, falling back to ASGI scope state.

    Needed for the catch-all handler, which Starlette runs outside our middleware
    (after the contextvar has been reset).
    """
    return request_id_var.get() or request.scope.get("state", {}).get("request_id")


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


class NotFound(AppError):
    def __init__(self, message: str = "Resource not found.", details: Any = None) -> None:
        super().__init__(404, "not_found", message, details)


class Forbidden(AppError):
    def __init__(self, message: str = "Forbidden.", details: Any = None) -> None:
        super().__init__(403, "forbidden", message, details)


class Unauthorized(AppError):
    def __init__(self, message: str = "Authentication required.", details: Any = None) -> None:
        super().__init__(401, "unauthorized", message, details)


class Conflict(AppError):
    def __init__(self, message: str = "Conflict.", details: Any = None) -> None:
        super().__init__(409, "conflict", message, details)


class ValidationFailed(AppError):
    def __init__(self, message: str = "Validation failed.", details: Any = None) -> None:
        super().__init__(422, "validation_error", message, details)


class TooManyRequests(AppError):
    def __init__(self, message: str = "Too many requests.", details: Any = None) -> None:
        super().__init__(429, "too_many_requests", message, details)


class BadRequest(AppError):
    def __init__(self, message: str = "Bad request.", details: Any = None) -> None:
        super().__init__(400, "bad_request", message, details)


_STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    422: "validation_error",
    429: "too_many_requests",
}


def _code_for_status(status: int) -> str:
    if status in _STATUS_CODES:
        return _STATUS_CODES[status]
    try:
        return HTTPStatus(status).phrase.lower().replace(" ", "_").replace("-", "_")
    except ValueError:
        return "error"


async def _app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    exc = cast(AppError, exc)
    return JSONResponse(
        error_body(exc.code, exc.message, exc.details, _rid(request)), status_code=exc.status_code
    )


async def _http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    exc = cast(StarletteHTTPException, exc)
    detail = exc.detail
    if isinstance(detail, dict) and isinstance(detail.get("message"), str):
        message = detail["message"]  # {"message": ..., **details}
        details = {k: v for k, v in detail.items() if k != "message"} or None
    else:
        message = detail if isinstance(detail, str) else HTTPStatus(exc.status_code).phrase
        details = None if isinstance(detail, str) else detail
    return JSONResponse(
        error_body(_code_for_status(exc.status_code), message, details, _rid(request)),
        status_code=exc.status_code,
        headers=getattr(exc, "headers", None),
    )


async def _validation_handler(request: Request, exc: Exception) -> JSONResponse:
    exc = cast(RequestValidationError, exc)
    details = [
        {
            "field": ".".join(str(p) for p in err["loc"] if p != "body"),
            "message": err["msg"],
        }
        for err in exc.errors()
    ]
    return JSONResponse(
        error_body("validation_error", "Request validation failed.", details, _rid(request)),
        status_code=422,
    )


async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    rid = _rid(request)
    token = request_id_var.set(rid)
    try:
        logger.error("unhandled exception", exc_info=(type(exc), exc, exc.__traceback__))
    finally:
        request_id_var.reset(token)
    headers = {"X-Request-ID": rid} if rid else None
    return JSONResponse(
        error_body("internal_error", "An internal error occurred.", None, rid),
        status_code=500,
        headers=headers,
    )


# PostgreSQL SQLSTATE classes we translate.
_UNIQUE_VIOLATION = "23505"
_FK_VIOLATION = "23503"
_CHECK_VIOLATION = "23514"
_NOT_NULL_VIOLATION = "23502"
_KEY_RE = re.compile(r"Key \((?P<cols>[^)]*)\)")


def _unique_field_hint(orig: Any) -> list[str]:
    detail = getattr(getattr(orig, "diag", None), "message_detail", None) or ""
    m = _KEY_RE.search(detail)
    if not m:
        return []
    cols = [c.strip() for c in m.group("cols").split(",")]
    fields = [c for c in cols if c != "organization_id"]
    # Expression indexes show up as e.g. "lower(name::text)".
    return [re.sub(r"^lower\((\w+).*\)$", r"\1", c) for c in fields]


async def _integrity_handler(request: Request, exc: Exception) -> JSONResponse:
    exc = cast(IntegrityError, exc)
    orig = exc.orig
    sqlstate = getattr(orig, "sqlstate", None)
    constraint = getattr(getattr(orig, "diag", None), "constraint_name", None)
    rid = _rid(request)
    if sqlstate == _UNIQUE_VIOLATION:
        fields = _unique_field_hint(orig)
        return JSONResponse(
            error_body(
                "conflict",
                "A record with the same unique value already exists.",
                {"fields": fields, "constraint": constraint},
                rid,
            ),
            status_code=409,
        )
    if sqlstate in (_FK_VIOLATION, _CHECK_VIOLATION, _NOT_NULL_VIOLATION):
        return JSONResponse(
            error_body(
                "validation_error",
                "The request violates a data integrity rule.",
                {"constraint": constraint},
                rid,
            ),
            status_code=422,
        )
    return await _unhandled_handler(request, exc)


_RETRYABLE_STATES = frozenset({"40001", "40P01"})  # serialization_failure, deadlock_detected


async def _dbapi_handler(request: Request, exc: Exception) -> JSONResponse:
    """Serialization failures/deadlocks -> 409 conflict_retry; DB unreachable -> 503."""
    rid = _rid(request)
    sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
    if sqlstate in _RETRYABLE_STATES:
        return JSONResponse(
            error_body(
                "conflict_retry",
                "The change conflicted with a concurrent update. Please retry.",
                {"retryable": True},
                rid,
            ),
            status_code=409,
        )
    if isinstance(exc, OperationalError | PoolTimeoutError):
        logger.error("database unavailable", exc_info=(type(exc), exc, exc.__traceback__))
        return JSONResponse(
            error_body(
                "service_unavailable",
                "The service is temporarily unavailable. Please try again shortly.",
                None,
                rid,
            ),
            status_code=503,
            headers={"Retry-After": "2"},
        )
    return await _unhandled_handler(request, exc)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(DBAPIError, _dbapi_handler)
    app.add_exception_handler(PoolTimeoutError, _dbapi_handler)
    app.add_exception_handler(IntegrityError, _integrity_handler)
    app.add_exception_handler(Exception, _unhandled_handler)
