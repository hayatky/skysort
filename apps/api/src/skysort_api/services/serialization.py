from __future__ import annotations

from datetime import datetime

from skysort_api.infra.models import Group, GroupMember, Job, Photo, PhotoEvaluation, TechnicalScore


def isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def photo_to_review_item(
    photo: Photo,
    evaluation: PhotoEvaluation | None,
    technical: TechnicalScore | None,
    group_id: str | None = None,
) -> dict[str, object]:
    return {
        "photo_id": photo.id,
        "group_id": evaluation.group_id if evaluation and evaluation.group_id else group_id,
        "file_name": photo.file_name,
        "file_path": photo.file_path,
        "capture_time": isoformat(photo.capture_time),
        "camera_model": photo.camera_model,
        "lens_model": photo.lens_model,
        "thumb_url": f"/api/media/thumbs/{photo.id}",
        "preview_url": f"/api/media/previews/{photo.id}",
        "is_missing": photo.is_missing,
        "provisional_rating": evaluation.provisional_rating if evaluation else None,
        "provisional_selection_status": evaluation.provisional_selection_status if evaluation else "normal",
        "rating": evaluation.rating if evaluation else None,
        "selection_status": evaluation.selection_status if evaluation else "normal",
        "evaluation_status": evaluation.evaluation_status if evaluation else "provisional",
        "ai_reason": evaluation.ai_reason if evaluation else None,
        "pick_flag": evaluation.pick_flag if evaluation else False,
        "best_cut_flag": evaluation.best_cut_flag if evaluation else False,
        "reviewed_flag": evaluation.reviewed_flag if evaluation else False,
        "user_override_flag": evaluation.user_override_flag if evaluation else False,
        "stale_flag": evaluation.stale_flag if evaluation else False,
        "stale_reason": evaluation.stale_reason if evaluation else None,
        "technical_score_total": technical.technical_score_total if technical else None,
        "semantic_score": evaluation.semantic_score if evaluation else None,
        "composition_score": evaluation.composition_score if evaluation else None,
        "subject_state_score": evaluation.subject_state_score if evaluation else None,
        "rarity_score": evaluation.rarity_score if evaluation else None,
    }


def job_to_progress(job: Job) -> dict[str, object]:
    import json

    return {
        "job_id": job.id,
        "status": job.status,
        "total_files": job.total_files,
        "imported_files": job.imported_files,
        "grouped_files": job.grouped_files,
        "technically_scored_files": job.technically_scored_files,
        "semantically_scored_files": job.semantically_scored_files,
        "provisional_rated_files": job.provisional_rated_files,
        "final_rated_files": job.final_rated_files,
        "failed_files": job.failed_files,
        "current_stage": job.current_stage,
        "errors": json.loads(job.error_messages_json),
        "started_at": isoformat(job.started_at),
        "finished_at": isoformat(job.finished_at),
    }


def group_to_item(group: Group, photos: list[dict[str, object]]) -> dict[str, object]:
    reviewed_count = sum(1 for photo in photos if photo["reviewed_flag"])
    return {
        "id": group.id,
        "job_id": group.job_id,
        "representative_photo_id": group.representative_photo_id,
        "representative_thumb_url": f"/api/media/thumbs/{group.representative_photo_id}" if group.representative_photo_id else None,
        "best_photo_id": group.best_photo_id,
        "group_size": group.group_size,
        "group_start_time": isoformat(group.group_start_time),
        "group_end_time": isoformat(group.group_end_time),
        "stale_flag": group.stale_flag,
        "stale_reason": group.stale_reason,
        "created_at": isoformat(group.created_at),
        "reviewed_count": reviewed_count,
        "unreviewed_count": max(0, group.group_size - reviewed_count),
        "technical_score_total": max((photo["technical_score_total"] or 0) for photo in photos) if photos else None,
        "semantic_score": max((photo["semantic_score"] or 0) for photo in photos) if photos else None,
        "composition_score": max((photo["composition_score"] or 0) for photo in photos) if photos else None,
        "subject_state_score": max((photo["subject_state_score"] or 0) for photo in photos) if photos else None,
        "rarity_score": max((photo["rarity_score"] or 0) for photo in photos) if photos else None,
        "items": photos,
    }
