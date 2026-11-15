#!/usr/bin/env bash
# FixFlow full verification (QA-05): backend, web, mobile. Fails fast on the first failing check.
#
#   ./scripts/verify-all.sh
#   SKIP_MOBILE=1 ./scripts/verify-all.sh        # also SKIP_BACKEND=1 / SKIP_WEB=1
#
# Backend tests need a reachable PostgreSQL (docker compose up -d db). They use the SEPARATE
# fixflow_test database via TEST_DATABASE_URL and never touch the demo database.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="$HOME/.bun/bin:$HOME/Flutter/flutter/bin:$PATH"

TEST_DATABASE_URL="${TEST_DATABASE_URL:-postgresql+psycopg://fixflow:fixflow-dev-password@localhost:5432/fixflow_test}"
export TEST_DATABASE_URL
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"

START=$SECONDS
SUMMARY=()

section() { printf '\n==================== %s ====================\n' "$1"; }
step() { printf '\n--> %s\n' "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "ERROR: required tool '$1' not found on PATH" >&2; exit 2; }; }
finish() {
  local name="$1" began="$2"
  SUMMARY+=("$name: PASS ($((SECONDS - began))s)")
}

if [ "${SKIP_BACKEND:-0}" != "1" ]; then
  section "Precondition: PostgreSQL reachable at ${DB_HOST}:${DB_PORT}"
  if ! (exec 3<>"/dev/tcp/${DB_HOST}/${DB_PORT}") 2>/dev/null; then
    echo "ERROR: PostgreSQL is not reachable at ${DB_HOST}:${DB_PORT}." >&2
    echo "       Start it with:  docker compose up -d db" >&2
    exit 2
  fi
  echo "ok"

  section "Backend (ruff, ruff format, ty, pytest)"
  need uv
  began=$SECONDS
  cd "$ROOT/backend"
  step "uv sync --frozen";            uv sync --frozen
  step "uv run ruff check .";         uv run ruff check .
  step "uv run ruff format --check ."; uv run ruff format --check .
  step "uv run ty check .";           uv run ty check .
  step "uv run pytest -q";            uv run pytest -q
  finish backend "$began"
else
  echo "SKIP backend (SKIP_BACKEND=1)"; SUMMARY+=("backend: SKIPPED")
fi

if [ "${SKIP_WEB:-0}" != "1" ]; then
  section "Web (bun install, lint, typecheck, test:ci, build)"
  need bun
  began=$SECONDS
  cd "$ROOT/web"
  step "bun install --frozen-lockfile"; bun install --frozen-lockfile
  step "bun run lint";                  bun run lint
  step "bun run typecheck";             bun run typecheck
  step "bun run test:ci";               bun run test:ci
  step "bun run build";                 bun run build
  finish web "$began"
else
  echo "SKIP web (SKIP_WEB=1)"; SUMMARY+=("web: SKIPPED")
fi

if [ "${SKIP_MOBILE:-0}" != "1" ]; then
  section "Mobile (pub get, dart format, analyze, test, apk)"
  need flutter
  need dart
  began=$SECONDS
  cd "$ROOT/mobile"
  FMT_DIRS=(lib test)
  [ -d integration_test ] && FMT_DIRS+=(integration_test)
  step "flutter pub get";  flutter pub get
  step "dart format --output=none --set-exit-if-changed ${FMT_DIRS[*]}"
  dart format --output=none --set-exit-if-changed "${FMT_DIRS[@]}"
  step "flutter analyze";  flutter analyze
  step "flutter test";     flutter test
  step "flutter build apk --debug"; flutter build apk --debug
  finish mobile "$began"
else
  echo "SKIP mobile (SKIP_MOBILE=1)"; SUMMARY+=("mobile: SKIPPED")
fi

section "Summary"
printf '%s\n' "${SUMMARY[@]}"
echo "PASS: all required checks passed in $((SECONDS - START))s"
