from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .settings import ensure_runtime_dirs, get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal: sessionmaker[Session] | None = None
SessionLocal: sessionmaker[Session] | None = None


def get_engine():
    global _engine, _SessionLocal, SessionLocal
    if _engine is None:
        settings = get_settings()
        ensure_runtime_dirs()
        db_path = Path(settings.database_url.replace("sqlite:///", ""))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            settings.database_url,
            connect_args={"check_same_thread": False, "timeout": settings.sqlite_busy_timeout_seconds},
        )
        @event.listens_for(_engine, "connect")
        def _configure_sqlite(dbapi_connection, _connection_record):  # type: ignore[no-redef]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA busy_timeout = 30000;")
            cursor.close()
        _SessionLocal = sessionmaker(_engine, expire_on_commit=False, class_=Session)
        SessionLocal = _SessionLocal
    return _engine


def init_db() -> None:
    get_engine()


def reset_engine() -> None:
    global _engine, _SessionLocal, SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
    SessionLocal = None


@contextmanager
def session_scope() -> Iterator[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        get_engine()
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
