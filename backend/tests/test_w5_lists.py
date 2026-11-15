"""List enrichment: technician/appointment on lists, request brief on estimates."""

from datetime import UTC, datetime, time, timedelta

from sqlalchemy import event

from tests.p3_helpers import create_est
from tests.sched_helpers import API, TZ, assign, give_availability, triaged


def _slot(days=3, hour=10):
    d = (datetime.now(TZ) + timedelta(days=days)).date()
    s = datetime.combine(d, time(hour, 0), tzinfo=TZ).astimezone(UTC)
    return s, s + timedelta(hours=1)


def test_request_list_has_technician_and_appointment(client, db, sw, hd):
    give_availability(db, sw.w.org, sw.w.tech, time(0, 0), time(23, 59), range(7))
    assigned = triaged(db, sw.w)
    plain = triaged(db, sw.w)
    s, e = _slot()
    assert assign(client, hd, assigned, sw.w.tech, s, e).status_code == 201
    r = client.get(f"{API}/requests?page_size=100", headers=hd["disp"])
    assert r.status_code == 200, r.text
    items = {i["id"]: i for i in r.json()["items"]}
    a = items[str(assigned.id)]
    assert a["technician"]["membership_id"] == str(sw.w.tech[1].id) and a["technician"]["name"]
    assert datetime.fromisoformat(a["appointment"]["start_at"]) == s
    assert datetime.fromisoformat(a["appointment"]["end_at"]) == e
    assert (
        items[str(plain.id)]["technician"] is None and items[str(plain.id)]["appointment"] is None
    )
    detail = client.get(f"{API}/requests/{assigned.id}", headers=hd["disp"]).json()
    assert detail["technician"]["membership_id"] == str(sw.w.tech[1].id)
    assert detail["appointment"]["start_at"] == detail["assignment"]["start_at"]


def test_request_list_assignment_lookup_is_batched(client, db, sw, hd):
    for _ in range(6):
        triaged(db, sw.w)
    counts = []

    def count(conn, cursor, statement, *a):
        counts.append(statement)

    eng = db.get_bind()
    event.listen(eng, "before_cursor_execute", count)
    try:
        client.get(f"{API}/requests?page_size=100", headers=hd["disp"])
        n_many = len(counts)
        counts.clear()
        client.get(f"{API}/requests?page_size=1", headers=hd["disp"])
        n_one = len(counts)
    finally:
        event.remove(eng, "before_cursor_execute", count)
    assert n_many == n_one  # query count does not grow with the number of rows


def test_overdue_items_carry_technician_and_appointment(client, db, sw, hd):
    r = client.get(f"{API}/dashboard/overdue", headers=hd["disp"])
    assert r.status_code == 200
    for i in r.json()["items"]:
        assert "technician" in i and "appointment" in i


def test_estimates_list_includes_request_brief(client, db, sw, hd):
    req = triaged(db, sw.w)
    assert create_est(client, hd, req).status_code == 201
    r = client.get(f"{API}/estimates", headers=hd["disp"])
    assert r.status_code == 200, r.text
    item = next(i for i in r.json()["items"] if i["request_id"] == str(req.id))
    assert item["request"] == {
        "id": str(req.id),
        "display_id": f"REQ-{req.number}",
        "title": req.title,
    }
