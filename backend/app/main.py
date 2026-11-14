from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import BodySizeLimitMiddleware, RequestIdMiddleware

VERSION = "0.1.0"


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)

    app = FastAPI(
        title="FixFlow API",
        version=VERSION,
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url=None,
    )
    register_error_handlers(app)
    app.include_router(api_router)

    # Middleware order: the last added is outermost.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Org-Id",
            "X-Request-ID",
            "Idempotency-Key",
        ],
        expose_headers=["X-Request-ID"],
    )
    # Pure-JSON bodies will get a stricter limit later; this is the global ceiling.
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.MAX_UPLOAD_BYTES * 4)
    app.add_middleware(RequestIdMiddleware)
    return app


app = create_app()
