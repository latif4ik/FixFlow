"""Phase 3a helpers: accepted / in-progress jobs, estimates, inventory items."""

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from app.models import InventoryItem
from tests.sched_helpers import API, assign, local_slot, triaged

_day = [3]


def accepted_job(client, db, sw, hd, requester=None):
    """A request assigned to sw.w.tech via the API and accepted by them (ACCEPTED)."""
    kw = {"requester": requester} if requester else {}
    req = triaged(db, sw.w, **kw)
    _day[0] += 1
    s, e = local_slot(_day[0], 10)
    r = assign(client, hd, req, sw.w.tech, s, e)
    assert r.status_code == 201, r.text
    r = client.post(f"{API}/requests/{req.id}/accept", headers=hd["tech"])
    assert r.status_code == 200, r.text
    return req


def in_progress_job(client, db, sw, hd):
    req = accepted_job(client, db, sw, hd)
    r = client.post(f"{API}/requests/{req.id}/start", headers=hd["tech"])
    assert r.status_code == 200, r.text
    return req


def make_item(
    db,
    org,
    code: str | None = None,
    stock="10",
    threshold="2",
    price=1000,
    unit="pcs",
    active=True,
) -> InventoryItem:
    item = InventoryItem(
        organization_id=org.id,
        code=code or f"IT-{uuid.uuid4().hex[:6]}",
        name="Test item",
        unit=unit,
        stock_quantity=Decimal(stock),
        reorder_threshold=Decimal(threshold),
        unit_price_minor=price,
        is_active=active,
    )
    db.add(item)
    db.commit()
    return item


def stock_of(db, item_id) -> Decimal:
    return db.execute(
        text("SELECT stock_quantity FROM inventory_items WHERE id=:i"), {"i": item_id}
    ).scalar_one()


def est_body(**over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "labor_minutes": 90,
        "labor_rate_minor": 50000,  # 500.00 KGS / hour
        "notes": "Replace compressor relay",
        "lines": [
            {"description": "Relay", "quantity": "2", "unit_price_minor": 12050},
            {"description": "Cable", "quantity": "1.5", "unit_price_minor": 333},
        ],
    }
    body.update(over)
    return body


def create_est(client, hd, req, who="disp", **over):
    return client.post(f"{API}/requests/{req.id}/estimates", json=est_body(**over), headers=hd[who])


def submit_est(client, hd, est_id, who="disp"):
    r = client.post(f"{API}/estimates/{est_id}/submit", headers=hd[who])
    assert r.status_code == 200, r.text
    return r.json()


def decide(client, headers, est, decision="APPROVE", reason=None, **extra):
    body: dict[str, Any] = {"version": est["version"], "decision": decision}
    if reason:
        body["reason"] = reason
    return client.post(f"{API}/estimates/{est['id']}/decision", json=body, headers=headers, **extra)


def add_completion_file(db, org, req, membership) -> None:
    from app.models import EvidenceFile
    from app.models.enums import FilePurpose

    db.add(
        EvidenceFile(
            organization_id=org.id,
            request_id=req.id,
            uploaded_by_membership_id=membership.id,
            purpose=FilePurpose.COMPLETION,
            original_filename="done.png",
            storage_key=f"x/{uuid.uuid4()}.png",
            mime_type="image/png",
            size_bytes=1,
            width=1,
            height=1,
            sha256="0" * 64,
        )
    )
    db.commit()


def consume(client, headers, req, item, qty="1", cmd=None):
    return client.post(
        f"{API}/requests/{req.id}/materials",
        json={
            "client_command_id": cmd or str(uuid.uuid4()),
            "item_id": str(item.id),
            "quantity": str(qty),
        },
        headers=headers,
    )
