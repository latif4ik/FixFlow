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


def test_payload_too_large_chunked_without_content_length() -> None:
    def chunks():
        for _ in range(10):
            yield b"x" * 50

    r = TestClient(_app()).post(
        "/echo", content=chunks(), headers={"content-type": "application/json"}
    )
    assert r.status_code == 413
    err = r.json()["error"]
    assert err["code"] == "payload_too_large" and err["details"] == {"max_bytes": 100}


def test_chunked_body_under_limit_still_works() -> None:
    def chunks():
        yield b'{"name": "a",'
        yield b' "count": 2}'

    r = TestClient(_app()).post(
        "/echo", content=chunks(), headers={"content-type": "application/json"}
    )
    assert r.status_code == 200 and r.json() == {"name": "a", "count": 2}


def test_chunked_multipart_upload_over_limit_413() -> None:
    from typing import Annotated

    from fastapi import File, UploadFile

    app = _app()

    @app.post("/up")
    def up(file: Annotated[UploadFile, File()]) -> dict:
        return {"n": len(file.file.read())}

    def body():
        yield b'--b\r\nContent-Disposition: form-data; name="file"; filename="a.bin"\r\n'
        yield b"Content-Type: application/octet-stream\r\n\r\n"
        for _ in range(10):
            yield b"y" * 50
        yield b"\r\n--b--\r\n"

    r = TestClient(app).post(
        "/up", content=body(), headers={"content-type": "multipart/form-data; boundary=b"}
    )
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "payload_too_large"


def test_500_from_allowed_origin_has_cors_headers(monkeypatch) -> None:
    from app.main import create_app

    app = create_app()

    @app.get("/api/v1/_boom")
    def boom() -> None:
        raise RuntimeError("kaboom")

    c = TestClient(app, raise_server_exceptions=False)
    r = c.get("/api/v1/_boom", headers={"Origin": "http://localhost:3000"})
    assert r.status_code == 500
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert r.json()["error"]["code"] == "internal_error"
    assert r.json()["error"]["request_id"] == r.headers["x-request-id"]
    bad = c.get("/api/v1/_boom", headers={"Origin": "http://evil.test"})
    assert bad.status_code == 500 and "access-control-allow-origin" not in bad.headers


def test_db_errors_mapped_to_envelope() -> None:
    from sqlalchemy.exc import OperationalError

    class _Orig(Exception):
        def __init__(self, sqlstate: str | None) -> None:
            self.sqlstate = sqlstate

    app = _app()

    @app.get("/serial")
    def serial() -> None:
        raise OperationalError("stmt", {}, _Orig("40001"))

    @app.get("/deadlock")
    def deadlock() -> None:
        from sqlalchemy.exc import DBAPIError

        raise DBAPIError("stmt", {}, _Orig("40P01"))

    @app.get("/down")
    def down() -> None:
        raise OperationalError("stmt", {}, _Orig(None))

    c = TestClient(app, raise_server_exceptions=False)
    for path in ("/serial", "/deadlock"):
        r = c.get(path)
        assert r.status_code == 409 and r.json()["error"]["code"] == "conflict_retry"
    r = c.get("/down")
    assert r.status_code == 503 and r.json()["error"]["code"] == "service_unavailable"
    assert "stmt" not in r.text
