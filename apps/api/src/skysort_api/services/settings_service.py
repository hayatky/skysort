from __future__ import annotations

from skysort_api.api.schemas import SettingsResponse
from skysort_api.infra.settings import UI_MUTABLE_FIELDS, get_settings, persist_settings


def get_settings_response() -> SettingsResponse:
    settings = get_settings()
    return SettingsResponse(
        ai_provider=settings.ai_provider,
        ai_base_url=settings.ai_base_url,
        ai_model_name=settings.ai_model_name,
        allow_remote_ai=settings.allow_remote_ai,
        ai_timeout_seconds=settings.ai_timeout_seconds,
        ai_max_tokens=settings.ai_max_tokens,
        ai_concurrency=settings.ai_concurrency,
        image_processing_concurrency=settings.image_processing_concurrency,
        similarity_threshold=settings.similarity_threshold,
        time_proximity_seconds=settings.time_proximity_seconds,
        candidate_limit=settings.candidate_limit,
        thumbnail_size=settings.thumbnail_size,
        preview_size=settings.preview_size,
        compare_preview_size=settings.compare_preview_size,
        preview_jpeg_quality=settings.preview_jpeg_quality,
        highlight_threshold=settings.highlight_threshold,
        shadow_threshold=settings.shadow_threshold,
        exiftool_path=settings.exiftool_path,
        cache_dir=str(settings.cache_dir),
        weights=SettingsResponse.WeightSettingsPayload(**settings.weights.model_dump()),
        rating_thresholds=SettingsResponse.RatingThresholdsPayload(**settings.rating_thresholds.model_dump()),
    )


def update_settings(payload) -> SettingsResponse:
    updates = {}
    for key, value in payload.model_dump(exclude_none=True).items():
        if key in UI_MUTABLE_FIELDS:
            updates[key] = value
    if updates:
        persist_settings(updates)
    return get_settings_response()
