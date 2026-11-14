import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select

from app.core.config import get_settings
from app.main import create_app
from app.models import EvidenceFile, RequestEvent
from app.models.enums import RequestStatus
from app.services import files as files_svc
from app.services import request_access as access
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


def root() -> Path:
    return Path(get_settings().UPLOAD_DIR)


def stored_files() -> list[Path]:
    return [p for p in root().rglob("*") if p.is_file()]


def count_rows(db) -> int:
    return db.scalar(select(func.count()).select_from(EvidenceFile)) or 0


@pytest.mark.parametrize(
    ("fmt", "mime"), [("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")]
)
def test_valid_images_accepted_and_served(client, db, w, hd, fmt, mime):
    req = seed_request(db, w)
    r = upload(client, hd["req1"], req.id, image_bytes(fmt, (30, 20)), name="my photo.x")
    assert r.status_code == 201, r.text
    body = r.json()
    assert (body["mime_type"], body["width"], body["height"]) == (mime, 30, 20)
    assert body["purpose"] == "INTAKE" and body["original_filename"] == "my photo.x"
    row = db.get(EvidenceFile, body["id"])
    assert row is not None and row.storage_key.startswith(f"{w.org.id}/")
    on_disk = root() / row.storage_key
    assert on_disk.is_file() and "photo" not in on_disk.name
    d = client.get(f"{API}/files/{body['id']}", headers=hd["req1"])
    assert d.status_code == 200 and d.headers["content-type"] == mime
    assert d.headers["x-content-type-options"] == "nosniff"
    assert d.headers["cache-control"] == "private, no-store"
    assert d.headers["content-disposition"].startswith("inline; filename=")
    assert d.content == on_disk.read_bytes()
    assert client.get(f"{API}/files/{body['id']}", headers=hd["disp"]).status_code == 200


def test_filename_is_sanitized_and_path_never_used(client, db, w, hd):
    req = seed_request(db, w)
    r = upload(client, hd["req1"], req.id, image_bytes(), name='../../etc/pa"ss\r\nwd.png')
    assert r.status_code == 201
    name = r.json()["original_filename"]
    assert "/" not in name and '"' not in name and "\n" not in name and ".." not in name[:1]
    row = db.get(EvidenceFile, r.json()["id"])
    assert row is not None and ".." not in row.storage_key


def test_fake_extension_rejected(client, db, w, hd):
    req = seed_request(db, w)
    r = upload(client, hd["req1"], req.id, b"just some text, not an image", name="evil.jpg")
    assert r.status_code == 422
    assert r.json()["error"]["details"][0]["field"] == "file"
    gif = io.BytesIO()
    Image.new("RGB", (5, 5)).save(gif, format="GIF")
    assert upload(client, hd["req1"], req.id, gif.getvalue(), name="a.png").status_code == 422
    # PNG header followed by garbage
    assert (
        upload(client, hd["req1"], req.id, image_bytes()[:60] + b"junk", name="a.png").status_code
        == 422
    )
    assert upload(client, hd["req1"], req.id, b"", name="a.png").status_code == 422
    assert count_rows(db) == 0 and stored_files() == []


def test_oversized_rejected_without_leftovers(client, db, w, hd):
    req = seed_request(db, w)
    big = b"\x89PNG" + b"0" * (10 * 1024 * 1024)
    r = upload(client, hd["req1"], req.id, big)
    assert r.status_code == 413 and r.json()["error"]["code"] == "payload_too_large"
    assert count_rows(db) == 0 and stored_files() == []


def test_exactly_ten_mib_boundary(client, db, w, hd, monkeypatch):
    monkeypatch.setattr(get_settings(), "MAX_UPLOAD_BYTES", 1000)
    req = seed_request(db, w)
    assert upload(client, hd["req1"], req.id, b"x" * 1001).status_code == 413
    # <= limit proceeds to content validation (422 for non-image), not 413
    assert upload(client, hd["req1"], req.id, b"x" * 1000).status_code == 422


