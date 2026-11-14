"""Operational CLI: ``python -m app.cli <command>``.

Extension points for later phases (add a subparser + handler for each):
  - seed                 load demo data (implemented)
  - reset-demo           DESTRUCTIVE local wipe + re-seed (guarded)
  - sla-escalate         notify on overdue requests (idempotent)
  - generate-maintenance generate maintenance-plan requests (--as-of DATE)
"""

import argparse
import shutil
import sys
import time
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

from alembic.config import Config as AlembicConfig
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import make_url

from alembic import command as alembic_command
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
    from app.seed import DEMO_PASSWORD, format_credentials, format_summary, seed, summary

    get_engine()
    with SessionLocal() as db:
        rows = seed(db)
        data = summary(db)
    print(format_summary(data))
    print("\nDISPOSABLE DEMO CREDENTIALS (local development only)")
    print(format_credentials(rows))
    print(f"\nPassword for every account: {DEMO_PASSWORD}")
    return 0


LOCAL_DB_HOSTS = frozenset({"db", "localhost", "127.0.0.1", "::1"})
RESET_ENVIRONMENTS = frozenset({"development", "test"})
BACKEND_DIR = Path(__file__).resolve().parent.parent


def reset_refusal(
    environment: str, database_url: str, upload_dir: str, confirmed: bool
) -> str | None:
    """Why reset-demo must not run, or None when it is allowed."""
    if not confirmed:
        return "refusing: pass --yes-destroy-local-data to confirm this DESTRUCTIVE command"
    if environment not in RESET_ENVIRONMENTS:
        return f"refusing: ENVIRONMENT={environment!r} (allowed: development, test)"
    host = make_url(database_url).host or ""
    if host not in LOCAL_DB_HOSTS:
        return f"refusing: database host {host!r} is not local (allowed: {sorted(LOCAL_DB_HOSTS)})"
    if not upload_dir.strip() or Path(upload_dir).resolve() == Path("/"):
        return f"refusing: unsafe UPLOAD_DIR {upload_dir!r}"
    return None


def _wipe_uploads(upload_dir: str) -> int:
    root = Path(upload_dir).resolve()
    removed = 0
    if not root.is_dir():
        return 0
    for child in root.iterdir():
        removed += sum(1 for p in child.rglob("*") if p.is_file()) if child.is_dir() else 1
        shutil.rmtree(child) if child.is_dir() and not child.is_symlink() else child.unlink()
    return removed


def _alembic_config() -> AlembicConfig:
    cfg = AlembicConfig(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


def _cmd_migrate(_: argparse.Namespace) -> int:
    alembic_command.upgrade(_alembic_config(), "head")
    print("migrations at head")
    return 0


def _cmd_check_ready(_: argparse.Namespace) -> int:
    url = get_settings().DATABASE_URL
    err = _try_connect(url)
    if err is not None:
        print(f"NOT READY: database unreachable ({type(err).__name__})")
        return 1
    head = ScriptDirectory.from_config(_alembic_config()).get_current_head()
    engine = build_engine(url)
    try:
        with engine.connect() as conn:
            current = MigrationContext.configure(conn).get_current_revision()
    finally:
        engine.dispose()
    if current != head:
        print(f"NOT READY: migrations at {current}, head is {head}")
        return 1
    print(f"ready: database reachable, migrations at head ({head})")
    return 0


def _cmd_reset_demo(args: argparse.Namespace) -> int:
    from app.db.session import SessionLocal, get_engine
    from app.seed import DEMO_PASSWORD, format_credentials, format_summary, seed, summary

    settings = get_settings()
    why = reset_refusal(
        settings.ENVIRONMENT,
        settings.DATABASE_URL,
        settings.UPLOAD_DIR,
        args.yes_destroy_local_data,
    )
    if why:
        print(why)
        return 2
    engine = get_engine()
    with engine.begin() as conn:
        names = (
            conn.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                    "AND tablename <> 'alembic_version'"
                )
            )
            .scalars()
            .all()
        )
        if names:
            quoted = ", ".join(f'"{n}"' for n in names)
            conn.execute(text(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE"))
    print(f"truncated {len(names)} tables")
    print(f"deleted {_wipe_uploads(settings.UPLOAD_DIR)} files under {settings.UPLOAD_DIR}")
    with SessionLocal() as db:
        rows = seed(db)
        data = summary(db)
    print("re-seeded demo data\n")
    print(format_summary(data))
    print("\nDISPOSABLE DEMO CREDENTIALS (local development only)")
    print(format_credentials(rows))
    print(f"\nPassword for every account: {DEMO_PASSWORD}")
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
    sub.add_parser("migrate", help="alembic upgrade head").set_defaults(func=_cmd_migrate)
    sub.add_parser(
        "check-ready", help="exit 0 only if the DB is reachable and migrations are at head"
    ).set_defaults(func=_cmd_check_ready)
    rst = sub.add_parser(
        "reset-demo",
        help="DESTRUCTIVE: TRUNCATE every table, delete uploaded files, re-seed. Local "
        "development/test databases only (host db/localhost/127.0.0.1/::1).",
    )
    rst.add_argument(
        "--yes-destroy-local-data",
        action="store_true",
        help="required confirmation: ALL data in the local database and UPLOAD_DIR is destroyed",
    )
    rst.set_defaults(func=_cmd_reset_demo)
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
