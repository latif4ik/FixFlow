import pytest
from sqlalchemy import select

from app.core.errors import Conflict
from app.core.tenancy import Ctx
from app.models import (
    AuditEvent,
    Membership,
    MembershipRole,
    SecurityEvent,
    Session,
    TechnicianProfile,
    User,
)
from app.services.members import update_member
from tests.factories import PASSWORD, h, login, make_member, make_org

R = MembershipRole


@pytest.fixture
def w(db):
    org = make_org(db, "Org A")
    admin = make_member(db, org, R.ADMIN)
    admin2 = make_member(db, org, R.ADMIN)
    disp = make_member(db, org, R.DISPATCHER)
    req = make_member(db, org, R.REQUESTER)
    return {"org": org, "admin": admin, "admin2": admin2, "disp": disp, "req": req}


def test_cannot_change_own_role_or_deactivate_self(client, w):
    hd = h(login(client, w["admin"][0]), w["org"])
    mid = w["admin"][1].id
    assert (
        client.patch(
            f"/api/v1/org/members/{mid}", json={"is_active": False}, headers=hd
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/v1/org/members/{mid}", json={"role": "DISPATCHER"}, headers=hd
        ).status_code
        == 422
    )


def test_cannot_remove_last_admin_409(db, w):
    # Through the API an acting admin always remains; the guard protects concurrent/stale callers,
    # so exercise the service directly with an actor that is not the target.
    org = w["org"]
    db.query(Membership).filter(Membership.id == w["admin2"][1].id).update({"is_active": False})
    db.commit()
    actor = w["disp"][1]
    ctx = Ctx(w["disp"][0].id, org.id, actor.id, R.ADMIN, "Asia/Bishkek")
    with pytest.raises(Conflict):
        update_member(db, ctx, w["admin"][1].id, R.DISPATCHER, None)
    with pytest.raises(Conflict):
        update_member(db, ctx, w["admin"][1].id, None, False)


def test_role_change_audited_with_before_after_and_security_event(client, db, w):
    hd = h(login(client, w["admin"][0]), w["org"])
    mid = w["req"][1].id
    r = client.patch(f"/api/v1/org/members/{mid}", json={"role": "DISPATCHER"}, headers=hd)
    assert r.status_code == 200 and r.json()["role"] == "DISPATCHER"
    ev = db.scalars(select(AuditEvent).where(AuditEvent.action == "membership.role_changed")).one()
    assert ev.before == {"role": "REQUESTER", "is_active": True}
    assert ev.after == {"role": "DISPATCHER", "is_active": True}
    assert ev.target_id == mid and ev.actor_membership_id == w["admin"][1].id
    sec = db.scalars(
        select(SecurityEvent).where(SecurityEvent.event_type == "membership_role_changed")
    ).one()
    assert sec.user_id == w["req"][0].id and sec.details["to"] == "DISPATCHER"
    audit = client.get("/api/v1/audit?action=membership.role_changed", headers=hd).json()
    assert audit["total"] == 1 and audit["items"][0]["actor_name"]


def test_deactivation_scope_and_session_revocation(client, db, w):
    other = make_org(db, "Org B")
    user = w["req"][0]
    _, m_other = make_member(db, other, R.REQUESTER, user)
    tok = login(client, user)
    hd = h(login(client, w["admin"][0]), w["org"])
    # deactivating in org A keeps the user's session (still active in org B)
    r = client.patch(f"/api/v1/org/members/{w['req'][1].id}", json={"is_active": False}, headers=hd)
    assert r.status_code == 200
    assert client.get("/api/v1/me", headers=h(tok)).status_code == 200
    assert client.get("/api/v1/org", headers=h(tok, w["org"])).status_code == 403
    assert client.get("/api/v1/org", headers=h(tok, other)).status_code == 200
    assert db.scalars(
        select(SecurityEvent).where(SecurityEvent.event_type == "membership_deactivated")
    ).one()
    # deactivating the last active membership revokes all sessions
    m_other.is_active = False
    db.commit()
    admin_b = make_member(db, other, R.ADMIN)
    hb = h(login(client, admin_b[0]), other)
    client.patch(f"/api/v1/org/members/{m_other.id}", json={"is_active": True}, headers=hb)
    assert (
        client.patch(
            f"/api/v1/org/members/{m_other.id}", json={"is_active": False}, headers=hb
        ).status_code
        == 200
    )
    assert client.get("/api/v1/me", headers=h(tok)).status_code == 401
    assert all(s.revoked_at for s in db.scalars(select(Session).where(Session.user_id == user.id)))
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": PASSWORD}
        ).status_code
        == 200
    )


