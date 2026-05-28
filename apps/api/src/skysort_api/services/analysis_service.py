from __future__ import annotations

import json
import logging
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Iterator, TypeVar

from skysort_api.domain.evaluation import (
    SemanticMetrics,
    TechnicalMetrics,
    compute_technical_total,
    final_rating_from_scores,
    provisional_rating_from_technical,
    provisional_rating_from_technical_decision,
    technical_candidate_quality,
    technical_reject_risk,
)
from skysort_api.domain.grouping import PhotoCandidate, grouping_boundary_reason, max_group_similarity
from skysort_api.infra.ai_client import AIResult, VisionLanguageModelClient, json_schema_response_format
from skysort_api.infra.file_scan import build_source_signature
from skysort_api.infra.image_tools import (
    build_contact_sheet_data_url,
    build_data_url,
    compute_technical_metrics,
    compute_visual_features,
    ensure_preview_assets,
    extract_image_metadata,
)
from skysort_api.infra.models import AIResponse, Group, GroupMember, Job, JobFailure, Photo, PhotoEvaluation, RatingHistory, TechnicalScore
from skysort_api.infra.prompt_store import load_prompt
from skysort_api.infra.settings import get_settings

from .repositories import EvaluationRepository, FailureRepository, GroupRepository, JobRepository, PhotoRepository

logger = logging.getLogger(__name__)
T = TypeVar("T")
R = TypeVar("R")

SINGLE_IMAGE_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "schema_version": {"type": "string"},
        "ranking": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "photo_id": {"type": "string"},
                    "semantic_score": {"type": "number"},
                    "composition_score": {"type": "number"},
                    "subject_state_score": {"type": "number"},
                    "rarity_score": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": ["photo_id", "semantic_score", "composition_score", "subject_state_score", "rarity_score", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["schema_version", "ranking"],
    "additionalProperties": False,
}

GROUP_COMPARE_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "schema_version": {"type": "string"},
        "best_photo_id": {"type": "string"},
        "keep_photo_ids": {"type": "array", "items": {"type": "string"}},
        "reject_photo_ids": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
        "reason_by_photo_id": {"type": "object"},
        "ranking": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "photo_id": {"type": "string"},
                    "rank": {"type": "integer"},
                    "semantic_score": {"type": "number"},
                    "rarity_score": {"type": "number"},
                    "confidence": {"type": "number"},
                    "problem_tags": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                },
                "required": ["photo_id", "rank", "semantic_score", "rarity_score", "confidence", "problem_tags", "reason"],
                "additionalProperties": False,
            },
        },
        "drop_candidates": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["schema_version", "best_photo_id", "keep_photo_ids", "reject_photo_ids", "confidence", "ranking", "reason_by_photo_id"],
    "additionalProperties": False,
}


@dataclass(slots=True)
class PreviousGroupState:
    group: Group
    members: list[GroupMember]
    paths: frozenset[str]


@dataclass(slots=True)
class PreviousAnalysisContext:
    job: Job
    evaluation_settings_match: bool
    photos_by_path: dict[str, Photo]
    photos_by_id: dict[str, Photo]
    evaluations_by_photo_id: dict[str, PhotoEvaluation]
    technical_by_photo_id: dict[str, TechnicalScore]
    groups_by_path_set: dict[frozenset[str], PreviousGroupState]
    ai_responses_by_group_id: dict[str, list[AIResponse]]


@dataclass(slots=True)
class GroupCompareResult:
    best_photo_id: str | None
    ranking_by_photo_id: dict[str, dict[str, object]]
    drop_candidates: set[str]
    keep_candidates: set[str]


@dataclass(slots=True)
class PhotoPreparationTask:
    photo_id: str
    file_path: str
    source_signature: str
    reuse_cached_metadata: bool
    cached_metadata: dict[str, object] | None


@dataclass(slots=True)
class PhotoPreparationResult:
    photo_id: str
    thumb_path: str
    preview_path: str
    metadata: dict[str, object]
    similarity_seed: float
    visual_features: dict[str, object]


@dataclass(slots=True)
class TechnicalScoreResult:
    photo_id: str
    metrics: TechnicalMetrics
    total: float


@dataclass(slots=True)
class SinglePhotoAITask:
    photo_id: str
    job_id: str
    group_id: str | None
    prompt_hash: str
    prompt_name: str
    target_photo_ids: list[str]
    payload: dict[str, object]


@dataclass(slots=True)
class SinglePhotoAIResult:
    photo_id: str
    task: SinglePhotoAITask
    response: AIResult
    semantic: SemanticMetrics


class PreviewGenerationError(RuntimeError):
    pass


class MetadataExtractionError(RuntimeError):
    pass


class AnalysisCanceled(RuntimeError):
    pass


def run_analysis(session, job_id: str, cancel_requested: Callable[[], bool] | None = None) -> None:
    job_repo = JobRepository(session)
    photo_repo = PhotoRepository(session)
    group_repo = GroupRepository(session)
    eval_repo = EvaluationRepository(session)
    failure_repo = FailureRepository(session)
    ai_client = VisionLanguageModelClient()

    job = job_repo.get(job_id)
    if job is None:
        raise ValueError(f"Job not found: {job_id}")

    previous_job = job_repo.previous_for_root_path(job.root_path, job.id)
    previous_context = _load_previous_context(session, job, previous_job) if previous_job is not None else None

    try:
        _raise_if_cancel_requested(session, job, cancel_requested)
        health = ai_client.health_check()
        if not _health_ready(health):
            _fail_job(session, job, failure_repo, "ai_health_failed", health.error_detail or "AI health check failed")
            return

        job.status = "running"
        job.started_at = job.started_at or datetime.now(timezone.utc)
        job.current_stage = "preview_exif"
        job.updated_at = datetime.now(timezone.utc)
        session.commit()
        _raise_if_cancel_requested(session, job, cancel_requested)

        reuse_cache = _reuse_cache_enabled(job)
        settings_snapshot = get_settings()
        photos = photo_repo.list_by_job(job_id)
        candidate_records: list[tuple[Photo, PhotoCandidate]] = []
        preparation_tasks = [
            _build_photo_preparation_task(
                photo,
                previous_photo=previous_context.photos_by_path.get(photo.file_path) if previous_context else None,
                reuse_cache=reuse_cache,
            )
            for photo in photos
        ]
        photos_by_id = {photo.id: photo for photo in photos}
        for task, result in _iter_with_concurrency(
            preparation_tasks,
            max_workers=settings_snapshot.image_processing_concurrency,
            worker=_prepare_photo_from_task,
        ):
            _raise_if_cancel_requested(session, job, cancel_requested)
            photo = photos_by_id[task.photo_id]
            try:
                if isinstance(result, BaseException):
                    raise result
                _apply_photo_preparation_result(photo, result)
                candidate_records.append(
                    (
                        photo,
                        PhotoCandidate(
                            photo_id=photo.id,
                            capture_timestamp_ms=photo.capture_timestamp_ms,
                            capture_order_index=photo.capture_order_index,
                            similarity_seed=result.similarity_seed,
                            visual_features=result.visual_features,
                        ),
                    )
                )
            except Exception as exc:
                logger.exception("Preview/EXIF processing failed for %s", photo.file_path)
                _record_failure(session, job, failure_repo, "preview_exif", str(exc), photo=photo, retryable=True, reason_code=_reason_code_for_exception("preview_exif", exc))
            finally:
                job.imported_files = len(candidate_records)
                job.updated_at = datetime.now(timezone.utc)
                session.commit()

        ordered_candidate_records = _sort_candidate_records(candidate_records)
        ordered_photos = [photo for photo, _ in ordered_candidate_records]

        _raise_if_cancel_requested(session, job, cancel_requested)
        job.current_stage = "grouped"
        job.updated_at = datetime.now(timezone.utc)
        groups, members = _group_candidates(job_id, ordered_candidate_records)
        group_repo.replace_for_job(job_id, groups, members)
        members_by_group_id = _group_members_by_group(members)
        job.grouped_files = len(ordered_candidate_records)
        session.commit()

        _raise_if_cancel_requested(session, job, cancel_requested)
        job.current_stage = "technically_scored"
        job.updated_at = datetime.now(timezone.utc)
        technical_tasks = [photo for photo in ordered_photos if not photo.is_missing]
        reusable_photo_ids: set[str] = set()
        photos_to_score: list[Photo] = []
        for photo in technical_tasks:
            _raise_if_cancel_requested(session, job, cancel_requested)
            try:
                if _reuse_technical_score(eval_repo, previous_context, photo, job.id):
                    reusable_photo_ids.add(photo.id)
                    _refresh_progress_counts(job, eval_repo)
                    job.updated_at = datetime.now(timezone.utc)
                    session.commit()
                else:
                    photos_to_score.append(photo)
            except Exception as exc:
                logger.exception("Technical score reuse failed for %s", photo.file_path)
                _record_failure(session, job, failure_repo, "technical_scoring", str(exc), photo=photo, retryable=True)
                _refresh_progress_counts(job, eval_repo)
                job.updated_at = datetime.now(timezone.utc)
                session.commit()
        for photo, result in _iter_with_concurrency(
            photos_to_score,
            max_workers=settings_snapshot.image_processing_concurrency,
            worker=_compute_technical_score_result,
        ):
            _raise_if_cancel_requested(session, job, cancel_requested)
            if photo.is_missing:
                continue
            try:
                if isinstance(result, BaseException):
                    raise result
                if photo.id not in reusable_photo_ids:
                    _apply_technical_score_result(session, eval_repo, photo, job.id, result)
            except Exception as exc:
                logger.exception("Technical scoring failed for %s", photo.file_path)
                _record_failure(session, job, failure_repo, "technical_scoring", str(exc), photo=photo, retryable=True, reason_code=_reason_code_for_exception("technical_scoring", exc))
            finally:
                _refresh_progress_counts(job, eval_repo)
                job.updated_at = datetime.now(timezone.utc)
                session.commit()

        _apply_group_relative_technical_scores(eval_repo, job, groups, members_by_group_id)
        _refresh_progress_counts(job, eval_repo)
        job.updated_at = datetime.now(timezone.utc)
        session.commit()

        _raise_if_cancel_requested(session, job, cancel_requested)
        job.current_stage = "semantically_scored"
        job.updated_at = datetime.now(timezone.utc)
        session.commit()
        for group in groups:
            _raise_if_cancel_requested(session, job, cancel_requested)
            try:
                member_ids = [member.photo_id for member in members_by_group_id[group.id]]
                reused = _reuse_group_results(
                    session,
                    eval_repo,
                    photo_repo,
                    previous_context,
                    job,
                    group,
                    members_by_group_id[group.id],
                )
                if not reused:
                    _evaluate_group(session, eval_repo, photo_repo, failure_repo, job, group, member_ids, ai_client)
            except Exception as exc:
                logger.exception("Group AI evaluation failed for %s", group.id)
                _record_failure(session, job, failure_repo, "semantically_scored", str(exc), group=group, retryable=True, reason_code=_reason_code_for_exception("semantically_scored", exc))
            finally:
                _refresh_progress_counts(job, eval_repo)
                job.updated_at = datetime.now(timezone.utc)
                session.commit()

        job.current_stage = "finalized"
        _refresh_progress_counts(job, eval_repo)
        job.status = "completed"
        job.finished_at = datetime.now(timezone.utc)
        job.updated_at = job.finished_at
        session.commit()
    except AnalysisCanceled:
        _cancel_job(session, job)


