from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

CONNECT_TIMEOUT_SECONDS = 3

_engine: Engine | None = None

# Bound lazily to whichever engine is current (see set_engine / get_engine).
SessionLocal: sessionmaker[Session] = sessionmaker(autoflush=False, expire_on_commit=False)


def build_engine(url: str) -> Engine:
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_recycle=1800,
        connect_args={"connect_timeout": CONNECT_TIMEOUT_SECONDS},
    )


def get_engine() -> Engine:
    engine = _engine
    if engine is None:
        engine = build_engine(get_settings().DATABASE_URL)
        set_engine(engine)
    return engine


def set_engine(engine: Engine | None) -> None:
    """Replace the module-level engine (used by tests). Disposes the previous one."""
    global _engine
    if _engine is not None and _engine is not engine:
        _engine.dispose()
    _engine = engine
    SessionLocal.configure(bind=engine)


def get_db() -> Iterator[Session]:
    get_engine()
    session = SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
