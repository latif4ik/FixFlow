import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from alembic import command
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


@pytest.fixture
def client(migrated_db: str) -> Iterator[TestClient]:
    set_engine(build_engine(migrated_db))
    with TestClient(create_app()) as c:
        yield c
    set_engine(None)


@pytest.fixture
def db_engine(migrated_db: str) -> Iterator[object]:
    engine = build_engine(migrated_db)
    yield engine
    engine.dispose()