def reanalyze_photos(session, job_id: str, photo_ids: list[str], scope: str) -> None:
    photo_repo = PhotoRepository(session)
    eval_repo = EvaluationRepository(session)
    group_repo = GroupRepository(session)
    failure_repo = FailureRepository(session)
    ai_client = VisionLanguageModelClient()
    job = JobRepository(session).get(job_id)
    if job is None:
        raise ValueError(f"Job not found: {job_id}")

    impacted_groups: set[str] = set()
    for photo_id in photo_ids:
        photo = photo_repo.get(photo_id)
        if photo is None or photo.job_id != job_id or photo.is_missing:
            continue
        current = eval_repo.current_for_photo(photo_id, job_id)
        if current and current.group_id:
            impacted_groups.add(current.group_id)
        if scope in {"technical_only", "full"}:
            _score_photo(session, eval_repo, photo, job_id)
            session.commit()
    if scope in {"ai_only", "full"}:
        for group_id in impacted_groups:
            group = group_repo.get(group_id)
            if group is None:
                continue
            member_ids = [member.photo_id for member in group_repo.list_members(group_id)]
            _evaluate_group(session, eval_repo, photo_repo, failure_repo, job, group, member_ids, ai_client)
            session.commit()
    _refresh_progress_counts(job, eval_repo)
    session.commit()


def _chunked(items: list[T], chunk_size: int) -> list[list[T]]:
    size = max(1, chunk_size)
    return [items[index : index + size] for index in range(0, len(items), size)]


def _raise_if_cancel_requested(session, job: Job, cancel_requested: Callable[[], bool] | None) -> None:
    session.refresh(job)
    if bool(cancel_requested and cancel_requested()) or job.cancel_requested or job.status == "canceling":
        job.cancel_requested = True
        job.status = "canceling"
        job.updated_at = datetime.now(timezone.utc)
        session.commit()
        raise AnalysisCanceled()


def _cancel_job(session, job: Job) -> None:
    now = datetime.now(timezone.utc)
    job.status = "canceled"
    job.current_stage = "canceled"
    job.cancel_requested = True
    job.canceled_at = now
    job.finished_at = now
    job.updated_at = now
    session.commit()


def _map_with_concurrency(
    items: list[T],
    *,
    max_workers: int,
    worker: Callable[[T], R],
) -> list[tuple[T, R | BaseException]]:
    bounded_workers = max(1, min(max_workers, len(items))) if items else 1
    if bounded_workers == 1:
        results: list[tuple[T, R | BaseException]] = []
        for item in items:
            try:
                results.append((item, worker(item)))
            except BaseException as exc:
                results.append((item, exc))
        return results
    with ThreadPoolExecutor(max_workers=bounded_workers) as executor:
        futures = [executor.submit(worker, item) for item in items]
        mapped: list[tuple[T, R | BaseException]] = []
        for item, future in zip(items, futures, strict=True):
            try:
                mapped.append((item, future.result()))
            except BaseException as exc:
                mapped.append((item, exc))
        return mapped


def _iter_with_concurrency(
    items: list[T],
    *,
    max_workers: int,
    worker: Callable[[T], R],
) -> Iterator[tuple[T, R | BaseException]]:
    bounded_workers = max(1, min(max_workers, len(items))) if items else 1
    if bounded_workers == 1:
        for item in items:
            try:
                yield item, worker(item)
            except BaseException as exc:
                yield item, exc
        return

    iterator = iter(items)
    max_pending = bounded_workers * 2
    with ThreadPoolExecutor(max_workers=bounded_workers) as executor:
        pending = {}

        def submit_until_full() -> None:
            while len(pending) < max_pending:
                try:
                    item = next(iterator)
                except StopIteration:
                    return
                pending[executor.submit(worker, item)] = item

        submit_until_full()
        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                item = pending.pop(future)
                try:
                    yield item, future.result()
                except BaseException as exc:
                    yield item, exc
            submit_until_full()


def _build_photo_preparation_task(
    photo: Photo,
    *,
    previous_photo: Photo | None,
    reuse_cache: bool,
) -> PhotoPreparationTask:
    reuse_cached_metadata = bool(
        reuse_cache
        and previous_photo is not None
        and _same_source_signature(photo, previous_photo)
        and _has_cached_metadata(previous_photo)
    )
    cached_metadata = _metadata_from_photo(previous_photo) if previous_photo is not None and reuse_cached_metadata else None
    return PhotoPreparationTask(
        photo_id=photo.id,
        file_path=photo.file_path,
        source_signature=_source_signature_for_photo(photo),
        reuse_cached_metadata=reuse_cached_metadata,
        cached_metadata=cached_metadata,
    )


def _prepare_photo_from_task(task: PhotoPreparationTask) -> PhotoPreparationResult:
    file_path = Path(task.file_path)
    try:
        thumb_path, preview_path = ensure_preview_assets(path=file_path, source_signature=task.source_signature)
    except Exception as exc:
        raise PreviewGenerationError(str(exc)) from exc
    try:
        metadata = task.cached_metadata if task.reuse_cached_metadata and task.cached_metadata is not None else extract_image_metadata(file_path)
    except Exception as exc:
        raise MetadataExtractionError(str(exc)) from exc
    visual_features = compute_visual_features(file_path)
    return PhotoPreparationResult(
        photo_id=task.photo_id,
        thumb_path=str(thumb_path),
        preview_path=str(preview_path),
        metadata=metadata,
        similarity_seed=int(str(visual_features["phash"])[:4], 16) / 65535.0,
        visual_features=visual_features,
    )


def _apply_photo_preparation_result(photo: Photo, result: PhotoPreparationResult) -> None:
    photo.thumb_path = result.thumb_path
    photo.preview_path = result.preview_path
    photo.visual_features_json = json.dumps(result.visual_features)
    metadata = result.metadata
    photo.width = metadata["width"]
    photo.height = metadata["height"]
    photo.orientation = metadata["orientation"]
    photo.capture_time = metadata["capture_time"]
    photo.capture_timestamp_ms = metadata["capture_timestamp_ms"]
    photo.camera_model = metadata["camera_model"]
    photo.lens_model = metadata["lens_model"]
    photo.focal_length = metadata["focal_length"]
    photo.aperture = metadata["aperture"]
    photo.iso = metadata["iso"]
    photo.shutter_speed = metadata["shutter_speed"]
    photo.updated_at = datetime.now(timezone.utc)


def _metadata_from_photo(photo: Photo) -> dict[str, object]:
    return {
        "width": photo.width,
        "height": photo.height,
        "orientation": photo.orientation,
        "capture_time": photo.capture_time,
        "capture_timestamp_ms": photo.capture_timestamp_ms,
        "camera_model": photo.camera_model,
        "lens_model": photo.lens_model,
        "focal_length": photo.focal_length,
        "aperture": photo.aperture,
        "iso": photo.iso,
        "shutter_speed": photo.shutter_speed,
    }


def _prepare_photo(photo: Photo, *, previous_photo: Photo | None, reuse_cache: bool) -> None:
    task = _build_photo_preparation_task(photo, previous_photo=previous_photo, reuse_cache=reuse_cache)
    _apply_photo_preparation_result(photo, _prepare_photo_from_task(task))


def _sort_candidate_records(candidate_records: list[tuple[Photo, PhotoCandidate]]) -> list[tuple[Photo, PhotoCandidate]]:
    return sorted(
        candidate_records,
        key=lambda item: (
            item[1].capture_timestamp_ms if item[1].capture_timestamp_ms is not None else float("inf"),
            item[0].capture_order_index,
            item[0].file_path,
        ),
    )


def _group_candidates(job_id: str, candidate_records: list[tuple[Photo, PhotoCandidate]]) -> tuple[list[Group], list[GroupMember]]:
    settings = get_settings()
    groups: list[Group] = []
    members: list[GroupMember] = []
    current_members: list[tuple[Photo, PhotoCandidate]] = []
    boundary_reason = "job_start"
    built_records: list[tuple[Group, list[tuple[Photo, PhotoCandidate]]]] = []
    for photo, candidate in candidate_records:
        reason = grouping_boundary_reason(
            [item[1] for item in current_members],
            candidate,
            settings.time_proximity_seconds,
            settings.similarity_threshold,
        )
        if reason is not None and current_members:
            group = _build_group(job_id, current_members, members, boundary_reason=boundary_reason)
            groups.append(group)
            built_records.append((group, current_members))
            current_members = []
            boundary_reason = reason
        current_members.append((photo, candidate))
    if current_members:
        group = _build_group(job_id, current_members, members, boundary_reason=boundary_reason)
        groups.append(group)
        built_records.append((group, current_members))
    _mark_merge_suggestions(built_records, settings.time_proximity_seconds, settings.similarity_threshold)
    return groups, members


