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
    assert first["service_requests"] == 30 and first["work_notes"] == 14 + 2 * 12
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
    assert page["total"] == 15
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


def test_seeded_estimates_inventory_notifications(client, db, db_engine):
    seed(db)
    first = _counts(db_engine)
    seed(db)
    assert _counts(db_engine) == first  # re-run adds nothing
    assert first["inventory_items"] == 20 and first["material_usage"] == 10
    assert first["estimates"] == 10 and first["estimate_lines"] == 2 * (2 + 2 + 1 + 2 + 1)
    assert first["notifications"] == 16
    assert first["stock_movements"] == 20 + 10  # initial ADDITION per item + 1 per usage
    # stock agrees with the ledger everywhere (SEED consistency)
    bad = db.execute(
        text(
            "SELECT count(*) FROM inventory_items i WHERE i.stock_quantity <> "
            "(SELECT COALESCE(sum(delta), 0) FROM stock_movements m WHERE m.item_id = i.id)"
        )
    ).scalar()
    assert bad == 0
    # totals were computed server-side style: total = labor + materials, KGS
    bad = db.execute(
        text(
            "SELECT count(*) FROM estimates e WHERE e.total_minor <> e.labor_cost_minor + "
            "e.materials_total_minor OR e.materials_total_minor <> (SELECT COALESCE("
            "sum(line_total_minor), 0) FROM estimate_lines l WHERE l.estimate_id = e.id) "
            "OR e.currency <> 'KGS'"
        )
    ).scalar()
    assert bad == 0
    statuses = db.execute(
        text("SELECT status, count(*) FROM estimates GROUP BY 1 ORDER BY 1")
    ).all()
    assert dict(statuses) == {"APPROVED": 4, "AWAITING_APPROVAL": 2, "DRAFT": 2, "SUPERSEDED": 2}

    # low-stock list is non-empty for each org's dispatcher; race-demo item has 2 units
    disp = _login(client, "dispatcher@northwind.demo")
    low = client.get("/api/v1/inventory/low-stock", headers=disp).json()
    assert {i["code"] for i in low} == {"LED-BULB-12W", "SEALANT-SIL"}
    assert next(i for i in low if i["code"] == "SEALANT-SIL")["stock_quantity"] == "2.000"
    assert client.get(
        "/api/v1/inventory/low-stock", headers=_login(client, "admin@alatoo.demo")
    ).json()

    # the EST-04 demo: technician2's ACCEPTED job has a pending estimate => start blocked
    t2 = _login(client, "technician2@northwind.demo")
    items = client.get("/api/v1/me/assignments?scope=upcoming", headers=t2).json()["items"]
    job = next(i for i in items if i["request"]["status"] == "ACCEPTED")
    assert job["estimate_status"] == "AWAITING_APPROVAL" and "start" not in job["allowed_actions"]
    r = client.post(f"/api/v1/requests/{job['request']['id']}/start", headers=t2)
    assert r.status_code == 409 and r.json()["error"]["code"] == "estimate_not_approved"
    # the owning requester approves, then the technician can start
    r1 = _login(client, "requester1@northwind.demo")
    est = client.get(f"/api/v1/requests/{job['request']['id']}/estimates", headers=r1).json()[0]
    ok = client.post(
        f"/api/v1/estimates/{est['id']}/decision",
        json={"version": est["version"], "decision": "APPROVE"},
        headers=r1,
    )
    assert ok.status_code == 200
    assert (
        client.post(f"/api/v1/requests/{job['request']['id']}/start", headers=t2).status_code == 200
    )
    # notifications: seeded unread + the new approval for the dispatcher
    unread = client.get("/api/v1/notifications/unread-count", headers=disp).json()["unread"]
    assert unread >= 3


def test_seed_sla_and_maintenance_demo_data(client, db, db_engine):
    seed(db)
    c = _counts(db_engine)
    assert c["maintenance_plans"] == 4 and c["holidays"] == 2
    r = client.post(
        "/api/v1/auth/login", json={"email": "dispatcher@northwind.demo", "password": "demo1234"}
    )
    org = r.json()["memberships"][0]["organization"]["id"]
    hd = {**h(r.json()["token"]), "X-Org-Id": org}
    over = client.get("/api/v1/requests?sla_state=OVERDUE", headers=hd).json()
    assert over["total"] == 1 and "overdue demo" in over["items"][0]["title"]
    q = client.get("/api/v1/dashboard/overdue", headers=hd).json()
    assert q["count"] == 1 and q["items"][0]["escalated_at"] is None
    plans = client.get("/api/v1/maintenance-plans", headers=hd).json()
    assert plans["total"] == 2 and all(p["next_occurrence"] for p in plans["items"])
    due = next(p for p in plans["items"] if p["recurrence"] == "WEEKLY")
    assert due["last_generated_for"] is None  # nothing generated yet: occurrences are already due
    # every seeded request has an SLA cache; finished ones keep their outcome
    with db_engine.connect() as conn:
        missing = conn.execute(
            text("SELECT count(*) FROM service_requests WHERE sla_budget_minutes IS NULL")
        ).scalar()
        stopped = conn.execute(
            text("SELECT count(*) FROM service_requests WHERE sla_stopped_at IS NOT NULL")
        ).scalar()
        assert (
            conn.execute(
                text(
                    "SELECT count(*) FROM service_requests WHERE sla_stopped_at IS NOT NULL "
                    "AND sla_outcome IS NULL"
                )
            ).scalar()
            == 0
        )
    assert missing == 0 and stopped > 0
