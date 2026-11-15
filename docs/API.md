# FixFlow API

Covers API-01, API-02, API-09 and DOC-02. Base URL (local): `http://localhost:8000/api/v1`.

- **OpenAPI JSON:** `GET /api/v1/openapi.json`
- **Interactive docs (Swagger UI):** http://localhost:8000/api/v1/docs
- The web client's types are generated from this schema (`cd web && bun run gen:api`).

Generated OpenAPI lists every field; this document explains conventions and shows real flows.

## 1. Conventions

### Authentication and headers

| Header | Used on | Meaning |
|---|---|---|
| `Authorization: Bearer <token>` | everything except `/auth/login` and `/health/*` | Opaque session token from login (stored server-side only as a hash). |
| `X-Org-Id: <organization uuid>` | every org-scoped route (all except login/logout, `/me`, health) | Explicit organization selection (ROLE-02). The server re-verifies membership on every request. |
| `Idempotency-Key: <1-128 chars>` | optional, on assignment, reassignment, unassign, decline, estimate create/lines/submit/decision/withdraw, stock additions/adjustments, `POST /maintenance-plans/generate` | Retrying with the same key and same payload replays the original response; same key with a different payload returns `409 idempotency_key_reused`. |
| `X-Request-ID` | optional in, always out | Trace id echoed in the response and in every error body. |

Retry identity for **notes**, **file uploads** and **material consumption** uses a body field instead:
`client_command_id` (UUID, plus `client_index` for files). Replaying returns `200` with the original record
(`Idempotent-Replayed: true` on materials) instead of `201`.

`GET /me` and `GET /me/membership` are the current-user / current-membership endpoints (AUTH-04). `GET /me` needs only
the Bearer token and lists memberships; `GET /me/membership` also needs `X-Org-Id`.

### Error format

Every error uses one JSON shape:

```json
{ "error": { "code": "schedule_conflict", "message": "The technician was just booked for an overlapping time. Pick another slot.",
             "details": { "technician_membership_id": "...", "start_at": "...", "end_at": "..." },
             "request_id": "c0a8..." } }
```

| Status | Typical `code` | When |
|---|---|---|
| 400 | `org_required` | Missing/invalid `X-Org-Id`. |
| 401 | `unauthorized`, `session_expired` | Missing, invalid, revoked or expired token. |
| 403 | `forbidden`, `org_access_denied` | Role not allowed; not a member of the org. |
| 404 | `not_found` | Missing **or in another organization** (no existence leak). |
| 409 | `conflict`, `schedule_conflict`, `insufficient_stock`, `idempotency_key_reused`, invalid transition | State/concurrency conflicts. |
| 413 | | Body over the size cap. |
| 422 | `validation_error` | Field errors; `details` is a list of `{field, message}`. |
| 429 | `too_many_requests` | Login rate limit. |

### Pagination

List endpoints take `page` (1-based, default 1) and `page_size` (default 20, **max 100**; env `DEFAULT_PAGE_SIZE` /
`MAX_PAGE_SIZE`) and return `{ "items": [...], "total": n, "page": 1, "page_size": 20 }`.

### Roles

`R` requester, `D` dispatcher, `A` admin, `T` technician. "Staff" = D + A. The table shows the intended audience;
finer rules (own requests only, assigned jobs only) are enforced server-side per resource.

## 2. Endpoints

All paths are relative to `/api/v1`.

### Health and auth
| Method | Path | Notes |
|---|---|---|
| GET | `/health/live` | Liveness, no DB. |
| GET | `/health/ready` | Readiness; 503 when the database is unreachable. |
| POST | `/auth/login` | `{email, password}` -> `{token, expires_at, user, memberships[]}`. Rate limited. |
| POST | `/auth/logout` | 204; revokes the session. |
| GET | `/me` | User + active memberships (org selector). |
| GET | `/me/membership` | Current membership for `X-Org-Id`. |

### Organization and staff (admin unless noted)
| Method | Path | Notes |
|---|---|---|
| GET / PATCH | `/org` | Settings, timezone. |
| GET / PUT | `/org/business-hours` | Weekly intervals. |
| GET / POST | `/org/holidays` | Dates excluded from SLA time. |
| DELETE | `/org/holidays/{holiday_id}` | |
| GET / POST | `/org/members` | Staff list / create. |
| PATCH | `/org/members/{membership_id}` | Role, activation (no platform role exists). |
| GET | `/audit` | Immutable audit timeline, paginated. |
| GET / POST / PATCH | `/skills`, `/skills/{id}` | Skill catalog. |
| GET / POST / PATCH | `/categories`, `/categories/{id}` | Service categories (disable, not delete). |
| GET | `/technicians`, `/technicians/me`, `/technicians/{membership_id}` | Technician profiles. |
| PUT | `/technicians/{membership_id}/skills` | |
| PUT | `/technicians/{membership_id}/availability` | Weekly availability. |
| POST / DELETE | `/technicians/{membership_id}/time-off[/{id}]` | |

