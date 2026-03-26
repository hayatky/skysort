from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from skysort_api.infra.file_scan import build_source_signature, compute_fast_hash, file_metadata, iter_photo_files, normalize_root_path
from skysort_api.infra.image_tools import asset_paths_for_signature
from skysort_api.infra.models import Job, Photo
from skysort_api.infra.prompt_store import load_prompt
from skysort_api.infra.settings import get_settings
from .repositories import JobRepository, PhotoRepository


def create_import_job(session, root_path: str, recursive: bool, file_types: list[str], reuse_cache: bool) -> tuple[str, int]:
    root = normalize_root_path(root_path)
    files = iter_photo_files(root, recursive=recursive, file_types=file_types)
    settings = get_settings()
    _, prompt_hash = load_prompt("single_image_v1")
    job_repo = JobRepository(session)
    photo_repo = PhotoRepository(session)
    previous_job = job_repo.latest_for_root_path(str(root))
    previous_photos = {}
    if previous_job is not None:
        previous_photos = {photo.file_path: photo for photo in photo_repo.list_for_paths(previous_job.id)}
    job_id = f"job_{uuid.uuid4().hex[:10]}"
    job = Job(
        id=job_id,
        root_path=str(root),
        status="queued",
        total_files=len(files),
        imported_files=0,
        current_stage="imported",
        settings_snapshot_json=json.dumps(_settings_snapshot(settings, reuse_cache)),
        app_version=settings.app_version,
        model_name=settings.ai_model_name,
        prompt_template_hash=prompt_hash,
        response_schema_version=settings.response_schema_version,
    )
    photos = []
    now = datetime.now(timezone.utc)
    current_paths = {str(path) for path in files}
    for index, path in enumerate(files):
        size, mtime = file_metadata(path)
        file_hash = compute_fast_hash(path)
        previous = previous_photos.get(str(path))
        photos.append(
            _build_photo_record(
                job_id=job_id,
                path=path,
                file_hash=file_hash,
                file_size=size,
                file_mtime=mtime,
                capture_order_index=index,
                created_at=now,
                updated_at=now,
                previous=previous,
                reuse_cache=reuse_cache,
            )
        )
    for missing_path, previous in previous_photos.items():
        if missing_path in current_paths:
            continue
        photos.append(
            Photo(
                id=f"photo_{uuid.uuid4().hex[:12]}",
                job_id=job_id,
                file_path=previous.file_path,
                file_name=previous.file_name,
                file_hash=previous.file_hash,
                file_size=previous.file_size,
                file_mtime=previous.file_mtime,
                capture_time=previous.capture_time,
                capture_timestamp_ms=previous.capture_timestamp_ms,
                capture_order_index=previous.capture_order_index,
                camera_model=previous.camera_model,
                lens_model=previous.lens_model,
                focal_length=previous.focal_length,
                shutter_speed=previous.shutter_speed,
                aperture=previous.aperture,
                iso=previous.iso,
                width=previous.width,
                height=previous.height,
                orientation=previous.orientation,
                preview_path=previous.preview_path,
                thumb_path=previous.thumb_path,
                is_missing=True,
                created_at=now,
                updated_at=now,
            )
        )

    job_repo.add(job)
    photo_repo.add_many(photos)
    return job_id, len(photos)


def _build_photo_record(
    *,
    job_id: str,
    path,
    file_hash: str,
    file_size: int,
    file_mtime: float,
    capture_order_index: int,
    created_at,
    updated_at,
    previous: Photo | None,
    reuse_cache: bool,
) -> Photo:
    photo = Photo(
        id=f"photo_{uuid.uuid4().hex[:12]}",
        job_id=job_id,
        file_path=str(path),
        file_name=path.name,
        file_hash=file_hash,
        file_size=file_size,
        file_mtime=file_mtime,
        capture_order_index=capture_order_index,
        created_at=created_at,
        updated_at=updated_at,
    )
    current_signature = build_source_signature(path, file_hash, file_size, file_mtime)
    thumb_path, preview_path = asset_paths_for_signature(current_signature)
    photo.thumb_path = str(thumb_path)
    photo.preview_path = str(preview_path)

    if previous is None or not reuse_cache:
        return photo

    previous_signature = build_source_signature(previous.file_path, previous.file_hash, previous.file_size, previous.file_mtime)
    if current_signature != previous_signature:
        return photo

    photo.capture_time = previous.capture_time
    photo.capture_timestamp_ms = previous.capture_timestamp_ms
    photo.camera_model = previous.camera_model
    photo.lens_model = previous.lens_model
    photo.focal_length = previous.focal_length
    photo.shutter_speed = previous.shutter_speed
    photo.aperture = previous.aperture
    photo.iso = previous.iso
    photo.width = previous.width
    photo.height = previous.height
    photo.orientation = previous.orientation
    return photo


def _settings_snapshot(settings, reuse_cache: bool) -> dict[str, object]:
    return {
        "ai_base_url": settings.ai_base_url,
        "ai_model_name": settings.ai_model_name,
        "ai_concurrency": settings.ai_concurrency,
        "image_processing_concurrency": settings.image_processing_concurrency,
        "thumbnail_size": settings.thumbnail_size,
        "preview_size": settings.preview_size,
        "compare_preview_size": settings.compare_preview_size,
        "preview_jpeg_quality": settings.preview_jpeg_quality,
        "similarity_threshold": settings.similarity_threshold,
        "time_proximity_seconds": settings.time_proximity_seconds,
        "candidate_limit": settings.candidate_limit,
        "highlight_threshold": settings.highlight_threshold,
        "shadow_threshold": settings.shadow_threshold,
        "weights": settings.weights.model_dump(),
        "rating_thresholds": settings.rating_thresholds.model_dump(),
        "exiftool_path": settings.exiftool_path,
        "reuse_cache": reuse_cache,
    }