def test_create_member_new_user_existing_user_and_technician_profile(client, db, w):
    hd = h(login(client, w["admin"][0]), w["org"])
    r = client.post(
        "/api/v1/org/members",
        json={
            "email": "New@X.test",
            "full_name": "New T",
            "role": "TECHNICIAN",
            "password": "longenough1",
        },
        headers=hd,
    )
    assert r.status_code == 201 and r.json()["email"] == "new@x.test"
    mid = r.json()["membership_id"]
    assert db.get(TechnicianProfile, mid) is not None
    assert (
        client.post(
            "/api/v1/org/members",
            json={"email": "new@x.test", "full_name": "x", "role": "ADMIN"},
            headers=hd,
        ).status_code
        == 409
    )
    r = client.post(
        "/api/v1/org/members",
        json={"email": "nobody@x.test", "full_name": "x", "role": "ADMIN"},
        headers=hd,
    )
    assert r.status_code == 422
    r = client.post(
        "/api/v1/org/members",
        json={"email": "short@x.test", "full_name": "x", "role": "ADMIN", "password": "short"},
        headers=hd,
    )
    assert r.status_code == 422
    # existing user from another org is added without a password
    other = make_org(db, "Org B")
    u, _ = make_member(db, other, R.REQUESTER)
    r = client.post(
        "/api/v1/org/members",
        json={"email": u.email, "full_name": "ignored", "role": "REQUESTER"},
        headers=hd,
    )
    assert r.status_code == 201
    assert db.scalars(select(User).where(User.email == u.email)).one().full_name != "ignored"
    # platform role is not a valid role
    r = client.post(
        "/api/v1/org/members",
        json={
            "email": "p@x.test",
            "full_name": "x",
            "role": "SUPERADMIN",
            "password": "longenough1",
        },
        headers=hd,
    )
    assert r.status_code == 422
    assert client.get("/api/v1/org/members?role=TECHNICIAN", headers=hd).json()["total"] == 1
    assert client.get("/api/v1/org/members?q=new", headers=hd).json()["total"] == 1


def test_validation_errors_and_org_settings(client, db, w):
    hd = h(login(client, w["admin"][0]), w["org"])
    assert (
        client.patch("/api/v1/org", json={"timezone": "Mars/Phobos"}, headers=hd).status_code == 422
    )
    r = client.patch(
        "/api/v1/org", json={"timezone": "Europe/Berlin", "name": "Renamed"}, headers=hd
    )
    assert r.status_code == 200 and r.json()["timezone"] == "Europe/Berlin"
    overlapping = {
        "intervals": [
            {"weekday": 0, "open_time": "09:00", "close_time": "12:00"},
            {"weekday": 0, "open_time": "11:00", "close_time": "15:00"},
        ]
    }
    assert client.put("/api/v1/org/business-hours", json=overlapping, headers=hd).status_code == 422
    ok = {
        "intervals": [
            {"weekday": 0, "open_time": "13:00", "close_time": "18:00"},
            {"weekday": 0, "open_time": "09:00", "close_time": "12:00"},
            {"weekday": 6, "open_time": "10:00", "close_time": "14:00"},
        ]
    }
    r = client.put("/api/v1/org/business-hours", json=ok, headers=hd)
    assert r.status_code == 200 and [i["open_time"] for i in r.json()["intervals"]][:2] == [
        "09:00:00",
        "13:00:00",
    ]
    bad = {"intervals": [{"weekday": 7, "open_time": "09:00", "close_time": "10:00"}]}
    assert client.put("/api/v1/org/business-hours", json=bad, headers=hd).status_code == 422
    r = client.post("/api/v1/org/holidays", json={"date": "2026-12-31", "name": "NYE"}, headers=hd)
    assert r.status_code == 201
    assert (
        client.post(
            "/api/v1/org/holidays", json={"date": "2026-12-31", "name": "dup"}, headers=hd
        ).status_code
        == 409
    )
    assert client.delete(f"/api/v1/org/holidays/{r.json()['id']}", headers=hd).status_code == 204
    actions = {e.action for e in db.query(AuditEvent)}
    assert {
        "org.updated",
        "org.business_hours_replaced",
        "holiday.created",
        "holiday.deleted",
    } <= actions