### Properties and assets
| Method | Path | Notes |
|---|---|---|
| GET / POST | `/properties` | Requesters see only granted properties. |
| GET / PATCH | `/properties/{property_id}` | |
| GET / POST | `/properties/{property_id}/access` | Who may request here (ASSET-03). |
| DELETE | `/properties/{property_id}/access/{membership_id}` | Revoke. |
| GET / POST | `/assets` | Asset list / create; requesters see only assets of granted properties. |
| GET / PATCH | `/assets/{asset_id}` | Detail (open work, last service, next maintenance) / update (retire via status). |
| GET | `/assets/{asset_id}/history` | Service history. |

### Requests and lifecycle
| Method | Path | Notes |
|---|---|---|
| POST | `/requests` | Create (requester, or staff on behalf). |
| GET | `/requests` | Filters: `status`, `priority`, `category_id`, `property_id`, `asset_id`, `q`, `created_from`, `created_to`, `sla_state`, `technician_id`; `sort=newest\|oldest\|priority\|due`. |
| GET / PATCH | `/requests/{id}` | Detail incl. `allowed_actions`, SLA, estimate state. |
| POST | `/requests/{id}/duplicate` | Link this request to the one it duplicates (`duplicate_of_id`, `reason`). |
| POST | `/requests/{id}/triage` `/cancel` `/close` `/reopen` | Lifecycle wrappers. |
| POST | `/requests/{id}/transitions` | Generic `{to_status, reason, note}`. |
| POST | `/requests/{id}/accept` `/start` `/block` `/resume` `/complete` | Technician actions. |
| GET | `/requests/{id}/timeline` | Chronological activity. |
| GET / POST | `/requests/{id}/notes` | `client_command_id` makes POST replay-safe; `visibility` PUBLIC/INTERNAL. |
| POST | `/requests/{id}/files` | multipart: `file`, `purpose` (INTAKE/NOTE/COMPLETION), optional `client_command_id`, `client_index`. JPEG/PNG/WebP <= 10 MiB. |
| GET | `/files/{file_id}` | Authenticated download. |
| POST | `/requests/{id}/feedback` | Requester rating 1-5 after completion. |

### Assignments and scheduling
| Method | Path | Notes |
|---|---|---|
| GET | `/requests/{id}/candidates` | Eligibility list with reasons, workload. |
| GET | `/requests/{id}/suggestions` | Smart Assign slots (see [PRODUCT_DECISIONS.md](PRODUCT_DECISIONS.md)). |
| POST / PUT | `/requests/{id}/assignment` | Assign (201) / reschedule. Body `{technician_membership_id, start_at, end_at}`. |
| POST | `/requests/{id}/assignment/unassign` | |
| POST | `/requests/{id}/decline` | Technician declines before starting. |
| GET | `/requests/{id}/assignments` | History. |
| GET | `/me/assignments` | Technician inbox. |
| GET | `/schedule` | Day/week workload timeline. |

### Estimates and inventory
| Method | Path | Notes |
|---|---|---|
| POST / GET | `/requests/{id}/estimates` | Create new version / list versions. |
| GET | `/estimates`, `/estimates/{id}` | |
| PATCH / PUT | `/estimates/{id}`, `/estimates/{id}/lines` | Draft only. |
| POST | `/estimates/{id}/submit` `/decision` `/withdraw` | Decision body `{version, decision: APPROVE\|REJECT, reason}`. |
| GET / POST | `/inventory`, `/inventory/{id}` (GET/PATCH) | Items. |
| GET | `/inventory/low-stock` | At or below reorder threshold. |
| POST | `/inventory/{id}/additions`, `/adjustments` | Stock movements. |
| GET | `/inventory/{id}/movements` | Ledger. |
| POST / GET | `/requests/{id}/materials` | Consume `{client_command_id, item_id, quantity}` / list. |

### SLA, maintenance, reports, notifications, live
| Method | Path | Notes |
|---|---|---|
| GET | `/dashboard/overdue` | Overdue queue and counts. |
| POST | `/admin/sla/escalate` | Same as CLI `sla-escalate`. |
| GET / POST | `/maintenance-plans`, `/maintenance-plans/{id}` (GET/PATCH) | Plans, history, next occurrence. |
| POST | `/maintenance-plans/generate` | `{as_of}`; idempotent. |
| GET | `/reports/summary`, `/reports/daily`, `/reports/distribution` | Staff. Filters `from`, `to`, category, technician. |
| GET | `/notifications`, `/notifications/unread-count` | Own notifications only. |
| POST | `/notifications/read-all`, `/notifications/{id}/read` | |
| POST | `/stream/ticket` | 60 s ticket. |
| GET | `/stream?ticket=...` | `text/event-stream` live updates. |

## 3. Examples

Set once (demo credentials are disposable):

```bash
API=http://localhost:8000/api/v1
```

**Login** and pick the organization:

