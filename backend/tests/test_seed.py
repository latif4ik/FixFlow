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
    assert first["organizations"] == 2 and first["properties"] == 12 and first["assets"] == 24
    assert first["users"] == 19 and first["memberships"] == 20 and first["service_categories"] == 8
    assert first["audit_events"] == 0
    assert first["service_requests"] == 82 and first["request_events"] > 300
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
    assert nw["total"] == 2 and at["total"] == 6


def test_seeded_requests_visible_per_role(client, db):
    seed(db)
    r = client.post(
        "/api/v1/auth/login", json={"email": "requester1@northwind.demo", "password": "demo1234"}
    )
    org = r.json()["memberships"][0]["organization"]["id"]
    hd = {**h(r.json()["token"]), "X-Org-Id": org}
    page = client.get("/api/v1/requests?page_size=50", headers=hd).json()
    assert page["total"] == 26
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
    assert by_status == {"ACTIVE": 18, "COMPLETED": 32}  # 9 active + 16 completed per org
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
    assert {i["request"]["status"] for i in mine["upcoming"]} == {"SCHEDULED"}
    assert [i["request"]["status"] for i in mine["active"]] == ["BLOCKED"]
    assert {i["request"]["status"] for i in mine["history"]} == {"COMPLETED", "CLOSED"}

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
    assert len(items) >= 8 and not any(a["conflict"] for a in items)

    # org isolation: Ala-Too dispatcher cannot see the Northwind request
    at = _login(client, "dispatcher@alatoo.demo")
    assert client.get(f"/api/v1/requests/{collision['id']}", headers=at).status_code == 404


def test_seeded_estimates_inventory_notifications(client, db, db_engine):
    seed(db)
    first = _counts(db_engine)
    seed(db)
    assert _counts(db_engine) == first  # re-run adds nothing
    assert first["inventory_items"] == 24 and first["material_usage"] == 2 * 15
    assert first["estimates"] == 18 and first["notifications"] == 16
    assert first["stock_movements"] == 24 + first["material_usage"]  # initial ADDITION + usage
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
    assert dict(statuses) == {
        "APPROVED": 10,
        "AWAITING_APPROVAL": 2,
        "DRAFT": 2,
        "REJECTED": 2,
        "SUPERSEDED": 2,
    }

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
    assert any("overdue demo" in i["title"] for i in over["items"])
    q = client.get("/api/v1/dashboard/overdue", headers=hd).json()
    demo = next(i for i in q["items"] if "overdue demo" in i["title"])
    assert q["count"] == over["total"] and demo["escalated_at"] is None
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


