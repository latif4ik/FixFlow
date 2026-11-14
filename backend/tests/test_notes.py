import threading

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.models import WorkNote
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
    return {k: h(login(client, getattr(w, k)[0]), w.org) for k in ("admin", "disp", "req1", "req2")}


def post(client, hd, who, req, **body):
    body.setdefault("body", "Visible text")
    return client.post(f"{API}/requests/{req.id}/notes", json=body, headers=hd[who])


def test_requester_cannot_post_internal(client, db, w, hd):
    req = seed_request(db, w)
    r = post(client, hd, "req1", req, visibility="INTERNAL")
    assert r.status_code == 403
    assert db.scalars(select(WorkNote)).all() == []


def test_requester_does_not_see_internal(client, db, w, hd):
    req = seed_request(db, w)
    assert post(client, hd, "disp", req, body="secret", visibility="INTERNAL").status_code == 201
    assert post(client, hd, "req1", req, body="hello").status_code == 201
    mine = client.get(f"{API}/requests/{req.id}/notes", headers=hd["req1"]).json()
    assert [n["body"] for n in mine["items"]] == ["hello"] and mine["total"] == 1
    staff = client.get(f"{API}/requests/{req.id}/notes", headers=hd["disp"]).json()
    assert {n["body"] for n in staff["items"]} == {"hello", "secret"}
    detail = client.get(f"{API}/requests/{req.id}", headers=hd["req1"]).json()
    assert [n["body"] for n in detail["notes"]] == ["hello"]
    tl = detail["timeline"]
    assert [e["data"]["visibility"] for e in tl if e["type"] == "NOTE_ADDED"] == ["PUBLIC"]
    n = post(client, hd, "disp", req).json()
    assert {"id", "author", "created_at", "visibility", "attachments", "kind"} <= set(n)
    assert n["author"]["membership_id"] == str(w.disp[1].id)


def test_other_requester_and_technician_cannot_post(client, db, w, hd):
    req = seed_request(db, w)
    assert post(client, hd, "req2", req).status_code == 404


def test_idempotent_replay_and_conflict(client, db, w, hd):
    req = seed_request(db, w)
    key = new_id()
    first = post(client, hd, "req1", req, client_command_id=key)
    assert first.status_code == 201
    again = post(client, hd, "req1", req, client_command_id=key)
    assert again.status_code == 200 and again.json()["id"] == first.json()["id"]
    assert again.json()["created_at"] == first.json()["created_at"]
    diff = post(client, hd, "req1", req, client_command_id=key, body="Different text")
    assert diff.status_code == 409 and diff.json()["error"]["code"] == "idempotency_key_reused"
    other_req = seed_request(db, w)
    assert post(client, hd, "req1", other_req, client_command_id=key).status_code == 409
    assert len(db.scalars(select(WorkNote)).all()) == 1
    # a different member of the org cannot replay someone else's key
    assert post(client, hd, "disp", req, client_command_id=key).status_code == 409


def test_concurrent_same_key_creates_one_note(client, db, w, hd):
    for _ in range(3):
        req = seed_request(db, w)
        key = new_id()
        barrier = threading.Barrier(2)
        out = []

        def run(req=req, key=key, barrier=barrier, out=out):
            with TestClient(client.app) as c:
                barrier.wait()
                out.append(
                    c.post(
                        f"{API}/requests/{req.id}/notes",
                        json={"body": "same", "client_command_id": key},
                        headers=hd["req1"],
                    )
                )

        ts = [threading.Thread(target=run) for _ in range(2)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        assert sorted(r.status_code for r in out) == [200, 201], [r.text for r in out]
        assert len({r.json()["id"] for r in out}) == 1
        n = db.scalars(select(WorkNote).where(WorkNote.request_id == req.id)).all()
        assert len(n) == 1


@pytest.mark.parametrize("status", [S.CLOSED, S.CANCELED])
def test_no_notes_on_terminal(client, db, w, hd, status):
    req = seed_request(db, w, status=status)
    assert post(client, hd, "disp", req).status_code == 409
    assert post(client, hd, "req1", req).status_code == 409


def test_note_validation(client, db, w, hd):
    req = seed_request(db, w)
    assert post(client, hd, "req1", req, body="   ").status_code == 422
    assert post(client, hd, "req1", req, body="x" * 2001).status_code == 422
    assert post(client, hd, "req1", req, kind="CANCEL").status_code == 422
    assert post(client, hd, "req1", req, kind="TRIAGE").status_code == 422
    assert post(client, hd, "disp", req, kind="TRIAGE", visibility="INTERNAL").status_code == 201


def test_note_attachments(client, db, w, hd):
    req = seed_request(db, w)
    f = upload(client, hd["req1"], req.id, image_bytes(), purpose="NOTE")
    assert f.status_code == 201, f.text
    fid = f.json()["id"]
    assert post(client, hd, "req2", req, attachment_ids=[fid]).status_code == 404
    # staff cannot claim the requester's file
    assert post(client, hd, "disp", req, attachment_ids=[fid]).status_code == 422
    assert post(client, hd, "req1", req, attachment_ids=[new_id()]).status_code == 422
    ok = post(client, hd, "req1", req, attachment_ids=[fid])
    assert ok.status_code == 201 and [a["id"] for a in ok.json()["attachments"]] == [fid]
    # already linked -> cannot be linked to a second note
    assert post(client, hd, "req1", req, attachment_ids=[fid]).status_code == 422


def test_notes_are_immutable_in_db(client, db, w, hd):
    req = seed_request(db, w)
    nid = post(client, hd, "req1", req).json()["id"]
    for sql in (
        "UPDATE work_notes SET body = 'x' WHERE id = :i",
        "DELETE FROM work_notes WHERE id = :i",
    ):
        with pytest.raises(DBAPIError, match="append-only"):
            db.execute(text(sql), {"i": nid})
        db.rollback()
    # events too
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("DELETE FROM request_events"))
    db.rollback()
    assert [
        r for r in client.app.routes if getattr(r, "path", "").endswith("/notes/{note_id}")
    ] == []
