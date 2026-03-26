from __future__ import annotations

from pathlib import Path

import pytest

from skysort_api.infra.database import Base, get_engine, reset_engine, session_scope
from skysort_api.infra.settings import get_runtime_settings


@pytest.fixture()
def isolated_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    database_path = tmp_path / "skysort.db"
    monkeypatch.setenv("SKYSORT_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("SKYSORT_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("SKYSORT_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("SKYSORT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SKYSORT_TMP_DIR", str(tmp_path / "tmp"))
    get_runtime_settings.cache_clear()
    reset_engine()
    Base.metadata.create_all(get_engine())
    yield tmp_path
    reset_engine()
    get_runtime_settings.cache_clear()


@pytest.fixture()
def db_session(isolated_runtime: Path):
    with session_scope() as session:
        yield session
