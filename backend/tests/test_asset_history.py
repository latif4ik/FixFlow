"""Asset detail (open work, last service, next maintenance) and history (ASSET-04/05)."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.models import Assignment, MaterialUsage
from app.models.enums import AssignmentStatus, RequestStatus
from tests.factories import h, login
from tests.p3_helpers import add_completion_file, make_item
from tests.req_helpers import make_world, seed_request
from tests.sched_helpers import API
from tests.test_maintenance import body, gen, mk

S = RequestStatus


def finished_job(db, w, title="Fixed compressor"):
    done = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
    req = seed_request(
        db, w, S.COMPLETED, asset_id=w.asset.id, title=title, completed_at=done, priority="HIGH"
    )
    db.add(
        Assignment(
            organization_id=w.org.id,
            request_id=req.id,
            technician_membership_id=w.tech[1].id,
            start_at=done - timedelta(hours=2),
            end_at=done - timedelta(hours=1),
            status=AssignmentStatus.COMPLETED,
            active=False,
            assigned_by_membership_id=w.disp[1].id,
        )
    )
    item = make_item(db, w.org, price=1500)
    for qty in ("1", "2.5"):
        db.add(
            MaterialUsage(
                organization_id=w.org.id,
                request_id=req.id,
                item_id=item.id,
                technician_membership_id=w.tech[1].id,
                quantity=Decimal(qty),
                unit_cost_minor_snapshot=1500,
                total_cost_minor=int(Decimal(qty) * 1500),
                client_command_id=uuid.uuid4(),
                payload_hash="0" * 64,
            )
        )
    db.commit()
    add_completion_file(db, w.org, req, w.tech[1])
    return req, item


def test_asset_detail_open_work_last_service_and_next_maintenance(client, db, sw, hd):
    w = sw.w
    done, _ = finished_job(db, w)
    open1 = seed_request(db, w, S.IN_PROGRESS, asset_id=w.asset.id, title="Open job one")
    seed_request(db, w, S.CLOSED, asset_id=w.asset.id, title="Old closed job")
    seed_request(db, w, S.CANCELED, asset_id=w.asset.id, title="Canceled job")
    mk(client, hd, w, first_date="2026-12-01", title="Monthly service A", recurrence="MONTHLY")
    mk(client, hd, w, first_date="2026-11-20", title="Weekly service B")
    mk(client, hd, w, first_date="2026-11-10", title="Disabled service C")
    pc = client.get(f"{API}/maintenance-plans?asset_id={w.asset.id}", headers=hd["disp"]).json()
    c = next(p for p in pc["items"] if p["title"] == "Disabled service C")
    client.patch(
        f"{API}/maintenance-plans/{c['id']}", json={"is_enabled": False}, headers=hd["disp"]
    )
    r = client.get(f"{API}/assets/{w.asset.id}", headers=hd["disp"])
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["code"] == w.asset.code
    assert {i["id"] for i in a["open_work"]} == {str(open1.id), str(done.id)}
    assert all(i["status"] not in ("CLOSED", "CANCELED") for i in a["open_work"])
    last = a["last_completed_service"]
    assert last["request"]["id"] == str(done.id) and last["completed_at"].startswith("2026-11-10")
    assert last["technician"]["membership_id"] == str(w.tech[1].id)
    nm = a["next_maintenance"]
    assert nm["title"] == "Weekly service B" and nm["date"] == "2026-11-20"
    # after generation the next date moves on
    gen(client, hd, "2026-11-20")
    nm = client.get(f"{API}/assets/{w.asset.id}", headers=hd["disp"]).json()["next_maintenance"]
    assert nm["date"] == "2026-11-27"


def test_asset_detail_for_requester_and_access_rules(client, db, sw, hd):
    w = sw.w
    mine = seed_request(db, w, S.SUBMITTED, asset_id=w.asset.id, title="My own request")
    seed_request(db, w, S.SUBMITTED, requester=w.req2[1], asset_id=w.asset.id, title="Not mine")
    mk(client, hd, w)
    r = client.get(f"{API}/assets/{w.asset.id}", headers=hd["req1"])
    assert r.status_code == 200
    assert [i["id"] for i in r.json()["open_work"]] == [str(mine.id)]
    assert r.json()["next_maintenance"] is None
    assert client.get(f"{API}/assets/{w.asset.id}", headers=hd["req2"]).status_code == 404
    assert client.get(f"{API}/assets/{w.asset.id}", headers=hd["tech"]).status_code == 403
    r = client.get(f"{API}/assets/{w.asset.id}", headers=hd["disp"])
    assert {i["id"] for i in r.json()["open_work"]} == {i["id"] for i in r.json()["open_work"]}
    assert len(r.json()["open_work"]) == 2


def test_asset_history_fields_pagination_and_access(client, db, sw, hd):
    w = sw.w
    done, item = finished_job(db, w)
    seed_request(db, w, S.CANCELED, asset_id=w.asset.id, title="Canceled job", sla_outcome="MET")
    seed_request(
        db,
        w,
        S.SUBMITTED,
        asset_id=w.other_asset.id,
        property_id=w.hidden.id,
        title="Other asset request",
    )
    r = client.get(f"{API}/assets/{w.asset.id}/history", headers=hd["disp"])
    assert r.status_code == 200, r.text
    body_ = r.json()
    assert body_["total"] == 2
    row = next(i for i in body_["items"] if i["request_id"] == str(done.id))
    assert row["status"] == "COMPLETED" and row["completed_at"].startswith("2026-11-10")
    assert row["technician"]["membership_id"] == str(w.tech[1].id)
    assert row["outcome"]["status"] == "COMPLETED"
    assert row["attachment_count"] == 1
    mats = row["materials"]
    assert mats["total_cost_minor"] == 1500 + 3750
    assert mats["items"][0]["item_id"] == str(item.id) and mats["items"][0]["quantity"] == "3.500"
    assert mats["items"][0]["total_cost_minor"] == 5250
    canceled = next(i for i in body_["items"] if i["status"] == "CANCELED")
    assert canceled["outcome"]["sla_outcome"] == "MET" and canceled["technician"] is None
    assert canceled["materials"] == {"items": [], "total_cost_minor": 0}
    page = client.get(
        f"{API}/assets/{w.asset.id}/history?page_size=1&page=2", headers=hd["admin"]
    ).json()
    assert page["total"] == 2 and len(page["items"]) == 1
    assert client.get(f"{API}/assets/{w.asset.id}/history", headers=hd["req1"]).status_code == 403
    assert client.get(f"{API}/assets/{w.asset.id}/history", headers=hd["tech"]).status_code == 403


def test_asset_history_and_detail_org_isolation(client, db, sw, hd):
    w = sw.w
    other = make_world(db, "Org B")
    hb = h(login(client, other.admin[0]), other.org)
    assert client.get(f"{API}/assets/{w.asset.id}", headers=hb).status_code == 404
    assert client.get(f"{API}/assets/{w.asset.id}/history", headers=hb).status_code == 404
    assert client.get(f"{API}/assets/{uuid.uuid4()}/history", headers=hd["disp"]).status_code == 404
    mk(client, hd, w)
    assert client.post(f"{API}/maintenance-plans", json=body(other), headers=hb).status_code == 201
    assert client.get(f"{API}/assets/{other.asset.id}", headers=hb).json()["next_maintenance"]