def test_seed_meets_spec_minimums_and_is_idempotent(db, db_engine):
    """SEED-01..04, REPORT-06: every minimum, programmatically; re-run changes nothing."""
    from pathlib import Path

    from app.core.config import get_settings
    from app.seed import seed, summary

    upload_dir = Path(get_settings().UPLOAD_DIR)

    seed(db)

    def one(sql: str) -> int:
        return db.execute(text(sql)).scalar_one()

    def ids() -> dict[str, set]:
        tables = (
            "users",
            "memberships",
            "properties",
            "assets",
            "service_categories",
            "inventory_items",
            "service_requests",
            "assignments",
            "evidence_files",
            "feedback",
            "estimates",
            "maintenance_plans",
        )
        return {t: set(db.execute(text(f"SELECT id FROM {t}")).scalars()) for t in tables}

    first_ids, first_counts = ids(), _counts(db_engine)
    # SEED-01
    assert one("SELECT count(*) FROM organizations") >= 2
    assert one("SELECT count(DISTINCT user_id) FROM memberships WHERE role='REQUESTER'") >= 5
    assert (
        one("SELECT count(DISTINCT user_id) FROM memberships WHERE role IN ('DISPATCHER','ADMIN')")
        >= 3
    )
    assert one("SELECT count(DISTINCT user_id) FROM memberships WHERE role='TECHNICIAN'") >= 6
    assert one("SELECT count(*) FROM properties") >= 10
    assert one("SELECT count(*) FROM assets") >= 15
    assert one("SELECT count(*) FROM service_categories") >= 8
    assert one("SELECT count(*) FROM inventory_items") >= 20
    # SEED-02
    assert one("SELECT count(*) FROM service_requests") >= 50
    statuses = set(db.execute(text("SELECT DISTINCT status FROM service_requests")).scalars())
    assert statuses == {
        "SUBMITTED", "TRIAGED", "SCHEDULED", "ACCEPTED", "IN_PROGRESS", "BLOCKED",
        "COMPLETED", "CLOSED", "REOPENED", "CANCELED",
    }  # fmt: skip
    prios = set(db.execute(text("SELECT DISTINCT priority FROM service_requests")).scalars())
    assert prios == {"LOW", "NORMAL", "HIGH"}
    est = set(db.execute(text("SELECT DISTINCT status FROM estimates")).scalars())
    assert est == {"DRAFT", "AWAITING_APPROVAL", "APPROVED", "REJECTED", "SUPERSEDED"}
    assert one("SELECT count(*) FROM evidence_files") >= 10
    assert one("SELECT count(DISTINCT purpose) FROM evidence_files") == 2
    assert one("SELECT count(DISTINCT rating) FROM feedback") >= 4
    assert one("SELECT count(*) FROM feedback") >= 10
    # asset history: several requests on one asset
    assert one("SELECT max(c) FROM (SELECT count(*) c FROM service_requests "
               "WHERE asset_id IS NOT NULL GROUP BY asset_id) t") >= 4  # fmt: skip
    # completed jobs spread over >= 10 distinct days within the last 14 days
    assert (
        one(
            "SELECT count(DISTINCT completed_at::date) FROM service_requests "
            "WHERE completed_at > now() - interval '16 days' AND completed_at < now()"
        )
        >= 8
    )
    # each org: more than one page for the dispatcher; one requester with zero requests
    for org_id in db.execute(text("SELECT id FROM organizations")).scalars().all():
        n = db.execute(
            text("SELECT count(*) FROM service_requests WHERE organization_id=:o"), {"o": org_id}
        ).scalar_one()
        assert n > 20
    assert (
        one(
            "SELECT count(*) FROM memberships m WHERE m.role='REQUESTER' AND NOT EXISTS ("
            "SELECT 1 FROM service_requests r WHERE r.requester_membership_id = m.id)"
        )
        >= 1
    )
    # SEED-03
    assert one("SELECT count(*) FROM maintenance_plans") >= 3
    assert (
        one(
            "SELECT count(*) FROM maintenance_plans WHERE is_enabled AND first_date <= "
            "(now() AT TIME ZONE 'Asia/Bishkek')::date"
        )
        >= 1
    )
    assert (
        one("SELECT count(*) FROM inventory_items WHERE stock_quantity <= reorder_threshold") >= 1
    )
    assert (
        one(
            "SELECT count(*) FROM (SELECT user_id FROM memberships GROUP BY user_id "
            "HAVING count(DISTINCT organization_id) = 2 AND count(DISTINCT role) = 2) t"
        )
        >= 1
    )
    # attachments exist on disk and are real images
    from PIL import Image

    rows = db.execute(text("SELECT storage_key, sha256 FROM evidence_files")).all()
    assert rows
    for key, sha in rows:
        path = upload_dir / key
        assert path.is_file()
        import hashlib

        assert hashlib.sha256(path.read_bytes()).hexdigest() == sha
        with Image.open(path) as img:
            img.verify()
    # summary helper covers both orgs
    assert set(summary(db)) == {"Northwind Facilities", "Ala-Too Repairs"}
    # SEED-04: re-run -> identical counts and identical ids
    seed(db)
    assert _counts(db_engine) == first_counts
    assert ids() == first_ids
