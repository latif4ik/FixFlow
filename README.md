# FixFlow: field service operations platform

Demo video: <!-- VIDEO_LINK -->

FixFlow is a multi-organization service operations platform for building maintenance, equipment repair and on-site field
work. Requesters submit work, dispatchers triage and schedule it, technicians execute it, and admins configure and
audit it. Organizations are fully isolated from each other. One person can belong to several organizations with a
different role in each.

Three components share the same live PostgreSQL records:

| Component | Stack | Users | Folder |
|---|---|---|---|
| Backend API | Python 3.13, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 17 | all | [`backend/`](backend) |
| Web app | Next.js 16, React 19, TypeScript (strict), Tailwind 4, Bun | requester, dispatcher, admin | [`web/`](web) |
| Android app | Flutter (Riverpod, Drift/SQLite), Dart | technician | [`mobile/`](mobile) |

Original feature (WEB-09): **Smart Assign**, conflict-aware suggested technician slots for the dispatcher. Problem,
behavior, verification and trade-offs: [docs/PRODUCT_DECISIONS.md](docs/PRODUCT_DECISIONS.md).

## Feature status

Implemented (backend, web and Android unless noted): organization-scoped auth and roles; org switching; properties and
assets with requester access grants; request intake with images; table-driven lifecycle with audit/timeline;
technician skills, availability, time off; candidate list, Smart Assign and race-safe assignment (409 on overlap);
versioned estimates with approval gate; inventory with atomic, replay-safe consumption; business-time SLAs with
estimate pause and one-time overdue escalation; recurring maintenance plans; work notes and evidence uploads;
in-app notifications; live updates (SSE); dashboard, charts and reports; admin (business hours, holidays, categories,
skills, staff, inventory, audit); Android offline cache and outbox with conflict handling; deterministic seed, reset
command, smoke test and race simulator.

Not implemented or limited (honest list in [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md)): email/SMS/push
delivery, TLS, multi-node file storage, Android support for roles other than technician, a few small detail-screen
gaps.

## Prerequisites (versions this was developed and tested with)

| Tool | Version | Needed for |
|---|---|---|
| Docker + Compose v2 | Docker 29.7 | running the stack (the only requirement to run web + API + DB) |
| uv | 0.12 | backend local dev/tests (installs Python 3.13 from `backend/.python-version`) |
| Bun | 1.4 | web local dev/tests |
| Flutter | 3.47.9 stable (Dart 3.13.7) | Android app |
| Android SDK 36, Java 21 (e.g. JetBrains JBR 21), Android emulator or device | | building/running the APK |
| bash, curl, python3 | any recent | `scripts/smoke.sh`, `scripts/simulate_race.py` |

No paid services, API keys or external accounts are required.

## Quick start (Docker)

```bash
cp .env.example .env            # optional; every value has a working default
docker compose up -d --build    # db (5432), backend (8000), web (3000); migrations run automatically
# demo data is seeded automatically on backend start (idempotent; SEED_DEMO_DATA=false to skip)
```

| URL | What |
|---|---|
| http://localhost:3000 | Web app |
| http://localhost:8000/api/v1/docs | OpenAPI / Swagger UI (JSON at `/api/v1/openapi.json`) |
| http://localhost:8000/api/v1/health/ready | Readiness (DB-backed); `/health/live` is liveness |

Environment overrides are in `.env.example` (`API_PORT`, `WEB_PORT`, `DB_PORT`, `CORS_ORIGINS`, ...). If you change
`WEB_PORT`, add the new origin to `CORS_ORIGINS`; `NEXT_PUBLIC_API_URL` is baked into the web build (rebuild after
changing). Data persists in the `pgdata` and `uploads` volumes across `docker compose down`/`up`.

### Database and demo-data commands

All run inside the backend container (`docker compose exec backend ...`) or from `backend/` with `uv run` and a
`DATABASE_URL` pointing at the database (see "Backend" below):

