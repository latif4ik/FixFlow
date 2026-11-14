import logging
import re
import time
import uuid

from fastapi import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import request_id_var

logger = logging.getLogger("app.access")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class RequestIdMiddleware:
    """Pure ASGI middleware: sets request-id contextvar, header, and access log."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = None
        for name, value in scope["headers"]:
            if name == b"x-request-id":
                incoming = value.decode("latin-1")
                break
        request_id = incoming if incoming and _REQUEST_ID_RE.match(incoming) else str(uuid.uuid4())
        token = request_id_var.set(request_id)
        scope.setdefault("state", {})["request_id"] = request_id
        start = time.perf_counter()
        status_holder = {"status": 500}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                headers = [(k, v) for k, v in message["headers"] if k.lower() != b"x-request-id"]
                headers.append((b"x-request-id", request_id.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            logger.info(
                "request",
                extra={
                    "method": scope["method"],
                    "path": scope["path"],
                    "status": status_holder["status"],
                    "duration_ms": round((time.perf_counter() - start) * 1000, 2),
                },
            )
            request_id_var.reset(token)


class BodySizeLimitMiddleware:
    """Caps request bodies at ``max_bytes`` with 413.

    A declared Content-Length above the cap is rejected up front; bodies without one (chunked
    transfer) are counted as they stream in and aborted with 413 the moment the cap is crossed.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    def _too_large(self) -> HTTPException:
        return HTTPException(
            413,
            detail={"message": "Request body is too large.", "max_bytes": self.max_bytes},
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        for name, value in scope["headers"]:
            if name == b"content-length":
                try:
                    too_big = int(value) > self.max_bytes
                except ValueError:
                    too_big = False
                if too_big:
                    await self._reject(scope, receive, send)
                    return
                break

        received = 0
        started = False

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise self._too_large()
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except HTTPException as exc:
            if exc.status_code != 413 or started:
                raise
            await self._reject(scope, receive, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        from app.core.errors import error_body

        response = JSONResponse(
            error_body(
                "payload_too_large",
                "Request body is too large.",
                {"max_bytes": self.max_bytes},
                scope.get("state", {}).get("request_id"),
            ),
            status_code=413,
        )
        await response(scope, receive, send)


class CatchAllMiddleware:
    """Turns any unhandled exception into the 500 error envelope.

    Registered INSIDE CORSMiddleware so that even 500 responses carry the CORS headers (the
    framework's own catch-all handler runs outside every user middleware). If the response has
    already started the exception is re-raised (nothing sane can be sent).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except HTTPException:
            raise  # e.g. the body-size abort, handled by the outer middleware
        except Exception as exc:
            if started:
                raise
            from starlette.requests import Request

            from app.core.errors import _unhandled_handler

            response = await _unhandled_handler(Request(scope), exc)
            await response(scope, receive, tracking_send)
