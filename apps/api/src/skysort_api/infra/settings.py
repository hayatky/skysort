from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[5]
APP_ROOT = Path(__file__).resolve().parents[3]
VAR_ROOT = REPO_ROOT / "var"
DATA_ROOT = VAR_ROOT / "data"
CACHE_ROOT = VAR_ROOT / "cache"
LOG_ROOT = VAR_ROOT / "logs"
TMP_ROOT = VAR_ROOT / "tmp"
SETTINGS_FILE = DATA_ROOT / "settings.json"


class WeightSettings(BaseModel):
    technical_quality: float = 0.35
    composition: float = 0.35
    subject_state: float = 0.20
    rarity: float = 0.10


class RatingThresholds(BaseModel):
    star_5: float = 83.0
    star_4: float = 78.0
    star_3: float = 64.0
    star_2: float = 48.0
    reject: float = 20.0


class RuntimeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SKYSORT_", extra="ignore")

    app_name: str = "SkySort API"
    app_version: str = "0.1.0"
    database_url: str = f"sqlite:///{(DATA_ROOT / 'skysort.db').as_posix()}"
    ai_base_url: str = "http://127.0.0.1:1234/v1"
    ai_model_name: str = "qwen2.5-vl-7b-instruct"
    ai_timeout_seconds: float = 10.0
    ai_concurrency: int = 1
    image_processing_concurrency: int = 2
    thumb_size: int = 512
    thumbnail_size: int = 512
    preview_size: int = 1024
    compare_preview_size: int = 512
    preview_jpeg_quality: int = 90
    similarity_threshold: float = 0.86
    time_proximity_seconds: int = 4
    candidate_limit: int = 6
    highlight_threshold: int = 252
    shadow_threshold: int = 3
    cache_dir: Path = CACHE_ROOT
    log_dir: Path = LOG_ROOT
    data_dir: Path = DATA_ROOT
    tmp_dir: Path = TMP_ROOT
    exiftool_path: str = "exiftool"
    prompt_template_dir: Path = APP_ROOT / "src" / "skysort_api" / "infra" / "prompts"
    response_schema_version: str = "v1"
    localhost_only: bool = True
    sqlite_busy_timeout_seconds: float = 30.0
    cache_limit_mb: int = 8192
    log_retention_days: int = 30
    technical_weight: float = 0.35
    composition_weight: float = 0.35
    subject_state_weight: float = 0.20
    rarity_weight: float = 0.10
    weights: WeightSettings = Field(default_factory=WeightSettings)
    rating_thresholds: RatingThresholds = Field(default_factory=RatingThresholds)

    def snapshot(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        for key in ("cache_dir", "log_dir", "data_dir", "tmp_dir", "prompt_template_dir"):
            data[key] = str(data[key])
        return data


AppSettings = RuntimeSettings
Settings = RuntimeSettings

UI_MUTABLE_FIELDS = {
    "ai_base_url",
    "ai_model_name",
    "ai_concurrency",
    "image_processing_concurrency",
    "similarity_threshold",
    "time_proximity_seconds",
    "candidate_limit",
    "thumbnail_size",
    "preview_size",
    "compare_preview_size",
    "preview_jpeg_quality",
    "highlight_threshold",
    "shadow_threshold",
    "exiftool_path",
    "weights",
    "rating_thresholds",
}


def ensure_runtime_dirs() -> None:
    for path in _runtime_directories():
        path.mkdir(parents=True, exist_ok=True)


def load_persisted_settings() -> dict[str, Any]:
    ensure_runtime_dirs()
    settings_file = _settings_file_path()
    if not settings_file.exists():
        return {}
    return json.loads(settings_file.read_text())


def persist_settings(update: dict[str, Any]) -> None:
    current = load_persisted_settings()
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(current.get(key), dict):
            merged = dict(current[key])
            merged.update(value)
            current[key] = merged
        else:
            current[key] = value
    _settings_file_path().write_text(json.dumps(current, indent=2, sort_keys=True))
    get_runtime_settings.cache_clear()


@lru_cache(maxsize=1)
def get_runtime_settings() -> RuntimeSettings:
    ensure_runtime_dirs()
    overrides = load_persisted_settings()
    return RuntimeSettings(**overrides)


def get_settings() -> RuntimeSettings:
    return get_runtime_settings()


def _runtime_directories() -> tuple[Path, Path, Path, Path, Path]:
    data_dir = _env_or_default("SKYSORT_DATA_DIR", DATA_ROOT)
    cache_dir = _env_or_default("SKYSORT_CACHE_DIR", CACHE_ROOT)
    log_dir = _env_or_default("SKYSORT_LOG_DIR", LOG_ROOT)
    tmp_dir = _env_or_default("SKYSORT_TMP_DIR", TMP_ROOT)
    return VAR_ROOT, data_dir, cache_dir, log_dir, tmp_dir


def _settings_file_path() -> Path:
    return _env_or_default("SKYSORT_DATA_DIR", DATA_ROOT) / "settings.json"


def _env_or_default(key: str, default: Path) -> Path:
    value = os.getenv(key)
    return Path(value) if value else default
