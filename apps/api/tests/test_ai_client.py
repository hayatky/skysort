from __future__ import annotations

from skysort_api.infra.ai_client import VisionLanguageModelClient
from skysort_api.infra.settings import get_runtime_settings


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class _FakeHTTPXClient:
    last_headers: dict[str, str] | None = None

    def __init__(self, *args, headers=None, **kwargs):
        _FakeHTTPXClient.last_headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, path: str):
        assert path == "/models"
        return _FakeResponse({"data": [{"id": "openai/gpt-5-nano"}]})

    def post(self, path: str, json):
        assert path == "/chat/completions"
        assert json["model"] == "openai/gpt-5-nano"
        return _FakeResponse({"choices": [{"message": {"content": '{"ok": true}'}}]})


def test_health_check_rejects_remote_endpoint_without_opt_in(isolated_runtime, monkeypatch) -> None:
    monkeypatch.setenv("SKYSORT_AI_PROVIDER", "openrouter")
    monkeypatch.setenv("SKYSORT_AI_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("SKYSORT_AI_MODEL_NAME", "openai/gpt-5-nano")
    monkeypatch.delenv("SKYSORT_AI_API_KEY", raising=False)
    get_runtime_settings.cache_clear()

    health = VisionLanguageModelClient().health_check()

    assert health.reachable is False
    assert health.remote_allowed is False
    assert health.error_detail == "Remote AI endpoints require allow_remote_ai=true"


def test_health_check_requires_openrouter_api_key(isolated_runtime, monkeypatch) -> None:
    monkeypatch.setenv("SKYSORT_AI_PROVIDER", "openrouter")
    monkeypatch.setenv("SKYSORT_AI_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("SKYSORT_AI_MODEL_NAME", "openai/gpt-5-nano")
    monkeypatch.setenv("SKYSORT_ALLOW_REMOTE_AI", "true")
    monkeypatch.delenv("SKYSORT_AI_API_KEY", raising=False)
    get_runtime_settings.cache_clear()

    health = VisionLanguageModelClient().health_check()

    assert health.reachable is False
    assert health.auth_configured is False
    assert health.error_detail == "OpenRouter requires SKYSORT_AI_API_KEY"


def test_health_check_sends_openrouter_auth_headers(isolated_runtime, monkeypatch) -> None:
    monkeypatch.setenv("SKYSORT_AI_PROVIDER", "openrouter")
    monkeypatch.setenv("SKYSORT_AI_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("SKYSORT_AI_MODEL_NAME", "openai/gpt-5-nano")
    monkeypatch.setenv("SKYSORT_ALLOW_REMOTE_AI", "true")
    monkeypatch.setenv("SKYSORT_AI_API_KEY", "secret-token")
    monkeypatch.setenv("SKYSORT_AI_REFERER", "https://example.test/skysort")
    monkeypatch.setenv("SKYSORT_AI_TITLE", "SkySort Test")
    monkeypatch.setattr("skysort_api.infra.ai_client.httpx.Client", _FakeHTTPXClient)
    get_runtime_settings.cache_clear()

    health = VisionLanguageModelClient().health_check()

    assert health.reachable is True
    assert health.auth_configured is True
    assert _FakeHTTPXClient.last_headers == {
        "Authorization": "Bearer secret-token",
        "HTTP-Referer": "https://example.test/skysort",
        "X-Title": "SkySort Test",
    }
