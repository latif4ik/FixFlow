from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.core.security import hash_email, hash_token
from app.models import MembershipRole, SecurityEvent, Session
from tests.factories import PASSWORD, h, login, make_member, make_org, make_user

R = MembershipRole


def test_login_success_shape(client, db):
    org = make_org(db, "Alpha")
    user, m = make_member(db, org, R.ADMIN)
    r = client.post("/api/v1/auth/login", json={"email": user.email.upper(), "password": PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["token"] and body["expires_at"]
    assert body["user"]["email"] == user.email
    assert body["memberships"][0]["membership_id"] == str(m.id)
    assert body["memberships"][0]["role"] == "ADMIN"
    assert body["memberships"][0]["organization"]["timezone"] == "Asia/Bishkek"


def test_wrong_password_and_unknown_email_are_generic(client, db):
    org = make_org(db)
    user, _ = make_member(db, org, R.ADMIN)
    bad = client.post("/api/v1/auth/login", json={"email": user.email, "password": "nope-nope"})
    unknown = client.post(
        "/api/v1/auth/login", json={"email": "who@x.test", "password": "nope-nope"}
    )
    assert bad.status_code == unknown.status_code == 401
    assert (
        bad.json()["error"]["message"]
        == unknown.json()["error"]["message"]
        == "Invalid email or password."
    )
    assert bad.json()["error"]["code"] == unknown.json()["error"]["code"]


def test_deactivated_user_cannot_login_but_attempt_recorded(client, db):
    user = make_user(db, active=False)
    r = client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})
    assert r.status_code == 401
    assert r.json()["error"]["message"] == "Invalid email or password."
    ev = db.query(SecurityEvent).filter_by(event_type="login_failed").one()
    assert ev.details == {"reason": "inactive"} and ev.user_id == user.id


def test_failed_login_recorded_without_secrets(client, db):
    user = make_user(db)
    client.post("/api/v1/auth/login", json={"email": user.email, "password": "super-secret-wrong"})
    ev = db.query(SecurityEvent).filter_by(event_type="login_failed").one()
    assert ev.email_hash == hash_email(user.email)  # hashed, not raw
    assert user.email not in str(ev.__dict__) and "super-secret-wrong" not in str(ev.__dict__)


def test_missing_and_garbage_token_401(client, db):
    assert client.get("/api/v1/me").status_code == 401
    r = client.get("/api/v1/me", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"
    assert client.get("/api/v1/me", headers={"Authorization": "Basic abc"}).status_code == 401


def test_expired_session_401_session_expired(client, db):
    user = make_user(db)
    db.add(
        Session(
            user_id=user.id,
            token_hash=hash_token("expired-token"),
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
    )
    db.commit()
    r = client.get("/api/v1/me", headers=h("expired-token"))
    assert r.status_code == 401 and r.json()["error"]["code"] == "session_expired"


def test_logout_revokes_session_and_records_event(client, db):
    org = make_org(db)
    user, _ = make_member(db, org, R.ADMIN)
    token = login(client, user)
    assert client.get("/api/v1/me", headers=h(token)).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=h(token)).status_code == 204
    assert client.get("/api/v1/me", headers=h(token)).status_code == 401
    assert db.query(SecurityEvent).filter_by(event_type="session_revoked").count() == 1


def test_no_plaintext_token_or_password_stored(client, db, db_engine):
    org = make_org(db)
    user, _ = make_member(db, org, R.ADMIN)
    token = login(client, user)
    client.post("/api/v1/auth/login", json={"email": user.email, "password": "wrong-password-x"})
    client.post("/api/v1/auth/logout", headers=h(token))
    with db_engine.connect() as conn:
        tables = (
            conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))
            .scalars()
            .all()
        )
        for t in tables:
            dump = conn.execute(text(f'SELECT t::text FROM "{t}" t')).scalars().all()
            blob = "\n".join(dump)
            assert token not in blob, t
            assert PASSWORD not in blob and "wrong-password-x" not in blob, t
    row = db.query(Session).one()
    assert row.token_hash == hash_token(token) and row.token_hash != token


def test_me_and_membership_endpoints(client, db):
    org = make_org(db, "Alpha")
    user, m = make_member(db, org, R.DISPATCHER)
    token = login(client, user)
    me = client.get("/api/v1/me", headers=h(token)).json()
    assert me["user"]["id"] == str(user.id) and len(me["memberships"]) == 1
    cur = client.get("/api/v1/me/membership", headers=h(token, org)).json()
    assert cur["membership_id"] == str(m.id) and cur["role"] == "DISPATCHER"
    assert cur["organization"]["id"] == str(org.id)
    # org header required / malformed
    r = client.get("/api/v1/me/membership", headers=h(token))
    assert r.status_code == 400 and r.json()["error"]["code"] == "org_required"
    r = client.get("/api/v1/me/membership", headers={**h(token), "X-Org-Id": "not-a-uuid"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "org_required"


def test_rate_limit_per_email(client, db):
    for i in range(10):
        r = client.post(
            "/api/v1/auth/login", json={"email": "victim@x.test", "password": f"bad-{i}"}
        )
        assert r.status_code == 401
    r = client.post("/api/v1/auth/login", json={"email": "victim@x.test", "password": "bad-11"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "too_many_requests"
    # a different email from the same IP is still allowed (limit is 30/IP)
    r = client.post("/api/v1/auth/login", json={"email": "other@x.test", "password": "bad"})
    assert r.status_code == 401


def test_rate_limit_per_ip(client, db):
    for i in range(30):
        r = client.post("/api/v1/auth/login", json={"email": f"u{i}@x.test", "password": "bad"})
        assert r.status_code == 401
    r = client.post("/api/v1/auth/login", json={"email": "fresh@x.test", "password": "bad"})
    assert r.status_code == 429
