from sqlalchemy import text


def test_btree_gist_extension_installed(db_engine) -> None:
    with db_engine.connect() as conn:
        found = conn.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'btree_gist'")
        ).scalar()
    assert found == "btree_gist"


def _alembic_cfg(url: str):
    from alembic.config import Config

    from tests.conftest import BACKEND_DIR

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def test_downgrade_to_baseline_and_upgrade_again(migrated_db: str, db_engine) -> None:
    from alembic import command

    cfg = _alembic_cfg(migrated_db)
    db_engine.dispose()  # release pooled connections before DDL
    command.downgrade(cfg, "0001_baseline")
    with db_engine.connect() as conn:
        tables = set(
            conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
            ).scalars()
        )
    assert tables == {"alembic_version"}
    command.upgrade(cfg, "head")
    with db_engine.connect() as conn:
        assert conn.execute(text("SELECT to_regclass('public.audit_events')")).scalar()
        assert (
            conn.execute(
                text("SELECT count(*) FROM pg_trigger WHERE tgname = 'trg_audit_events_immutable'")
            ).scalar()
            == 1
        )


def test_models_match_migrations(migrated_db: str, db_engine) -> None:
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app.db.base import Base

    with db_engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def test_downgrade_to_0002_and_upgrade_again(migrated_db: str, db_engine) -> None:
    from alembic import command

    cfg = _alembic_cfg(migrated_db)
    db_engine.dispose()
    command.downgrade(cfg, "0002_identity_org_assets")
    with db_engine.connect() as conn:
        assert conn.execute(text("SELECT to_regclass('public.service_requests')")).scalar() is None
        cols = set(
            conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='organizations'"
                )
            ).scalars()
        )
        assert "request_seq" not in cols
    command.upgrade(cfg, "head")
    with db_engine.connect() as conn:
        assert conn.execute(text("SELECT to_regclass('public.work_notes')")).scalar()
        n = conn.execute(
            text("SELECT count(*) FROM pg_trigger WHERE tgname LIKE 'trg_%_immutable'")
        ).scalar()
        assert n == 8  # audit, events, notes, estimates, lines, usage, movements, feedback


def test_downgrade_to_0003_and_upgrade_again(migrated_db: str, db_engine) -> None:
    from alembic import command

    cfg = _alembic_cfg(migrated_db)
    db_engine.dispose()
    command.downgrade(cfg, "0003_requests")
    with db_engine.connect() as conn:
        assert conn.execute(text("SELECT to_regclass('public.assignments')")).scalar() is None
        assert conn.execute(text("SELECT to_regclass('public.idempotency_keys')")).scalar() is None
        assert conn.execute(text("SELECT to_regclass('public.service_requests')")).scalar()
        assert (
            conn.execute(
                text("SELECT count(*) FROM pg_proc WHERE proname = 'forbid_assignment_delete'")
            ).scalar()
            == 0
        )
    command.upgrade(cfg, "head")
    with db_engine.connect() as conn:
        assert conn.execute(text("SELECT to_regclass('public.assignments')")).scalar()
        names = set(
            conn.execute(
                text("SELECT conname FROM pg_constraint WHERE conrelid = 'assignments'::regclass")
            ).scalars()
        )
        assert "ex_assignments_technician_no_overlap" in names
        assert (
            conn.execute(
                text(
                    "SELECT contype FROM pg_constraint "
                    "WHERE conname = 'ex_assignments_technician_no_overlap'"
                )
            ).scalar()
            == "x"
        )
        assert (
            conn.execute(
                text(
                    "SELECT count(*) FROM pg_indexes "
                    "WHERE indexname = 'uq_assignments_one_active_per_request'"
                )
            ).scalar()
            == 1
        )
    # drift check stays clean after the round trip
    test_models_match_migrations(migrated_db, db_engine)


