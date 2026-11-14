#!/usr/bin/env python3
"""Concurrency simulation for the FixFlow API (SEED-06, development only).

Fires genuinely parallel HTTP requests (threads released by a barrier) at a RUNNING, SEEDED
backend and checks that the invariants hold: exactly one winner, a clear error for the loser,
no lost or duplicated stock. Standard library only (urllib + threading + json), so it runs
without the project venv:

    python3 scripts/simulate_race.py assignment   # two dispatchers assign one technician to the
                                                   # same window on two TRIAGED requests
                                                   # -> one 201, one 409 schedule_conflict (or 422)
    python3 scripts/simulate_race.py inventory    # two technicians consume > half of the
                                                   # low-stock item on IN_PROGRESS jobs
                                                   # -> one 201, one 409 insufficient_stock
    python3 scripts/simulate_race.py replay       # the same client_command_id sent twice in
                                                   # parallel -> exactly one usage is recorded
    python3 scripts/simulate_race.py all          # run the three scenarios

Environment: API_URL (default http://localhost:8000), DEMO_PASSWORD (default demo1234).
Each run creates its own fresh requests (and tops up stock when needed) through the API, so it can
be repeated without a reset; scratch requests are completed/canceled afterwards. Exit code 0 only
when every invariant held. The Android offline toggle belongs to the mobile app (not here).
Uses the DISPOSABLE demo credentials created by `python -m app.cli seed`.
"""

import json
import os
import struct
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zlib
from datetime import date, timedelta
from decimal import Decimal

API = os.environ.get("API_URL", "http://localhost:8000").rstrip("/") + "/api/v1"
PASSWORD = os.environ.get("DEMO_PASSWORD", "demo1234")
NW = "Northwind"
SESSIONS: dict[str, dict] = {}