def _score_photo(session, eval_repo: EvaluationRepository, photo: Photo, job_id: str) -> None:
    _apply_technical_score_result(session, eval_repo, photo, job_id, _compute_technical_score_result(photo))


def _compute_technical_score_result(photo: Photo) -> TechnicalScoreResult:
    settings = get_settings()
    metrics_raw = compute_technical_metrics(Path(photo.file_path), settings.highlight_threshold, settings.shadow_threshold)
    metrics = TechnicalMetrics(**metrics_raw)
    total = compute_technical_total(metrics)
    return TechnicalScoreResult(photo_id=photo.id, metrics=metrics, total=total)


def _apply_technical_score_result(
    session,
    eval_repo: EvaluationRepository,
    photo: Photo,
    job_id: str,
    result: TechnicalScoreResult,
) -> None:
    metrics = result.metrics
    total = result.total
    eval_repo.add_technical(
        TechnicalScore(
            id=f"tech_{uuid.uuid4().hex[:10]}",
            photo_id=photo.id,
            job_id=job_id,
            sharpness_score=metrics.sharpness_score,
            motion_blur_score=metrics.motion_blur_score,
            highlight_clip_ratio=metrics.highlight_clip_ratio,
            shadow_clip_ratio=metrics.shadow_clip_ratio,
            technical_score_total=total,
            candidate_quality_score=total,
            reject_risk_score=_absolute_reject_risk(metrics, total),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    current = eval_repo.current_for_photo(photo.id, job_id)
    provisional_rating, provisional_selection = provisional_rating_from_technical(total, _threshold_map())
    eval_repo.add_evaluation(
        _build_evaluation(
            photo_id=photo.id,
            job_id=job_id,
            group_id=current.group_id if current else None,
            current=current,
            semantic=_semantic_from_current(current),
            rating=current.rating if current and current.user_override_flag else provisional_rating,
            selection_status=current.selection_status if current and current.user_override_flag else provisional_selection,
            evaluation_status="provisional",
            provisional_rating=provisional_rating,
            provisional_selection_status=provisional_selection,
            best_cut_flag=current.best_cut_flag if current else False,
            pick_flag=current.pick_flag if current and current.user_override_flag else False,
            reviewed_flag=current.reviewed_flag if current else False,
        )
    )
    _record_history(eval_repo, current, photo.id, job_id, provisional_rating, provisional_selection, "technical_refresh")
    session.flush()


def _apply_group_relative_technical_scores(
    eval_repo: EvaluationRepository,
    job: Job,
    groups: list[Group],
    members_by_group_id: dict[str, list[GroupMember]],
) -> None:
    for group in groups:
        group_members = members_by_group_id.get(group.id, [])
        scored = [
            (member, score)
            for member in group_members
            if (score := eval_repo.technical_for_photo(member.photo_id, job.id)) is not None
        ]
        if not scored:
            continue
        sharpness_ranks = _rank_percentiles({member.photo_id: score.sharpness_score for member, score in scored})
        exposure_ranks = _rank_percentiles({member.photo_id: _exposure_health(score) for member, score in scored})
        for member, score in scored:
            sharpness_rank = sharpness_ranks[member.photo_id]
            exposure_rank = exposure_ranks[member.photo_id]
            score.sharpness_rank = sharpness_rank
            score.exposure_rank = exposure_rank
            score.candidate_quality_score = _candidate_quality(score, sharpness_rank, exposure_rank)
            score.reject_risk_score = _reject_risk(score, sharpness_rank)
            score.updated_at = datetime.now(timezone.utc)
            _refresh_provisional_from_technical(eval_repo, job.id, group.id, member.photo_id, score)


def _refresh_provisional_from_technical(
    eval_repo: EvaluationRepository,
    job_id: str,
    group_id: str,
    photo_id: str,
    score: TechnicalScore,
) -> None:
    current = eval_repo.current_for_photo(photo_id, job_id)
    provisional_rating, provisional_selection = _provisional_from_technical_score(score)
    eval_repo.add_evaluation(
        _build_evaluation(
            photo_id=photo_id,
            job_id=job_id,
            group_id=group_id,
            current=current,
            semantic=SemanticMetrics(
                semantic_score=current.semantic_score if current else None,
                composition_score=current.composition_score if current else None,
                subject_state_score=current.subject_state_score if current else None,
                rarity_score=current.rarity_score if current else None,
                confidence_score=current.ai_confidence_score if current else None,
                problem_tags=_json_list(current.problem_tags_json) if current else None,
                reason=current.ai_reason if current else None,
            ),
            rating=current.rating if current and current.user_override_flag else provisional_rating,
            selection_status=current.selection_status if current and current.user_override_flag else provisional_selection,
            evaluation_status="provisional",
            provisional_rating=provisional_rating,
            provisional_selection_status=provisional_selection,
            best_cut_flag=current.best_cut_flag if current else False,
            pick_flag=current.pick_flag if current and current.user_override_flag else False,
            reviewed_flag=current.reviewed_flag if current else False,
        )
    )
    _record_history(eval_repo, current, photo_id, job_id, provisional_rating, provisional_selection, "technical_relative_refresh")


def _rank_percentiles(values_by_photo_id: dict[str, float]) -> dict[str, float]:
    if not values_by_photo_id:
        return {}
    if len(values_by_photo_id) == 1:
        return {next(iter(values_by_photo_id)): 100.0}
    ordered = sorted(values_by_photo_id.items(), key=lambda item: item[1])
    denominator = len(ordered) - 1
    return {
        photo_id: round((index / denominator) * 100.0, 2)
        for index, (photo_id, _value) in enumerate(ordered)
    }


def _candidate_quality(score: TechnicalScore, sharpness_rank: float, exposure_rank: float) -> float:
    return technical_candidate_quality(
        score.technical_score_total,
        sharpness_rank,
        exposure_rank,
        score.motion_blur_score,
    )


def _reject_risk(score: TechnicalScore, sharpness_rank: float) -> float:
    return technical_reject_risk(
        score.highlight_clip_ratio,
        score.shadow_clip_ratio,
        score.motion_blur_score,
        sharpness_rank,
    )


def _absolute_reject_risk(metrics: TechnicalMetrics, total: float) -> float:
    exposure_risk = min(100.0, (metrics.highlight_clip_ratio * 180.0) + (metrics.shadow_clip_ratio * 140.0))
    blur_risk = max(0.0, 100.0 - metrics.motion_blur_score)
    total_risk = max(0.0, 100.0 - total)
    return round((exposure_risk * 0.35) + (blur_risk * 0.35) + (total_risk * 0.30), 2)


def _exposure_health(score: TechnicalScore) -> float:
    return max(0.0, 100.0 - (score.highlight_clip_ratio * 180.0) - (score.shadow_clip_ratio * 140.0))


def _technical_decision_score(score: TechnicalScore | None) -> float:
    if score is None:
        return 0.0
    return score.candidate_quality_score if score.candidate_quality_score is not None else score.technical_score_total


def _obvious_reject(score: TechnicalScore | None, reject_threshold: float) -> bool:
    if score is None:
        return True
    if score.reject_risk_score is not None and score.reject_risk_score >= 88.0:
        return True
    return _technical_decision_score(score) < max(10.0, reject_threshold * 0.5)


def _json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed if isinstance(item, str)] if isinstance(parsed, list) else []


def _semantic_from_current(current: PhotoEvaluation | None) -> SemanticMetrics:
    return SemanticMetrics(
        semantic_score=current.semantic_score if current else None,
        composition_score=current.composition_score if current else None,
        subject_state_score=current.subject_state_score if current else None,
        rarity_score=current.rarity_score if current else None,
        confidence_score=current.ai_confidence_score if current else None,
        problem_tags=_json_list(current.problem_tags_json) if current else None,
        reason=current.ai_reason if current else None,
    )


def _provisional_from_technical_score(score: TechnicalScore) -> tuple[int | None, str]:
    return provisional_rating_from_technical_decision(
        _technical_decision_score(score),
        reject_risk_score=score.reject_risk_score,
        thresholds=_threshold_map(),
    )


def _evaluate_group(
    session,
    eval_repo: EvaluationRepository,
    photo_repo: PhotoRepository,
    failure_repo: FailureRepository,
    job: Job,
    group: Group,
    photo_ids: list[str],
    ai_client: VisionLanguageModelClient,
) -> None:
    settings = get_settings()
    current_evaluations = {
        photo_id: (eval_repo.current_for_photo(photo_id, job.id) or eval_repo.latest_for_photo(photo_id, job.id))
        for photo_id in photo_ids
    }
    technical_scores = {photo_id: eval_repo.technical_for_photo(photo_id, job.id) for photo_id in photo_ids}
    ordered_ids, candidate_pool, single_eval_ids = _select_ai_candidate_pool(
        photo_ids,
        technical_scores,
        reject_threshold=_threshold_map()["reject"],
        candidate_limit=settings.candidate_limit,
    )
    if group.merge_suggested:
        _mark_merge_suggested_group_for_review(eval_repo, job, group, current_evaluations, ordered_ids)
        return
    if settings.ai_concurrency <= 1:
        semantic_results = {
            photo_id: _evaluate_single_photo(eval_repo, photo_repo.get(photo_id), group.id, technical_scores[photo_id], ai_client)
            for photo_id in single_eval_ids
        }
    else:
        single_ai_tasks = [
            task
            for task in (
                _build_single_photo_ai_task(photo_repo.get(photo_id), group.id, technical_scores[photo_id])
                for photo_id in single_eval_ids
            )
            if task is not None
        ]
        semantic_results: dict[str, SemanticMetrics] = {}
        for task, result in _map_with_concurrency(
            single_ai_tasks,
            max_workers=settings.ai_concurrency,
            worker=lambda item: _execute_single_photo_ai_task(item, ai_client),
        ):
            if isinstance(result, BaseException):
                raise result
            _store_single_photo_ai_result(eval_repo, result)
            semantic_results[result.photo_id] = result.semantic
    for photo_id, semantic in semantic_results.items():
        if semantic.ai_failed:
            _record_failure(
                session,
                job,
                failure_repo,
                "semantically_scored",
                "AI response could not be parsed or did not match schema",
                photo=photo_repo.get(photo_id),
                retryable=True,
                reason_code="json_parse_failed",
            )
    compare_result = _choose_best_photo(eval_repo, photo_repo, group.id, candidate_pool or ordered_ids[:1], ai_client)
    for photo_id, ranking in compare_result.ranking_by_photo_id.items():
        semantic_results[photo_id] = _merge_group_compare_semantic(semantic_results.get(photo_id), ranking)

    resolved_outcomes: dict[str, tuple[SemanticMetrics, int | None, str, str]] = {}
    group.stale_flag = False
    group.stale_reason = None
    group.updated_at = datetime.now(timezone.utc)

    for photo_id in photo_ids:
        current = current_evaluations.get(photo_id)
        technical_total = _technical_decision_score(technical_scores[photo_id])
        semantic = semantic_results.get(photo_id)
        if semantic is None:
            rating = current.rating if current else None
            selection_status = current.selection_status if current else "normal"
            evaluation_status = current.evaluation_status if current else "provisional"
            semantic = _semantic_from_current(current)
            semantic.ai_failed = evaluation_status == "ai_eval_failed"
        else:
            rating, selection_status, evaluation_status = final_rating_from_scores(
                technical_total,
                semantic,
                _weight_map(),
                _threshold_map(),
            )
        if photo_id in compare_result.drop_candidates and not (current and current.user_override_flag):
            rating = None
            selection_status = "rejected"
            evaluation_status = "final"
        resolved_outcomes[photo_id] = (semantic, rating, selection_status, evaluation_status)

    overridden_best = next(
        (
            item.photo_id
            for item in current_evaluations.values()
            if item and item.user_override_flag and item.best_cut_flag and item.selection_status != "rejected"
        ),
        None,
    )
    chosen_best = overridden_best or _choose_best_photo_from_outcomes(
        ordered_ids,
        current_evaluations,
        resolved_outcomes,
        group.representative_photo_id,
        compare_result.best_photo_id,
    )
    group.best_photo_id = chosen_best
    group.representative_photo_id = ordered_ids[0] if ordered_ids else group.representative_photo_id

    for photo_id in photo_ids:
        current = current_evaluations.get(photo_id)
        semantic, rating, selection_status, evaluation_status = resolved_outcomes[photo_id]
        if current and current.user_override_flag:
            rating = current.rating
            selection_status = current.selection_status
            pick_flag = current.pick_flag
            best_cut_flag = current.best_cut_flag and photo_id == chosen_best
            reviewed_flag = current.reviewed_flag
        else:
            pick_flag = bool(photo_id in compare_result.keep_candidates or (rating is not None and rating >= 4))
            best_cut_flag = photo_id == chosen_best and selection_status != "rejected"
            reviewed_flag = current.reviewed_flag if current else False
        evaluation = _build_evaluation(
            photo_id=photo_id,
            job_id=job.id,
            group_id=group.id,
            current=current,
            semantic=semantic,
            rating=rating,
            selection_status=selection_status,
            evaluation_status=evaluation_status,
            provisional_rating=current.provisional_rating if current else None,
            provisional_selection_status=current.provisional_selection_status if current else "normal",
            best_cut_flag=best_cut_flag,
            pick_flag=pick_flag,
            reviewed_flag=reviewed_flag,
        )
        eval_repo.add_evaluation(evaluation)
        _record_history(eval_repo, current, photo_id, job.id, rating, selection_status, "analysis_refresh")
    if chosen_best is None and photo_ids:
        _record_failure(session, job, failure_repo, "semantically_scored", "Unable to select best photo", group=group, retryable=True, reason_code="json_parse_failed")


def _mark_merge_suggested_group_for_review(
    eval_repo: EvaluationRepository,
    job: Job,
    group: Group,
    current_evaluations: dict[str, PhotoEvaluation | None],
    ordered_ids: list[str],
) -> None:
    group.best_photo_id = None
    group.stale_flag = True
    group.stale_reason = "merge_suggested"
    group.updated_at = datetime.now(timezone.utc)
    for photo_id in ordered_ids:
        current = current_evaluations.get(photo_id)
        semantic = _semantic_from_current(current)
        evaluation = _build_evaluation(
            photo_id=photo_id,
            job_id=job.id,
            group_id=group.id,
            current=current,
            semantic=semantic,
            rating=current.rating if current else None,
            selection_status=current.selection_status if current else "normal",
            evaluation_status=current.evaluation_status if current else "provisional",
            provisional_rating=current.provisional_rating if current else None,
            provisional_selection_status=current.provisional_selection_status if current else "normal",
            best_cut_flag=False,
            pick_flag=current.pick_flag if current else False,
            reviewed_flag=current.reviewed_flag if current else False,
        )
        evaluation.stale_flag = True
        evaluation.stale_reason = "merge_suggested"
        eval_repo.add_evaluation(evaluation)
        _record_history(
            eval_repo,
            current,
            photo_id,
            job.id,
            evaluation.rating,
            evaluation.selection_status,
            "merge_suggested_review",
        )


def _evaluate_single_photo(
    eval_repo: EvaluationRepository,
    photo: Photo | None,
    group_id: str | None,
    technical: TechnicalScore | None,
    ai_client: VisionLanguageModelClient,
) -> SemanticMetrics:
    task = _build_single_photo_ai_task(photo, group_id, technical)
    if task is None:
        return SemanticMetrics(ai_failed=True)
    result = _execute_single_photo_ai_task(task, ai_client)
    _store_single_photo_ai_result(eval_repo, result)
    return result.semantic


def _build_single_photo_ai_task(
    photo: Photo | None,
    group_id: str | None,
    technical: TechnicalScore | None,
) -> SinglePhotoAITask | None:
    if photo is None:
        return None
    prompt, prompt_hash = load_prompt("single_image_v1")
    settings = get_settings()
    content = prompt.replace("{{ photo_id }}", photo.id).replace("{{ technical_score_total }}", str(technical.technical_score_total if technical else 0)).replace("{{ capture_time }}", photo.capture_time.isoformat() if photo.capture_time else "")
    payload = {
        "model": settings.ai_model_name,
        "max_tokens": settings.ai_max_tokens,
        "response_format": json_schema_response_format("single_image_review", SINGLE_IMAGE_RESPONSE_SCHEMA),
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": content},
                    {"type": "image_url", "image_url": {"url": build_data_url(Path(photo.preview_path or photo.file_path), settings.preview_size)}},
                ],
            }
        ],
    }
    return SinglePhotoAITask(
        photo_id=photo.id,
        job_id=photo.job_id,
        group_id=group_id,
        prompt_hash=prompt_hash,
        prompt_name="single_image_v1",
        target_photo_ids=[photo.id],
        payload=payload,
    )


