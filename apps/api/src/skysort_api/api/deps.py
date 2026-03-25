from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from skysort_api.infra.database import session_scope


def get_session() -> Iterator[Session]:
    with session_scope() as session:
        yield session


def get_db() -> Iterator[Session]:
    with session_scope() as session:
        yield session
