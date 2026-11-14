# FixFlow backend

Python 3.13, FastAPI, SQLAlchemy 2 (sync, psycopg 3), Alembic, Postgres 17.

## Run locally (uv)

```sh
docker compose up -d db              # from the project root
cd backend
uv sync
export DATABASE_URL=postgresql+psycopg://fixflow:fixflow-dev-password@localhost:5432/fixflow
uv run python -m app.cli wait-db
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

API docs: http://localhost:8000/api/v1/docs. Whole stack: `docker compose up -d --build`.

## Tests

The compose Postgres creates a `fixflow_test` database on first init. The database name in
`TEST_DATABASE_URL` must contain `test`, otherwise pytest aborts. Without it, DB tests are skipped.

```sh
TEST_DATABASE_URL=postgresql+psycopg://fixflow:fixflow-dev-password@localhost:5432/fixflow_test uv run pytest -q
```

## Lint and types

```sh
uv run ruff check . && uv run ruff format --check . && uv run ty check .
```
