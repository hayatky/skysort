from __future__ import annotations

import importlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from skysort_api.infra.ai_client import AIHealthResult
from skysort_api.infra.models import Job
from skysort_api.main import create_app
from skysort_api.infra.settings import get_runtime_settings
from skysort_api.services.import_service import create_import_job


def test_settings_update_persists_provider_fields_without_secret(isolated_runtime: Path) -> None:
    client = TestClient(create_app())

    response = client.patch(
        "/api/settings",
        json={
            "ai_provider": "openrouter",
            "ai_base_url": "https://openrouter.ai/api/v1",
            "ai_model_name": "openai/gpt-5-nano",
            "allow_remote_ai": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ai_provider"] == "openrouter"
    assert body["allow_remote_ai"] is True

    settings_path = isolated_runtime / "data" / "settings.json"
    saved = json.loads(settings_path.read_text())
    assert saved["ai_provider"] == "openrouter"
    assert saved["allow_remote_ai"] is True
    assert "ai_api_key" not in saved
    assert "ai_referer" not in saved
    assert "ai_title" not in saved


def test_ai_health_route_returns_provider_fields(isolated_runtime, monkeypatch) -> None:
    router_module = importlib.import_module("skysort_api.api.router")
    monkeypatch.setattr(
        router_module,
        "get_ai_health_service",
        lambda: AIHealthResult(
            provider="openrouter",
            reachable=False,
            localhost_only=False,
            remote_allowed=True,
            auth_configured=False,
            available_models=[],
            configured_model="openai/gpt-5-nano",
            configured_model_exists=False,
            model_loadable=False,
            vision_capable=False,
            structured_json_capable=False,
            checked_at="2026-03-26T00:00:00Z",
            error_detail="OpenRouter requires SKYSORT_AI_API_KEY",
        ),
    )
    client = TestClient(create_app())

    response = client.get("/api/ai/health")

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "openrouter"
    assert body["remote_allowed"] is True
    assert body["auth_configured"] is False


def test_import_job_snapshot_records_provider_without_secret(db_session, isolated_runtime, monkeypatch) -> None:
    monkeypatch.setenv("SKYSORT_AI_PROVIDER", "openrouter")
    monkeypatch.setenv("SKYSORT_AI_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("SKYSORT_AI_MODEL_NAME", "openai/gpt-5-nano")
    monkeypatch.setenv("SKYSORT_ALLOW_REMOTE_AI", "true")
    monkeypatch.setenv("SKYSORT_AI_API_KEY", "secret-token")

    get_runtime_settings.cache_clear()
    source_dir = isolated_runtime / "photos"
    source_dir.mkdir()
    (source_dir / "alpha.jpg").write_bytes(b"fake-jpeg")

    job_id, count = create_import_job(db_session, str(source_dir), True, [".jpg"], True)

    assert count == 1
    job = db_session.get(Job, job_id)
    snapshot = json.loads(job.settings_snapshot_json)
    assert snapshot["ai_provider"] == "openrouter"
    assert snapshot["allow_remote_ai"] is True
    assert "ai_api_key" not in snapshot