| Command | Effect |
|---|---|
| `python -m app.cli migrate` | `alembic upgrade head` (the container does this on every start) |
| `python -m app.cli seed` | Load deterministic demo data; idempotent, never duplicates |
| `python -m app.cli check-ready` | Exit 0 only if the DB is reachable and migrations are at head |
| `python -m app.cli reset-demo --yes-destroy-local-data` | **DESTRUCTIVE.** Truncates all tables, deletes uploaded files, re-seeds. Refuses non-local hosts and `ENVIRONMENT=production` |
| `python -m app.cli sla-escalate [--now ISO]` | Create overdue escalation notifications (idempotent) |
| `python -m app.cli generate-maintenance --as-of YYYY-MM-DD` | Generate due preventive-maintenance requests (idempotent) |
| `python -m app.cli sla-recompute` | Re-derive cached SLA due dates |

Fresh empty database: `docker compose down -v && docker compose up -d --build` (the `-v` deletes data), then `seed`.
Seed dates anchor to the first seed run, so run `reset-demo` before demonstrating (see known limitations).

## Demo accounts (disposable, demo-only)

Password for every account: `demo1234`. These exist only in the seed and must never be reused anywhere.

| Role | Northwind Facilities | Ala-Too Repairs |
|---|---|---|
| Admin | `admin@northwind.demo` | `admin@alatoo.demo` |
| Dispatcher | `dispatcher@northwind.demo` | `dispatcher@alatoo.demo` |
| Technician (Android) | `technician1@northwind.demo` ... `technician4@northwind.demo` | `technician1@alatoo.demo` ... |
| Requester | `requester1@northwind.demo`, `requester2@...`, `requester3@...` | `requester1@alatoo.demo` ... |
| Member of both orgs | `shared@fixflow.demo` (dispatcher in Ala-Too, requester in Northwind) | |

Seed size: 2 organizations, 50+ requests across all statuses and priorities, properties, assets, inventory items,
estimates, attachments, feedback, preventive-maintenance plans.

## Demo scenarios (Northwind, after `reset-demo`)

| Scenario | How to see it |
|---|---|
| **Scheduling collision** | Dispatcher: open **REQ-14** "Chiller noise in the server room" -> Assignment -> Pick manually. Technician Three is the only HVAC technician and is already booked for the window; the form explains why. Concurrent version: `python3 scripts/simulate_race.py assignment`. |
| **Smart Assign** | Same screen -> Smart suggestions -> pick a date -> Suggest slots -> Assign. |
| **Overdue / escalation** | **REQ-41** is overdue; see Dashboard and **Overdue** queue; `python -m app.cli sla-escalate`. |
| **Estimate approval gate** | **REQ-8** (owner `requester1`) has estimate v1 awaiting approval; the technician cannot start until the requester approves. |
| **Low stock** | Admin -> Inventory: `SEALANT-SIL` is below its reorder threshold. Race: `python3 scripts/simulate_race.py inventory`. |
| **Preventive maintenance** | Admin -> Maintenance plans: "Weekly rooftop AC filter check" is due; generate it (twice: no duplicate). CLI: `generate-maintenance --as-of <date>`. |
| **Multi-organization** | Sign in as `shared@fixflow.demo`, switch organization; cached data is cleared. |
| **Empty state** | `requester2@northwind.demo` has no property access; the new-request form explains how to get access. |
| **Offline Android** | Install the APK, sign in as `technician1@northwind.demo`, enable the in-app *Simulate offline* dev toggle, add a note + photo, kill and reopen the app, go online: exactly one note and one attachment arrive. |

## Local development

### Backend (`backend/`)

```bash
docker compose up -d db                      # Postgres on localhost:5432 (also creates the fixflow_test database)
cd backend
uv sync --frozen
export DATABASE_URL=postgresql+psycopg://fixflow:fixflow-dev-password@localhost:5432/fixflow
uv run python -m app.cli migrate && uv run python -m app.cli seed
uv run uvicorn app.main:app --reload --port 8000
```
(The compose password above is the dev placeholder from `.env.example`. If you also run the `backend` container, stop
it first or change `API_PORT`.) Python settings are read from the environment or `backend/.env`.

