from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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


class PhotoMutationRequest(BaseModel):
    job_id: str
    rating: int | None = None
    selection_status: str | None = None
    pick_flag: bool | None = None
    best_cut_flag: bool | None = None
    reviewed_flag: bool | None = None


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


class XmpExportRequest(BaseModel):
    job_id: str
    photo_ids: list[str] = Field(default_factory=list)
    dry_run: bool = True
    conflict_policy: str = "skip"


class ExportResultsRequest(BaseModel):
    job_id: str
    format: str
    filters: dict[str, Any] = Field(default_factory=dict)


class SettingsResponse(BaseModel):
    ai_base_url: str
    ai_model_name: str
    ai_concurrency: int
    image_processing_concurrency: int
    similarity_threshold: float
    time_proximity_seconds: int
    candidate_limit: int
    thumbnail_size: int
    preview_size: int
    compare_preview_size: int
    preview_jpeg_quality: int
    exiftool_path: str
    cache_dir: str


class SettingsUpdateRequest(BaseModel):
    ai_base_url: str | None = None
    ai_model_name: str | None = None
    ai_concurrency: int | None = None
    image_processing_concurrency: int | None = None
    similarity_threshold: float | None = None
    time_proximity_seconds: int | None = None
    candidate_limit: int | None = None
    thumbnail_size: int | None = None
    preview_size: int | None = None
    compare_preview_size: int | None = None
    preview_jpeg_quality: int | None = None
    exiftool_path: str | None = None
