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
