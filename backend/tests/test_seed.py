from sqlalchemy import text

from app.seed import seed
from tests.factories import h


def _counts(engine) -> dict[str, int]:
    with engine.connect() as conn:
        names = (
            conn.execute(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname='public' AND tablename <> 'alembic_version'"
                )
            )
            .scalars()
            .all()
        )
        return {n: conn.execute(text(f'SELECT count(*) FROM "{n}"')).scalar() for n in names}


def test_seed_is_idempotent_and_usable(client, db, db_engine):
    seed(db)
    first = _counts(db_engine)
    seed(db)
    assert _counts(db_engine) == first
    assert first["organizations"] == 2 and first["properties"] == 6 and first["assets"] == 12
    assert first["users"] == 15 and first["memberships"] == 16 and first["service_categories"] == 8
    assert first["audit_events"] == 0
    assert first["service_requests"] == 12 and first["work_notes"] == 14
    assert first["request_events"] > 12
    # the shared user has different roles in different orgs
    r = client.post(
        "/api/v1/auth/login", json={"email": "shared@fixflow.demo", "password": "demo1234"}
    )
    assert r.status_code == 200
    roles = {m["organization"]["name"]: m["role"] for m in r.json()["memberships"]}
    assert roles == {"Northwind Facilities": "REQUESTER", "Ala-Too Repairs": "DISPATCHER"}
    orgs = {m["organization"]["name"]: m["organization"]["id"] for m in r.json()["memberships"]}
    tok = r.json()["token"]
    nw = client.get(
        "/api/v1/properties", headers={**h(tok), "X-Org-Id": orgs["Northwind Facilities"]}
    ).json()
    at = client.get(
        "/api/v1/properties", headers={**h(tok), "X-Org-Id": orgs["Ala-Too Repairs"]}
    ).json()
    assert nw["total"] == 2 and at["total"] == 3


def test_seeded_requests_visible_per_role(client, db):
    seed(db)
    r = client.post(
        "/api/v1/auth/login", json={"email": "requester1@northwind.demo", "password": "demo1234"}
    )
    org = r.json()["memberships"][0]["organization"]["id"]
    hd = {**h(r.json()["token"]), "X-Org-Id": org}
    page = client.get("/api/v1/requests?page_size=50", headers=hd).json()
    assert page["total"] == 6
    assert {i["status"] for i in page["items"]} == {"SUBMITTED", "TRIAGED", "CANCELED", "REOPENED"}
    first = next(i for i in page["items"] if i["title"] == "Rooftop AC not cooling")
    detail = client.get(f"/api/v1/requests/{first['id']}", headers=hd).json()
    assert [n["visibility"] for n in detail["notes"]] == ["PUBLIC"]
    assert detail["timeline"][0]["type"] == "REQUEST_CREATED"
