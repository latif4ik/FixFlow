import pytest
from sqlalchemy import text

from app.models import Notification
from app.models.enums import RequestStatus
from tests.factories import h, login
from tests.req_helpers import make_world, seed_request

API = "/api/v1"
S = RequestStatus


@pytest.fixture
def fw(client, db):
    w = make_world(db)
    hd = {
        k: h(login(client, getattr(w, k)[0]), w.org)
        for k in ("admin", "disp", "tech", "req1", "req2")
    }
    return w, hd


def _post(client, hd, who, req, **body):
    body.setdefault("rating", 5)
    return client.post(f"{API}/requests/{req.id}/feedback", json=body, headers=hd[who])


def test_owner_submits_once_and_sees_it_in_detail(client, db, fw):
    w, hd = fw
    req = seed_request(db, w, status=S.COMPLETED)
    r = _post(client, hd, "req1", req, rating=4, comment="  Quick and tidy  ")
    assert r.status_code == 201, r.text
    assert r.json()["rating"] == 4 and r.json()["comment"] == "Quick and tidy"
    again = _post(client, hd, "req1", req, rating=1)
    assert again.status_code == 409
    for who in ("req1", "disp", "admin"):
        d = client.get(f"{API}/requests/{req.id}", headers=hd[who]).json()
        assert d["feedback"]["rating"] == 4
        assert any(t["type"] == "FEEDBACK_SUBMITTED" for t in d["timeline"])


def test_closed_request_accepts_feedback(client, db, fw):
    w, hd = fw
    req = seed_request(db, w, status=S.CLOSED)
    assert _post(client, hd, "req1", req).status_code == 201


@pytest.mark.parametrize(
    "status", [S.SUBMITTED, S.TRIAGED, S.SCHEDULED, S.IN_PROGRESS, S.REOPENED, S.CANCELED]
)
def test_only_completed_or_closed(client, db, fw, status):
    w, hd = fw
    req = seed_request(db, w, status=status)
    assert _post(client, hd, "req1", req).status_code == 409


def test_non_owner_roles_cannot_leave_feedback(client, db, fw):
    w, hd = fw
    req = seed_request(db, w, status=S.COMPLETED)
    assert _post(client, hd, "req2", req).status_code == 404  # other requester: invisible
    assert _post(client, hd, "disp", req).status_code == 403
    assert _post(client, hd, "admin", req).status_code == 403
    assert _post(client, hd, "tech", req).status_code == 404  # unassigned technician: invisible


@pytest.mark.parametrize("rating", [0, 6, -1, "x", None])
def test_rating_bounds(client, db, fw, rating):
    w, hd = fw
    req = seed_request(db, w, status=S.COMPLETED)
    r = client.post(
        f"{API}/requests/{req.id}/feedback", json={"rating": rating}, headers=hd["req1"]
    )
    assert r.status_code == 422


def test_comment_length_limit(client, db, fw):
    w, hd = fw
    req = seed_request(db, w, status=S.COMPLETED)
    assert _post(client, hd, "req1", req, comment="x" * 2001).status_code == 422
    assert _post(client, hd, "req1", req, comment="x" * 2000).status_code == 201


def test_staff_notified_and_audited(client, db, fw):
    w, hd = fw
    req = seed_request(db, w, status=S.COMPLETED)
    assert _post(client, hd, "req1", req, rating=2).status_code == 201
    got = db.query(Notification).filter(Notification.type == "FEEDBACK_RECEIVED").all()
    assert {n.recipient_membership_id for n in got} == {w.admin[1].id, w.disp[1].id}
    n = client.get(f"{API}/notifications", headers=hd["disp"]).json()
    assert n["items"][0]["type"] == "FEEDBACK_RECEIVED"
    assert (
        db.execute(
            text("SELECT count(*) FROM audit_events WHERE action='request.feedback'")
        ).scalar()
        == 1
    )


def test_feedback_is_immutable_in_db(client, db, fw):
    w, hd = fw
    req = seed_request(db, w, status=S.COMPLETED)
    _post(client, hd, "req1", req)
    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError):
        db.execute(text("UPDATE feedback SET rating = 1"))
    db.rollback()
    with pytest.raises(DBAPIError):
        db.execute(text("DELETE FROM feedback"))
    db.rollback()
