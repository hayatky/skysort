from __future__ import annotations

import json
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from .settings import get_settings


TINY_IMAGE_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WmIWKAAAAAASUVORK5CYII="
)


@dataclass(slots=True)
class AIHealthResult:
    reachable: bool
    localhost_only: bool
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
        if self.settings.localhost_only and not localhost_only:
            return AIHealthResult(
                reachable=False,
                localhost_only=False,
                available_models=[],
                configured_model=self.settings.ai_model_name,
                configured_model_exists=False,
                model_loadable=False,
                vision_capable=False,
                structured_json_capable=False,
                checked_at=checked_at,
                error_detail="AI base URL must be localhost-only",
            )
        try:
            with httpx.Client(base_url=self.settings.ai_base_url, timeout=self.settings.ai_timeout_seconds) as client:
                models_response = client.get("/models")
                models_response.raise_for_status()
                models = [item.get("id", "") for item in models_response.json().get("data", [])]
                configured_exists = self.settings.ai_model_name in models if models else True
                probe_payload = {
                    "model": self.settings.ai_model_name,
                    "response_format": {"type": "json_object"},
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
                reachable=True,
                localhost_only=localhost_only,
                available_models=models,
                configured_model=self.settings.ai_model_name,
                configured_model_exists=configured_exists,
                model_loadable=configured_exists and json_capable,
                vision_capable=json_capable,
                structured_json_capable=json_capable,
                checked_at=checked_at,
                error_detail=None if json_capable else "Vision or JSON probe failed",
            )
        except Exception as exc:
            return AIHealthResult(
                reachable=False,
                localhost_only=localhost_only,
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
        with httpx.Client(base_url=self.settings.ai_base_url, timeout=30.0) as client:
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


def _extract_json(raw_text: str) -> str | None:
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return raw_text[start : end + 1]


def _is_localhost_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.hostname in {"127.0.0.1", "localhost", "::1"}