def test_downgrade_to_0004_and_upgrade_again(migrated_db: str, db_engine) -> None:
    from alembic import command

    cfg = _alembic_cfg(migrated_db)
    db_engine.dispose()
    command.downgrade(cfg, "0004_assignments")
    with db_engine.connect() as conn:
        for t in (
            "estimates",
            "estimate_lines",
            "inventory_items",
            "material_usage",
            "stock_movements",
            "notifications",
        ):
            assert conn.execute(text(f"SELECT to_regclass('public.{t}')")).scalar() is None
        assert conn.execute(text("SELECT to_regclass('public.assignments')")).scalar()
        assert (
            conn.execute(
                text("SELECT count(*) FROM pg_proc WHERE proname LIKE 'estimate%guard_immutable'")
            ).scalar()
            == 0
        )
    command.upgrade(cfg, "head")
    with db_engine.connect() as conn:
        assert (
            conn.execute(
                text(
                    "SELECT count(*) FROM pg_trigger WHERE tgname IN "
                    "('trg_estimates_immutable','trg_estimate_lines_immutable',"
                    "'trg_material_usage_immutable','trg_stock_movements_immutable')"
                )
            ).scalar()
            == 4
        )
    test_models_match_migrations(migrated_db, db_engine)


def test_downgrade_to_0005_and_upgrade_again(migrated_db: str, db_engine) -> None:
    from alembic import command

    cfg = _alembic_cfg(migrated_db)
    db_engine.dispose()
    command.downgrade(cfg, "0005_estimates_inventory")
    with db_engine.connect() as conn:
        assert conn.execute(text("SELECT to_regclass('public.maintenance_plans')")).scalar() is None
        cols = set(
            conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'service_requests'"
                )
            ).scalars()
        )
        assert not cols & {"plan_id", "occurrence_date", "sla_due_at", "overdue_notified_at"}
        assert conn.execute(text("SELECT to_regclass('public.estimates')")).scalar()
    command.upgrade(cfg, "head")
    with db_engine.connect() as conn:
        assert conn.execute(text("SELECT to_regclass('public.maintenance_plans')")).scalar()
        assert (
            conn.execute(
                text(
                    "SELECT count(*) FROM pg_constraint "
                    "WHERE conname = 'uq_service_requests_plan_occurrence'"
                )
            ).scalar()
            == 1
        )
        assert (
            conn.execute(
                text(
                    "SELECT count(*) FROM pg_indexes "
                    "WHERE indexname = 'ix_service_requests_org_sla_due'"
                )
            ).scalar()
            == 1
        )


def test_downgrade_to_0006_and_upgrade_again(migrated_db: str, db_engine) -> None:
    from alembic import command

    cfg = _alembic_cfg(migrated_db)
    db_engine.dispose()
    command.downgrade(cfg, "0006_sla_maintenance")
    with db_engine.connect() as conn:
        assert conn.execute(text("SELECT to_regclass('public.feedback')")).scalar() is None
        assert conn.execute(text("SELECT to_regclass('public.stream_tickets')")).scalar() is None
        assert conn.execute(text("SELECT to_regclass('public.maintenance_plans')")).scalar()
        assert (
            conn.execute(
                text(
                    "SELECT count(*) FROM pg_indexes WHERE indexname IN "
                    "('ix_service_requests_org_completed','ix_estimates_org_decided',"
                    "'ix_material_usage_org_created','ix_assignments_org_start_end')"
                )
            ).scalar()
            == 0
        )
    command.upgrade(cfg, "head")
    with db_engine.connect() as conn:
        assert conn.execute(text("SELECT to_regclass('public.feedback')")).scalar()
        assert conn.execute(text("SELECT to_regclass('public.stream_tickets')")).scalar()
        assert (
            conn.execute(
                text("SELECT count(*) FROM pg_trigger WHERE tgname = 'trg_feedback_immutable'")
            ).scalar()
            == 1
        )
    test_models_match_migrations(migrated_db, db_engine)