def _execute_single_photo_ai_task(
    task: SinglePhotoAITask,
    ai_client: VisionLanguageModelClient,
) -> SinglePhotoAIResult:
    response = ai_client.evaluate("single", task.payload)
    response = _validate_ai_response(response, "single", task.target_photo_ids)
    ranking = response.parsed_json.get("ranking", [{}])[0] if response.parsed_json else {}
    semantic = SemanticMetrics(
        semantic_score=ranking.get("semantic_score"),
        composition_score=ranking.get("composition_score"),
        subject_state_score=ranking.get("subject_state_score"),
        rarity_score=ranking.get("rarity_score"),
        confidence_score=ranking.get("confidence"),
        problem_tags=ranking.get("problem_tags") if isinstance(ranking.get("problem_tags"), list) else None,
        reason=ranking.get("reason"),
        ai_failed=response.parsed_json is None,
    )
    return SinglePhotoAIResult(photo_id=task.photo_id, task=task, response=response, semantic=semantic)


def _store_single_photo_ai_result(eval_repo: EvaluationRepository, result: SinglePhotoAIResult) -> None:
    _store_ai_response(
        eval_repo,
        result.task.job_id,
        result.task.photo_id,
        result.task.group_id,
        "single",
        result.task.prompt_hash,
        result.task.prompt_name,
        result.response,
        result.task.target_photo_ids,
    )


def _select_ai_candidate_pool(
    photo_ids: list[str],
    technical_scores: dict[str, TechnicalScore | None],
    *,
    reject_threshold: float,
    candidate_limit: int,
) -> tuple[list[str], list[str], list[str]]:
    ordered_ids = sorted(
        photo_ids,
        key=lambda photo_id: _technical_decision_score(technical_scores[photo_id]),
        reverse=True,
    )
    candidate_pool = [
        photo_id
        for photo_id in ordered_ids
        if not _obvious_reject(technical_scores[photo_id], reject_threshold)
    ]
    if not candidate_pool:
        candidate_pool = ordered_ids[:1]
    return ordered_ids, candidate_pool, candidate_pool[:candidate_limit]


