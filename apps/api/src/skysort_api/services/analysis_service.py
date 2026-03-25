from __future__ import annotations

import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from skysort_api.domain.evaluation import (
    SemanticMetrics,
    TechnicalMetrics,
    compute_technical_total,
    final_rating_from_scores,
    provisional_rating_from_technical,
)
from skysort_api.domain.grouping import PhotoCandidate, should_start_new_group
from skysort_api.infra.ai_client import VisionLanguageModelClient
from skysort_api.infra.image_tools import (
    build_data_url,
    compute_similarity_seed,
    compute_technical_metrics,
    ensure_preview_assets,
    extract_image_metadata,
)
from skysort_api.infra.models import AIResponse, Group, GroupMember, Job, JobFailure, Photo, PhotoEvaluation, RatingHistory, TechnicalScore
from skysort_api.infra.prompt_store import load_prompt
from skysort_api.infra.settings import get_settings

from .repositories import EvaluationRepository, FailureRepository, GroupRepository, JobRepository, PhotoRepository

logger = logging.getLogger(__name__)


def run_analysis(session, job_id: str) -> None:
    settings = get_settings()
    job_repo = JobRepository(session)
    photo_repo = PhotoRepository(session)
    group_repo = GroupRepository(session)
    eval_repo = EvaluationRepository(session)
    failure_repo = FailureRepository(session)
    ai_client = VisionLanguageModelClient()

    job = job_repo.get(job_id)
    if job is None:
        raise ValueError(f"Job not found: {job_id}")

    health = ai_client.health_check()
    if not _health_ready(health):
        _fail_job(session, job, failure_repo, "ai_health_failed", health.error_detail or "AI health check failed")
        return

    job.status = "running"
    job.started_at = job.started_at or datetime.now(timezone.utc)
    job.current_stage = "preview_exif"
    session.commit()

    photos = photo_repo.list_by_job(job_id)
    candidate_records: list[tuple[Photo, PhotoCandidate]] = []
    for photo in photos:
        try:
            _prepare_photo(photo)
            candidate_records.append(
                (
                    photo,
                    PhotoCandidate(
                        photo_id=photo.id,
                        capture_timestamp_ms=photo.capture_timestamp_ms,
                        capture_order_index=photo.capture_order_index,
                        similarity_seed=compute_similarity_seed(Path(photo.file_path)),
                    ),
                )
            )
        except Exception as exc:
            logger.exception("Preview/EXIF processing failed for %s", photo.file_path)
            _record_failure(session, job, failure_repo, "preview_exif", str(exc), photo=photo, retryable=True)
        finally:
            job.imported_files = len(candidate_records)
            session.commit()

    job.current_stage = "grouped"
    groups, members = _group_candidates(job_id, candidate_records)
    group_repo.replace_for_job(job_id, groups, members)
    job.grouped_files = len(candidate_records)
    session.commit()

    job.current_stage = "technically_scored"
    for photo in photos:
        if photo.is_missing:
            continue
        try:
            _score_photo(session, eval_repo, photo, job.id)
        except Exception as exc:
            logger.exception("Technical scoring failed for %s", photo.file_path)
            _record_failure(session, job, failure_repo, "technical_scoring", str(exc), photo=photo, retryable=True)
        finally:
            _refresh_progress_counts(job, eval_repo)
            session.commit()

    job.current_stage = "semantically_scored"
    for group in groups:
        try:
            member_ids = [member.photo_id for member in sorted((item for item in members if item.group_id == group.id), key=lambda item: item.sort_order)]
            _evaluate_group(session, eval_repo, photo_repo, failure_repo, job, group, member_ids, ai_client)
        except Exception as exc:
            logger.exception("Group AI evaluation failed for %s", group.id)
            _record_failure(session, job, failure_repo, "semantically_scored", str(exc), group=group, retryable=True)
        finally:
            _refresh_progress_counts(job, eval_repo)
            session.commit()

    job.current_stage = "finalized"
    _refresh_progress_counts(job, eval_repo)
    job.status = "completed"
    job.finished_at = datetime.now(timezone.utc)
    session.commit()


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