```bash
curl -s $API/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"dispatcher@northwind.demo","password":"demo1234"}'
# -> {"token":"<opaque>","expires_at":"...","user":{...},
#     "memberships":[{"membership_id":"...","organization":{"id":"<ORG>","name":"Northwind Facilities"},"role":"DISPATCHER"}]}
TOKEN=<token from the response>; ORG=<organization.id from memberships>
```

**List requests** (overdue and high priority, newest first, page 1):

```bash
curl -s "$API/requests?priority=HIGH&sla_state=OVERDUE&sort=due&page=1&page_size=20" \
  -H "Authorization: Bearer $TOKEN" -H "X-Org-Id: $ORG"
# -> {"items":[{...}],"total":3,"page":1,"page_size":20}
```

**Create a request** (requester token; ids come from `/categories` and `/properties`):

```bash
curl -s $API/requests -H "Authorization: Bearer $TOKEN" -H "X-Org-Id: $ORG" \
  -H 'Content-Type: application/json' \
  -d '{"title":"Sparking socket in meeting room","description":"Socket near the window sparks when plugged in.",
       "category_id":"<CATEGORY>","property_id":"<PROPERTY>","priority":"HIGH"}'
```

**Triage and assign** (dispatcher; the `Idempotency-Key` makes a network retry safe):

```bash
curl -s -X POST $API/requests/$REQ/triage -H "Authorization: Bearer $TOKEN" -H "X-Org-Id: $ORG" \
  -H 'Content-Type: application/json' -d '{}'

curl -s -X POST $API/requests/$REQ/assignment -H "Authorization: Bearer $TOKEN" -H "X-Org-Id: $ORG" \
  -H 'Content-Type: application/json' -H 'Idempotency-Key: assign-req14-tech1-v1' \
  -d '{"technician_membership_id":"<TECH>","start_at":"2026-11-18T08:00:00Z","end_at":"2026-11-18T09:30:00Z"}'
# 201 -> {"assignment":{...,"status":"ACTIVE"},"request":{"display_id":"REQ-14","status":"SCHEDULED"}}
```

Repeating the same command with the same key and body returns the original response; the same key with a different
body returns `409 idempotency_key_reused`.

**Scheduling conflict** (a second assignment overlapping the same technician; the loser of a true race gets 409, an
overlap detected up front by the eligibility check is reported as a 422 with the reason):

```bash
curl -s -X POST $API/requests/$OTHER_REQ/assignment -H "Authorization: Bearer $TOKEN" -H "X-Org-Id: $ORG" \
  -H 'Content-Type: application/json' \
  -d '{"technician_membership_id":"<TECH>","start_at":"2026-11-18T08:30:00Z","end_at":"2026-11-18T09:30:00Z"}'
# 409 {"error":{"code":"schedule_conflict","message":"The technician was just booked for an overlapping time. Pick another slot.",
#               "details":{"technician_membership_id":"<TECH>","start_at":"...","end_at":"..."},"request_id":"..."}}
```

Adjacent windows (one ends at 09:30, the next starts at 09:30) are accepted because ranges are half-open. The concurrent
case is reproduced by `python3 scripts/simulate_race.py assignment`.

**Offline replay commands** (what the Android outbox sends; safe to repeat):

```bash
# 1. evidence image, keyed by command id + index
curl -s -X POST $API/requests/$REQ/files -H "Authorization: Bearer $TOKEN" -H "X-Org-Id: $ORG" \
  -F file=@photo.jpg -F purpose=NOTE -F client_command_id=7b0c2f0e-5d3a-4a8e-9a53-1d6a5f0c1111 -F client_index=0
# 201 first time, 200 + the same record on replay

# 2. the note, same command id
curl -s -X POST $API/requests/$REQ/notes -H "Authorization: Bearer $TOKEN" -H "X-Org-Id: $ORG" \
  -H 'Content-Type: application/json' \
  -d '{"body":"Replaced the breaker.","visibility":"PUBLIC","client_command_id":"7b0c2f0e-5d3a-4a8e-9a53-1d6a5f0c1111","attachment_ids":["<FILE_ID>"]}'
# 201 first time, 200 on replay: exactly one note and one file exist server-side.

# Material consumption, replay-safe; a second concurrent consumption of the last units gets 409 insufficient_stock
curl -s -X POST $API/requests/$REQ/materials -H "Authorization: Bearer $TOKEN" -H "X-Org-Id: $ORG" \
  -H 'Content-Type: application/json' \
  -d '{"client_command_id":"0d9c5b2e-1111-4a8e-9a53-1d6a5f0c2222","item_id":"<ITEM>","quantity":2}'
```

If the job was reassigned or closed before the replay, notes/files return 403/404/409; the mobile app keeps the draft
and shows a conflict state ([mobile docs](../mobile/ARCHITECTURE_NOTES.md)).

**Live updates:**

```bash
curl -s -X POST $API/stream/ticket -H "Authorization: Bearer $TOKEN" -H "X-Org-Id: $ORG"   # -> {"ticket":"...","expires_at":"..."}
curl -N "$API/stream?ticket=<ticket>"                                                         # -> event: ready ...
```
