import pytest
from sqlalchemy import select

from app.models import AuditEvent, RequestEvent, ServiceRequest
from app.models.enums import RequestStatus
from tests.factories import h, login
from tests.req_helpers import LONG_DESC, make_category, make_world, payload, retire, seed_request

API = "/api/v1"


@pytest.fixture
def w(db):
    return make_world(db)


@pytest.fixture
def hd(client, w):
    """Auth headers for each role of the main org."""

    def _h(who: str):
        return h(login(client, getattr(w, who)[0]), w.org)

    return {k: _h(k) for k in ("admin", "disp", "tech", "req1", "req2")}


# ---------------- create ----------------
def test_requester_creates_request(client, w, hd):
    r = client.post(f"{API}/requests", json=payload(w, priority="HIGH"), headers=hd["req1"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["number"] == 1 and body["display_id"] == "REQ-1"
    assert body["status"] == "SUBMITTED" and body["priority"] == "HIGH"
    assert body["requester"]["membership_id"] == str(w.req1[1].id)
    assert body["property"]["id"] == str(w.prop.id)
    assert body["assignment"] is None and body["materials"] == []
    assert [e["type"] for e in body["timeline"]] == ["REQUEST_CREATED"]
    assert "edit" in body["allowed_actions"] and "cancel" in body["allowed_actions"]
    n2 = client.post(f"{API}/requests", json=payload(w), headers=hd["req1"]).json()["number"]
    assert n2 == 2


def test_numbers_are_independent_per_org(client, db, w, hd):
    other = make_world(db, "Org B")
    client.post(f"{API}/requests", json=payload(w), headers=hd["req1"])
    ho = h(login(client, other.req1[0]), other.org)
    r = client.post(f"{API}/requests", json=payload(other), headers=ho)
    assert r.json()["number"] == 1


@pytest.mark.parametrize(
    ("field", "value", "ok"),
    [
        ("title", "a" * 4, False),
        ("title", "a" * 5, True),
        ("title", "a" * 120, True),
        ("title", "a" * 121, False),
        ("title", "  ab  cd  ", False),  # trims to 6 chars? "ab  cd" is 6 -> ok below
        ("description", "d" * 19, False),
        ("description", "d" * 20, True),
        ("description", "d" * 3000, True),
        ("description", "d" * 3001, False),
        ("description", " " * 5 + "d" * 19 + " " * 5, False),
    ],
)
def test_length_bounds(client, w, hd, field, value, ok):
    if field == "title" and value == "  ab  cd  ":
        ok = True
    r = client.post(f"{API}/requests", json=payload(w, **{field: value}), headers=hd["req1"])
    if ok:
        assert r.status_code == 201, r.text
    else:
        assert r.status_code == 422
        assert field in [d["field"] for d in r.json()["error"]["details"]]


def test_property_not_granted_and_other_org_same_response(client, db, w, hd):
    other = make_world(db, "Org B")
    a = client.post(
        f"{API}/requests", json=payload(w, property_id=str(w.hidden.id)), headers=hd["req1"]
    )
    b = client.post(
        f"{API}/requests", json=payload(w, property_id=str(other.prop.id)), headers=hd["req1"]
    )
    assert a.status_code == b.status_code == 422
    ea, eb = a.json()["error"], b.json()["error"]
    ea.pop("request_id"), eb.pop("request_id")
    assert ea == eb and ea["details"][0]["field"] == "property_id"


def test_asset_rules(client, db, w, hd):
    bad = client.post(
        f"{API}/requests", json=payload(w, asset_id=str(w.other_asset.id)), headers=hd["req1"]
    )
    assert bad.status_code == 422 and bad.json()["error"]["details"][0]["field"] == "asset_id"
    ok = client.post(
        f"{API}/requests", json=payload(w, asset_id=str(w.asset.id)), headers=hd["req1"]
    )
    assert ok.status_code == 201 and ok.json()["asset"]["id"] == str(w.asset.id)
    retire(db, w.asset)
    r = client.post(
        f"{API}/requests", json=payload(w, asset_id=str(w.asset.id)), headers=hd["req1"]
    )
    assert r.status_code == 422


def test_category_rules(client, db, w, hd):
    off = make_category(db, w.org, "Off", enabled=False)
    r = client.post(f"{API}/requests", json=payload(w, category_id=str(off.id)), headers=hd["req1"])
    assert r.status_code == 422 and r.json()["error"]["details"][0]["field"] == "category_id"
    foreign = make_category(db, make_world(db, "Org B").org, "X")
    r = client.post(
        f"{API}/requests", json=payload(w, category_id=str(foreign.id)), headers=hd["req1"]
    )
    assert r.status_code == 422


def test_staff_creates_on_behalf_and_technician_cannot(client, w, hd):
    r = client.post(
        f"{API}/requests",
        json=payload(w, property_id=str(w.hidden.id), requester_membership_id=str(w.req2[1].id)),
        headers=hd["disp"],
    )
    assert r.status_code == 201, r.text
    assert r.json()["requester"]["membership_id"] == str(w.req2[1].id)
    assert r.json()["created_by"]["membership_id"] == str(w.disp[1].id)
    none = client.post(f"{API}/requests", json=payload(w), headers=hd["disp"])
    assert none.status_code == 201 and none.json()["requester"] is None
    bad = client.post(
        f"{API}/requests",
        json=payload(w, requester_membership_id=str(w.disp[1].id)),
        headers=hd["disp"],
    )
    assert bad.status_code == 422
    assert client.post(f"{API}/requests", json=payload(w), headers=hd["tech"]).status_code == 403
    own = client.post(
        f"{API}/requests",
        json=payload(w, requester_membership_id=str(w.req2[1].id)),
        headers=hd["req1"],
    )
    assert own.status_code == 422


def test_preferred_window(client, w, hd):
    ok = payload(
        w,
        preferred_window_start="2030-01-01T09:00:00Z",
        preferred_window_end="2030-01-01T11:00:00Z",
    )
    assert client.post(f"{API}/requests", json=ok, headers=hd["req1"]).status_code == 201
    bad = payload(
        w,
        preferred_window_start="2030-01-01T11:00:00Z",
        preferred_window_end="2030-01-01T09:00:00Z",
    )
    assert client.post(f"{API}/requests", json=bad, headers=hd["req1"]).status_code == 422
    half = payload(w, preferred_window_start="2030-01-01T11:00:00Z")
    assert client.post(f"{API}/requests", json=half, headers=hd["req1"]).status_code == 422


def test_create_writes_event_and_audit(client, db, w, hd):
    rid = client.post(f"{API}/requests", json=payload(w), headers=hd["req1"]).json()["id"]
    ev = db.scalars(select(RequestEvent).where(RequestEvent.request_id == rid)).all()
    assert [e.type for e in ev] == ["REQUEST_CREATED"] and ev[0].actor_membership_id == w.req1[1].id
    audit = db.scalars(select(AuditEvent).where(AuditEvent.action == "request.create")).all()
    assert len(audit) == 1 and str(audit[0].target_id) == rid


# ---------------- visibility ----------------
def test_visibility(client, db, w, hd):
    mine = seed_request(db, w, requester=w.req1[1])
    theirs = seed_request(db, w, requester=w.req2[1], title="Other person")
    assert [i["id"] for i in client.get(f"{API}/requests", headers=hd["req1"]).json()["items"]] == [
        str(mine.id)
    ]
    assert client.get(f"{API}/requests/{theirs.id}", headers=hd["req1"]).status_code == 404
    assert client.get(f"{API}/requests/{theirs.id}/notes", headers=hd["req1"]).status_code == 404
    assert client.get(f"{API}/requests/{theirs.id}/timeline", headers=hd["req1"]).status_code == 404
    assert (
        client.post(
            f"{API}/requests/{theirs.id}/notes", json={"body": "hi"}, headers=hd["req1"]
        ).status_code
        == 404
    )
    assert client.get(f"{API}/requests", headers=hd["disp"]).json()["total"] == 2
    assert client.get(f"{API}/requests", headers=hd["tech"]).json()["total"] == 0
    assert client.get(f"{API}/requests/{mine.id}", headers=hd["tech"]).status_code == 404


def test_org_isolation(client, db, w):
    other = make_world(db, "Org B")
    ho = h(login(client, other.admin[0]), other.org)
    req = seed_request(db, w)
    assert client.get(f"{API}/requests/{req.id}", headers=ho).status_code == 404
    assert client.get(f"{API}/requests", headers=ho).json()["total"] == 0
    assert client.post(f"{API}/requests/{req.id}/triage", json={}, headers=ho).status_code == 404


# ---------------- list ----------------
def test_list_pagination_filters_sort_search(client, db, w, hd):
    from app.models.enums import Priority

    cat2 = make_category(db, w.org, "Plumbing")
    reqs = [
        seed_request(db, w, title="Alpha broken door", priority=Priority.LOW),
        seed_request(
            db, w, title="Bravo leaking pipe", priority=Priority.HIGH, category_id=cat2.id
        ),
        seed_request(db, w, title="Charlie flickering light", status=RequestStatus.TRIAGED),
        seed_request(db, w, title="Delta hidden", property_id=w.hidden.id),
    ]
    d = hd["disp"]
    page = client.get(f"{API}/requests?page=2&page_size=3", headers=d).json()
    assert page["total"] == 4 and len(page["items"]) == 1 and page["page"] == 2

    def ids(qs: str) -> list[str]:
        r = client.get(f"{API}/requests?{qs}", headers=d)
        return [i["title"] for i in r.json()["items"]]

    assert ids("status=TRIAGED") == ["Charlie flickering light"]
    assert set(ids("status=TRIAGED&status=SUBMITTED")) == {r.title for r in reqs}
    assert ids("priority=HIGH") == ["Bravo leaking pipe"]
    assert ids(f"category_id={cat2.id}") == ["Bravo leaking pipe"]
    assert ids(f"property_id={w.hidden.id}") == ["Delta hidden"]
    n = reqs[2].number
    assert ids(f"q=REQ-{n}") == ["Charlie flickering light"]
    assert ids(f"q=req-{n}") == ["Charlie flickering light"]
    assert ids(f"q={n}") == ["Charlie flickering light"]
    assert ids("q=pipe") == ["Bravo leaking pipe"]
    assert ids("q=100%25") == []
    assert ids("q=Hidden") == ["Delta hidden"]  # property name fragment
    assert ids("q=1 Test") and len(ids("q=1 Test St")) == 4  # address fragment
    assert ids("sort=oldest")[0] == "Alpha broken door"
    assert ids("sort=newest")[0] == "Delta hidden"
    assert (
        ids("sort=priority")[0] == "Bravo leaking pipe"
        and ids("sort=priority")[-1] == "Alpha broken door"
    )
    assert client.get(f"{API}/requests?sort=bogus", headers=d).status_code == 422
    item = client.get(f"{API}/requests", headers=d).json()["items"][0]
    assert {
        "id",
        "number",
        "display_id",
        "title",
        "status",
        "priority",
        "category",
        "property",
        "asset",
        "requester",
        "created_at",
        "updated_at",
    } <= set(item)


# ---------------- triage & edits ----------------
def test_triage_and_permissions(client, db, w, hd):
    req = seed_request(db, w)
    assert (
        client.post(f"{API}/requests/{req.id}/triage", json={}, headers=hd["req1"]).status_code
        == 403
    )
    r = client.post(
        f"{API}/requests/{req.id}/triage", json={"note": "Needs HVAC tech"}, headers=hd["disp"]
    )
    assert r.status_code == 200 and r.json()["status"] == "TRIAGED"
    notes = client.get(f"{API}/requests/{req.id}/notes", headers=hd["disp"]).json()["items"]
    assert notes[0]["kind"] == "TRIAGE" and notes[0]["visibility"] == "INTERNAL"
    assert client.get(f"{API}/requests/{req.id}/notes", headers=hd["req1"]).json()["total"] == 0


def test_priority_category_change_needs_reason(client, db, w, hd):
    req = seed_request(db, w)
    cat2 = make_category(db, w.org, "Plumbing")
    url = f"{API}/requests/{req.id}"
    r = client.patch(url, json={"priority": "HIGH"}, headers=hd["disp"])
    assert r.status_code == 422 and r.json()["error"]["details"][0]["field"] == "reason"
    r = client.patch(url, json={"priority": "HIGH", "reason": "no"}, headers=hd["disp"])
    assert r.status_code == 422
    r = client.patch(
        url, json={"priority": "HIGH", "reason": "Water damage risk"}, headers=hd["disp"]
    )
    assert r.status_code == 200 and r.json()["priority"] == "HIGH"
    r = client.patch(
        url, json={"category_id": str(cat2.id), "reason": "Actually a pipe"}, headers=hd["disp"]
    )
    assert r.status_code == 200 and r.json()["category"]["id"] == str(cat2.id)
    ev = db.scalars(
        select(RequestEvent).where(
            RequestEvent.request_id == req.id, RequestEvent.type == "PRIORITY_CHANGED"
        )
    ).one()
    assert ev.data == {"from": "NORMAL", "to": "HIGH", "reason": "Water damage risk"}
    assert ev.actor_membership_id == w.disp[1].id
    audit = db.scalars(
        select(AuditEvent).where(AuditEvent.action == "request.priority_change")
    ).one()
    assert audit.before == {"priority": "NORMAL"} and audit.after["priority"] == "HIGH"
    assert db.scalars(
        select(AuditEvent).where(AuditEvent.action == "request.category_change")
    ).one()
    off = make_category(db, w.org, "Off", enabled=False)
    r = client.patch(
        url, json={"category_id": str(off.id), "reason": "try disabled"}, headers=hd["disp"]
    )
    assert r.status_code == 422
    # requesters cannot change them; requesters never see the staff-only events
    assert client.patch(url, json={"priority": "LOW"}, headers=hd["req1"]).status_code == 403
    types = [
        e["type"]
        for e in client.get(f"{API}/requests/{req.id}", headers=hd["req1"]).json()["timeline"]
    ]
    assert "PRIORITY_CHANGED" not in types


def test_requester_edit_only_while_submitted(client, db, w, hd):
    req = seed_request(db, w)
    url = f"{API}/requests/{req.id}"
    r = client.patch(url, json={"title": "New better title"}, headers=hd["req1"])
    assert r.status_code == 200 and r.json()["title"] == "New better title"
    types = [e["type"] for e in r.json()["timeline"]]
    assert types == ["REQUEST_UPDATED"]
    assert client.patch(url, json={"title": "x"}, headers=hd["req1"]).status_code == 422
    assert (
        client.patch(url, json={"title": "Staff edit title"}, headers=hd["disp"]).status_code == 403
    )
    assert client.patch(url, json={"title": "other"}, headers=hd["req2"]).status_code == 404
    client.post(f"{API}/requests/{req.id}/triage", json={}, headers=hd["disp"])
    r = client.patch(url, json={"description": LONG_DESC + " more"}, headers=hd["req1"])
    assert r.status_code == 409


def test_duplicate_link(client, db, w, hd):
    a, b = seed_request(db, w), seed_request(db, w)
    url = f"{API}/requests/{a.id}/duplicate"
    reason = {"reason": "Same leak reported twice"}
    assert (
        client.post(
            url, json={"duplicate_of_id": str(b.id), **reason}, headers=hd["req1"]
        ).status_code
        == 403
    )
    assert (
        client.post(
            url, json={"duplicate_of_id": str(a.id), **reason}, headers=hd["disp"]
        ).status_code
        == 422
    )
    r = client.post(url, json={"duplicate_of_id": str(b.id), **reason}, headers=hd["disp"])
    assert r.status_code == 200 and r.json()["duplicate_of"]["number"] == b.number
    back = client.post(
        f"{API}/requests/{b.id}/duplicate",
        json={"duplicate_of_id": str(a.id), **reason},
        headers=hd["disp"],
    )
    assert back.status_code == 422
    other = make_world(db, "Org B")
    foreign = seed_request(db, other)
    r = client.post(url, json={"duplicate_of_id": str(foreign.id), **reason}, headers=hd["disp"])
    assert r.status_code == 422
    assert db.scalars(select(RequestEvent).where(RequestEvent.type == "DUPLICATE_LINKED")).one()


def test_requests_persist(client, db, w, hd):
    rid = client.post(f"{API}/requests", json=payload(w), headers=hd["req1"]).json()["id"]
    db.expire_all()
    assert db.get(ServiceRequest, rid) is not None