def _choose_best_photo(
    eval_repo: EvaluationRepository,
    photo_repo: PhotoRepository,
    group_id: str | None,
    photo_ids: list[str],
    ai_client: VisionLanguageModelClient,
) -> GroupCompareResult:
    contenders = list(photo_ids)
    if not contenders:
        return GroupCompareResult(best_photo_id=None, ranking_by_photo_id={}, drop_candidates=set(), keep_candidates=set())

    ranking_by_photo_id: dict[str, dict[str, object]] = {}
    drop_candidates: set[str] = set()
    keep_candidates: set[str] = set()
    while len(contenders) > 6:
        winners: list[str] = []
        for chunk in _overlapping_compare_windows(contenders):
            result = _compare_chunk(eval_repo, photo_repo, group_id, chunk, ai_client)
            _merge_group_compare_payloads(ranking_by_photo_id, result.ranking_by_photo_id)
            drop_candidates.update(result.drop_candidates)
            keep_candidates.update(result.keep_candidates)
            winners.append(result.best_photo_id or chunk[0])
        contenders = list(dict.fromkeys([*winners, *contenders[: min(3, len(contenders))]]))[:6]
    result = _compare_chunk(eval_repo, photo_repo, group_id, contenders, ai_client)
    _merge_group_compare_payloads(ranking_by_photo_id, result.ranking_by_photo_id)
    drop_candidates.update(result.drop_candidates)
    keep_candidates.update(result.keep_candidates)
    return GroupCompareResult(
        best_photo_id=result.best_photo_id or contenders[0],
        ranking_by_photo_id=ranking_by_photo_id,
        drop_candidates=drop_candidates,
        keep_candidates=keep_candidates,
    )


def _overlapping_compare_windows(photo_ids: list[str], window_size: int = 6, overlap: int = 2) -> list[list[str]]:
    if len(photo_ids) <= window_size:
        return [photo_ids]
    stride = max(1, window_size - overlap)
    windows = [
        photo_ids[index : index + window_size]
        for index in range(0, len(photo_ids), stride)
        if index + window_size <= len(photo_ids)
    ]
    last_window = photo_ids[-window_size:]
    if not windows or windows[-1] != last_window:
        windows.append(last_window)
    return windows


def _compare_chunk(
    eval_repo: EvaluationRepository,
    photo_repo: PhotoRepository,
    group_id: str | None,
    photo_ids: list[str],
    ai_client: VisionLanguageModelClient,
) -> GroupCompareResult:
    prompt, prompt_hash = load_prompt("group_compare_v1")
    settings = get_settings()
    sheet_items: list[tuple[str, Path]] = []
    for photo_id in photo_ids:
        photo = photo_repo.get(photo_id)
        if photo is None:
            continue
        sheet_items.append((photo_id, Path(photo.preview_path or photo.file_path)))
    contact_sheet_url, label_map = build_contact_sheet_data_url(
        sheet_items,
        settings.compare_preview_size,
        settings.preview_jpeg_quality,
    )
    label_map_text = "\n".join(f"{label}: {photo_id}" for label, photo_id in label_map.items())
    content = [
        {
            "type": "text",
            "text": prompt.replace("{{ candidate_photo_ids }}", ", ".join(photo_ids)).replace("{{ label_photo_id_map }}", label_map_text),
        },
        {"type": "image_url", "image_url": {"url": contact_sheet_url}},
    ]
    payload = {
        "model": settings.ai_model_name,
        "max_tokens": settings.ai_max_tokens,
        "response_format": json_schema_response_format("group_compare_review", GROUP_COMPARE_RESPONSE_SCHEMA),
        "messages": [{"role": "user", "content": content}],
    }
    response = ai_client.evaluate("group_compare", payload)
    response = _validate_ai_response(response, "group_compare", photo_ids)
    if photo_ids:
        exemplar = photo_repo.get(photo_ids[0])
        if exemplar is not None:
            _store_ai_response(
                eval_repo,
                exemplar.job_id,
                None,
                group_id,
                "group_compare",
                prompt_hash,
                "group_compare_v1",
                response,
                photo_ids,
            )
    if response.parsed_json is None:
        return GroupCompareResult(best_photo_id=None, ranking_by_photo_id={}, drop_candidates=set(), keep_candidates=set())

    ranking_by_photo_id = {}
    for item in response.parsed_json.get("ranking", []):
        if not isinstance(item, dict):
            continue
        photo_id = item.get("photo_id")
        if not photo_id or str(photo_id) not in photo_ids:
            continue
        ranking_by_photo_id[str(photo_id)] = {
            "semantic_score": item.get("semantic_score"),
            "rarity_score": item.get("rarity_score"),
            "confidence": item.get("confidence"),
            "problem_tags": item.get("problem_tags"),
            "reason": item.get("reason"),
            "rank": item.get("rank"),
        }

    reject_ids = response.parsed_json.get("reject_photo_ids", response.parsed_json.get("drop_candidates", []))
    drop_candidates = {
        str(photo_id)
        for photo_id in reject_ids
        if str(photo_id) in photo_ids
    }
    keep_candidates = {
        str(photo_id)
        for photo_id in response.parsed_json.get("keep_photo_ids", [])
        if str(photo_id) in photo_ids
    }
    best_photo_id = response.parsed_json.get("best_photo_id")
    return GroupCompareResult(
        best_photo_id=str(best_photo_id) if best_photo_id else None,
        ranking_by_photo_id=ranking_by_photo_id,
        drop_candidates=drop_candidates,
        keep_candidates=keep_candidates,
    )


def _validate_ai_response(response, phase: str, photo_ids: list[str]):
    if response.parsed_json is None:
        return response
    normalized = normalize_and_validate_ai_payload(phase, response.parsed_json, photo_ids)
    if normalized is not None:
        response.parsed_json = normalized
        return response
    response.parsed_json = None
    response.status = "ai_eval_failed"
    return response


def normalize_and_validate_ai_payload(phase: str, payload: dict[str, object] | None, photo_ids: list[str]) -> dict[str, object] | None:
    if payload is None or not _validate_common_ai_payload(payload):
        return None
    normalized = _normalize_single_payload(payload, photo_ids) if phase == "single" else _normalize_group_compare_payload(payload, photo_ids)
    if normalized is None:
        return None
    valid = _validate_single_payload(normalized, photo_ids) if phase == "single" else _validate_group_compare_payload(normalized, photo_ids)
    return normalized if valid else None


def _normalize_single_payload(payload: dict[str, object], photo_ids: list[str]) -> dict[str, object] | None:
    expected_ids = set(photo_ids)
    ranking = payload.get("ranking")
    if not isinstance(ranking, list) or not ranking:
        return dict(payload)
    normalized_items = []
    for item in ranking:
        if not isinstance(item, dict):
            normalized_items.append(item)
            continue
        normalized_item = dict(item)
        photo_id = _coerce_photo_id(normalized_item.get("photo_id"), photo_ids)
        if photo_id is not None:
            normalized_item["photo_id"] = photo_id
        elif len(expected_ids) == 1:
            normalized_item["photo_id"] = photo_ids[0]
        normalized_items.append(normalized_item)
    if len(expected_ids) == 1 and len(normalized_items) > 1:
        ranked_items = [item for item in normalized_items if isinstance(item, dict) and item.get("photo_id") == photo_ids[0]]
        if len(ranked_items) == len(normalized_items):
            normalized_items = [max(ranked_items, key=_single_ranking_quality)]
    normalized = dict(payload)
    normalized["ranking"] = normalized_items
    return normalized


def _normalize_group_compare_payload(payload: dict[str, object], photo_ids: list[str]) -> dict[str, object] | None:
    expected_ids = set(photo_ids)
    normalized = dict(payload)
    ranking = payload.get("ranking")
    if isinstance(ranking, list):
        normalized_ranking = []
        for item in ranking:
            if not isinstance(item, dict):
                normalized_ranking.append(item)
                continue
            normalized_item = dict(item)
            photo_id = _coerce_photo_id(normalized_item.get("photo_id"), photo_ids)
            if photo_id is not None:
                normalized_item["photo_id"] = photo_id
            normalized_ranking.append(normalized_item)
        normalized["ranking"] = normalized_ranking

    best_photo_id = _coerce_photo_id(normalized.get("best_photo_id"), photo_ids)
    if best_photo_id is not None:
        normalized["best_photo_id"] = best_photo_id
        ranking_items = normalized.get("ranking")
        if isinstance(ranking_items, list) and not any(isinstance(item, dict) and item.get("photo_id") == best_photo_id for item in ranking_items):
            rank_one_items = [item for item in ranking_items if isinstance(item, dict) and item.get("rank") == 1]
            if len(rank_one_items) == 1 and _coerce_photo_id(rank_one_items[0].get("photo_id"), photo_ids) is None:
                rank_one_items[0]["photo_id"] = best_photo_id
        if isinstance(ranking_items, list):
            valid_ranking_ids = {item.get("photo_id") for item in ranking_items if isinstance(item, dict) and item.get("photo_id") in expected_ids}
            invalid_ranking_items = [item for item in ranking_items if isinstance(item, dict) and item.get("photo_id") not in expected_ids]
            missing_ranking_ids = [photo_id for photo_id in photo_ids if photo_id not in valid_ranking_ids]
            if len(invalid_ranking_items) == 1 and len(missing_ranking_ids) == 1:
                invalid_ranking_items[0]["photo_id"] = missing_ranking_ids[0]
    if "confidence" not in normalized or not _is_number(normalized.get("confidence")):
        normalized["confidence"] = 0.0
    if not isinstance(normalized.get("keep_photo_ids"), list):
        normalized["keep_photo_ids"] = [best_photo_id] if isinstance(best_photo_id, str) and best_photo_id in expected_ids else []
    normalized["keep_photo_ids"] = _valid_photo_id_list(normalized.get("keep_photo_ids"), photo_ids)
    reject_source = normalized.get("reject_photo_ids")
    if not isinstance(reject_source, list):
        reject_source = normalized.get("drop_candidates")
    normalized["reject_photo_ids"] = _valid_photo_id_list(reject_source, photo_ids)
    if isinstance(normalized.get("drop_candidates"), list):
        normalized["drop_candidates"] = _valid_photo_id_list(normalized.get("drop_candidates"), photo_ids)

    reason_by_photo_id = normalized.get("reason_by_photo_id")
    if isinstance(reason_by_photo_id, dict):
        reasons = {}
        for photo_id, reason in reason_by_photo_id.items():
            coerced_id = _coerce_photo_id(photo_id, photo_ids)
            if coerced_id is not None and isinstance(reason, str):
                reasons[coerced_id] = reason
    else:
        reasons = {}
    for item in normalized.get("ranking", []) if isinstance(normalized.get("ranking"), list) else []:
        if isinstance(item, dict) and isinstance(item.get("photo_id"), str) and item["photo_id"] in expected_ids and isinstance(item.get("reason"), str):
            reasons.setdefault(str(item["photo_id"]), str(item["reason"]))
    normalized["reason_by_photo_id"] = reasons
    return normalized


