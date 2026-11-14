"""Phase 3c carry-over fixes: upload replay ordering, note row lock."""

import threading
import time

import pytest
from sqlalchemy import text

from app.models.enums import RequestStatus
from tests.factories import h, login
from tests.req_helpers import image_bytes, make_world, new_id, seed_request, upload

API = "/api/v1"
S = RequestStatus


@pytest.fixture
def w(db):
    return make_world(db)


@pytest.fixture
def hd(client, w):
    return {
        k: h(login(client, getattr(w, k)[0]), w.org)
        for k in ("admin", "disp", "tech", "req1", "req2")
    }


def test_upload_replay_after_status_change_returns_original(client, db, w, hd):
    req = seed_request(db, w)  # SUBMITTED: intake images allowed
    key = new_id()
    data = image_bytes("PNG")
    a = upload(client, hd["req1"], req.id, data, client_command_id=key, client_index=0)
    assert a.status_code == 201
    db.execute(text("UPDATE service_requests SET status='TRIAGED' WHERE id=:i"), {"i": req.id})
    db.commit()
    b = upload(client, hd["req1"], req.id, data, client_command_id=key, client_index=0)
    assert b.status_code == 200, b.text
    assert b.json()["id"] == a.json()["id"]
    # a NEW upload (different key) is still refused by the status rule
    c = upload(client, hd["req1"], req.id, data, client_command_id=new_id(), client_index=0)
    assert c.status_code == 409


def test_upload_replay_requires_visibility_first(client, db, w, hd):
    req = seed_request(db, w)
    key = new_id()
    upload(client, hd["req1"], req.id, image_bytes("PNG"), client_command_id=key, client_index=0)
    r = upload(client, hd["req2"], req.id, image_bytes("PNG"), client_command_id=key)
    assert r.status_code == 404


def test_new_upload_without_permission_still_403_with_command_id(client, db, w, hd):
    req = seed_request(db, w, status=S.IN_PROGRESS)
    r = upload(
        client,
        hd["req1"],
        req.id,
        image_bytes("PNG"),
        purpose="COMPLETION",
        client_command_id=new_id(),
    )
    assert r.status_code == 403


def test_note_creation_waits_for_request_row_lock(client, db, db_engine, w, hd):
    req = seed_request(db, w, status=S.TRIAGED)
    from sqlalchemy.orm import Session

    holder = Session(db_engine)
    holder.execute(text("SELECT id FROM service_requests WHERE id=:i FOR UPDATE"), {"i": req.id})
    result: dict = {}

    def post_note() -> None:
        result["r"] = client.post(
            f"{API}/requests/{req.id}/notes",
            json={"body": "hello there", "visibility": "PUBLIC"},
            headers=hd["req1"],
        )
        result["t"] = time.monotonic()

    t0 = time.monotonic()
    th = threading.Thread(target=post_note)
    th.start()
    time.sleep(0.6)
    assert "r" not in result, "note must block on the request row lock"
    holder.execute(text("UPDATE service_requests SET status='CANCELED' WHERE id=:i"), {"i": req.id})
    holder.commit()
    holder.close()
    th.join(10)
    assert result["r"].status_code == 409  # sees the cancel: note refused, no race
    assert result["t"] - t0 >= 0.5
