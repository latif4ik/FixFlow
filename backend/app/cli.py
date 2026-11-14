"""Operational CLI: ``python -m app.cli <command>``.

Extension points for later phases (add a subparser + handler for each):
  - seed                 load demo data
  - reset-demo           wipe and re-seed the demo organisations
  - sla-escalate         notify on overdue requests (idempotent)
  - generate-maintenance generate maintenance-plan requests (--as-of DATE)
"""

import argparse
import sys
import time
from collections.abc import Callable

from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import build_engine

MAX_TOTAL_SECONDS = 60.0
INITIAL_DELAY = 0.5
MAX_DELAY = 5.0


def _try_connect(url: str) -> Exception | None:
    engine = build_engine(url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return None
    except Exception as exc:
        return exc
    finally:
        engine.dispose()


def wait_db(
    url: str,
    max_total: float = MAX_TOTAL_SECONDS,
    attempt: Callable[[str], Exception | None] = _try_connect,
) -> bool:
    deadline = time.monotonic() + max_total
    delay = INITIAL_DELAY
    n = 0
    while True:
        n += 1
        err = attempt(url)
        if err is None:
            print(f"database ready after {n} attempt(s)", flush=True)
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            print(f"database not reachable after {n} attempt(s): {type(err).__name__}", flush=True)
            return False
        print(f"waiting for database (attempt {n}): {type(err).__name__}", flush=True)
        time.sleep(min(delay, remaining))
        delay = min(delay * 2, MAX_DELAY)


def _cmd_wait_db(_: argparse.Namespace) -> int:
    return 0 if wait_db(get_settings().DATABASE_URL) else 1


def _cmd_check_db(_: argparse.Namespace) -> int:
    err = _try_connect(get_settings().DATABASE_URL)
    if err is None:
        print("ok")
        return 0
    print(f"database unavailable: {type(err).__name__}")
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="FixFlow CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("wait-db", help="wait for the database with exponential backoff").set_defaults(
        func=_cmd_wait_db
    )
    sub.add_parser("check-db", help="single connectivity check").set_defaults(func=_cmd_check_db)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