def test_dimension_bounds(client, db, w, hd):
    req = seed_request(db, w)
    assert upload(client, hd["req1"], req.id, image_bytes("PNG", (8001, 1))).status_code == 422
    assert upload(client, hd["req1"], req.id, image_bytes("PNG", (1, 8001))).status_code == 422
    assert upload(client, hd["req1"], req.id, image_bytes("PNG", (8000, 1))).status_code == 201
    # decompression bomb: tiny file declaring ~400 megapixels
    buf = io.BytesIO()
    Image.new("1", (20000, 20000)).save(buf, format="PNG")
    assert len(buf.getvalue()) < 1_000_000
    r = upload(client, hd["req1"], req.id, buf.getvalue())
    assert r.status_code == 422
    assert count_rows(db) == 1


def test_fourth_intake_rejected_and_state_rules(client, db, w, hd):
    req = seed_request(db, w)
    for _ in range(3):
        assert upload(client, hd["req1"], req.id, image_bytes()).status_code == 201
    r = upload(client, hd["req1"], req.id, image_bytes())
    assert r.status_code == 409
    assert count_rows(db) == 3 and len(stored_files()) == 3
    triaged = seed_request(db, w, status=S.TRIAGED)
    assert upload(client, hd["req1"], triaged.id, image_bytes()).status_code == 409
    assert upload(client, hd["req2"], req.id, image_bytes()).status_code == 404
    assert upload(client, hd["tech"], req.id, image_bytes()).status_code == 404


def test_purpose_rules(client, db, w, hd, monkeypatch):
    prog = seed_request(db, w, status=S.IN_PROGRESS)
    # staff may not upload completion evidence
    assert (
        upload(client, hd["disp"], prog.id, image_bytes(), purpose="COMPLETION").status_code == 403
    )
    assert (
        upload(client, hd["req1"], prog.id, image_bytes(), purpose="COMPLETION").status_code == 403
    )
    # assigned technician (Phase 2b hook simulated) may, only while IN_PROGRESS
    monkeypatch.setattr(
        access,
        "get_active_assignment",
        lambda d, r: SimpleNamespace(technician_membership_id=w.tech[1].id),
    )
    from sqlalchemy import true

    monkeypatch.setattr(access, "technician_visibility_filter", lambda ctx: true())
    ok = upload(client, hd["tech"], prog.id, image_bytes(), purpose="COMPLETION")
    assert ok.status_code == 201 and ok.json()["purpose"] == "COMPLETION"
    other = seed_request(db, w, status=S.ACCEPTED)
    assert (
        upload(client, hd["tech"], other.id, image_bytes(), purpose="COMPLETION").status_code == 409
    )
    # requester can see completion evidence
    assert client.get(f"{API}/files/{ok.json()['id']}", headers=hd["req1"]).status_code == 200
    # NOTE uploads follow note rules
    assert upload(client, hd["req1"], prog.id, image_bytes(), purpose="NOTE").status_code == 201
    closed = seed_request(db, w, status=S.CLOSED)
    assert upload(client, hd["req1"], closed.id, image_bytes(), purpose="NOTE").status_code == 409


def test_download_authorization(client, db, w, hd):
    req = seed_request(db, w)
    fid = upload(client, hd["req1"], req.id, image_bytes()).json()["id"]
    assert client.get(f"{API}/files/{fid}").status_code == 401
    other = make_world(db, "Org B")
    ho = h(login(client, other.admin[0]), other.org)
    assert client.get(f"{API}/files/{fid}", headers=ho).status_code == 404
    assert client.get(f"{API}/files/{fid}", headers=hd["req2"]).status_code == 404
    assert client.get(f"{API}/files/{new_id()}", headers=hd["req1"]).status_code == 404


