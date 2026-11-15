# Known limitations and risk notes

Covers DOC-04 and SEC-09. Nothing listed here is presented as finished. Each item was checked against the code in this
repository. Test names refer to files under `backend/tests/`; "run" commands assume the stack from the README is up
(except pytest, which uses the separate `fixflow_test` database).

## 1. Security and reliability risk notes (SEC-09)

| # | Risk | Mitigation | Status | Reproduce / verify |
|---|---|---|---|---|
| R1 | **Double-booking a technician under concurrent assignment** (two dispatchers click Assign at once). | PostgreSQL `EXCLUDE USING gist` on `(technician, tstzrange[start,end))` for active assignments; loser maps to `409 schedule_conflict`. No in-process lock. | Mitigated | `python3 scripts/simulate_race.py assignment` -> one 201, one 409. `uv run pytest tests/test_assignment_concurrency.py tests/test_assignment_db.py`. |
| R2 | **Negative or double-charged stock** when two technicians consume the last units, or a client retries. | Conditional `UPDATE ... WHERE stock >= q`, `CHECK (stock_quantity >= 0)`, unique `(org, client_command_id)`, one transaction with the usage row. | Mitigated | `python3 scripts/simulate_race.py inventory` and `replay`. `uv run pytest tests/test_inventory_concurrency.py`. |
| R3 | **Cross-organization data access** (IDOR via ids, headers, files, notifications, SSE). | `X-Org-Id` re-verified against membership on every request; all queries org-scoped; foreign rows answer 404; composite FKs; per-recipient notification filter; stream tickets bound to membership. | Mitigated, covered by tests | `uv run pytest tests/test_tenancy.py tests/test_files.py tests/test_stream.py`; `bash scripts/smoke.sh` includes a cross-org 404. |
| R4 | **Credential brute force on `/auth/login`.** | DB-backed throttle shared by all workers: 10 failures per email hash / 30 per IP in 15 min -> 429. Argon2id hashing, constant-ish time for unknown emails, failed attempts recorded without passwords. | **Partially mitigated.** The IP is the TCP peer (`request.client.host`); behind a reverse proxy every client would share one IP and `X-Forwarded-For` is not trusted. There is no CAPTCHA or account lockout notification. | `uv run pytest tests/test_auth.py -k rate_limit`. Manually: 11 wrong passwords for one email return 429 on the 11th (do not do this on the demo account, it locks it for 15 minutes). |
| R5 | **Session theft.** Web keeps the opaque bearer token in `sessionStorage` (readable by any XSS); mobile uses `flutter_secure_storage`. | Tokens expire (12 h default), can be revoked server-side, stored only hashed in the DB; React escapes output; strict CORS allow-list, no cookies. | Accepted for this scope. No refresh-token rotation, no CSP header configured. | `sessions` table holds only `token_hash`; `grep -rn sessionStorage web/src/lib/auth/session.ts`. |
| R6 | **Cleartext transport.** Android app and compose stack use plain HTTP (`usesCleartextTraffic`, no TLS terminator). | None beyond being local-only; passwords are argon2-hashed at rest but travel unencrypted on the LAN. | Accepted for local demo; **must not be deployed as is.** | `mobile/android/.../network_security_config.xml`; `curl -v http://localhost:8000/api/v1/health/live`. |
| R7 | **Evidence file storage durability and abuse.** | Content sniffing (JPEG/PNG/WebP), 10 MiB and pixel limits, sanitized names, server-generated paths, authenticated downloads, failed uploads leave no record. Files live on one Docker volume with **no replication, backup or antivirus scanning**. | Partially mitigated | `uv run pytest tests/test_files.py`. `docker compose down` keeps the `uploads` volume; `docker compose down -v` deletes it together with the database. |
| R8 | **Live updates missed.** SSE is a hint channel; a worker's `LISTEN` connection can drop. | Client refetches canonical state on every (re)connect and on `resync`; reconnect with backoff; slow consumers dropped. | Mitigated by design; delivery is best effort | `uv run pytest tests/test_stream.py`; stop and start the db container with the web app open and watch the queue refetch. |
| R9 | **Database outage.** | `/health/ready` returns 503, mutations return 5xx instead of success, clients keep drafts (mobile outbox). | Mitigated | `uv run pytest tests/test_health.py -k ready_503`; `docker compose stop db; curl -i localhost:8000/api/v1/health/ready`; `docker compose start db`. |

