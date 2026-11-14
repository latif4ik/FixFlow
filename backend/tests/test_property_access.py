import pytest

from app.models import AuditEvent, MembershipRole
from tests.factories import (
    grant,
    h,
    login,
    make_asset,
    make_member,
    make_org,
    make_property,
)

R = MembershipRole


@pytest.fixture
def w(db):
    org = make_org(db, "Org A")
    other = make_org(db, "Org B")
    disp = make_member(db, org, R.DISPATCHER)
    req1 = make_member(db, org, R.REQUESTER)
    req2 = make_member(db, org, R.REQUESTER)
    p1, p2 = make_property(db, org, "Granted"), make_property(db, org, "Hidden")
    a1, a2 = make_asset(db, org, p1, "G-1"), make_asset(db, org, p2, "H-1")
    grant(db, p1, req1[1], disp[1])
    return {
        "org": org,
        "other": other,
        "disp": disp,
        "req1": req1,
        "req2": req2,
        "p1": p1,
        "p2": p2,
        "a1": a1,
        "a2": a2,
    }


def test_requester_sees_only_granted(client, w):
    tok = login(client, w["req1"][0])
    hd = h(tok, w["org"])
    props = client.get("/api/v1/properties", headers=hd).json()
    assert [p["id"] for p in props["items"]] == [str(w["p1"].id)]
    assets = client.get("/api/v1/assets", headers=hd).json()
    assert [a["id"] for a in assets["items"]] == [str(w["a1"].id)]
    assert client.get(f"/api/v1/properties/{w['p1'].id}", headers=hd).status_code == 200
    assert client.get(f"/api/v1/assets/{w['a1'].id}", headers=hd).status_code == 200
    # filter by a hidden property must not leak
    assert client.get(f"/api/v1/assets?property_id={w['p2'].id}", headers=hd).json()["total"] == 0
    # requester with no grants sees an empty list
    tok2 = login(client, w["req2"][0])
    assert client.get("/api/v1/properties", headers=h(tok2, w["org"])).json()["items"] == []


def test_non_granted_and_other_org_property_same_404(client, db, w):
    other_prop = make_property(db, w["other"], "Foreign")
    other_asset = make_asset(db, w["other"], other_prop, "F-1")
    hd = h(login(client, w["req1"][0]), w["org"])
    responses = []
    for url in (
        f"/api/v1/properties/{w['p2'].id}",
        f"/api/v1/properties/{other_prop.id}",
        f"/api/v1/assets/{w['a2'].id}",
        f"/api/v1/assets/{other_asset.id}",
    ):
        r = client.get(url, headers=hd)
        assert r.status_code == 404
        body = r.json()["error"]
        responses.append((body["code"], body["details"]))
    assert len(set(responses)) == 1


def test_grant_to_non_requester_is_422(client, db, w):
    hd = h(login(client, w["disp"][0]), w["org"])
    tech = make_member(db, w["org"], R.TECHNICIAN)
    for mid in (w["disp"][1].id, tech[1].id):
        r = client.post(
            f"/api/v1/properties/{w['p2'].id}/access", json={"membership_id": str(mid)}, headers=hd
        )
        assert r.status_code == 422
        assert r.json()["error"]["details"][0]["field"] == "membership_id"
    foreign = make_member(db, w["other"], R.REQUESTER)
    r = client.post(
        f"/api/v1/properties/{w['p2'].id}/access",
        json={"membership_id": str(foreign[1].id)},
        headers=hd,
    )
    assert r.status_code == 422


def test_grant_revoke_visibility_and_audit(client, db, w):
    hd = h(login(client, w["disp"][0]), w["org"])
    hr = h(login(client, w["req2"][0]), w["org"])
    assert client.get(f"/api/v1/properties/{w['p2'].id}", headers=hr).status_code == 404
    r = client.post(
        f"/api/v1/properties/{w['p2'].id}/access",
        json={"membership_id": str(w["req2"][1].id)},
        headers=hd,
    )
    assert r.status_code == 201
    assert (
        client.post(
            f"/api/v1/properties/{w['p2'].id}/access",
            json={"membership_id": str(w["req2"][1].id)},
            headers=hd,
        ).status_code
        == 409
    )
    assert client.get(f"/api/v1/properties/{w['p2'].id}", headers=hr).status_code == 200
    lst = client.get(f"/api/v1/properties/{w['p2'].id}/access", headers=hd).json()
    assert lst["total"] == 1 and lst["items"][0]["membership_id"] == str(w["req2"][1].id)
    assert (
        client.delete(
            f"/api/v1/properties/{w['p2'].id}/access/{w['req2'][1].id}", headers=hd
        ).status_code
        == 204
    )
    assert client.get(f"/api/v1/properties/{w['p2'].id}", headers=hr).status_code == 404
    assert client.get("/api/v1/assets", headers=hr).json()["items"] == []
    actions = [e.action for e in db.query(AuditEvent).order_by(AuditEvent.created_at)]
    assert actions == ["property_access.granted", "property_access.revoked"]
    assert (
        client.delete(
            f"/api/v1/properties/{w['p2'].id}/access/{w['req2'][1].id}", headers=hd
        ).status_code
        == 404
    )
