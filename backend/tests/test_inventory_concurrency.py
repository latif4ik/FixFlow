"""E2E-06 / INV-04 / INV-05: last-units race and concurrent replay (real PostgreSQL)."""

import uuid
from decimal import Decimal

from sqlalchemy import func, select

from app.models import AuditEvent, MaterialUsage, StockMovement
from tests.p3_helpers import in_progress_job, make_item, stock_of
from tests.sched_helpers import API
from tests.test_assignment_concurrency import race

ITERATIONS = 4


def consumer(req_id, item_id, qty, headers, cmd=None):
    url = f"{API}/requests/{req_id}/materials"
    body = {
        "client_command_id": cmd or str(uuid.uuid4()),
        "item_id": str(item_id),
        "quantity": str(qty),
    }

    def call(c):
        return c.post(url, json=body, headers=headers)

    return call


def counts(db, item_id):
    db.expire_all()
    usages = db.scalar(
        select(func.count()).select_from(MaterialUsage).where(MaterialUsage.item_id == item_id)
    )
    moves = db.scalar(
        select(func.count())
        .select_from(StockMovement)
        .where(StockMovement.item_id == item_id, StockMovement.kind == "CONSUMPTION")
    )
    return usages, moves


def test_last_units_two_jobs_exactly_one_wins(client, db, sw, hd):
    """Different requests (so no request-row serialization): the conditional UPDATE decides."""
    for _ in range(ITERATIONS):
        a = in_progress_job(client, db, sw, hd)
        # the same technician cannot hold two overlapping jobs; use tech2 for the second one
        b = _in_progress_for(client, db, sw, hd, "tech2", sw.tech2)
        item = make_item(db, sw.w.org, stock="5", price=1000)
        res = race(
            client.app,
            [
                consumer(a.id, item.id, 4, hd["tech"]),
                consumer(b.id, item.id, 4, hd["tech2"]),
            ],
        )
        assert sorted(r.status_code for r in res) == [201, 409], [r.text for r in res]
        loser = next(r for r in res if r.status_code == 409).json()["error"]
        assert loser["code"] == "insufficient_stock"
        assert Decimal(loser["details"]["available"]) == 1
        assert stock_of(db, item.id) == Decimal("1")
        assert counts(db, item.id) == (1, 1)
        n = db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.action == "inventory.consume",
                AuditEvent.after["item_id"].astext == str(item.id),
            )
        )
        assert n == 1


def test_last_units_same_job_two_threads(client, db, sw, hd):
    for _ in range(ITERATIONS):
        req = in_progress_job(client, db, sw, hd)
        item = make_item(db, sw.w.org, stock="5")
        res = race(
            client.app,
            [consumer(req.id, item.id, 4, hd["tech"]), consumer(req.id, item.id, 4, hd["tech"])],
        )
        assert sorted(r.status_code for r in res) == [201, 409], [r.text for r in res]
        assert stock_of(db, item.id) == Decimal("1")
        assert counts(db, item.id) == (1, 1)


def test_concurrent_replay_same_command_id_decrements_once(client, db, sw, hd):
    for _ in range(ITERATIONS):
        req = in_progress_job(client, db, sw, hd)
        item = make_item(db, sw.w.org, stock="10", price=300)
        cmd = str(uuid.uuid4())
        res = race(
            client.app,
            [
                consumer(req.id, item.id, 3, hd["tech"], cmd),
                consumer(req.id, item.id, 3, hd["tech"], cmd),
                consumer(req.id, item.id, 3, hd["tech"], cmd),
            ],
        )
        codes = sorted(r.status_code for r in res)
        assert codes == [200, 200, 201], [r.text for r in res]
        assert len({r.json()["id"] for r in res}) == 1
        assert stock_of(db, item.id) == Decimal("7")
        assert counts(db, item.id) == (1, 1)


def test_concurrent_same_command_id_across_requests_is_safe(client, db, sw, hd):
    """Same client_command_id raced on two different requests: unique key arbitrates, the
    loser's decrement is rolled back with it (savepoint)."""
    a = in_progress_job(client, db, sw, hd)
    b = _in_progress_for(client, db, sw, hd, "tech2", sw.tech2)
    item = make_item(db, sw.w.org, stock="10")
    cmd = str(uuid.uuid4())
    res = race(
        client.app,
        [consumer(a.id, item.id, 2, hd["tech"], cmd), consumer(b.id, item.id, 2, hd["tech2"], cmd)],
    )
    assert 201 in [r.status_code for r in res]
    assert all(r.status_code in (201, 409) for r in res), [r.text for r in res]
    assert stock_of(db, item.id) == Decimal("8")
    assert counts(db, item.id) == (1, 1)


def _in_progress_for(client, db, sw, hd, who, tech):
    from tests.p3_helpers import _day
    from tests.sched_helpers import assign, local_slot, triaged

    req = triaged(db, sw.w)
    _day[0] += 1
    s, e = local_slot(_day[0], 10)
    assert assign(client, hd, req, tech, s, e).status_code == 201
    assert client.post(f"{API}/requests/{req.id}/accept", headers=hd[who]).status_code == 200
    assert client.post(f"{API}/requests/{req.id}/start", headers=hd[who]).status_code == 200
    return req
