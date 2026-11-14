from app.cli import wait_db


def test_wait_db_retries_then_succeeds() -> None:
    calls = iter([RuntimeError("down"), RuntimeError("down"), None])
    assert wait_db("x", max_total=30, attempt=lambda _: next(calls)) is True


def test_wait_db_gives_up() -> None:
    assert wait_db("x", max_total=0.0, attempt=lambda _: RuntimeError("down")) is False


# ---- reset-demo guard + check-ready / migrate ----------------------------------------------
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.cli import main, reset_refusal  # noqa: E402

LOCAL = "postgresql+psycopg://u:p@localhost:5432/fixflow"


def test_reset_refuses_without_flag():
    assert "--yes-destroy-local-data" in str(reset_refusal("development", LOCAL, "/data/u", False))


def test_reset_refuses_production():
    assert "production" in str(reset_refusal("production", LOCAL, "/data/u", True))


@pytest.mark.parametrize("host", ["db.example.com", "10.0.0.5", "prod-db"])
def test_reset_refuses_nonlocal_host(host):
    url = f"postgresql+psycopg://u:p@{host}:5432/fixflow"
    assert "not local" in str(reset_refusal("development", url, "/data/u", True))


@pytest.mark.parametrize("upload", ["", "  ", "/"])
def test_reset_refuses_unsafe_upload_dir(upload):
    assert "UPLOAD_DIR" in str(reset_refusal("development", LOCAL, upload, True))


@pytest.mark.parametrize("host", ["db", "localhost", "127.0.0.1", "::1"])
def test_reset_allows_local_hosts(host):
    h = f"[{host}]" if ":" in host else host
    url = f"postgresql+psycopg://u:p@{h}:5432/fixflow"
    assert reset_refusal("test", url, "/data/u", True) is None


def test_reset_command_refuses_in_production(monkeypatch, capsys):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "ENVIRONMENT", "production")
    assert main(["reset-demo", "--yes-destroy-local-data"]) == 2
    assert "refusing" in capsys.readouterr().out


def test_reset_command_without_flag_exits_2(capsys):
    assert main(["reset-demo"]) == 2
    assert "refusing" in capsys.readouterr().out


def test_reset_demo_works_on_test_db_and_reseeds(
    client, db, monkeypatch, capsys, test_database_url
):
    from pathlib import Path

    from app.core.config import get_settings
    from app.seed import seed

    settings = get_settings()
    monkeypatch.setattr(settings, "DATABASE_URL", test_database_url)
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    seed(db)
    stray = Path(settings.UPLOAD_DIR) / "stray" / "old.bin"
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_bytes(b"x")
    db.execute(text("UPDATE service_requests SET title = 'tampered' WHERE number = 1"))
    db.commit()
    assert main(["reset-demo", "--yes-destroy-local-data"]) == 0
    out = capsys.readouterr().out
    assert "truncated" in out and "DISPOSABLE DEMO CREDENTIALS" in out
    assert not stray.exists()
    db.expire_all()
    assert (
        db.execute(text("SELECT count(*) FROM service_requests WHERE title='tampered'")).scalar()
        == 0
    )
    assert db.execute(text("SELECT count(*) FROM service_requests")).scalar() == 82
    assert any(p.is_file() for p in Path(settings.UPLOAD_DIR).rglob("*"))


def test_check_ready_ok_and_not_ready(migrated_db, monkeypatch, capsys):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "DATABASE_URL", migrated_db)
    assert main(["check-ready"]) == 0
    assert "ready" in capsys.readouterr().out
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql+psycopg://x:y@127.0.0.1:1/none")
    assert main(["check-ready"]) == 1
    assert "NOT READY" in capsys.readouterr().out


def test_migrate_is_noop_at_head(migrated_db, monkeypatch, capsys):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "DATABASE_URL", migrated_db)
    assert main(["migrate"]) == 0
