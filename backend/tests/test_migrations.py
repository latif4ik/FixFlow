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
        assert n == 3
