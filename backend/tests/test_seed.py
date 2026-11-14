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
    assert first["service_requests"] == 28 and first["work_notes"] == 14 + 2 * 12
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
    assert page["total"] == 14
    assert {i["status"] for i in page["items"]} == {
        "SUBMITTED",
        "TRIAGED",
        "CANCELED",
        "REOPENED",
        "SCHEDULED",
        "ACCEPTED",
        "IN_PROGRESS",
        "BLOCKED",
        "COMPLETED",
        "CLOSED",
    }
    first = next(i for i in page["items"] if i["title"] == "Rooftop AC not cooling")
    detail = client.get(f"/api/v1/requests/{first['id']}", headers=hd).json()
    assert [n["visibility"] for n in detail["notes"]] == ["PUBLIC"]
    assert detail["timeline"][0]["type"] == "REQUEST_CREATED"


def _login(client, email):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": "demo1234"})
    assert r.status_code == 200, r.text
    org = r.json()["memberships"][0]["organization"]["id"]
    return {**h(r.json()["token"]), "X-Org-Id": org}


def test_seeded_assignments_and_collision_candidate(client, db, db_engine):
    from sqlalchemy import select

    from app.models import Assignment
    from app.models.enums import AssignmentStatus

    seed(db)
    seed(db)  # second run adds nothing (also covered by counts above)
    per_org = db.execute(
        text("SELECT organization_id, status, count(*) FROM assignments GROUP BY 1, 2")
    ).all()
    by_status = {}
    for _, st, n in per_org:
        by_status[st] = by_status.get(st, 0) + n
    assert by_status == {"ACTIVE": 10, "COMPLETED": 6}  # 5 active + 3 completed per org
    assert db.scalar(select(Assignment).limit(1)) is not None
    assert AssignmentStatus.ACTIVE.value in by_status

    disp = _login(client, "dispatcher@northwind.demo")
    page = client.get("/api/v1/requests?page_size=50", headers=disp).json()["items"]
    collision = next(i for i in page if i["title"] == "Chiller noise in the server room")
    assert collision["status"] == "TRIAGED"
    detail = client.get(f"/api/v1/requests/{collision['id']}", headers=disp).json()
    start, end = detail["preferred_window_start"], detail["preferred_window_end"]
    cands = client.get(
        f"/api/v1/requests/{collision['id']}/candidates",
        params={"start_at": start, "end_at": end},
        headers=disp,
    ).json()
    skilled = [c for c in cands if c["name"].startswith("Technician Three")]
    assert skilled and skilled[0]["eligible"] is False
    assert [r["code"] for r in skilled[0]["reasons"]] == ["overlap"]
    assert not any(c["eligible"] for c in cands)  # nobody else has the hvac skill
    r = client.post(
        f"/api/v1/requests/{collision['id']}/assignment",
        json={
            "technician_membership_id": skilled[0]["membership_id"],
            "start_at": start,
            "end_at": end,
        },
        headers=disp,
    )
    assert r.status_code == 422 and r.json()["error"]["details"]["reasons"][0]["code"] == "overlap"

    # technician1 sees only their own jobs through /me/assignments
    t1 = _login(client, "technician1@northwind.demo")
    mine = {
        sc: client.get(f"/api/v1/me/assignments?scope={sc}", headers=t1).json()["items"]
        for sc in ("upcoming", "active", "history")
    }
    assert [i["request"]["status"] for i in mine["upcoming"]] == ["SCHEDULED"]
    assert [i["request"]["status"] for i in mine["active"]] == ["BLOCKED"]
    assert [i["request"]["status"] for i in mine["history"]] == ["COMPLETED"]

    # the schedule view loads for the week, and seeded data has no drift conflicts
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    sch = client.get(
        "/api/v1/schedule",
        params={
            "from": (now - timedelta(days=7)).isoformat(),
            "to": (now + timedelta(days=7)).isoformat(),
        },
        headers=disp,
    )
    assert sch.status_code == 200
    items = [a for t in sch.json()["technicians"] for a in t["assignments"]]
    assert len(items) == 8 and not any(a["conflict"] for a in items)

    # org isolation: Ala-Too dispatcher cannot see the Northwind request
    at = _login(client, "dispatcher@alatoo.demo")
    assert client.get(f"/api/v1/requests/{collision['id']}", headers=at).status_code == 404