def _prepare_photo(photo: Photo) -> None:
    thumb_path, preview_path = ensure_preview_assets(path=Path(photo.file_path), photo_id=photo.id)
    metadata = extract_image_metadata(Path(photo.file_path))
    photo.thumb_path = str(thumb_path)
    photo.preview_path = str(preview_path)
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


def _group_candidates(job_id: str, candidate_records: list[tuple[Photo, PhotoCandidate]]) -> tuple[list[Group], list[GroupMember]]:
    settings = get_settings()
    groups: list[Group] = []
    members: list[GroupMember] = []
    current_members: list[tuple[Photo, PhotoCandidate]] = []
    previous: PhotoCandidate | None = None
    for photo, candidate in candidate_records:
        if should_start_new_group(previous, candidate, settings.time_proximity_seconds, settings.similarity_threshold) and current_members:
            groups.append(_build_group(job_id, current_members, members))
            current_members = []
        current_members.append((photo, candidate))
        previous = candidate
    if current_members:
        groups.append(_build_group(job_id, current_members, members))
    return groups, members


def _score_photo(session, eval_repo: EvaluationRepository, photo: Photo, job_id: str) -> None:
    settings = get_settings()
    metrics_raw = compute_technical_metrics(Path(photo.file_path), settings.highlight_threshold, settings.shadow_threshold)
    metrics = TechnicalMetrics(**metrics_raw)
    total = compute_technical_total(metrics)
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
            semantic=SemanticMetrics(),
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
    ordered_ids = sorted(
        photo_ids,
        key=lambda photo_id: (technical_scores[photo_id].technical_score_total if technical_scores[photo_id] else 0.0),
        reverse=True,
    )
    candidate_pool = [
        photo_id
        for photo_id in ordered_ids
        if (technical_scores[photo_id].technical_score_total if technical_scores[photo_id] else 0.0) >= _threshold_map()["reject"]
    ]
    if not candidate_pool:
        candidate_pool = ordered_ids[:1]
    single_eval_ids = candidate_pool[: settings.candidate_limit]
    semantic_results = {
        photo_id: _evaluate_single_photo(eval_repo, photo_repo.get(photo_id), group.id, technical_scores[photo_id], ai_client)
        for photo_id in single_eval_ids
    }
    compare_pool = candidate_pool[: max(settings.candidate_limit * 2, 6)]
    best_photo_id = _choose_best_photo(eval_repo, photo_repo, group.id, compare_pool or ordered_ids[:1], ai_client)

    overridden_best = next((item.photo_id for item in current_evaluations.values() if item.user_override_flag and item.best_cut_flag), None)
    chosen_best = overridden_best or best_photo_id or (ordered_ids[0] if ordered_ids else None)
    group.best_photo_id = chosen_best
    group.representative_photo_id = ordered_ids[0] if ordered_ids else group.representative_photo_id
    group.stale_flag = False
    group.stale_reason = None
    group.updated_at = datetime.now(timezone.utc)

    for photo_id in photo_ids:
        current = current_evaluations.get(photo_id)
        technical_total = technical_scores[photo_id].technical_score_total if technical_scores[photo_id] else 0.0
        semantic = semantic_results.get(photo_id)
        if semantic is None:
            rating = current.rating if current else None
            selection_status = current.selection_status if current else "normal"
            evaluation_status = current.evaluation_status if current else "provisional"
            semantic = SemanticMetrics(reason=current.ai_reason if current else None, ai_failed=evaluation_status == "ai_eval_failed")
        else:
            rating, selection_status, evaluation_status = final_rating_from_scores(
                technical_total,
                semantic,
                _weight_map(),
                _threshold_map(),
            )
        if current and current.user_override_flag:
            rating = current.rating
            selection_status = current.selection_status
            pick_flag = current.pick_flag
            best_cut_flag = current.best_cut_flag
            reviewed_flag = current.reviewed_flag
        else:
            pick_flag = bool(rating is not None and rating >= 4)
            best_cut_flag = photo_id == chosen_best
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
        _record_failure(session, job, failure_repo, "semantically_scored", "Unable to select best photo", group=group, retryable=True)


