#!/bin/sh
set -eu
python -m app.cli wait-db
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
