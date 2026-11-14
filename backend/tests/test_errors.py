from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errors import Conflict, register_error_handlers
from app.core.middleware import BodySizeLimitMiddleware, RequestIdMiddleware


class Payload(BaseModel):
    name: str
    count: int


def _app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.post("/echo")
    def echo(p: Payload) -> Payload:
        return p

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("super secret internal detail")

    @app.get("/conflict")
    def conflict() -> None:
        raise Conflict("already exists", {"id": 1})

    app.add_middleware(BodySizeLimitMiddleware, max_bytes=100)
    app.add_middleware(RequestIdMiddleware)
    return app


def test_unknown_route_404_envelope() -> None:
    from app.main import create_app

    with TestClient(create_app()) as c:
        r = c.get("/api/v1/nope")
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["code"] == "not_found"
    assert err["request_id"] == r.headers["x-request-id"]
    assert set(err) == {"code", "message", "details", "request_id"}


def test_validation_error_422_with_field_details() -> None:
    c = TestClient(_app())
    r = c.post("/echo", json={"name": "x", "count": "abc"})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation_error"
    assert err["details"][0]["field"] == "count"
    assert "message" in err["details"][0]
    assert err["request_id"]


def test_app_error_envelope() -> None:
    r = TestClient(_app()).get("/conflict")
    assert r.status_code == 409
    err = r.json()["error"]
    assert (err["code"], err["message"], err["details"]) == (
        "conflict",
        "already exists",
        {"id": 1},
    )


def test_unhandled_exception_500_does_not_leak() -> None:
    c = TestClient(_app(), raise_server_exceptions=False)
    r = c.get("/boom")
    assert r.status_code == 500
    assert "super secret" not in r.text
    err = r.json()["error"]
    assert err["code"] == "internal_error"
    assert err["request_id"] == r.headers["x-request-id"]


def test_method_not_allowed_envelope() -> None:
    r = TestClient(_app()).get("/echo")
    assert r.status_code == 405
    assert r.json()["error"]["code"] == "method_not_allowed"


def test_payload_too_large() -> None:
    r = TestClient(_app()).post("/echo", content=b"x" * 500, headers={"content-type": "text/plain"})
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "payload_too_large"
