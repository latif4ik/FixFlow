#!/usr/bin/env bash
# FixFlow smoke test: drives a RUNNING, SEEDED backend through real HTTP.
#
#   docker compose up -d --build backend
#   docker compose exec backend python -m app.cli seed        # (or reset-demo --yes-destroy-local-data)
#   bash scripts/smoke.sh                                      # API_URL defaults to http://localhost:8000
#
# Positive path: requester creates a HIGH request -> dispatcher triages -> candidates/assign
# (Idempotency-Key + replay) -> technician accepts, starts, adds a note, uploads a completion PNG,
# completes -> requester closes + leaves feedback -> timeline and reports checked.
# Negative path: cross-org 404, requester triage 403, overlapping assignment 409/422, bad token 401.
# Re-runnable: it searches future business-day windows for a free technician each run and cancels
# its scratch request. Needs bash, curl, python3 (no jq). Exits 1 on the first unexpected result.
# Uses the DISPOSABLE demo credentials (password demo1234) created by the seed.
set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"
BASE="$API_URL/api/v1"
PASSWORD="${DEMO_PASSWORD:-demo1234}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
PASSED=0
CODE=""
RESP=""

pass() { PASSED=$((PASSED + 1)); echo "PASS  $1"; }
fail() {
  echo "FAIL  $1" >&2
  echo "      status=$CODE body=$RESP" >&2
  exit 1
}

# J <json> <python expression over d>  -> prints the value
J() { python3 -c 'import json,sys; d=json.loads(sys.argv[1]); print(eval(sys.argv[2]))' "$1" "$2"; }

TOKEN=""
ORG=""
as() { TOKEN="$(eval echo "\${TOK_$1}")"; ORG="$(eval echo "\${ORG_$1}")"; }

# req <label> <expected codes, | separated> <METHOD> <path> [json body] [extra curl args...]
req() {
  local label="$1" expected="$2" method="$3" path="$4" body="${5:-}"
  shift 5 2>/dev/null || shift $#
  local args=(-sS -o "$TMP/body" -w '%{http_code}' -X "$method" "$BASE$path")
  [ -n "$TOKEN" ] && args+=(-H "Authorization: Bearer $TOKEN")
  [ -n "$ORG" ] && args+=(-H "X-Org-Id: $ORG")
  if [ -n "$body" ]; then args+=(-H 'Content-Type: application/json' --data "$body"); fi
  CODE="$(curl "${args[@]}" "$@" || true)"
  RESP="$(cat "$TMP/body" 2>/dev/null || true)"
  case "|$expected|" in
    *"|$CODE|"*) pass "$label ($CODE)" ;;
    *) fail "$label (expected $expected)" ;;
  esac
}

login() { # login <key> <email> <org name fragment>
  local out
  out="$(curl -sS -X POST "$BASE/auth/login" -H 'Content-Type: application/json' \
    --data "{\"email\":\"$2\",\"password\":\"$PASSWORD\"}")" || { CODE=000; RESP="$out"; fail "login $2"; }
  RESP="$out"
  local tok org mem
  tok="$(J "$out" 'd["token"]' 2>/dev/null)" || { CODE=?; fail "login $2"; }
  org="$(J "$out" "[m['organization']['id'] for m in d['memberships'] if '$3' in m['organization']['name']][0]")"
  mem="$(J "$out" "[m['membership_id'] for m in d['memberships'] if '$3' in m['organization']['name']][0]")"
  eval "TOK_$1='$tok'; ORG_$1='$org'; MEM_$1='$mem'"
  pass "login $2"
}

echo "== smoke against $API_URL =="
TOKEN=""; ORG=""
req "health live" 200 GET /health/live
req "health ready" 200 GET /health/ready

login req requester1@northwind.demo Northwind
login disp dispatcher@northwind.demo Northwind
login t1 technician1@northwind.demo Northwind
login t2 technician2@northwind.demo Northwind
login t3 technician3@northwind.demo Northwind
login t4 technician4@northwind.demo Northwind
login ala admin@alatoo.demo Ala-Too