def _valid_photo_id_list(value: object, photo_ids: list[str]) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for value_item in value:
        photo_id = _coerce_photo_id(value_item, photo_ids)
        if photo_id is not None and photo_id not in result:
            result.append(photo_id)
    return result


def _coerce_photo_id(value: object, photo_ids: list[str]) -> str | None:
    if not isinstance(value, str):
        return None
    expected_ids = set(photo_ids)
    if value in expected_ids:
        return value
    if len(value) == 1 and value.isalpha():
        index = ord(value.upper()) - ord("A")
        if 0 <= index < len(photo_ids):
            return photo_ids[index]
    for photo_id in photo_ids:
        if photo_id in value:
            return photo_id
    compact_value = "".join(character for character in value.replace("photo_id_", "photo_") if character.isalnum() or character == "_")
    if compact_value in expected_ids:
        return compact_value
    close_matches = [
        (SequenceMatcher(None, compact_value, photo_id).ratio(), photo_id)
        for photo_id in photo_ids
        if compact_value.startswith(photo_id[:10]) or photo_id.startswith(compact_value[:10])
    ]
    if not close_matches:
        return None
    best_ratio, best_photo_id = max(close_matches, key=lambda item: item[0])
    return best_photo_id if best_ratio >= 0.78 else None


def _single_ranking_quality(item: dict[str, object]) -> float:
    score = 0.0
    for key in ("semantic_score", "composition_score", "subject_state_score", "rarity_score"):
        value = item.get(key)
        if _is_number(value):
            score += float(value)
    return score


def _validate_common_ai_payload(payload: dict[str, object]) -> bool:
    return payload.get("schema_version") == get_settings().response_schema_version


def _validate_single_payload(payload: dict[str, object], photo_ids: list[str]) -> bool:
    if not _validate_common_ai_payload(payload):
        return False
    ranking = payload.get("ranking")
    if not isinstance(ranking, list) or len(ranking) != 1:
        return False
    return _validate_ranking_item(ranking[0], set(photo_ids), require_rank=False)


def _validate_group_compare_payload(payload: dict[str, object], photo_ids: list[str]) -> bool:
    if not _validate_common_ai_payload(payload):
        return False
    expected_ids = set(photo_ids)
    best_photo_id = payload.get("best_photo_id")
    if not isinstance(best_photo_id, str) or best_photo_id not in expected_ids:
        return False
    if not _is_number(payload.get("confidence")):
        return False
    keep_photo_ids = payload.get("keep_photo_ids")
    if not isinstance(keep_photo_ids, list) or not all(isinstance(photo_id, str) and photo_id in expected_ids for photo_id in keep_photo_ids):
        return False
    reject_photo_ids = payload.get("reject_photo_ids")
    if not isinstance(reject_photo_ids, list) or not all(isinstance(photo_id, str) and photo_id in expected_ids for photo_id in reject_photo_ids):
        return False
    reason_by_photo_id = payload.get("reason_by_photo_id")
    if not isinstance(reason_by_photo_id, dict):
        return False
    if not all(isinstance(photo_id, str) and photo_id in expected_ids and isinstance(reason, str) for photo_id, reason in reason_by_photo_id.items()):
        return False
    ranking = payload.get("ranking")
    if not isinstance(ranking, list) or not ranking:
        return False
    if not all(_validate_ranking_item(item, expected_ids, require_rank=True) for item in ranking):
        return False
    drop_candidates = payload.get("drop_candidates")
    return drop_candidates is None or (isinstance(drop_candidates, list) and all(isinstance(photo_id, str) and photo_id in expected_ids for photo_id in drop_candidates))


def _validate_ranking_item(item: object, photo_ids: set[str], *, require_rank: bool) -> bool:
    if not isinstance(item, dict):
        return False
    photo_id = item.get("photo_id")
    if not isinstance(photo_id, str) or photo_id not in photo_ids:
        return False
    if require_rank and not isinstance(item.get("rank"), int):
        return False
    if not _is_number(item.get("semantic_score")):
        return False
    if "composition_score" in item and not _is_number(item.get("composition_score")):
        return False
    if "subject_state_score" in item and not _is_number(item.get("subject_state_score")):
        return False
    if "rarity_score" in item and not _is_number(item.get("rarity_score")):
        return False
    if "confidence" in item and not _is_number(item.get("confidence")):
        return False
    if "problem_tags" in item:
        problem_tags = item.get("problem_tags")
        if not isinstance(problem_tags, list) or not all(isinstance(tag, str) for tag in problem_tags):
            return False
    return isinstance(item.get("reason"), str) and bool(item.get("reason"))


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _merge_group_compare_semantic(existing: SemanticMetrics | None, ranking: dict[str, object]) -> SemanticMetrics:
    merged = existing or SemanticMetrics()
    if ranking.get("semantic_score") is not None:
        merged.semantic_score = float(ranking["semantic_score"])
    if ranking.get("rarity_score") is not None:
        merged.rarity_score = float(ranking["rarity_score"])
    if ranking.get("confidence") is not None:
        merged.confidence_score = float(ranking["confidence"])
    if isinstance(ranking.get("problem_tags"), list):
        merged.problem_tags = [str(tag) for tag in ranking["problem_tags"] if isinstance(tag, str)]
    if ranking.get("reason"):
        merged.reason = str(ranking["reason"])
    return merged


def _merge_group_compare_payloads(target: dict[str, dict[str, object]], source: dict[str, dict[str, object]]) -> None:
    for photo_id, payload in source.items():
        merged = dict(target.get(photo_id, {}))
        merged.update({key: value for key, value in payload.items() if value is not None})
        target[photo_id] = merged


def _choose_best_photo_from_outcomes(
    ordered_ids: list[str],
    current_evaluations: dict[str, PhotoEvaluation | None],
    outcomes: dict[str, tuple[SemanticMetrics, int | None, str, str]],
    representative_photo_id: str | None,
    preferred_photo_id: str | None,
) -> str | None:
    candidates = [
        photo_id
        for photo_id in ordered_ids
        if outcomes[photo_id][2] != "rejected"
    ]
    if not candidates:
        return None
    if preferred_photo_id and preferred_photo_id in candidates:
        return preferred_photo_id

    rated = [photo_id for photo_id in candidates if outcomes[photo_id][1] is not None]
    if rated:
        return sorted(
            rated,
            key=lambda photo_id: (
                outcomes[photo_id][1] or 0,
                current_evaluations[photo_id].provisional_rating if current_evaluations[photo_id] else 0,
                -ordered_ids.index(photo_id),
            ),
            reverse=True,
        )[0]

    provisional = [
        photo_id
        for photo_id in candidates
        if current_evaluations[photo_id] and current_evaluations[photo_id].provisional_rating is not None
    ]
    if provisional:
        return sorted(
            provisional,
            key=lambda photo_id: (
                current_evaluations[photo_id].provisional_rating if current_evaluations[photo_id] else 0,
                -ordered_ids.index(photo_id),
            ),
            reverse=True,
        )[0]

    if representative_photo_id and representative_photo_id in candidates:
        return representative_photo_id
    return candidates[0]


