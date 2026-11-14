import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import get_settings
from app.db.session import build_engine, set_engine
from app.main import create_app

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _test_url() -> str | None:
    return os.environ.get("TEST_DATABASE_URL") or None


def _assert_safe(url: str) -> None:
    db_name = make_url(url).database or ""
    if "test" not in db_name:
        pytest.exit(
            f"Refusing to run: TEST_DATABASE_URL database name {db_name!r} does not contain "
            "'test'. Tests must never touch a non-test database.",
            returncode=2,
        )


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = _test_url()
    if url is None:
        pytest.skip("TEST_DATABASE_URL is not set; skipping database-dependent tests")
    _assert_safe(url)
    return url


@pytest.fixture(scope="session")
def migrated_db(test_database_url: str) -> str:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", test_database_url.replace("%", "%%"))
    command.upgrade(cfg, "head")
    return test_database_url


def _truncate_all(engine) -> None:
    with engine.begin() as conn:
        names = conn.execute(
            text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                "AND tablename <> 'alembic_version'"
            )
        ).scalars()
        quoted = ", ".join(f'"{n}"' for n in names)
        if quoted:
            conn.execute(text(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE"))


@pytest.fixture
def db_engine(migrated_db: str) -> Iterator[object]:
    """Engine on the migrated test DB with every table emptied first."""
    engine = build_engine(migrated_db)
    _truncate_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def client(migrated_db: str, db_engine: object) -> Iterator[TestClient]:
    set_engine(build_engine(migrated_db))
    with TestClient(create_app()) as c:
        yield c
    set_engine(None)


@pytest.fixture
def db(db_engine) -> Iterator[Session]:
    with Session(db_engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture(autouse=True, scope="session")
def _upload_dir() -> Iterator[Path]:
    """Evidence uploads must never touch the real volume during tests."""
    settings = get_settings()
    original = settings.UPLOAD_DIR
    with tempfile.TemporaryDirectory(prefix="fixflow-test-uploads-") as d:
        settings.UPLOAD_DIR = d
        yield Path(d)
    settings.UPLOAD_DIR = original


@pytest.fixture(autouse=True)
def _clean_upload_dir(_upload_dir: Path) -> None:
    for child in _upload_dir.iterdir():
        shutil.rmtree(child) if child.is_dir() else child.unlink()


@pytest.fixture
def sw(db: Session):
    """Scheduling world: two skilled technicians available daily 09:00-18:00 Asia/Bishkek."""
    from tests.sched_helpers import make_sched_world

    return make_sched_world(db)


@pytest.fixture
def hd(client: TestClient, sw):
    from tests.factories import h, login

    w = sw.w
    out = {
        k: h(login(client, getattr(w, k)[0]), w.org)
        for k in ("admin", "disp", "tech", "req1", "req2")
    }
    out["tech2"] = h(login(client, sw.tech2[0]), w.org)
    return out