# ---- catalog lookups ----
as req
req "requester lists granted properties" 200 GET "/properties?page_size=50"
PROP="$(J "$RESP" "d['items'][0]['id']")"
as disp
req "dispatcher lists categories" 200 GET "/categories?page_size=50"
CAT="$(J "$RESP" "[c['id'] for c in d['items'] if c['name']=='Electrical'][0]")"

create_request() { # create_request <title> -> sets REQ_ID (as requester)
  as req
  req "requester creates HIGH request" 201 POST /requests \
    "{\"title\":\"$1\",\"description\":\"Smoke test: outlet sparks when used, please inspect soon.\",\"category_id\":\"$CAT\",\"property_id\":\"$PROP\",\"priority\":\"HIGH\"}"
  REQ_ID="$(J "$RESP" "d['id']")"
  [ "$(J "$RESP" "d['status']")" = "SUBMITTED" ] || fail "new request is SUBMITTED"
}

new_request() { # new_request <title> -> create + triage, sets REQ_ID
  create_request "$1"
  as disp
  req "dispatcher triages" 200 POST "/requests/$REQ_ID/triage" '{"note":"Smoke test triage."}'
  [ "$(J "$RESP" "d['status']")" = "TRIAGED" ] || fail "request is TRIAGED"
}

new_request "Smoke test: sparking outlet $(date +%s)"
R1="$REQ_ID"

# ---- find a free future window with an eligible technician ----
WINDOW_FOUND=""
for off in $(seq 7 400); do
  read -r START END < <(python3 - "$off" <<'PY'
import sys, datetime as dt
d = dt.date.today() + dt.timedelta(days=int(sys.argv[1]))
if d.weekday() >= 5:
    print("SKIP SKIP")
else:  # 10:00-11:00 Asia/Bishkek (UTC+6) = 04:00-05:00Z
    print(f"{d}T04:00:00Z {d}T05:00:00Z")
PY
)
  [ "$START" = "SKIP" ] && continue
  CODE=; RESP="$(curl -sS -G "$BASE/requests/$R1/candidates" -H "Authorization: Bearer $TOKEN" \
    -H "X-Org-Id: $ORG" --data-urlencode "start_at=$START" --data-urlencode "end_at=$END")"
  TECH="$(J "$RESP" "next((c['membership_id'] for c in d if c['eligible']), '')" 2>/dev/null || true)"
  if [ -n "$TECH" ]; then WINDOW_FOUND=1; break; fi
done
[ -n "$WINDOW_FOUND" ] || { CODE=-; fail "no eligible technician in any future window"; }
pass "candidates: eligible technician for $START"
TECH_KEY=""
for k in t1 t2 t3 t4; do
  [ "$(eval echo "\${MEM_$k}")" = "$TECH" ] && TECH_KEY="$k"
done
[ -n "$TECH_KEY" ] || fail "eligible technician is not one of technician1..4"

IDEM="$(python3 -c 'import uuid; print(uuid.uuid4())')"
ASSIGN="{\"technician_membership_id\":\"$TECH\",\"start_at\":\"$START\",\"end_at\":\"$END\"}"
req "assign technician" 201 POST "/requests/$R1/assignment" "$ASSIGN" -H "Idempotency-Key: $IDEM"
FIRST="$RESP"
req "assign replay (same Idempotency-Key)" 201 POST "/requests/$R1/assignment" "$ASSIGN" -H "Idempotency-Key: $IDEM"
[ "$RESP" = "$FIRST" ] || fail "idempotent replay returned a different body"
pass "replay returned the identical response"

# ---- technician work ----
as "$TECH_KEY"
req "technician accepts" 200 POST "/requests/$R1/accept" ""
req "technician starts" 200 POST "/requests/$R1/start" ""
req "technician adds a note" "200|201" POST "/requests/$R1/notes" '{"body":"Found a loose neutral, fixing it now."}'
python3 - "$TMP/done.png" <<'PY'
import struct, sys, zlib
def chunk(t, d):
    c = struct.pack(">I", len(d)) + t + d
    return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
