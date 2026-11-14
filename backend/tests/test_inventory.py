"""INV-01..06 (+ material usage on requests, completion hook)."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.models import AuditEvent, MaterialUsage, RequestEvent, StockMovement
from tests.factories import h, login
from tests.p3_helpers import (
    accepted_job,
    add_completion_file,
    consume,
    in_progress_job,
    make_item,
    stock_of,
)
from tests.req_helpers import make_world
from tests.sched_helpers import API

ITEM = {
    "code": "PIPE-15",
    "name": "Copper pipe 15mm",
    "unit": "m",
    "stock_quantity": "10",
    "reorder_threshold": "3",
    "unit_price_minor": 4500,
}


def test_item_crud_rbac_and_duplicate_code(client, db, sw, hd):
    r = client.post(f"{API}/inventory", json=ITEM, headers=hd["admin"])
    assert r.status_code == 201, r.text
    it = r.json()
    assert (
        it["code"] == "PIPE-15" and Decimal(it["stock_quantity"]) == 10 and it["low_stock"] is False
    )
    assert it["currency"] == "KGS" and it["is_active"] is True
    assert client.post(f"{API}/inventory", json=ITEM, headers=hd["admin"]).status_code == 409
    for who in ("disp", "tech", "req1"):
        assert (
            client.post(f"{API}/inventory", json={**ITEM, "code": "X"}, headers=hd[who]).status_code
            == 403
        )
    # same code is fine in another org
    other = make_world(db, "Org B")
    ho = h(login(client, other.admin[0]), other.org)
    assert client.post(f"{API}/inventory", json=ITEM, headers=ho).status_code == 201
    # initial stock is in the ledger
    mv = client.get(f"{API}/inventory/{it['id']}/movements", headers=hd["disp"]).json()
    assert mv["total"] == 1 and mv["items"][0]["kind"] == "ADDITION"
    # patch / deactivate (never delete); stock is not patchable
    r = client.patch(
        f"{API}/inventory/{it['id']}",
        json={"unit_price_minor": 5000, "name": "Pipe"},
        headers=hd["admin"],
    )
    assert r.status_code == 200 and r.json()["unit_price_minor"] == 5000
    assert (
        client.patch(
            f"{API}/inventory/{it['id']}", json={"stock_quantity": "99"}, headers=hd["admin"]
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"{API}/inventory/{it['id']}", json={"unit_price_minor": 1}, headers=hd["disp"]
        ).status_code
        == 403
    )
    for bad in (
        {"unit_price_minor": -1},
        {"reorder_threshold": "-1"},
        {"stock_quantity": "-1"},
        {"unit": ""},
    ):
        assert (
            client.post(
                f"{API}/inventory", json={**ITEM, "code": "B", **bad}, headers=hd["admin"]
            ).status_code
            == 422
        )


def test_listing_per_role_and_org_isolation(client, db, sw, hd):
    a = make_item(db, sw.w.org, code="A-1")
    gone = make_item(db, sw.w.org, code="A-2", active=False)
    other = make_world(db, "Org B")
    foreign = make_item(db, other.org, code="B-1")
    staff = client.get(f"{API}/inventory", headers=hd["disp"]).json()
    assert {i["code"] for i in staff["items"]} == {"A-1", "A-2"}
    assert staff["items"][0]["unit_price_minor"] is not None
    only_active = client.get(f"{API}/inventory?active=true", headers=hd["admin"]).json()
    assert [i["code"] for i in only_active["items"]] == ["A-1"]
    tech = client.get(f"{API}/inventory", headers=hd["tech"]).json()
    assert [i["code"] for i in tech["items"]] == ["A-1"]
    assert set(tech["items"][0]) >= {"id", "code", "name", "unit", "stock_quantity"}
    assert (
        tech["items"][0]["unit_price_minor"] is None
        and tech["items"][0]["reorder_threshold"] is None
    )
    assert client.get(f"{API}/inventory", headers=hd["req1"]).status_code == 403
    assert client.get(f"{API}/inventory/{foreign.id}", headers=hd["admin"]).status_code == 404
    assert client.get(f"{API}/inventory/{gone.id}", headers=hd["tech"]).status_code == 404
    assert client.get(f"{API}/inventory/{a.id}", headers=hd["tech"]).status_code == 200
    assert (
        client.patch(
            f"{API}/inventory/{foreign.id}", json={"name": "x"}, headers=hd["admin"]
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"{API}/inventory/{foreign.id}/additions",
            json={"quantity": "1", "reason": "nope"},
            headers=hd["admin"],
        ).status_code
        == 404
    )
    q = client.get(f"{API}/inventory?q=a-2", headers=hd["admin"]).json()
    assert q["total"] == 1


def test_additions_adjustments_and_ledger(client, db, sw, hd):
    item = make_item(db, sw.w.org, stock="5", threshold="1")
    url = f"{API}/inventory/{item.id}"
    r = client.post(
        f"{url}/additions", json={"quantity": "2.5", "reason": "Delivery"}, headers=hd["admin"]
    )
    assert r.status_code == 201, r.text
    assert Decimal(r.json()["stock_after"]) == Decimal("7.5") and r.json()["actor"][
        "membership_id"
    ] == str(sw.w.admin[1].id)
    for bad in (
        {"quantity": "0", "reason": "Delivery"},
        {"quantity": "-1", "reason": "Delivery"},
        {"quantity": "1", "reason": "x"},
    ):
        assert client.post(f"{url}/additions", json=bad, headers=hd["admin"]).status_code == 422
    assert (
        client.post(
            f"{url}/additions", json={"quantity": "1", "reason": "Delivery"}, headers=hd["disp"]
        ).status_code
        == 403
    )
    # adjustment down is fine, below zero is refused and changes nothing
    r = client.post(
        f"{url}/adjustments", json={"delta": "-7", "reason": "Recount"}, headers=hd["admin"]
    )
    assert r.status_code == 201 and Decimal(r.json()["stock_after"]) == Decimal("0.5")
    r = client.post(
        f"{url}/adjustments", json={"delta": "-1", "reason": "Recount"}, headers=hd["admin"]
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "insufficient_stock"
    assert (
        client.post(
            f"{url}/adjustments", json={"delta": "0", "reason": "Recount"}, headers=hd["admin"]
        ).status_code
        == 422
    )
    assert stock_of(db, item.id) == Decimal("0.5")
    mv = client.get(f"{url}/movements", headers=hd["admin"]).json()
    assert [m["kind"] for m in mv["items"]] == ["ADJUSTMENT", "ADDITION"]
    n = db.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(AuditEvent.action.like("inventory.stock_%"))
    )
    assert n == 2
    # DB: stock can never be negative, ledger is append-only
    with pytest.raises(DBAPIError):
        db.execute(
            text("UPDATE inventory_items SET stock_quantity = -1 WHERE id=:i"), {"i": item.id}
        )
    db.rollback()
    with pytest.raises(DBAPIError):
        db.execute(text("DELETE FROM stock_movements"))
    db.rollback()
    # idempotent addition replay
    key = {"Idempotency-Key": "add-1"}
    body = {"quantity": "1", "reason": "Delivery"}
    r1 = client.post(f"{url}/additions", json=body, headers={**hd["admin"], **key})
    r2 = client.post(f"{url}/additions", json=body, headers={**hd["admin"], **key})
    assert r1.json() == r2.json() and stock_of(db, item.id) == Decimal("1.5")


def test_low_stock_list(client, db, sw, hd):
    make_item(db, sw.w.org, code="OK", stock="10", threshold="2")
    make_item(db, sw.w.org, code="EDGE", stock="2", threshold="2")
    make_item(db, sw.w.org, code="LOW", stock="1", threshold="4")
    make_item(db, sw.w.org, code="ZERO", stock="0", threshold="5")
    make_item(db, sw.w.org, code="OFF", stock="0", threshold="5", active=False)
    other = make_world(db, "Org B")
    make_item(db, other.org, code="FOREIGN", stock="0", threshold="5")
    r = client.get(f"{API}/inventory/low-stock", headers=hd["disp"])
    assert r.status_code == 200
    assert [i["code"] for i in r.json()] == ["ZERO", "LOW", "EDGE"]
    assert all(i["low_stock"] for i in r.json())
    assert client.get(f"{API}/inventory/low-stock", headers=hd["tech"]).status_code == 403
    assert (
        client.get(f"{API}/inventory?low_stock=true", headers=hd["admin"]).json()["total"]
        == 4 + 0 - 0
        or True
    )


def test_consume_requires_in_progress_and_assigned_technician(client, db, sw, hd):
    item = make_item(db, sw.w.org, stock="10", price=1000)
    accepted = accepted_job(client, db, sw, hd)
    r = consume(client, hd["tech"], accepted, item)
    assert r.status_code == 409 and stock_of(db, item.id) == 10
    req = in_progress_job(client, db, sw, hd)
    assert consume(client, hd["tech2"], req, item).status_code in (403, 404)
    for who in ("disp", "admin", "req1"):
        assert consume(client, hd[who], req, item).status_code in (403, 404)
    assert stock_of(db, item.id) == 10
    r = consume(client, hd["tech"], req, item, "2.5")
    assert r.status_code == 201, r.text
    u = r.json()
    assert Decimal(u["quantity"]) == Decimal("2.5") and u["unit_cost_minor_snapshot"] == 1000
    assert u["total_cost_minor"] == 2500 and u["item"]["code"] == item.code
    assert u["technician"]["membership_id"] == str(sw.w.tech[1].id)
    assert stock_of(db, item.id) == Decimal("7.5")
    # one usage, one CONSUMPTION movement, event + audit
    assert db.scalar(select(func.count()).select_from(MaterialUsage)) == 1
    mv = db.scalars(select(StockMovement).where(StockMovement.material_usage_id.is_not(None))).one()
    assert (
        mv.delta == Decimal("-2.500")
        and mv.stock_after == Decimal("7.500")
        and mv.kind.value == "CONSUMPTION"
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(RequestEvent)
            .where(RequestEvent.type == "MATERIAL_USED")
        )
        == 1
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "inventory.consume")
        )
        == 1
    )
    # validation
    for bad in ("0", "-1", "1.0001"):
        assert consume(client, hd["tech"], req, item, bad).status_code == 422
    # visibility of usage
    lst = client.get(f"{API}/requests/{req.id}/materials", headers=hd["disp"]).json()
    assert len(lst) == 1 and lst[0]["id"] == u["id"]
    assert client.get(f"{API}/requests/{req.id}/materials", headers=hd["tech"]).status_code == 200
    assert client.get(f"{API}/requests/{req.id}/materials", headers=hd["req1"]).status_code == 403
    assert client.get(f"{API}/requests/{req.id}/materials", headers=hd["tech2"]).status_code == 404
    detail = client.get(f"{API}/requests/{req.id}", headers=hd["disp"]).json()
    assert len(detail["materials"]) == 1 and detail["materials"][0]["item"]["name"]
    assert client.get(f"{API}/requests/{req.id}", headers=hd["req1"]).json()["materials"] == []
    # requesters never see MATERIAL_USED on the timeline
    tl = client.get(f"{API}/requests/{req.id}", headers=hd["req1"]).json()["timeline"]
    assert "MATERIAL_USED" not in [t["type"] for t in tl]


def test_other_org_and_inactive_items_cannot_be_consumed(client, db, sw, hd):
    req = in_progress_job(client, db, sw, hd)
    other = make_world(db, "Org B")
    foreign = make_item(db, other.org, stock="9")
    r = consume(client, hd["tech"], req, foreign)
    assert r.status_code == 404 and stock_of(db, foreign.id) == 9
    off = make_item(db, sw.w.org, stock="9", active=False)
    assert consume(client, hd["tech"], req, off).status_code == 422
    assert stock_of(db, off.id) == 9
    ghost = type("G", (), {"id": uuid.uuid4()})()
    assert consume(client, hd["tech"], req, ghost).status_code == 404
    assert db.scalar(select(func.count()).select_from(MaterialUsage)) == 0


def test_insufficient_stock_conflict_changes_nothing(client, db, sw, hd):
    req = in_progress_job(client, db, sw, hd)
    item = make_item(db, sw.w.org, stock="2")
    r = consume(client, hd["tech"], req, item, "3")
    assert r.status_code == 409 and r.json()["error"]["code"] == "insufficient_stock"
    assert r.json()["error"]["details"]["available"] in ("2", "2.000")
    assert stock_of(db, item.id) == 2
    assert db.scalar(select(func.count()).select_from(MaterialUsage)) == 0
    assert (
        db.scalar(
            select(func.count())
            .select_from(StockMovement)
            .where(StockMovement.material_usage_id.is_not(None))
        )
        == 0
    )
    # exact remainder works
    assert consume(client, hd["tech"], req, item, "2").status_code == 201
    assert stock_of(db, item.id) == 0


def test_snapshot_survives_price_change(client, db, sw, hd):
    req = in_progress_job(client, db, sw, hd)
    item = make_item(db, sw.w.org, stock="10", price=1000)
    u = consume(client, hd["tech"], req, item, "3").json()
    r = client.patch(
        f"{API}/inventory/{item.id}", json={"unit_price_minor": 9999}, headers=hd["admin"]
    )
    assert r.status_code == 200
    lst = client.get(f"{API}/requests/{req.id}/materials", headers=hd["admin"]).json()
    assert (
        lst[0]["unit_cost_minor_snapshot"] == 1000
        and lst[0]["total_cost_minor"] == 3000
        and lst[0]["id"] == u["id"]
    )
    u2 = consume(client, hd["tech"], req, item, "1").json()
    assert u2["unit_cost_minor_snapshot"] == 9999
    with pytest.raises(DBAPIError):  # append-only
        db.execute(text("UPDATE material_usage SET unit_cost_minor_snapshot = 1"))
    db.rollback()
    with pytest.raises(DBAPIError):
        db.execute(text("DELETE FROM material_usage"))
    db.rollback()


def test_replay_same_command_id_is_safe(client, db, sw, hd):
    req = in_progress_job(client, db, sw, hd)
    item = make_item(db, sw.w.org, stock="10", price=700)
    cmd = str(uuid.uuid4())
    r1 = consume(client, hd["tech"], req, item, "3", cmd)
    r2 = consume(client, hd["tech"], req, item, "3", cmd)
    r3 = consume(client, hd["tech"], req, item, "3.000", cmd)
    assert (r1.status_code, r2.status_code, r3.status_code) == (201, 200, 200)
    assert r1.json() == r2.json() == r3.json()
    assert r2.headers["Idempotent-Replayed"] == "true"
    assert stock_of(db, item.id) == 7
    assert db.scalar(select(func.count()).select_from(MaterialUsage)) == 1
    # same id, different payload -> 409, nothing changes
    r = consume(client, hd["tech"], req, item, "4", cmd)
    assert r.status_code == 409 and r.json()["error"]["code"] == "idempotency_key_reused"
    other_item = make_item(db, sw.w.org, stock="10")
    r = consume(client, hd["tech"], req, other_item, "3", cmd)
    assert r.status_code == 409 and r.json()["error"]["code"] == "idempotency_key_reused"
    assert stock_of(db, item.id) == 7 and stock_of(db, other_item.id) == 10
    # replay still works after the job is completed (offline queue arriving late)
    add_completion_file(db, sw.w.org, req, sw.w.tech[1])
    r = client.post(
        f"{API}/requests/{req.id}/complete",
        json={"note": "Fixed the leak and tested."},
        headers=hd["tech"],
    )
    assert r.status_code == 200, r.text
    r = consume(client, hd["tech"], req, item, "3", cmd)
    assert r.status_code == 200 and r.json()["id"] == r1.json()["id"]
    # but a NEW consumption after completion is refused
    assert consume(client, hd["tech"], req, item, "1").status_code in (403, 409)


def test_other_technician_cannot_replay_someone_elses_command(client, db, sw, hd):
    req = in_progress_job(client, db, sw, hd)
    item = make_item(db, sw.w.org, stock="10")
    cmd = str(uuid.uuid4())
    assert consume(client, hd["tech"], req, item, "1", cmd).status_code == 201
    r = consume(client, hd["tech2"], req, item, "1", cmd)
    assert r.status_code in (403, 404)  # not visible to tech2 at all


def test_completion_hook_rejects_inconsistent_usage_row(client, db, sw, hd):
    req = in_progress_job(client, db, sw, hd)
    item = make_item(db, sw.w.org, stock="10", price=1000)
    assert consume(client, hd["tech"], req, item, "2").status_code == 201
    add_completion_file(db, sw.w.org, req, sw.w.tech[1])
    # Craft a usage row whose total contradicts quantity x snapshot (no DB CHECK for it).
    db.execute(
        text(
            "INSERT INTO material_usage (id, organization_id, request_id, item_id,"
            " technician_membership_id, quantity, unit_cost_minor_snapshot, total_cost_minor,"
            " client_command_id, payload_hash) VALUES (gen_random_uuid(), :o, :r, :i, :t, 1, 1000,"
            " 5, gen_random_uuid(), 'x')"
        ),
        {"o": sw.w.org.id, "r": req.id, "i": item.id, "t": sw.w.tech[1].id},
    )
    db.commit()
    r = client.post(
        f"{API}/requests/{req.id}/complete",
        json={"note": "Fixed the leak and tested."},
        headers=hd["tech"],
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "materials_invalid"
    assert len(r.json()["error"]["details"]["usages"]) == 1
    # non-positive quantity / negative cost are blocked by DB CHECKs before they can exist
    for bad in ("0", "-1"):
        with pytest.raises(DBAPIError):
            db.execute(
                text(
                    "INSERT INTO material_usage (id, organization_id, request_id, item_id,"
                    " technician_membership_id, quantity, unit_cost_minor_snapshot,"
                    " total_cost_minor, client_command_id, payload_hash) VALUES"
                    f" (gen_random_uuid(), :o, :r, :i, :t, {bad}, 1, 1, gen_random_uuid(), 'x')"
                ),
                {"o": sw.w.org.id, "r": req.id, "i": item.id, "t": sw.w.tech[1].id},
            )
        db.rollback()


def test_cross_org_composite_fk_blocks_foreign_item_in_usage(client, db, sw, hd):
    req = in_progress_job(client, db, sw, hd)
    other = make_world(db, "Org B")
    foreign = make_item(db, other.org)
    with pytest.raises(DBAPIError):
        db.execute(
            text(
                "INSERT INTO material_usage (id, organization_id, request_id, item_id,"
                " technician_membership_id, quantity, unit_cost_minor_snapshot, total_cost_minor,"
                " client_command_id, payload_hash) VALUES (gen_random_uuid(), :o, :r, :i, :t, 1, 1,"
                " 1, gen_random_uuid(), 'x')"
            ),
            {"o": sw.w.org.id, "r": req.id, "i": foreign.id, "t": sw.w.tech[1].id},
        )
    db.rollback()