def _evaluate_single_photo(
    eval_repo: EvaluationRepository,
    photo: Photo | None,
    group_id: str | None,
    technical: TechnicalScore | None,
    ai_client: VisionLanguageModelClient,
) -> SemanticMetrics:
    if photo is None:
        return SemanticMetrics(ai_failed=True)
    prompt, prompt_hash = load_prompt("single_image_v1")
    content = prompt.replace("{{ photo_id }}", photo.id).replace("{{ technical_score_total }}", str(technical.technical_score_total if technical else 0)).replace("{{ capture_time }}", photo.capture_time.isoformat() if photo.capture_time else "")
    payload = {
        "model": get_settings().ai_model_name,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": content},
                    {"type": "image_url", "image_url": {"url": build_data_url(Path(photo.preview_path or photo.file_path), get_settings().preview_size)}},
                ],
            }
        ],
    }
    response = ai_client.evaluate("single", payload)
    _store_ai_response(
        eval_repo,
        photo.job_id,
        photo.id,
        group_id,
        "single",
        prompt_hash,
        "single_image_v1",
        response,
        [photo.id],
    )
    ranking = response.parsed_json.get("ranking", [{}])[0] if response.parsed_json else {}
    return SemanticMetrics(
        semantic_score=ranking.get("semantic_score"),
        composition_score=ranking.get("composition_score"),
        subject_state_score=ranking.get("subject_state_score"),
        rarity_score=ranking.get("rarity_score"),
        reason=ranking.get("reason"),
        ai_failed=response.parsed_json is None,
    )


def _choose_best_photo(
    eval_repo: EvaluationRepository,
    photo_repo: PhotoRepository,
    group_id: str | None,
    photo_ids: list[str],
    ai_client: VisionLanguageModelClient,
) -> str | None:
    contenders = list(photo_ids)
    if not contenders:
        return None
    while len(contenders) > 6:
        winners: list[str] = []
        for index in range(0, len(contenders), 6):
            chunk = contenders[index : index + 6]
            winner = _compare_chunk(eval_repo, photo_repo, group_id, chunk, ai_client)
            if winner:
                winners.append(winner)
        contenders = winners or contenders[:6]
    return _compare_chunk(eval_repo, photo_repo, group_id, contenders, ai_client) or contenders[0]


def _compare_chunk(
    eval_repo: EvaluationRepository,
    photo_repo: PhotoRepository,
    group_id: str | None,
    photo_ids: list[str],
    ai_client: VisionLanguageModelClient,
) -> str | None:
    prompt, prompt_hash = load_prompt("group_compare_v1")
    content = [{"type": "text", "text": prompt.replace("{{ candidate_photo_ids }}", ", ".join(photo_ids))}]
    for photo_id in photo_ids:
        photo = photo_repo.get(photo_id)
        if photo is None:
            continue
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": build_data_url(Path(photo.preview_path or photo.file_path), get_settings().compare_preview_size)},
            }
        )
    payload = {
        "model": get_settings().ai_model_name,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "user", "content": content}],
    }
    response = ai_client.evaluate("group_compare", payload)
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
        return None
    best_photo_id = response.parsed_json.get("best_photo_id")
    return str(best_photo_id) if best_photo_id else None


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


def _build_group(job_id: str, current_members: list[tuple[Photo, PhotoCandidate]], members: list[GroupMember]) -> Group:
    group_id = f"group_{uuid.uuid4().hex[:10]}"
    for order, (photo, candidate) in enumerate(current_members):
        members.append(
            GroupMember(
                id=f"gm_{uuid.uuid4().hex[:12]}",
                group_id=group_id,
                photo_id=photo.id,
                sort_order=order,
                similarity_score=1.0 - abs(candidate.similarity_seed - current_members[0][1].similarity_seed),
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


def _record_failure(session, job: Job, failure_repo: FailureRepository, stage: str, message: str, *, photo: Photo | None = None, group: Group | None = None, retryable: bool) -> None:
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
            reason_code=stage,
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
    job.status = "failed"
    job.current_stage = stage
    job.finished_at = datetime.now(timezone.utc)
    _record_failure(session, job, failure_repo, stage, message, retryable=False)
    session.commit()


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
