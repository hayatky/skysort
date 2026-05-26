from __future__ import annotations

from fastapi import HTTPException

from skysort_api.infra.ai_client import AIHealthResult, VisionLanguageModelClient
from skysort_api.services.repositories import EvaluationRepository, FailureRepository, GroupRepository, JobRepository, PhotoRepository
from skysort_api.services.serialization import job_to_progress
from skysort_api.workers.job_runner import job_runner


def start_analysis(session, job_id: str) -> dict[str, bool]:
    job = JobRepository(session).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")

    health = VisionLanguageModelClient().health_check()
    if not _health_ready(health):
        raise HTTPException(status_code=400, detail=health.error_detail or "AI server health check failed")

    job_runner.start(job_id)
    return {"accepted": True}


def get_progress(session, job_id: str) -> dict[str, object]:
    job = JobRepository(session).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job_to_progress(job)


def get_failures(session, job_id: str) -> dict[str, object]:
    job = JobRepository(session).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    items = FailureRepository(session).list_for_job(job_id)
    photo_repo = PhotoRepository(session)
    rendered = []
    for item in items:
        photo = photo_repo.get(item.photo_id) if item.photo_id else None
        rendered.append(
            {
                "id": item.id,
                "stage": item.stage,
                "reason": item.message,
                "reason_code": item.reason_code,
                "retryable": item.retryable,
                "retry_scope": _scope_for_failure_stage(item.stage, item.reason_code),
                "photo_id": item.photo_id,
                "group_id": item.group_id,
                "file_name": photo.file_name if photo else None,
            }
        )
    return {"job_id": job_id, "items": rendered}


def retry_failure(session, job_id: str, failure_id: str) -> dict[str, object]:
    job = JobRepository(session).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    failure = FailureRepository(session).get(failure_id)
    if failure is None or failure.job_id != job_id:
        raise HTTPException(status_code=404, detail="failure not found")
    if not failure.retryable:
        raise HTTPException(status_code=400, detail="failure is not retryable")

    scope = _scope_for_failure_stage(failure.stage, failure.reason_code)
    photo_ids: list[str] = []
    if failure.photo_id:
        photo_ids = [failure.photo_id]
    elif failure.group_id:
        group_repo = GroupRepository(session)
        group = group_repo.get(failure.group_id)
        if group is None:
            raise HTTPException(status_code=404, detail="failure group not found")
        group.stale_flag = True
        group.stale_reason = f"retry:{failure.stage}"
        photo_ids = [member.photo_id for member in group_repo.list_members(failure.group_id)]
    else:
        raise HTTPException(status_code=400, detail="failure has no photo or group target")

    eval_repo = EvaluationRepository(session)
    for photo_id in photo_ids:
        current = eval_repo.current_for_photo(photo_id, job_id)
        if current is not None:
            current.stale_flag = True
            current.stale_reason = f"retry:{failure.stage}"
    session.commit()
    job_runner.start_photo_reanalysis(job_id, photo_ids, scope)
    return {"accepted": True, "failure_id": failure.id, "scope": scope, "photo_ids": photo_ids}


def get_ai_health() -> AIHealthResult:
    return VisionLanguageModelClient().health_check()


def _health_ready(health: AIHealthResult) -> bool:
    return bool(
        health.reachable
        and health.configured_model_exists
        and health.model_loadable
        and health.vision_capable
        and health.structured_json_capable
    )


def _scope_for_failure_stage(stage: str, reason_code: str | None = None) -> str:
    if reason_code in {"ai_timeout", "json_parse_failed"} or stage in {"semantically_scored", "ai_eval_failed", "single", "group_compare"}:
        return "ai_only"
    if reason_code in {"preview_generation_failed", "metadata_extraction_failed"}:
        return "full"
    if stage == "technical_scoring":
        return "technical_only"
    return "full"