### Web (`web/`)

```bash
cd web
bun install --frozen-lockfile
bun run dev                                  # http://localhost:3000, API at http://localhost:8000
# other API host: NEXT_PUBLIC_API_URL=http://host:8000 bun run dev
```
Scripts: `lint`, `typecheck`, `test:ci`, `build`, `gen:api` (regenerate the typed client from the running API). See
[web/README.md](web/README.md).

### Android app (`mobile/`)

```bash
export PATH="$HOME/Flutter/flutter/bin:$PATH"
cd mobile
flutter pub get
flutter build apk --debug                    # -> mobile/build/app/outputs/flutter-apk/app-debug.apk (about 220 MB)
adb install -r build/app/outputs/flutter-apk/app-debug.apk
```

**API base URL (no secrets in the APK):**

- **Emulator:** the default is `http://10.0.2.2:8000` (the emulator's alias for the host machine). Nothing to configure.
- **Physical device (same Wi-Fi as the computer):** on the sign-in screen open **Server**, enter
  `http://<computer LAN IP>:8000`, Save. Or bake it in at build time:
  `flutter build apk --debug --dart-define=API_BASE_URL=http://192.168.1.20:8000`.
- The local backend is plain HTTP, so cleartext is enabled in the debug app; use HTTPS for any real deployment.

More in [mobile/README.md](mobile/README.md) and [mobile/ARCHITECTURE_NOTES.md](mobile/ARCHITECTURE_NOTES.md).

## Tests and verification

```bash
./scripts/verify-all.sh          # backend + web + mobile, fails on the first failing check (needs: docker compose up -d db)
SKIP_MOBILE=1 ./scripts/verify-all.sh      # also SKIP_BACKEND=1 / SKIP_WEB=1
bash scripts/smoke.sh                      # 41 real HTTP checks against a running, seeded stack
python3 scripts/simulate_race.py all       # concurrent assignment, last-units inventory, replay races
```

Backend tests use the separate `fixflow_test` database through `TEST_DATABASE_URL` (default
`postgresql+psycopg://fixflow:fixflow-dev-password@localhost:5432/fixflow_test`) and never touch the demo database.
What is covered and the latest real results: [docs/VERIFICATION.md](docs/VERIFICATION.md).

## Documentation

| Document | Contents |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, tenancy, auth, lifecycle, DB-enforced guarantees, SLA, SSE, offline outbox |
| [docs/API.md](docs/API.md) | Headers, errors, pagination, endpoint overview, curl examples |
| [docs/PRODUCT_DECISIONS.md](docs/PRODUCT_DECISIONS.md) | Smart Assign: problem, behavior, trade-offs |
| [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) | Missing features, defects, security/reliability risk notes |
| [docs/VERIFICATION.md](docs/VERIFICATION.md) | Commands run, results, test coverage |
| [docs/AI_USAGE.md](docs/AI_USAGE.md) | AI tools used and how output was verified |
| [mobile/README.md](mobile/README.md), [mobile/ARCHITECTURE_NOTES.md](mobile/ARCHITECTURE_NOTES.md) | Android build, offline design |
| [web/README.md](web/README.md), [web/CONVENTIONS.md](web/CONVENTIONS.md) | Web scripts and conventions |

## Repository layout

```
compose.yaml  .env.example  README.md
backend/   FastAPI app, Alembic migrations (alembic/), tests (tests/), uv.lock
web/       Next.js app, bun.lock
mobile/    Flutter app, pubspec.lock
scripts/   verify-all.sh  smoke.sh  simulate_race.py
docs/      ARCHITECTURE  API  PRODUCT_DECISIONS  KNOWN_LIMITATIONS  VERIFICATION  AI_USAGE
```