def http(method, path, body=None, who=None, headers=None, raw=None, ctype=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    h = dict(headers or {})
    if data is not None:
        h["Content-Type"] = ctype or "application/json"
    if who:
        s = SESSIONS[who]
        h["Authorization"] = f"Bearer {s['token']}"
        h["X-Org-Id"] = s["org"]
    req = urllib.request.Request(API + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = r.read()
            return r.status, (json.loads(payload) if payload else None)
    except urllib.error.HTTPError as e:
        payload = e.read()
        try:
            return e.code, json.loads(payload)
        except ValueError:
            return e.code, {"raw": payload.decode(errors="replace")}


def login(key, email):
    status, body = http("POST", "/auth/login", {"email": email, "password": PASSWORD})
    if status != 200:
        die(f"login {email} failed: {status} {body}")
    m = next(m for m in body["memberships"] if NW in m["organization"]["name"])
    SESSIONS[key] = {"token": body["token"], "org": m["organization"]["id"], "mem": m["membership_id"]}


def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


def must(status_ok, status, body, what):
    if status not in (status_ok if isinstance(status_ok, tuple) else (status_ok,)):
        die(f"{what}: unexpected {status} {json.dumps(body)[:300]}")
    return body


def parallel(calls):
    """Run callables simultaneously (barrier); returns their results in order."""
    barrier = threading.Barrier(len(calls))
    out = [None] * len(calls)

    def run(i, fn):
        barrier.wait()
        out[i] = fn()

    threads = [threading.Thread(target=run, args=(i, fn)) for i, fn in enumerate(calls)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return out


def png() -> bytes:
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\x30\x80\xc0" * 8 for _ in range(8))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def setup():
    login("req", "requester1@northwind.demo")
    login("disp", "dispatcher@northwind.demo")
    login("admin", "admin@northwind.demo")
    for n in (1, 2, 3, 4):
        login(f"t{n}", f"technician{n}@northwind.demo")


_ctx: dict = {}


def catalog():
    if not _ctx:
        s, b = http("GET", "/properties?page_size=50", who="req")
        _ctx["prop"] = must(200, s, b, "properties")["items"][0]["id"]
        s, b = http("GET", "/categories?page_size=50", who="disp")
        _ctx["cat"] = next(c["id"] for c in must(200, s, b, "categories")["items"] if c["name"] == "Electrical")
    return _ctx


def new_triaged(label):
    c = catalog()
    s, b = http(
        "POST",
        "/requests",
        {
            "title": f"Race sim: {label} {uuid.uuid4().hex[:6]}",
            "description": "Concurrency simulation request, safe to ignore or cancel.",
            "category_id": c["cat"],
            "property_id": c["prop"],
            "priority": "HIGH",
        },
        who="req",
    )
    rid = must(201, s, b, "create request")["id"]
    s, b = http("POST", f"/requests/{rid}/triage", {"note": "race simulation"}, who="disp")
    must(200, s, b, "triage")
    return rid


def free_window(rid, start_off=7, exclude=()):
    """First future business-day 10:00-11:00 (Asia/Bishkek) slot with an eligible technician."""
    for off in range(start_off, start_off + 400):
        d = date.today() + timedelta(days=off)
        if d.weekday() >= 5:
            continue
        start, end = f"{d}T04:00:00Z", f"{d}T05:00:00Z"
        q = urllib.parse.urlencode({"start_at": start, "end_at": end})
        s, cands = http("GET", f"/requests/{rid}/candidates?{q}", who="disp")
        must(200, s, cands, "candidates")
        for c in cands:
            if c["eligible"] and c["membership_id"] not in exclude:
                return start, end, c["membership_id"], off
    die("no free window found")


def tech_key(mem):
    return next(k for k, v in SESSIONS.items() if k.startswith("t") and v["mem"] == mem)


def assign(rid, window, tech, who="disp"):
    start, end = window
    return http(
        "POST",
        f"/requests/{rid}/assignment",
        {"technician_membership_id": tech, "start_at": start, "end_at": end},
        who=who,
    )


def in_progress_job(label, exclude_tech=(), start_off=7):
    rid = new_triaged(label)
    start, end, tech, off = free_window(rid, start_off, exclude_tech)
    must(201, *assign(rid, (start, end), tech), "assign job")
    who = tech_key(tech)
    s, b = http("POST", f"/requests/{rid}/accept", who=who)
    must(200, s, b, "accept")
    s, b = http("POST", f"/requests/{rid}/start", who=who)
    must(200, s, b, "start")
    return rid, who, tech, off


def finish(rid, who):
    """Best-effort cleanup: completion image + complete."""
    boundary = uuid.uuid4().hex
    parts = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="purpose"\r\n\r\nCOMPLETION\r\n'
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="x.png"\r\n'
        "Content-Type: image/png\r\n\r\n"
    ).encode() + png() + f"\r\n--{boundary}--\r\n".encode()
    http("POST", f"/requests/{rid}/files", raw=parts, who=who,
         ctype=f"multipart/form-data; boundary={boundary}")
    s, _ = http("POST", f"/requests/{rid}/complete",
                {"note": "Race simulation job finished; nothing was repaired."}, who=who)
    if s != 200:
        print(f"  (cleanup: could not complete {rid}: {s})")


def cancel(rid):
    http("POST", f"/requests/{rid}/cancel", {"reason": "race simulation cleanup"}, who="disp")


def item(code):
    s, b = http("GET", "/inventory?page_size=100", who="disp")
    return next(i for i in must(200, s, b, "inventory")["items"] if i["code"] == code)


def stock(item_id):
    s, b = http("GET", f"/inventory/{item_id}", who="disp")
    return Decimal(must(200, s, b, "item")["stock_quantity"])


def ensure_stock(item_id, at_least):
    cur = stock(item_id)
    if cur < at_least:
        s, b = http("POST", f"/inventory/{item_id}/additions",
                    {"quantity": str(at_least - cur), "reason": "race simulation top-up"}, who="admin")
        must(201, s, b, "top up stock")
    return stock(item_id)


# ---------------------------------------------------------------- scenarios
def scenario_assignment():
    print("== assignment: two dispatchers, same technician, same window ==")
    a, b = new_triaged("assign A"), new_triaged("assign B")
    start, end, tech, _ = free_window(a)
    res = parallel([
        lambda: assign(a, (start, end), tech, "disp"),
        lambda: assign(b, (start, end), tech, "admin"),
    ])
    for name, (st, body) in zip("AB", res):
        code = (body or {}).get("error", {}).get("code", "-")
        print(f"  request {name}: HTTP {st} {code}")
    codes = sorted(st for st, _ in res)
    loser = next(body for st, body in res if st != 201) if codes[0] == 201 else None
    ok = (
        codes[0] == 201
        and codes[1] in (409, 422)
        and loser["error"]["code"] in ("schedule_conflict", "technician_ineligible")
    )
    for rid in (a, b):
        cancel(rid)
    print("  RESULT:", "OK one winner, one rejected" if ok else "VIOLATION")
    return ok


def scenario_inventory():
    print("== inventory: two parallel consumptions of more than half the stock ==")
    it = item("SEALANT-SIL")
    s0 = ensure_stock(it["id"], Decimal("2"))
    qty = (s0 / 2 + Decimal("0.001")).quantize(Decimal("0.001"))
    j1 = in_progress_job("inventory 1")
    j2 = in_progress_job("inventory 2", start_off=j1[3] + 1)
    before = stock(it["id"])
    print(f"  stock before: {before} (each consumption: {qty})")
    calls = [
        lambda j=j: http(
            "POST", f"/requests/{j[0]}/materials",
            {"client_command_id": str(uuid.uuid4()), "item_id": it["id"], "quantity": str(qty)},
            who=j[1],
        )
        for j in (j1, j2)
    ]
    res = parallel(calls)
    for n, (st, body) in enumerate(res, 1):
        print(f"  consumer {n}: HTTP {st} {(body or {}).get('error', {}).get('code', '-')}")
    after = stock(it["id"])
    print(f"  stock after:  {after}")
    codes = sorted(st for st, _ in res)
    err = next((b for st, b in res if st != 201), None)
    ok = (
        codes == [201, 409]
        and err["error"]["code"] == "insufficient_stock"
        and after == before - qty
        and after >= 0
    )
    for j in (j1, j2):
        finish(j[0], j[1])
    print("  RESULT:", "OK one success, one insufficient_stock, stock consistent" if ok else "VIOLATION")
    return ok


def scenario_replay():
    print("== replay: same client_command_id sent twice in parallel ==")
    it = item("SOCKET-16A")
    ensure_stock(it["id"], Decimal("5"))
    rid, who, _, _ = in_progress_job("replay")
    before = stock(it["id"])
    cmd = str(uuid.uuid4())
    payload = {"client_command_id": cmd, "item_id": it["id"], "quantity": "1"}
    res = parallel([lambda: http("POST", f"/requests/{rid}/materials", payload, who=who)] * 2)
    for n, (st, body) in enumerate(res, 1):
        print(f"  send {n}: HTTP {st} {(body or {}).get('error', {}).get('code', '-')}")
    s, usage = http("GET", f"/requests/{rid}/materials", who=who)
    after = stock(it["id"])
    n_usage = len(usage) if s == 200 else -1
    print(f"  usages recorded: {n_usage}; stock {before} -> {after}")
    ids = {b["id"] for st, b in res if st in (200, 201)}
    ok = (
        sorted(st for st, _ in res) in ([200, 201], [201, 201])
        and n_usage == 1
        and len(ids) == 1
        and after == before - 1
    )
    finish(rid, who)
    print("  RESULT:", "OK exactly one usage recorded" if ok else "VIOLATION")
    return ok


SCENARIOS = {"assignment": scenario_assignment, "inventory": scenario_inventory, "replay": scenario_replay}


def main(argv):
    if len(argv) != 2 or argv[1] not in (*SCENARIOS, "all"):
        print(__doc__)
        return 2
    setup()
    names = list(SCENARIOS) if argv[1] == "all" else [argv[1]]
    results = [SCENARIOS[n]() for n in names]
    if all(results):
        print("ALL INVARIANTS HELD")
        return 0
    print("INVARIANT VIOLATED", file=sys.stderr)
    return 1


if __name__ == "__main__":
    t0 = time.time()
    code = main(sys.argv)
    sys.exit(code)
