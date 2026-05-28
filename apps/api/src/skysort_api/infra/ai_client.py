from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from .settings import get_settings


TINY_IMAGE_DATA_URL = (
    "data:image/jpeg;base64,"
    "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoHBwYIDAoMDAsKCwsNDhIQDQ4R"
    "DgsLEBYQERMUFRUVDA8XGBYUGBIUFRT/2wBDAQMEBAUEBQkFBQkUDQsNFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUF"
    "BQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBT/wAARCAAQABADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAA"
    "ECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2"
    "JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJ"
    "WWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAH"
    "wEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdh"
    "cRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hp"
    "anN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk"
    "5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD9U6KKKAP/2Q=="
)

HEALTH_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}


@dataclass(slots=True)
class AIHealthResult:
    provider: str
    reachable: bool
    localhost_only: bool
    remote_allowed: bool
    auth_configured: bool
    available_models: list[str]
    configured_model: str
    configured_model_exists: bool
    model_loadable: bool
    vision_capable: bool
    structured_json_capable: bool
    checked_at: str
    error_detail: str | None = None


@dataclass(slots=True)
class AIResult:
    phase: str
    payload: dict[str, object]
    parsed_json: dict[str, object] | None
    raw_response_text: str
    status: str
    latency_ms: int


class VisionLanguageModelClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def health_check(self) -> AIHealthResult:
        checked_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        localhost_only = _is_localhost_url(self.settings.ai_base_url)
        auth_configured = self._auth_configured()
        if not localhost_only and not self.settings.allow_remote_ai:
            return AIHealthResult(
                provider=self.settings.ai_provider,
                reachable=False,
                localhost_only=False,
                remote_allowed=False,
                auth_configured=auth_configured,
                available_models=[],
                configured_model=self.settings.ai_model_name,
                configured_model_exists=False,
                model_loadable=False,
                vision_capable=False,
                structured_json_capable=False,
                checked_at=checked_at,
                error_detail="Remote AI endpoints require allow_remote_ai=true",
            )
        if not auth_configured:
            return AIHealthResult(
                provider=self.settings.ai_provider,
                reachable=False,
                localhost_only=localhost_only,
                remote_allowed=self.settings.allow_remote_ai,
                auth_configured=False,
                available_models=[],
                configured_model=self.settings.ai_model_name,
                configured_model_exists=False,
                model_loadable=False,
                vision_capable=False,
                structured_json_capable=False,
                checked_at=checked_at,
                error_detail="OpenRouter requires SKYSORT_AI_API_KEY",
            )
        try:
            with httpx.Client(
                base_url=self.settings.ai_base_url,
                timeout=self.settings.ai_timeout_seconds,
                headers=self._headers(),
            ) as client:
                models_response = client.get("/models")
                models_response.raise_for_status()
                models = [item.get("id", "") for item in models_response.json().get("data", [])]
                configured_exists = self.settings.ai_model_name in models if models else True
                probe_payload = {
                    "model": self.settings.ai_model_name,
                    "response_format": json_schema_response_format("health_probe", HEALTH_RESPONSE_SCHEMA),
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": 'Return {"ok":true} as JSON.'},
                                {"type": "image_url", "image_url": {"url": TINY_IMAGE_DATA_URL}},
                            ],
                        }
                    ],
                    "max_tokens": 32,
                }
                probe_response = client.post("/chat/completions", json=probe_payload)
                probe_response.raise_for_status()
                content = probe_response.json()["choices"][0]["message"]["content"]
                parsed = _recover_json(content)
                json_capable = bool(parsed and parsed.get("ok") is True)
            return AIHealthResult(
                provider=self.settings.ai_provider,
                reachable=True,
                localhost_only=localhost_only,
                remote_allowed=self.settings.allow_remote_ai,
                auth_configured=auth_configured,
                available_models=models,
                configured_model=self.settings.ai_model_name,
                configured_model_exists=configured_exists,
                model_loadable=configured_exists and json_capable,
                vision_capable=json_capable,
                structured_json_capable=json_capable,
                checked_at=checked_at,
                error_detail=None if json_capable else "Vision or JSON probe failed",
            )
        except httpx.HTTPStatusError as exc:
            error_detail = _format_http_error(exc)
            return AIHealthResult(
                provider=self.settings.ai_provider,
                reachable=False,
                localhost_only=localhost_only,
                remote_allowed=self.settings.allow_remote_ai,
                auth_configured=auth_configured,
                available_models=[],
                configured_model=self.settings.ai_model_name,
                configured_model_exists=False,
                model_loadable=False,
                vision_capable=False,
                structured_json_capable=False,
                checked_at=checked_at,
                error_detail=error_detail,
            )
        except Exception as exc:
            return AIHealthResult(
                provider=self.settings.ai_provider,
                reachable=False,
                localhost_only=localhost_only,
                remote_allowed=self.settings.allow_remote_ai,
                auth_configured=auth_configured,
                available_models=[],
                configured_model=self.settings.ai_model_name,
                configured_model_exists=False,
                model_loadable=False,
                vision_capable=False,
                structured_json_capable=False,
                checked_at=checked_at,
                error_detail=str(exc),
            )

    def evaluate(self, phase: str, payload: dict[str, object]) -> AIResult:
        start = time.perf_counter()
        status = "succeeded"
        parsed: dict[str, object] | None = None
        raw_text = ""
        retry_count = 0
        with httpx.Client(base_url=self.settings.ai_base_url, timeout=self.settings.ai_timeout_seconds, headers=self._headers()) as client:
            while retry_count <= 2:
                response = client.post("/chat/completions", json=payload)
                response.raise_for_status()
                body = response.json()
                raw_text = body["choices"][0]["message"]["content"]
                parsed = _recover_json(raw_text)
                if parsed is not None:
                    status = "retried" if retry_count else "succeeded"
                    break
                retry_count += 1
            if parsed is None:
                status = "ai_eval_failed"
        latency_ms = int((time.perf_counter() - start) * 1000)
        return AIResult(phase=phase, payload=payload, parsed_json=parsed, raw_response_text=raw_text, status=status, latency_ms=latency_ms)

    def _auth_configured(self) -> bool:
        if self.settings.ai_provider == "openrouter":
            return bool(self.settings.ai_api_key)
        return True

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.settings.ai_provider == "openrouter":
            headers["Authorization"] = f"Bearer {self.settings.ai_api_key}"
            if self.settings.ai_referer:
                headers["HTTP-Referer"] = self.settings.ai_referer
            if self.settings.ai_title:
                headers["X-Title"] = self.settings.ai_title
        return headers


def _recover_json(raw_text: str) -> dict[str, object] | None:
    for candidate in (raw_text, _extract_json(raw_text)):
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    return None


def json_schema_response_format(name: str, schema: dict[str, object]) -> dict[str, object]:
    return {"type": "json_schema", "json_schema": {"name": name, "schema": schema}}


def _format_http_error(exc: httpx.HTTPStatusError) -> str:
    detail = exc.response.text.strip()
    if detail:
        return f"{exc}; response body: {detail}"
    return str(exc)


def _extract_json(raw_text: str) -> str | None:
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return raw_text[start : end + 1]


def _is_localhost_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.hostname in {"127.0.0.1", "localhost", "::1"}
