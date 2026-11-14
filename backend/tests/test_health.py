import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import build_engine, set_engine
from app.main import create_app

UNREACHABLE = "postgresql+psycopg://x:x@127.0.0.1:1/x_test"


def test_live_does_not_touch_db() -> None:
    # Engine points at an unreachable DB: live must still succeed.
    set_engine(build_engine(UNREACHABLE))
    try:
        with TestClient(create_app()) as c:
            r = c.get("/api/v1/health/live")
    finally:
        set_engine(None)
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_ready_ok(client: TestClient) -> None:
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ready", "database": "ok"}


def test_ready_503_when_db_unreachable() -> None:
    set_engine(build_engine(UNREACHABLE))
    try:
        with TestClient(create_app()) as c:
            r = c.get("/api/v1/health/ready", headers={"X-Request-ID": "abc-123"})
    finally:
        set_engine(None)
    assert r.status_code == 503
    err = r.json()["error"]
    assert err["code"] == "not_ready"
    assert err["details"] == {"database": "unavailable"}
    assert err["request_id"] == "abc-123"


def test_request_id_echoed_when_valid() -> None:
    with TestClient(create_app()) as c:
        r = c.get("/api/v1/health/live", headers={"X-Request-ID": "my-req_ID-1"})
    assert r.headers["x-request-id"] == "my-req_ID-1"


@pytest.mark.parametrize("bad", ["has space", "x" * 65, "semi;colon"])
def test_request_id_replaced_when_invalid(bad: str) -> None:
    with TestClient(create_app()) as c:
        r = c.get("/api/v1/health/live", headers={"X-Request-ID": bad})
    rid = r.headers["x-request-id"]
    assert rid != bad
    assert re.fullmatch(r"[0-9a-f-]{36}", rid)


def test_request_id_generated_when_missing() -> None:
    with TestClient(create_app()) as c:
        r = c.get("/api/v1/health/live")
    assert re.fullmatch(r"[0-9a-f-]{36}", r.headers["x-request-id"])


def test_db_engine_query(db_engine) -> None:
    with db_engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar() == 1
