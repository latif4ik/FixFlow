import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.models import AuditEvent, MembershipRole
from tests.factories import h, login, make_member, make_org, make_property

R = MembershipRole


@pytest.fixture
def w(db):
    org = make_org(db, "Org A")
    disp = make_member(db, org, R.DISPATCHER)
    prop = make_property(db, org, "Tower")
    return {"org": org, "disp": disp, "prop": prop}


def _asset(prop, code="AC-1", **kw):
    return {"property_id": str(prop.id), "code": code, "name": "Unit", "asset_type": "HVAC", **kw}


def test_asset_crud_duplicate_code_and_retire(client, db, w):
    hd = h(login(client, w["disp"][0]), w["org"])
    r = client.post(
        "/api/v1/assets",
        json=_asset(w["prop"], serial_number="S1", installed_on="2024-05-01"),
        headers=hd,
    )
    assert r.status_code == 201 and r.json()["status"] == "ACTIVE"
    dup = client.post("/api/v1/assets", json=_asset(w["prop"]), headers=hd)
    assert dup.status_code == 409 and dup.json()["error"]["details"]["fields"] == ["code"]
    aid = r.json()["id"]
    p = client.patch(
        f"/api/v1/assets/{aid}", json={"status": "RETIRED", "notes": "scrapped"}, headers=hd
    )
    assert p.status_code == 200 and p.json()["status"] == "RETIRED"
    # retired asset is preserved and still readable
    assert client.get(f"/api/v1/assets/{aid}", headers=hd).status_code == 200
    assert client.get("/api/v1/assets?status=RETIRED&q=unit", headers=hd).json()["total"] == 1
    assert client.get("/api/v1/assets?status=ACTIVE", headers=hd).json()["total"] == 0
    assert (
        client.post(
            "/api/v1/assets", json=_asset(w["prop"], "Z", status="BROKEN"), headers=hd
        ).status_code
        == 422
    )
    ev = db.query(AuditEvent).filter_by(action="asset.retired").one()
    assert ev.before["status"] == "ACTIVE" and ev.after["status"] == "RETIRED"
    # archive a property (soft delete)
    r = client.patch(f"/api/v1/properties/{w['prop'].id}", json={"is_active": False}, headers=hd)
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert db.query(AuditEvent).filter_by(action="property.archived").count() == 1


def test_pagination_limits(client, w):
    hd = h(login(client, w["disp"][0]), w["org"])
    assert client.get("/api/v1/properties?page_size=101", headers=hd).status_code == 422
    assert client.get("/api/v1/properties?page_size=0", headers=hd).status_code == 422
    assert client.get("/api/v1/properties?page=0", headers=hd).status_code == 422
    r = client.get("/api/v1/properties?page_size=100", headers=hd)
    assert r.status_code == 200
    assert set(r.json()) == {"items", "total", "page", "page_size"} and r.json()["page_size"] == 100
    assert client.get("/api/v1/properties/not-a-uuid", headers=hd).status_code == 422


def test_audit_is_immutable_at_db_level(client, db, db_engine, w):
    hd = h(login(client, w["disp"][0]), w["org"])
    client.post("/api/v1/properties", json={"name": "N", "address": "A"}, headers=hd)
    assert db.query(AuditEvent).count() == 1
    for stmt in ("UPDATE audit_events SET action = 'tampered'", "DELETE FROM audit_events"):
        with db_engine.connect() as conn:
            with pytest.raises(DBAPIError, match="append-only"):
                conn.execute(text(stmt))
            conn.rollback()
    assert db.query(AuditEvent).count() == 1
