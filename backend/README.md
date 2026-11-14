# FixFlow backend

Python 3.13, FastAPI, SQLAlchemy 2 (sync, psycopg 3), Alembic, Postgres 17.

## Prerequisites

Docker (with Compose v2), [uv](https://docs.astral.sh/uv/), Python 3.13 (uv installs it on demand),
and `bash`, `curl`, `python3` for the scripts. Copy `.env.example` to `.env` (project root) to
override defaults; every value in it is a DEV PLACEHOLDER.

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://fixflow:fixflow@localhost:5432/fixflow` | app database (compose derives it from `POSTGRES_*`) |
| `TEST_DATABASE_URL` | none | pytest database; its name MUST contain `test` |
| `ENVIRONMENT` | `development` | `development` / `test` / `production` (`reset-demo` refuses `production`) |
| `CORS_ORIGINS` | `http://localhost:3000` | comma-separated allowed origins |
| `UPLOAD_DIR` | `/data/uploads` | evidence image storage |
| `SESSION_TTL_MINUTES`, `LOG_LEVEL`, `MAX_PAGE_SIZE`, `DEFAULT_PAGE_SIZE`, `MAX_UPLOAD_BYTES` | see `.env.example` | limits |
| `STREAM_TICKET_TTL_SECONDS`, `STREAM_HEARTBEAT_SECONDS`, `STREAM_REVALIDATE_SECONDS`, `STREAM_QUEUE_SIZE` | see `.env.example` | live-update (SSE) tuning |

## Run the stack

```sh
docker compose up -d --build        # from abdulatif-imarov/: db + backend (2 uvicorn workers)
```

Migrations run automatically on container start (`scripts/entrypoint.sh`). Manually:
`docker compose exec backend python -m app.cli migrate`.

API: http://localhost:8000 - OpenAPI UI http://localhost:8000/api/v1/docs, schema
http://localhost:8000/api/v1/openapi.json.

Without Docker for the app itself:

```sh
docker compose up -d db
cd backend && uv sync
export DATABASE_URL=postgresql+psycopg://fixflow:fixflow-dev-password@localhost:5432/fixflow
uv run python -m app.cli wait-db && uv run python -m app.cli migrate
uv run uvicorn app.main:app --reload
```

## CLI (`python -m app.cli <command>`; in compose: `docker compose exec backend ...`)

| Command | What it does |
|---|---|
| `wait-db`, `check-db` | wait for / test database connectivity |
| `migrate` | `alembic upgrade head` |
| `check-ready` | exit 0 only if the DB is reachable and migrations are at head |
| `seed` | deterministic, idempotent demo data; prints a per-org summary + credentials |
| `reset-demo --yes-destroy-local-data` | **DESTRUCTIVE**: TRUNCATEs every app table, deletes all files under `UPLOAD_DIR`, re-seeds. Refuses unless `ENVIRONMENT` is development/test AND the database host is `db`, `localhost`, `127.0.0.1` or `::1` AND the flag is given |
| `sla-escalate [--now ISO]` | notify staff about newly overdue requests (idempotent) |
| `generate-maintenance --as-of YYYY-MM-DD [--org ID]` | create requests for due maintenance occurrences (idempotent) |
| `sla-recompute` | re-derive the SLA cache of every request |

New empty demo environment from scratch:

```sh
docker compose down -v && docker compose up -d --build   # fresh volumes; migrations run on start
docker compose exec backend python -m app.cli check-ready
docker compose exec backend python -m app.cli seed
```

Reset a running local demo: `docker compose exec backend python -m app.cli reset-demo --yes-destroy-local-data`.

## Demo data

The seed (2 orgs, 12 properties, 24 assets, 82 requests covering every status and priority,
estimates in every state, 38 attachments, feedback, 4 maintenance plans, 24 inventory items with
low-stock cases) is deterministic: ids are UUIDv5 and timestamps derive from each organization's
creation date, so re-running adds nothing. Demo pointers (Northwind): "Chiller noise in the server
room" (collision candidate vs technician3), "Server room cooling failed (overdue demo)",
estimate-gate request "Fix dripping tap in the kitchen" (owner requester1), low-stock
`SEALANT-SIL`/`LED-BULB-12W`, due plan "Weekly rooftop AC filter check", requester2 has no
requests (empty state), `shared@fixflow.demo` is REQUESTER in Northwind and DISPATCHER in Ala-Too.

**DISPOSABLE DEMO CREDENTIALS** (local development only; password for all: `demo1234`)

| Account | Organization / role |
|---|---|
| `admin@northwind.demo`, `admin@alatoo.demo` | ADMIN |
| `dispatcher@northwind.demo`, `dispatcher@alatoo.demo` | DISPATCHER |
| `technician1..4@northwind.demo`, `technician1..4@alatoo.demo` | TECHNICIAN (technician3 = hvac; 1 electrical; 2 plumbing; 4 electrical+plumbing) |
| `requester1..3@northwind.demo`, `requester1..3@alatoo.demo` | REQUESTER |
| `shared@fixflow.demo` | REQUESTER in Northwind, DISPATCHER in Ala-Too |

## Verification scripts (need a running, seeded stack)

```sh
bash scripts/smoke.sh                        # real-HTTP lifecycle + expected 401/403/404/409|422
python3 scripts/simulate_race.py assignment  # one 201, one 409 schedule_conflict
python3 scripts/simulate_race.py inventory   # one 201, one 409 insufficient_stock
python3 scripts/simulate_race.py replay      # same client_command_id twice -> one usage
```

Both are re-runnable without a reset and exit non-zero on a violated invariant (`API_URL` selects
another host). The Android offline toggle comes with the mobile app; the race script covers the
backend concurrency half of SEED-06.

## Tests

The compose Postgres creates a `fixflow_test` database on first init. The database name in
`TEST_DATABASE_URL` must contain `test`, otherwise pytest aborts. Without it, DB tests are skipped.
Never run two pytest processes at once (shared database).

```sh
cd backend
TEST_DATABASE_URL=postgresql+psycopg://fixflow:fixflow-dev-password@localhost:5432/fixflow_test uv run pytest -q
```

## Lint and types

```sh
uv sync --frozen && uv run ruff check . && uv run ruff format --check . && uv run ty check .
```
