from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ImportRequest(BaseModel):
    root_path: str
    recursive: bool = True
    file_types: list[str] = Field(default_factory=lambda: [".arw", ".jpg", ".jpeg", ".png"])
    reuse_cache: bool = True


class ImportResponse(BaseModel):
    job_id: str
    registered_count: int


class AnalyzeRequest(BaseModel):
    reuse_cache: bool = True


class JobProgressResponse(BaseModel):
    job_id: str
    status: str
    total_files: int
    imported_files: int
    grouped_files: int
    technically_scored_files: int
    semantically_scored_files: int
    failed_files: int
    provisional_rated_files: int
    final_rated_files: int
    current_stage: str
    errors: list[str]
    started_at: str | None = None
    finished_at: str | None = None


class AIHealthResponse(BaseModel):
    provider: Literal["lm_studio", "openrouter"]
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


class PhotoMutationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    rating: int | None = Field(default=None, ge=1, le=5)
    selection_status: Literal["normal", "rejected"] | None = None
    pick_flag: bool | None = None
    best_cut_flag: bool | None = None
    reviewed_flag: bool | None = None

    @model_validator(mode="after")
    def validate_rejected_without_rating(self) -> "PhotoMutationRequest":
        if self.selection_status == "rejected" and self.rating is not None:
            raise ValueError("rejected photos cannot include a rating")
        return self


class BatchMutationRequest(BaseModel):
    job_id: str
    photo_ids: list[str]
    action: str
    payload: dict[str, Any] = Field(default_factory=dict)


class MutationResult(BaseModel):
    updated_count: int
    failed_count: int


class ReanalyzeRequest(BaseModel):
    job_id: str
    scope: str = "full"


class GroupMergeRequest(BaseModel):
    target_group_id: str
    stale_policy: Literal["mark_stale"] = "mark_stale"


class GroupSplitRequest(BaseModel):
    photo_ids: list[str]
    new_group_rule: Literal["selected_to_new_group"] = "selected_to_new_group"
    stale_policy: Literal["mark_stale"] = "mark_stale"
    best_cut_policy: Literal["clear"] = "clear"


class XmpExportRequest(BaseModel):
    job_id: str
    photo_ids: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = True
    conflict_policy: Literal["skip", "fail", "overwrite_safe_fields"] = "skip"


class ExportResultsRequest(BaseModel):
    job_id: str
    format: Literal["csv", "json"]
    filters: dict[str, Any] = Field(default_factory=dict)


class SettingsResponse(BaseModel):
    class WeightSettingsPayload(BaseModel):
        technical_quality: float
        composition: float
        subject_state: float
        rarity: float

    class RatingThresholdsPayload(BaseModel):
        star_5: float
        star_4: float
        star_3: float
        star_2: float
        reject: float

    ai_provider: Literal["lm_studio", "openrouter"]
    ai_base_url: str
    ai_model_name: str
    allow_remote_ai: bool
    ai_concurrency: int
    image_processing_concurrency: int
    similarity_threshold: float
    time_proximity_seconds: int
    candidate_limit: int
    thumbnail_size: int
    preview_size: int
    compare_preview_size: int
    preview_jpeg_quality: int
    highlight_threshold: int
    shadow_threshold: int
    exiftool_path: str
    cache_dir: str
    weights: WeightSettingsPayload
    rating_thresholds: RatingThresholdsPayload


class SettingsUpdateRequest(BaseModel):
    class WeightSettingsUpdatePayload(BaseModel):
        technical_quality: float | None = None
        composition: float | None = None
        subject_state: float | None = None
        rarity: float | None = None

    class RatingThresholdsUpdatePayload(BaseModel):
        star_5: float | None = None
        star_4: float | None = None
        star_3: float | None = None
        star_2: float | None = None
        reject: float | None = None

    ai_provider: Literal["lm_studio", "openrouter"] | None = None
    ai_base_url: str | None = None
    ai_model_name: str | None = None
    allow_remote_ai: bool | None = None
    ai_concurrency: int | None = None
    image_processing_concurrency: int | None = None
    similarity_threshold: float | None = None
    time_proximity_seconds: int | None = None
    candidate_limit: int | None = None
    thumbnail_size: int | None = None
    preview_size: int | None = None
    compare_preview_size: int | None = None
    preview_jpeg_quality: int | None = None
    highlight_threshold: int | None = None
    shadow_threshold: int | None = None
    exiftool_path: str | None = None
    weights: WeightSettingsUpdatePayload | None = None
    rating_thresholds: RatingThresholdsUpdatePayload | None = None