## 2. Incomplete or partial functionality

- **No email, SMS or push delivery.** Notifications are in-app only (web inbox with live unread count, Android
  inbox). The Android app polls the unread count while open; there is no FCM/background delivery. This matches PROD-05 but
  means a technician is not alerted when the app is closed.
- **Android is technician-only** (as required). Requesters, dispatchers and admins use the web app only. The Android
  offline queue supports **notes and images** only; every other action is online-only by design (MOB-08). The mobile
  suite counts and any open items are in [mobile/README.md](../mobile/README.md).
- **Request detail for technicians lacks asset serial number and property contact instructions.** The request detail
  payload's asset block has only `code` and `name` and the property block `name` and `address` (`AssetBrief`,
  `PropertyBrief` in `backend/app/schemas/requests.py`), although ROLE-03 allows technicians to see them for assigned
  jobs. They exist on `/assets/{id}` and `/properties/{id}` but those are staff-oriented screens.
- **Admin list filters are not reflected in the URL** (web), so filtered admin lists cannot be bookmarked or shared and
  reset on reload.
- **Navigation collapses into a drawer below 1536 px** wide; on typical laptop widths the full sidebar is not shown.
  All routes remain reachable, but it is an extra click.
- **No internationalization.** UI and API are English only (allowed by DOC-07).
- **Duplicate detection is manual** (a dispatcher links a request to the one it duplicates), as REQ-03 permits.
- **Reports** use the documented utilization definition (planned assignment minutes / available minutes); no CSV/PDF
  export.

## 3. Demo-data and environment caveats

- **Seed dates anchor to the first seed run** (the organization's creation date). A demo database that is several days
  old shows overdue/upcoming items relative to that old anchor, and appointment windows such as "18 Nov 14:00" in
  scripts drift. Before demonstrating or recording, run
  `docker compose exec -T backend python -m app.cli reset-demo --yes-destroy-local-data` (destroys local data; refuses
  non-local hosts and `ENVIRONMENT=production`).
- `scripts/smoke.sh` and `scripts/simulate_race.py` write real data to the running database (scratch requests,
  stock top-ups). They clean up what they can but are for the development database only.
- The Android debug APK is about 220 MB and needs Flutter 3.47.9, Android SDK 36 and Java 21 to build. Tested on the
  `Medium_Phone` emulator (API URL `http://10.0.2.2:8000`); a physical device is supported by setting the server URL in the
  app but was not tested on real hardware in this submission.
- Tooling note: `mobile/pubspec.yaml` overrides `path_provider_foundation` to avoid a macOS SDK linking issue on
  some hosts (iOS/macOS-only package, unused here).

## 4. Architectural limits (single-node assumptions)

- **Files on one volume.** `UPLOAD_DIR=/data/uploads` is a local Docker volume. Horizontal scaling across hosts would
  need shared or object storage.
- **Two uvicorn workers, fixed.** Correctness does not depend on this (constraints live in Postgres), but there is no
  autoscaling or supervisor beyond Docker.
- **SSE uses one `LISTEN` connection per API worker.** Capacity is bounded by Postgres connections and in-process
  queues (`STREAM_QUEUE_SIZE`); a `NOTIFY` payload is limited to a few KB so events carry ids only. A PgBouncer in
  transaction-pooling mode would break `LISTEN`.
- **Login throttling and SSE tickets are stored in PostgreSQL** (shared by workers) at the cost of a write per failed
  login or ticket.
- **No background scheduler in production.** SLA escalation and maintenance generation run by CLI/endpoint on demand
  (SLA-07, PM-05); nothing runs them periodically unless the operator adds cron/systemd.
- **Soft deletion model.** Users, categories, assets, inventory items and organizations are deactivated or retired, not
  deleted; there is no UI to purge data.