def test_skills_categories_technicians(client, db, w):
    org = w["org"]
    hd = h(login(client, w["admin"][0]), org)
    s1 = client.post("/api/v1/skills", json={"name": "HVAC"}, headers=hd)
    assert s1.status_code == 201
    dup = client.post("/api/v1/skills", json={"name": "hvac"}, headers=hd)
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "conflict"
    other_skill = client.post(
        "/api/v1/skills",
        json={"name": "Elec"},
        headers=h(login(client, make_member(db, make_org(db, "B"), R.ADMIN)[0]), None),
    )  # no org header -> 400
    assert other_skill.status_code == 400
    cat = client.post(
        "/api/v1/categories",
        json={
            "name": "Cooling",
            "default_duration_minutes": 60,
            "required_skill_ids": [s1.json()["id"]],
        },
        headers=hd,
    )
    assert cat.status_code == 201 and cat.json()["required_skills"][0]["name"] == "HVAC"
    assert (
        client.post(
            "/api/v1/categories", json={"name": "Bad", "default_duration_minutes": 10}, headers=hd
        ).status_code
        == 422
    )
    r = client.post(
        "/api/v1/categories",
        json={
            "name": "X",
            "default_duration_minutes": 60,
            "required_skill_ids": ["00000000-0000-0000-0000-000000000001"],
        },
        headers=hd,
    )
    assert r.status_code == 422
    # disable: hidden from requesters, visible to staff on request
    assert (
        client.patch(
            f"/api/v1/categories/{cat.json()['id']}", json={"is_enabled": False}, headers=hd
        ).status_code
        == 200
    )
    req_tok = login(client, w["req"][0])
    assert (
        client.get("/api/v1/categories?include_disabled=true", headers=h(req_tok, org)).json()[
            "total"
        ]
        == 0
    )
    assert client.get("/api/v1/categories", headers=hd).json()["total"] == 0
    assert client.get("/api/v1/categories?include_disabled=true", headers=hd).json()["total"] == 1
    # technician data
    tech_user, tech_m = make_member(db, org, R.TECHNICIAN)
    db.add(TechnicianProfile(organization_id=org.id, membership_id=tech_m.id))
    db.commit()
    url = f"/api/v1/technicians/{tech_m.id}"
    assert (
        client.put(f"{url}/skills", json={"skill_ids": [s1.json()["id"]]}, headers=hd).json()[
            "skills"
        ][0]["name"]
        == "HVAC"
    )
    assert (
        client.put(
            f"{url}/skills",
            json={"skill_ids": ["00000000-0000-0000-0000-000000000001"]},
            headers=hd,
        ).status_code
        == 422
    )
    av = {
        "intervals": [
            {"weekday": 1, "start_time": "09:00", "end_time": "12:00"},
            {"weekday": 1, "start_time": "11:00", "end_time": "13:00"},
        ]
    }
    assert client.put(f"{url}/availability", json=av, headers=hd).status_code == 422
    av["intervals"][1]["start_time"] = "12:00"
    assert len(client.put(f"{url}/availability", json=av, headers=hd).json()["availability"]) == 2
    to = client.post(
        f"{url}/time-off",
        json={
            "start_at": "2026-12-01T00:00:00Z",
            "end_at": "2026-12-03T00:00:00Z",
            "reason": "leave",
        },
        headers=hd,
    )
    assert to.status_code == 201
    assert (
        client.post(
            f"{url}/time-off",
            json={"start_at": "2026-12-03T00:00:00Z", "end_at": "2026-12-01T00:00:00Z"},
            headers=hd,
        ).status_code
        == 422
    )
    assert client.get(url, headers=hd).json()["time_off"][0]["reason"] == "leave"
    assert client.delete(f"{url}/time-off/{to.json()['id']}", headers=hd).status_code == 204
    assert client.get("/api/v1/technicians", headers=hd).json()["total"] == 1
    tech_hd = h(login(client, tech_user), org)
    assert client.get("/api/v1/technicians/me", headers=tech_hd).json()["membership_id"] == str(
        tech_m.id
    )
    assert client.get("/api/v1/technicians", headers=tech_hd).status_code == 403
    assert client.get("/api/v1/technicians/me", headers=hd).status_code == 403
