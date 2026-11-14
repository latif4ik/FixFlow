"""Operational CLI: ``python -m app.cli <command>``.

Extension points for later phases (add a subparser + handler for each):
  - seed                 load demo data (implemented)
  - reset-demo           wipe and re-seed the demo organisations
  - sla-escalate         notify on overdue requests (idempotent)
  - generate-maintenance generate maintenance-plan requests (--as-of DATE)
"""

import argparse
import sys
import time
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime

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


def _cmd_seed(_: argparse.Namespace) -> int:
    from app.db.session import SessionLocal, get_engine
    from app.seed import DEMO_PASSWORD, format_credentials, seed

    get_engine()
    with SessionLocal() as db:
        rows = seed(db)
    print(format_credentials(rows))
    print(f"\nDisposable demo credentials only. Password for every account: {DEMO_PASSWORD}")
    return 0


def _parse_now(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _cmd_sla_escalate(args: argparse.Namespace) -> int:
    from app.db.session import SessionLocal, get_engine
    from app.services.escalation import escalate_overdue

    get_engine()
    with SessionLocal() as db:
        count = escalate_overdue(db, args.now)
    print(count)
    return 0


def _cmd_sla_recompute(_: argparse.Namespace) -> int:
    from app.db.session import SessionLocal, get_engine
    from app.sla.service import recompute_all

    get_engine()
    with SessionLocal() as db:
        n = recompute_all(db)
        db.commit()
    print(n)
    return 0


def _cmd_generate_maintenance(args: argparse.Namespace) -> int:
    from app.db.session import SessionLocal, get_engine
    from app.services.maintenance import generate

    get_engine()
    with SessionLocal() as db:
        report = generate(db, args.org, args.as_of, commit_each=True)
    for plan in report.plans:
        for item in plan.created:
            print(
                f"created {item.display_id} plan={plan.plan_id} occurrence={item.occurrence_date}"
            )
    print(
        f"as_of={report.as_of} plans={report.plans_processed} created={report.requests_created} "
        f"skipped_existing={report.skipped_existing} errors={report.errors}"
    )
    return 1 if report.errors else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="FixFlow CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("wait-db", help="wait for the database with exponential backoff").set_defaults(
        func=_cmd_wait_db
    )
    sub.add_parser("check-db", help="single connectivity check").set_defaults(func=_cmd_check_db)
    sub.add_parser("seed", help="load deterministic demo data (idempotent)").set_defaults(
        func=_cmd_seed
    )
    esc = sub.add_parser(
        "sla-escalate", help="notify staff about newly overdue requests (idempotent); prints count"
    )
    esc.add_argument("--now", type=_parse_now, default=None, help="ISO-8601 instant (default: now)")
    esc.set_defaults(func=_cmd_sla_escalate)
    gen = sub.add_parser(
        "generate-maintenance",
        help="create requests for maintenance occurrences due on or before --as-of (idempotent)",
    )
    gen.add_argument("--as-of", type=date.fromisoformat, required=True, help="YYYY-MM-DD")
    gen.add_argument("--org", type=uuid.UUID, default=None, help="limit to one organization id")
    gen.set_defaults(func=_cmd_generate_maintenance)
    sub.add_parser("sla-recompute", help="re-derive the SLA cache of every request").set_defaults(
        func=_cmd_sla_recompute
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
