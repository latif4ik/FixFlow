# Verification

Covers QA-01..09 and DOC-05. It states what to run, what each check covers, and the latest real results. Remaining
failures and gaps are listed at the end and in [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).

## 1. One command: `scripts/verify-all.sh`

```bash
docker compose up -d db          # PostgreSQL must be reachable (the script checks and tells you if not)
./scripts/verify-all.sh          # backend, then web, then mobile; stops at the first failure with a non-zero exit
```

Flags: `SKIP_BACKEND=1`, `SKIP_WEB=1`, `SKIP_MOBILE=1`. `TEST_DATABASE_URL` defaults to
`postgresql+psycopg://fixflow:fixflow-dev-password@localhost:5432/fixflow_test`; the backend tests refuse databases whose
name does not contain "test", so the demo/production database is never touched. No private keys or paid services are
needed (QA-07).

The script runs exactly the QA-05 commands:

| Area | Commands (from the component folder) |
|---|---|
| `backend/` | `uv sync --frozen`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run ty check .`, `uv run pytest -q` |
| `web/` | `bun install --frozen-lockfile`, `bun run lint`, `bun run typecheck`, `bun run test:ci`, `bun run build` |
| `mobile/` | `flutter pub get`, `dart format --output=none --set-exit-if-changed lib test integration_test`, `flutter analyze`, `flutter test`, `flutter build apk --debug` |

## 2. Test counts and coverage

| Suite | Count | Result |
|---|---|---|
| Backend (pytest, 42 files) | **526** tests | all pass (latest run below) |
| Web (Vitest + MSW, 32 files) | **131** tests | all pass (latest run below) |
| Mobile (flutter test) | <!-- MOBILE_COUNT --> see [mobile/README.md](../mobile/README.md) | |

What the tests cover, mapped to QA-01..03:

- **Backend (QA-01):** lifecycle permissions and invalid transitions (`test_lifecycle.py`); organization isolation
  (`test_tenancy.py`, `test_property_access.py`, files/notifications/stream/reports/audit tests); estimate versioning,
  immutability and simultaneous approval (`test_estimates.py`); schedule overlap and concurrent assignment against real
  PostgreSQL (`test_assignment_db.py`, `test_assignment_concurrency.py`, `test_eligibility.py`); idempotency replay and
  key mismatch (`test_assignments_api.py`, `test_estimates.py`, `test_inventory.py`); inventory concurrency
  (`test_inventory_concurrency.py`); SLA business hours, holidays, pauses, escalation (`test_sla_calendar.py`,
  `test_sla_engine.py`, `test_sla_api.py`, `test_sla_escalation.py`); recurring-generation de-duplication including
  simultaneous runs (`test_maintenance.py`); protected file downloads (`test_files.py`); migrations vs models
  (`test_migrations.py`); readiness failing when the DB is down (`test_health.py`); CLI and seed (`test_cli.py`,
  `test_seed.py`).
- **Web (QA-02):** required-field validation on forms, list filter/search, protected routes/actions, and UI state after
  a successful backend-driven mutation (mock service worker backed; see `web/src/**/*.test.tsx`).
- **Mobile (QA-03):** assignment presentation, offline queue persistence across a closed and reopened database, idempotent
  replay, and the replay-conflict state (`mobile/test/outbox_test.dart`, `sync_controller_test.dart`,
  `outbox_ui_test.dart`, ...), plus an emulator integration test (`mobile/integration_test/`) and a live-backend test
  (`mobile/test/live/outbox_live_test.dart`).
- **Lint/format/type (QA-04):** ruff + ty (backend), eslint + strict `tsc` (web), `dart format` + `flutter analyze` (mobile).
- **Real tests, not placeholders (QA-06):** `web/package.json` declares `lint`, `typecheck`, `test:ci`, `build`.

## 3. Real HTTP smoke test (QA-08)

```bash
docker compose up -d --build
docker compose exec backend python -m app.cli reset-demo --yes-destroy-local-data   # or: ... seed
bash scripts/smoke.sh        # API_URL defaults to http://localhost:8000
```

41 checks through real HTTP against the running seeded stack. Positive path: requester creates a HIGH request ->
dispatcher triages -> candidates and assign (with `Idempotency-Key` and replay) -> technician accepts, starts, adds a
note, uploads a completion PNG, completes -> requester closes and leaves feedback -> timeline and reports. Negative
path: cross-organization 404, requester triage 403, overlapping assignment 409/422, invalid token 401. Exit status is
non-zero on the first unexpected result and the script prints `SMOKE OK: N checks passed` at the end. It writes
scratch data to the running database and is re-runnable.

## 4. Concurrency simulation (SEED-06, E2E-02/06)

```bash
python3 scripts/simulate_race.py all     # or: assignment | inventory | replay
```

Releases parallel HTTP requests with a barrier and checks: two dispatchers booking the same technician -> exactly one
201 and one 409; two technicians consuming more than the low-stock item holds -> one 201, one 409 `insufficient_stock`,
stock never negative; the same `client_command_id` sent twice in parallel -> exactly one usage record. Exit 0 only if all
invariants hold.

## 5. Android (E2E-01/04/05/10, MOB-10)

```bash
cd mobile && flutter build apk --debug       # -> mobile/build/app/outputs/flutter-apk/app-debug.apk
adb install -r build/app/outputs/flutter-apk/app-debug.apk
LIVE_API_URL=http://localhost:8000 flutter test test/live      # real-backend offline-queue test (writes demo data)
```

Manual cross-component check on the emulator (`Medium_Phone`, API `http://10.0.2.2:8000`): web dispatcher assigns a job,
it appears in the technician's inbox; the technician accepts/starts, goes offline (dev "Simulate offline" toggle), adds a
note and a photo, restarts the app, reconnects: exactly one note and one attachment exist on the server and show up in
the web timeline. Reassigning the job while the app is offline leaves the draft in a visible conflict state. Details: [mobile/README.md](../mobile/README.md).
<!-- MOBILE_RESULTS: lead to fill in the final mobile test count, APK size and emulator walkthrough result -->

## 6. Latest real run

`SKIP_MOBILE=1 ./scripts/verify-all.sh` on the development machine (macOS, Apple Silicon; uv 0.12.13, Bun 1.4.4,
Docker 29.7.2, PostgreSQL 17 in compose), 2026-11-15, mobile skipped because it was being modified at the time:

```
Backend:  uv sync --frozen            ok
          ruff check .                All checks passed!
          ruff format --check .       152 files already formatted
          ty check .                  All checks passed!
          pytest -q                   526 passed, 16 warnings in 295.02s (0:04:55)
Web:      bun install --frozen-lockfile  ok
          bun run lint / typecheck    ok
          bun run test:ci             Test Files 32 passed (32), Tests 131 passed (131)
          bun run build               ok (Next.js 16.4.6 production build)
Summary:  backend: PASS (299s)   web: PASS (17s)   mobile: SKIPPED
          PASS: all required checks passed in 316s
```

Not covered by that run (see section 5): the mobile steps, `smoke.sh` and `simulate_race.py`
(both write to the running demo database, so they were not part of this run; run them as in sections 3 and 4). <!-- MOBILE_RESULTS_RUN: replace with the full verify-all.sh output after the mobile agent finishes -->

## 7. Remaining failures and gaps

No failing automated check at the time of writing. Known gaps (not test failures) are in
[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md): no email/push delivery, tested only on an emulator (no physical device), single-node
file storage, three small web/detail-screen gaps.