def _store_ai_response(
    eval_repo: EvaluationRepository,
    job_id: str,
    photo_id: str | None,
    group_id: str | None,
    phase: str,
    prompt_hash: str,
    prompt_name: str,
    response,
    target_photo_ids: list[str],
) -> None:
    sanitized_payload = dict(response.payload)
    messages = []
    for message in sanitized_payload.get("messages", []):
        if not isinstance(message, dict):
            continue
        safe_message = dict(message)
        content = []
        for item in safe_message.get("content", []):
            if isinstance(item, dict) and item.get("type") == "image_url":
                content.append({"type": "image_url", "image_ref": "preview_jpeg"})
            else:
                content.append(item)
        safe_message["content"] = content
        messages.append(safe_message)
    sanitized_payload["messages"] = messages
    eval_repo.add_ai_response(
        AIResponse(
            id=f"ai_{uuid.uuid4().hex[:10]}",
            job_id=job_id,
            photo_id=photo_id,
            group_id=group_id,
            phase=phase,
            model_name=get_settings().ai_model_name,
            prompt_template_name=prompt_name,
            prompt_template_hash=prompt_hash,
            response_schema_version=get_settings().response_schema_version,
            request_payload=json.dumps(sanitized_payload),
            response_json=json.dumps(response.parsed_json) if response.parsed_json else None,
            raw_response_text=response.raw_response_text[:1000] if response.raw_response_text else None,
            raw_response_path=None,
            target_photo_ids_json=json.dumps(target_photo_ids),
            response_status=response.status,
            latency_ms=response.latency_ms,
            requested_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
    )


def _mark_merge_suggestions(
    group_records: list[tuple[Group, list[tuple[Photo, PhotoCandidate]]]],
    time_proximity_seconds: int,
    similarity_threshold: float,
) -> None:
    if len(group_records) < 2:
        return
    for previous, current in zip(group_records, group_records[1:], strict=False):
        previous_group, previous_members = previous
        current_group, current_members = current
        gap_seconds = _group_gap_seconds(previous_members, current_members)
        if gap_seconds is None or gap_seconds > max(12, time_proximity_seconds * 2):
            continue
        if min(len(previous_members), len(current_members)) > 4:
            continue
        if not _metadata_compatible(previous_members[-1][0], current_members[0][0]):
            continue
        similarity = max_group_similarity([item[1] for item in previous_members], current_members[0][1])
        if similarity < max(0.0, similarity_threshold - 0.1):
            continue
        current_group.merge_suggested = True
        current_group.merge_suggestion_reason = f"adjacent_gap={gap_seconds:.3f}s;similarity={similarity:.3f};previous_group={previous_group.id}"


def _group_gap_seconds(
    previous_members: list[tuple[Photo, PhotoCandidate]],
    current_members: list[tuple[Photo, PhotoCandidate]],
) -> float | None:
    previous_ts = previous_members[-1][1].capture_timestamp_ms
    current_ts = current_members[0][1].capture_timestamp_ms
    if previous_ts is None or current_ts is None:
        return None
    return max(0.0, (current_ts - previous_ts) / 1000.0)


def _metadata_compatible(previous: Photo, current: Photo) -> bool:
    if previous.camera_model and current.camera_model and previous.camera_model != current.camera_model:
        return False
    if previous.lens_model and current.lens_model and previous.lens_model != current.lens_model:
        return False
    if previous.focal_length is not None and current.focal_length is not None:
        return abs(previous.focal_length - current.focal_length) <= max(5.0, previous.focal_length * 0.05)
    return True


def _build_group(
    job_id: str,
    current_members: list[tuple[Photo, PhotoCandidate]],
    members: list[GroupMember],
    *,
    boundary_reason: str,
) -> Group:
    group_id = f"group_{uuid.uuid4().hex[:10]}"
    candidates = [candidate for _, candidate in current_members]
    for order, (photo, candidate) in enumerate(current_members):
        members.append(
            GroupMember(
                id=f"gm_{uuid.uuid4().hex[:12]}",
                group_id=group_id,
                photo_id=photo.id,
                sort_order=order,
                similarity_score=max_group_similarity(candidates[:order], candidate) if order else 1.0,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
    return Group(
        id=group_id,
        job_id=job_id,
        representative_photo_id=current_members[0][0].id,
        best_photo_id=None,
        group_size=len(current_members),
        group_start_time=current_members[0][0].capture_time,
        group_end_time=current_members[-1][0].capture_time,
        diversity_score=None,
        boundary_reason=boundary_reason,
        merge_suggested=False,
        merge_suggestion_reason=None,
        stale_flag=False,
        stale_reason=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _build_evaluation(
    *,
    photo_id: str,
    job_id: str,
    group_id: str | None,
    current: PhotoEvaluation | None,
    semantic: SemanticMetrics,
    rating: int | None,
    selection_status: str,
    evaluation_status: str,
    provisional_rating: int | None,
    provisional_selection_status: str,
    best_cut_flag: bool,
    pick_flag: bool,
    reviewed_flag: bool,
) -> PhotoEvaluation:
    return PhotoEvaluation(
        id=f"eval_{uuid.uuid4().hex[:10]}",
        photo_id=photo_id,
        job_id=job_id,
        group_id=group_id,
        semantic_score=semantic.semantic_score,
        composition_score=semantic.composition_score,
        subject_state_score=semantic.subject_state_score,
        rarity_score=semantic.rarity_score,
        ai_confidence_score=semantic.confidence_score,
        problem_tags_json=json.dumps(semantic.problem_tags or []),
        provisional_rating=provisional_rating,
        provisional_selection_status=provisional_selection_status,
        rating=rating,
        selection_status=selection_status,
        evaluation_status=evaluation_status,
        pick_flag=pick_flag,
        best_cut_flag=best_cut_flag,
        reviewed_flag=reviewed_flag,
        ai_reason=semantic.reason,
        user_override_flag=current.user_override_flag if current else False,
        stale_flag=False,
        stale_reason=None,
        version=1,
        is_current=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _refresh_progress_counts(job: Job, eval_repo: EvaluationRepository) -> None:
    current = eval_repo.list_current_for_job(job.id)
    job.failed_files = len(json.loads(job.error_messages_json))
    job.provisional_rated_files = len([item for item in current if item.evaluation_status == "provisional"])
    job.final_rated_files = len([item for item in current if item.evaluation_status in {"final", "ai_eval_failed"}])
    job.technically_scored_files = len([item for item in current if item.provisional_rating is not None or item.provisional_selection_status == "rejected"])
    job.semantically_scored_files = len([item for item in current if item.evaluation_status in {"final", "ai_eval_failed"}])


def _record_failure(
    session,
    job: Job,
    failure_repo: FailureRepository,
    stage: str,
    message: str,
    *,
    photo: Photo | None = None,
    group: Group | None = None,
    retryable: bool,
    reason_code: str | None = None,
) -> None:
    payload = json.loads(job.error_messages_json)
    payload.append(f"{stage}:{message}")
    job.error_messages_json = json.dumps(payload)
    failure_repo.add(
        JobFailure(
            id=f"fail_{uuid.uuid4().hex[:10]}",
            job_id=job.id,
            photo_id=photo.id if photo else None,
            group_id=group.id if group else None,
            stage=stage,
            reason_code=reason_code or stage,
            message=message,
            retryable=retryable,
            created_at=datetime.now(timezone.utc),
        )
    )
    session.flush()


def _record_history(eval_repo: EvaluationRepository, current: PhotoEvaluation | None, photo_id: str, job_id: str, new_rating: int | None, new_selection_status: str, reason: str) -> None:
    eval_repo.record_history(
        RatingHistory(
            id=f"hist_{uuid.uuid4().hex[:10]}",
            photo_id=photo_id,
            job_id=job_id,
            old_rating=current.rating if current else None,
            new_rating=new_rating,
            old_selection_status=current.selection_status if current else None,
            new_selection_status=new_selection_status,
            changed_by_user=False,
            changed_at=datetime.now(timezone.utc),
            reason=reason,
        )
    )


def _fail_job(session, job: Job, failure_repo: FailureRepository, stage: str, message: str) -> None:
    now = datetime.now(timezone.utc)
    job.status = "failed"
    job.current_stage = stage
    job.finished_at = now
    job.updated_at = now
    _record_failure(session, job, failure_repo, stage, message, retryable=False)
    session.commit()


def _reason_code_for_exception(stage: str, exc: BaseException) -> str:
    if isinstance(exc, PreviewGenerationError):
        return "preview_generation_failed"
    if isinstance(exc, MetadataExtractionError):
        return "metadata_extraction_failed"
    text = f"{type(exc).__name__}:{exc}".lower()
    if "timeout" in text and stage == "semantically_scored":
        return "ai_timeout"
    return stage


def _health_ready(health) -> bool:
    return bool(
        health.reachable
        and health.configured_model_exists
        and health.model_loadable
        and health.vision_capable
        and health.structured_json_capable
    )


def _weight_map() -> dict[str, float]:
    settings = get_settings()
    return {
        "technical_quality": settings.weights.technical_quality,
        "composition": settings.weights.composition,
        "subject_state": settings.weights.subject_state,
        "rarity": settings.weights.rarity,
    }


def _threshold_map() -> dict[str, float]:
    thresholds = get_settings().rating_thresholds
    return {
        "reject": thresholds.reject,
        "star_2": thresholds.star_2,
        "star_3": thresholds.star_3,
        "star_4": thresholds.star_4,
        "star_5": thresholds.star_5,
    }


def _reuse_cache_enabled(job: Job) -> bool:
    snapshot = json.loads(job.settings_snapshot_json)
    return bool(snapshot.get("reuse_cache", True))


def _load_previous_context(session, job: Job, previous_job: Job) -> PreviousAnalysisContext:
    photo_repo = PhotoRepository(session)
    eval_repo = EvaluationRepository(session)
    group_repo = GroupRepository(session)
    previous_photos = photo_repo.list_by_job(previous_job.id, include_missing=True)
    previous_photos_by_path = {photo.file_path: photo for photo in previous_photos}
    previous_photos_by_id = {photo.id: photo for photo in previous_photos}
    previous_evaluations = {evaluation.photo_id: evaluation for evaluation in eval_repo.list_current_for_job(previous_job.id)}
    previous_technical = {score.photo_id: score for score in eval_repo.list_technical_for_job(previous_job.id)}
    previous_groups_by_path_set: dict[frozenset[str], PreviousGroupState] = {}
    for group in group_repo.list_by_job(previous_job.id):
        members = group_repo.list_members(group.id)
        paths = frozenset(
            previous_photos_by_id[member.photo_id].file_path
            for member in members
            if member.photo_id in previous_photos_by_id and not previous_photos_by_id[member.photo_id].is_missing
        )
        if paths:
            previous_groups_by_path_set[paths] = PreviousGroupState(group=group, members=members, paths=paths)
    ai_responses_by_group_id: dict[str, list[AIResponse]] = {}
    for response in eval_repo.list_ai_responses_for_job(previous_job.id):
        if response.group_id is None:
            continue
        ai_responses_by_group_id.setdefault(response.group_id, []).append(response)
    return PreviousAnalysisContext(
        job=previous_job,
        evaluation_settings_match=_evaluation_settings_match(job, previous_job),
        photos_by_path=previous_photos_by_path,
        photos_by_id=previous_photos_by_id,
        evaluations_by_photo_id=previous_evaluations,
        technical_by_photo_id=previous_technical,
        groups_by_path_set=previous_groups_by_path_set,
        ai_responses_by_group_id=ai_responses_by_group_id,
    )


def _reuse_technical_score(
    eval_repo: EvaluationRepository,
    previous_context: PreviousAnalysisContext | None,
    photo: Photo,
    job_id: str,
) -> bool:
    if previous_context is None or not previous_context.evaluation_settings_match:
        return False
    previous_photo = previous_context.photos_by_path.get(photo.file_path)
    if previous_photo is None or not _same_source_signature(photo, previous_photo):
        return False
    previous_technical = previous_context.technical_by_photo_id.get(previous_photo.id)
    if previous_technical is None:
        return False

    eval_repo.add_technical(
        TechnicalScore(
            id=f"tech_{uuid.uuid4().hex[:10]}",
            photo_id=photo.id,
            job_id=job_id,
            sharpness_score=previous_technical.sharpness_score,
            motion_blur_score=previous_technical.motion_blur_score,
            highlight_clip_ratio=previous_technical.highlight_clip_ratio,
            shadow_clip_ratio=previous_technical.shadow_clip_ratio,
            technical_score_total=previous_technical.technical_score_total,
            sharpness_rank=previous_technical.sharpness_rank,
            exposure_rank=previous_technical.exposure_rank,
            candidate_quality_score=previous_technical.candidate_quality_score,
            reject_risk_score=previous_technical.reject_risk_score,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )

    previous_evaluation = previous_context.evaluations_by_photo_id.get(previous_photo.id)
    provisional_rating, provisional_selection = provisional_rating_from_technical(previous_technical.technical_score_total, _threshold_map())
    if previous_evaluation is not None:
        provisional_rating = previous_evaluation.provisional_rating if previous_evaluation.provisional_rating is not None else provisional_rating
        provisional_selection = previous_evaluation.provisional_selection_status or provisional_selection

    preserved_rating = provisional_rating
    preserved_selection = provisional_selection
    pick_flag = False
    best_cut_flag = False
    reviewed_flag = False
    user_override_flag = False
    if previous_evaluation is not None and previous_evaluation.user_override_flag:
        preserved_rating = previous_evaluation.rating
        preserved_selection = previous_evaluation.selection_status
        pick_flag = previous_evaluation.pick_flag
        best_cut_flag = previous_evaluation.best_cut_flag
        reviewed_flag = previous_evaluation.reviewed_flag
        user_override_flag = True

    evaluation = _build_evaluation(
        photo_id=photo.id,
        job_id=job_id,
        group_id=None,
        current=None,
        semantic=SemanticMetrics(),
        rating=preserved_rating,
        selection_status=preserved_selection,
        evaluation_status="provisional",
        provisional_rating=provisional_rating,
        provisional_selection_status=provisional_selection,
        best_cut_flag=best_cut_flag,
        pick_flag=pick_flag,
        reviewed_flag=reviewed_flag,
    )
    evaluation.user_override_flag = user_override_flag
    eval_repo.add_evaluation(evaluation)
    _record_history(eval_repo, None, photo.id, job_id, provisional_rating, provisional_selection, "technical_reuse")
    return True


def _reuse_group_results(
    session,
    eval_repo: EvaluationRepository,
    photo_repo: PhotoRepository,
    previous_context: PreviousAnalysisContext | None,
    job: Job,
    group: Group,
    members: list[GroupMember],
) -> bool:
    if previous_context is None or not previous_context.evaluation_settings_match:
        return False

    current_photos = [photo_repo.get(member.photo_id) for member in members]
    if any(photo is None for photo in current_photos):
        return False
    resolved_photos = [photo for photo in current_photos if photo is not None]
    current_paths = frozenset(photo.file_path for photo in resolved_photos)
    previous_group_state = previous_context.groups_by_path_set.get(current_paths)
    if previous_group_state is None or len(previous_group_state.members) != len(members):
        return False

    old_to_new_photo_ids: dict[str, str] = {}
    for photo in resolved_photos:
        previous_photo = previous_context.photos_by_path.get(photo.file_path)
        if previous_photo is None or not _same_source_signature(photo, previous_photo):
            return False
        previous_evaluation = previous_context.evaluations_by_photo_id.get(previous_photo.id)
        if previous_evaluation is None:
            return False
        old_to_new_photo_ids[previous_photo.id] = photo.id

    for photo in resolved_photos:
        previous_photo = previous_context.photos_by_path[photo.file_path]
        previous_evaluation = previous_context.evaluations_by_photo_id[previous_photo.id]
        cloned = _clone_group_evaluation(previous_evaluation, photo.id, job.id, group.id)
        eval_repo.add_evaluation(cloned)
        _record_history(eval_repo, None, photo.id, job.id, cloned.rating, cloned.selection_status, "analysis_reuse")

    previous_best_photo_id = previous_group_state.group.best_photo_id
    previous_representative_photo_id = previous_group_state.group.representative_photo_id
    group.best_photo_id = old_to_new_photo_ids.get(previous_best_photo_id) if previous_best_photo_id else None
    group.representative_photo_id = old_to_new_photo_ids.get(previous_representative_photo_id) if previous_representative_photo_id else group.representative_photo_id
    group.stale_flag = False
    group.stale_reason = None
    group.updated_at = datetime.now(timezone.utc)

    for response in previous_context.ai_responses_by_group_id.get(previous_group_state.group.id, []):
        eval_repo.add_ai_response(_clone_ai_response(response, job.id, group.id, old_to_new_photo_ids))

    session.flush()
    return True


def _group_members_by_group(members: list[GroupMember]) -> dict[str, list[GroupMember]]:
    grouped: dict[str, list[GroupMember]] = {}
    for member in members:
        grouped.setdefault(member.group_id, []).append(member)
    for group_id in grouped:
        grouped[group_id] = sorted(grouped[group_id], key=lambda item: item.sort_order)
    return grouped


def _same_source_signature(current: Photo, previous: Photo) -> bool:
    return _source_signature_for_photo(current) == _source_signature_for_photo(previous)


def _source_signature_for_photo(photo: Photo) -> str:
    return build_source_signature(photo.file_path, photo.file_hash, photo.file_size, photo.file_mtime)


def _has_cached_metadata(photo: Photo) -> bool:
    return photo.width is not None and photo.height is not None


def _evaluation_settings_match(current_job: Job, previous_job: Job) -> bool:
    current_snapshot = dict(json.loads(current_job.settings_snapshot_json))
    previous_snapshot = dict(json.loads(previous_job.settings_snapshot_json))
    current_snapshot.pop("reuse_cache", None)
    previous_snapshot.pop("reuse_cache", None)
    return current_snapshot == previous_snapshot


def _clone_group_evaluation(previous: PhotoEvaluation, photo_id: str, job_id: str, group_id: str) -> PhotoEvaluation:
    return PhotoEvaluation(
        id=f"eval_{uuid.uuid4().hex[:10]}",
        photo_id=photo_id,
        job_id=job_id,
        group_id=group_id,
        semantic_score=previous.semantic_score,
        composition_score=previous.composition_score,
        subject_state_score=previous.subject_state_score,
        rarity_score=previous.rarity_score,
        provisional_rating=previous.provisional_rating,
        provisional_selection_status=previous.provisional_selection_status,
        rating=previous.rating,
        selection_status=previous.selection_status,
        evaluation_status=previous.evaluation_status,
        pick_flag=previous.pick_flag,
        best_cut_flag=previous.best_cut_flag,
        reviewed_flag=previous.reviewed_flag,
        ai_reason=previous.ai_reason,
        ai_confidence_score=previous.ai_confidence_score,
        problem_tags_json=previous.problem_tags_json,
        user_override_flag=previous.user_override_flag,
        stale_flag=False,
        stale_reason=None,
        version=1,
        is_current=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _clone_ai_response(previous: AIResponse, job_id: str, group_id: str, old_to_new_photo_ids: dict[str, str]) -> AIResponse:
    translated_response_json = _translate_marshaled_json(previous.response_json, old_to_new_photo_ids)
    translated_payload = _translate_marshaled_json(previous.request_payload, old_to_new_photo_ids)
    translated_targets = _translate_marshaled_json(previous.target_photo_ids_json, old_to_new_photo_ids)
    return AIResponse(
        id=f"ai_{uuid.uuid4().hex[:10]}",
        job_id=job_id,
        photo_id=old_to_new_photo_ids.get(previous.photo_id) if previous.photo_id else None,
        group_id=group_id,
        phase=previous.phase,
        model_name=previous.model_name,
        prompt_template_name=previous.prompt_template_name,
        prompt_template_hash=previous.prompt_template_hash,
        response_schema_version=previous.response_schema_version,
        request_payload=translated_payload or previous.request_payload,
        response_json=translated_response_json,
        raw_response_text=_translate_raw_text(previous.raw_response_text, old_to_new_photo_ids),
        raw_response_path=previous.raw_response_path,
        target_photo_ids_json=translated_targets or previous.target_photo_ids_json,
        response_status=previous.response_status,
        latency_ms=previous.latency_ms,
        requested_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )


def _translate_marshaled_json(payload: str | None, old_to_new_photo_ids: dict[str, str]) -> str | None:
    if not payload:
        return payload
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return payload
    translated = _translate_payload(parsed, old_to_new_photo_ids)
    return json.dumps(translated, ensure_ascii=False)


def _translate_payload(value: Any, old_to_new_photo_ids: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {key: _translate_payload(item, old_to_new_photo_ids) for key, item in value.items()}
    if isinstance(value, list):
        return [_translate_payload(item, old_to_new_photo_ids) for item in value]
    if isinstance(value, str):
        translated = value
        for old_photo_id, new_photo_id in old_to_new_photo_ids.items():
            translated = translated.replace(old_photo_id, new_photo_id)
        return translated
    return value


def _translate_raw_text(raw_text: str | None, old_to_new_photo_ids: dict[str, str]) -> str | None:
    if raw_text is None:
        return None
    translated = raw_text
    for old_photo_id, new_photo_id in old_to_new_photo_ids.items():
        translated = translated.replace(old_photo_id, new_photo_id)
    return translated