w = h = 8
raw = b"".join(b"\x00" + b"\x20\x90\x40" * w for _ in range(h))
png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
png += chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
open(sys.argv[1], "wb").write(png)
PY
req "technician uploads completion PNG" 201 POST "/requests/$R1/files" "" \
  -F "file=@$TMP/done.png;type=image/png" -F "purpose=COMPLETION"
req "technician completes" 200 POST "/requests/$R1/complete" \
  '{"note":"Replaced the neutral terminal and tested the outlet under load."}'
[ "$(J "$RESP" "d['status']")" = "COMPLETED" ] || fail "request is COMPLETED"

# ---- requester closes + feedback ----
as req
req "requester closes" 200 POST "/requests/$R1/close" '{"reason":"Confirmed working, thanks."}'
[ "$(J "$RESP" "d['status']")" = "CLOSED" ] || fail "request is CLOSED"
req "requester submits feedback" 201 POST "/requests/$R1/feedback" '{"rating":5,"comment":"Smoke test feedback."}'

# ---- timeline + reports ----
as disp
req "timeline" 200 GET "/requests/$R1/timeline?page_size=100"
python3 - "$RESP" <<'PY' || fail "timeline events in expected order"
import json, sys
items = json.loads(sys.argv[1])["items"]
seen = [(i["type"], i["to_status"]) for i in items]
want = [("REQUEST_CREATED", "SUBMITTED"), ("STATUS_CHANGED", "TRIAGED"), ("ASSIGNED", None),
        ("STATUS_CHANGED", "SCHEDULED"), ("STATUS_CHANGED", "ACCEPTED"),
        ("STATUS_CHANGED", "IN_PROGRESS"), ("FILE_UPLOADED", None),
        ("STATUS_CHANGED", "COMPLETED"), ("STATUS_CHANGED", "CLOSED"),
        ("FEEDBACK_SUBMITTED", None)]
it = iter(seen)
missing = [w for w in want if not any(s == w for s in it)]
if missing:
    print("missing/out of order:", missing, "seen:", seen, file=sys.stderr)
    sys.exit(1)
PY
pass "timeline contains the expected events in order"
req "reports summary reachable" 200 GET /reports/summary

# ---- expected failures ----
as ala
req "Ala-Too admin cannot see a Northwind request (cross-org)" 404 GET "/requests/$R1"
create_request "Smoke test: triage probe $(date +%s)"
R3="$REQ_ID"
req "requester cannot triage (403)" 403 POST "/requests/$R3/triage" '{"note":"Nope."}'
req "requester cancels the triage probe" 200 POST "/requests/$R3/cancel" '{"reason":"Smoke test cleanup."}'
# R1 is finished, so its window is free again: book it with R2, then try to double-book with R4.
new_request "Smoke test: booking probe $(date +%s)"
R2="$REQ_ID"
req "assign scratch request into the freed window" 201 POST "/requests/$R2/assignment" "$ASSIGN"
new_request "Smoke test: overlap probe $(date +%s)"
R4="$REQ_ID"
as disp
req "overlapping assignment rejected (409 schedule_conflict / 422 ineligible)" "409|422" \
  POST "/requests/$R4/assignment" "$ASSIGN"
case "$CODE:$RESP" in
  409:*schedule_conflict*|422:*technician_ineligible*) pass "error code is schedule_conflict/technician_ineligible" ;;
  *) fail "unexpected error code for overlap" ;;
esac
req "dispatcher cancels booking probe" 200 POST "/requests/$R2/cancel" '{"reason":"Smoke test cleanup."}'
req "dispatcher cancels overlap probe" 200 POST "/requests/$R4/cancel" '{"reason":"Smoke test cleanup."}'
TOKEN="not-a-real-token"; ORG=""
req "invalid token rejected" 401 GET /requests

echo "== SMOKE OK: $PASSED checks passed against $API_URL =="
