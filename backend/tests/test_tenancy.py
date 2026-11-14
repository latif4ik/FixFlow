import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Asset, MembershipRole
from tests.factories import (
    grant,
    h,
    login,
    make_asset,
    make_member,
    make_org,
    make_property,
    make_user,
)

R = MembershipRole


@pytest.fixture
def world(db):
    a, b = make_org(db, "Org A"), make_org(db, "Org B")
    disp_a = make_member(db, a, R.DISPATCHER)
    disp_b = make_member(db, b, R.DISPATCHER)
    prop_a = make_property(db, a, "Prop A")
    prop_b = make_property(db, b, "Prop B")
    asset_a = make_asset(db, a, prop_a, "A-1")
    asset_b = make_asset(db, b, prop_b, "B-1")
    return {
        "a": a,
        "b": b,
        "disp_a": disp_a,
        "disp_b": disp_b,
        "prop_a": prop_a,
        "prop_b": prop_b,
        "asset_a": asset_a,
        "asset_b": asset_b,
    }


def test_member_of_a_using_org_b_header_is_403(client, world):
    tok = login(client, world["disp_a"][0])
    r = client.get("/api/v1/properties", headers=h(tok, world["b"]))
    assert r.status_code == 403 and r.json()["error"]["code"] == "org_access_denied"


def test_inactive_membership_or_org_is_403(client, db, world):
    user, m = world["disp_a"]
    tok = login(client, user)
    m.is_active = False
    db.commit()
    assert client.get("/api/v1/org", headers=h(tok, world["a"])).status_code == 403
    m.is_active = True
    world["a"].is_active = False
    db.commit()
    assert client.get("/api/v1/org", headers=h(tok, world["a"])).status_code == 403


def test_different_roles_per_org_for_same_user(client, db, world):
    user = make_user(db)
    make_member(db, world["a"], R.REQUESTER, user)
    make_member(db, world["b"], R.DISPATCHER, user)
    tok = login(client, user)
    assert (
        client.get("/api/v1/me/membership", headers=h(tok, world["a"])).json()["role"]
        == "REQUESTER"
    )
    assert (
        client.get("/api/v1/me/membership", headers=h(tok, world["b"])).json()["role"]
        == "DISPATCHER"
    )
    assert len(client.get("/api/v1/me", headers=h(tok)).json()["memberships"]) == 2


def test_cross_org_by_id_is_404(client, world):
    tok = login(client, world["disp_b"][0])
    hb = h(tok, world["b"])
    assert client.get(f"/api/v1/properties/{world['prop_a'].id}", headers=hb).status_code == 404
    assert client.get(f"/api/v1/assets/{world['asset_a'].id}", headers=hb).status_code == 404
    assert (
        client.patch(
            f"/api/v1/properties/{world['prop_a'].id}", json={"name": "x"}, headers=hb
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/v1/assets/{world['asset_a'].id}", json={"name": "x"}, headers=hb
        ).status_code
        == 404
    )
    assert (
        client.get(f"/api/v1/properties/{world['prop_a'].id}/access", headers=hb).status_code == 404
    )


def test_listings_never_return_other_org_rows(client, world):
    tok = login(client, world["disp_b"][0])
    hb = h(tok, world["b"])
    props = client.get("/api/v1/properties", headers=hb).json()
    assert [p["id"] for p in props["items"]] == [str(world["prop_b"].id)] and props["total"] == 1
    assets = client.get("/api/v1/assets", headers=hb).json()
    assert [a["id"] for a in assets["items"]] == [str(world["asset_b"].id)]
    assets = client.get(f"/api/v1/assets?property_id={world['prop_a'].id}", headers=hb).json()
    assert assets["items"] == [] and assets["total"] == 0


def test_asset_with_property_of_other_org_rejected_at_db_level(db, world):
    db.add(
        Asset(
            organization_id=world["a"].id,
            property_id=world["prop_b"].id,  # belongs to org B
            code="X-1",
            name="x",
            asset_type="t",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_api_rejects_other_org_property_for_asset_with_422(client, world):
    tok = login(client, world["disp_a"][0])
    r = client.post(
        "/api/v1/assets",
        json={"property_id": str(world["prop_b"].id), "code": "Z", "name": "z", "asset_type": "t"},
        headers=h(tok, world["a"]),
    )
    assert r.status_code == 422
    assert r.json()["error"]["details"][0]["field"] == "property_id"


def test_roles_enforced(client, db, world):
    a = world["a"]
    req = make_member(db, a, R.REQUESTER)
    tech = make_member(db, a, R.TECHNICIAN)
    t_req, t_tech, t_disp = (
        login(client, req[0]),
        login(client, tech[0]),
        login(client, world["disp_a"][0]),
    )
    r = client.post("/api/v1/properties", json={"name": "n", "address": "a"}, headers=h(t_req, a))
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    assert client.get("/api/v1/properties", headers=h(t_tech, a)).status_code == 403
    assert client.get("/api/v1/assets", headers=h(t_tech, a)).status_code == 403
    r = client.patch(
        f"/api/v1/org/members/{req[1].id}", json={"role": "DISPATCHER"}, headers=h(t_disp, a)
    )
    assert r.status_code == 403
    assert client.get("/api/v1/audit", headers=h(t_disp, a)).status_code == 403
    assert client.get("/api/v1/org/members", headers=h(t_disp, a)).status_code == 200
    assert client.get("/api/v1/org/members", headers=h(t_req, a)).status_code == 403
    grant(db, world["prop_a"], req[1], world["disp_a"][1])
    assert client.get("/api/v1/properties", headers=h(t_req, a)).status_code == 200