def test_requester_cannot_download_internal_note_attachment(client, db, w, hd):
    req = seed_request(db, w)
    f = upload(client, hd["disp"], req.id, image_bytes(), purpose="NOTE")
    assert f.status_code == 201
    fid = f.json()["id"]
    # unlinked staff file: hidden from requester
    assert client.get(f"{API}/files/{fid}", headers=hd["req1"]).status_code == 404
    n = client.post(
        f"{API}/requests/{req.id}/notes",
        json={"body": "internal pic", "visibility": "INTERNAL", "attachment_ids": [fid]},
        headers=hd["disp"],
    )
    assert n.status_code == 201
    assert client.get(f"{API}/files/{fid}", headers=hd["req1"]).status_code == 404
    assert client.get(f"{API}/files/{fid}", headers=hd["disp"]).status_code == 200
    detail = client.get(f"{API}/requests/{req.id}", headers=hd["req1"]).json()
    assert detail["files"] == []
    assert "FILE_UPLOADED" not in [e["type"] for e in detail["timeline"]]
    # a public note's attachment is downloadable
    f2 = upload(client, hd["disp"], req.id, image_bytes(), purpose="NOTE").json()["id"]
    client.post(
        f"{API}/requests/{req.id}/notes",
        json={"body": "public pic", "attachment_ids": [f2]},
        headers=hd["disp"],
    )
    assert client.get(f"{API}/files/{f2}", headers=hd["req1"]).status_code == 200


def test_missing_file_on_disk_is_404(client, db, w, hd):
    req = seed_request(db, w)
    fid = upload(client, hd["req1"], req.id, image_bytes()).json()["id"]
    row = db.get(EvidenceFile, fid)
    assert row is not None
    (root() / row.storage_key).unlink()
    assert client.get(f"{API}/files/{fid}", headers=hd["req1"]).status_code == 404


def test_idempotent_upload_replay(client, db, w, hd):
    req = seed_request(db, w)
    key = new_id()
    data = image_bytes()
    a = upload(client, hd["req1"], req.id, data, client_command_id=key, client_index=0)
    b = upload(client, hd["req1"], req.id, data, client_command_id=key, client_index=0)
    assert (a.status_code, b.status_code) == (201, 200) and a.json()["id"] == b.json()["id"]
    c = upload(
        client, hd["req1"], req.id, image_bytes("JPEG"), client_command_id=key, client_index=0
    )
    assert c.status_code == 409 and c.json()["error"]["code"] == "idempotency_key_reused"
    d = upload(
        client, hd["req1"], req.id, image_bytes("JPEG"), client_command_id=key, client_index=1
    )
    assert d.status_code == 201
    assert count_rows(db) == 2 and len(stored_files()) == 2


def test_db_failure_leaves_no_file_or_row(client, db, w, hd, monkeypatch):
    req = seed_request(db, w)

    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(files_svc, "record_audit", boom)
    with pytest.raises(RuntimeError):
        upload(client, hd["req1"], req.id, image_bytes())
    assert count_rows(db) == 0 and stored_files() == []
    assert db.scalar(select(func.count()).select_from(RequestEvent)) == 0


def test_file_survives_app_recreation(client, db, w, hd):
    req = seed_request(db, w)
    fid = upload(client, hd["req1"], req.id, image_bytes()).json()["id"]
    with TestClient(create_app()) as fresh:
        r = fresh.get(f"{API}/files/{fid}", headers=hd["req1"])
        assert r.status_code == 200 and r.headers["content-type"] == "image/png"


def test_detail_lists_files_with_metadata(client, db, w, hd):
    req = seed_request(db, w)
    fid = upload(client, hd["req1"], req.id, image_bytes()).json()["id"]
    detail = client.get(f"{API}/requests/{req.id}", headers=hd["disp"]).json()
    assert [f["id"] for f in detail["files"]] == [fid]
    assert detail["files"][0]["url"] == f"/api/v1/files/{fid}"
    assert "FILE_UPLOADED" in [e["type"] for e in detail["timeline"]]
