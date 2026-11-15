#!/bin/sh
set -eu
python -m app.cli wait-db
alembic upgrade head
# Load the deterministic, idempotent demo data so a fresh `docker compose up` is usable
# (and scripts/smoke.sh can run right away). Set SEED_DEMO_DATA=false to skip.
if [ "${SEED_DEMO_DATA:-true}" = "true" ]; then
  python -m app.cli seed
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
