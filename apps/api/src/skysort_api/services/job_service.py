from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException

from skysort_api.infra.ai_client import AIHealthResult, VisionLanguageModelClient
from skysort_api.services.import_service import create_import_job, create_project_job
from skysort_api.services.repositories import EvaluationRepository, FailureRepository, GroupRepository, JobRepository, PhotoRepository, ProjectRepository
from skysort_api.services.serialization import job_to_progress, job_to_summary, project_to_item
from skysort_api.workers.job_runner import job_runner


def list_projects(session, limit: int = 50) -> dict[str, object]:
    project_repo = ProjectRepository(session)
    job_repo = JobRepository(session)
    items = []
    for project in project_repo.list_recent(limit):
        latest_job = job_repo.get(project.last_job_id) if project.last_job_id else None
        items.append(project_to_item(project, latest_job))
    return {"items": items, "total": len(items)}


def get_project(session, project_id: str) -> dict[str, object]:
    project = ProjectRepository(session).get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    latest_job = JobRepository(session).get(project.last_job_id) if project.last_job_id else None
    return project_to_item(project, latest_job)


def list_project_jobs(session, project_id: str) -> dict[str, object]:
    project = ProjectRepository(session).get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    items = [job_to_summary(job) for job in JobRepository(session).list_for_project(project_id)]
    return {"project_id": project_id, "items": items, "total": len(items)}


def start_project_analysis(session, project_id: str, reuse_cache: bool = True) -> dict[str, object]:
    try:
        job_id, registered_count = create_project_job(session, project_id, reuse_cache=reuse_cache)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    start_analysis(session, job_id)
    return {"accepted": True, "project_id": project_id, "job_id": job_id, "registered_count": registered_count}


def start_analysis(session, job_id: str) -> dict[str, bool]:
    job = JobRepository(session).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status in {"running", "canceling"}:
        return {"accepted": True}

    health = VisionLanguageModelClient().health_check()
    if not _health_ready(health):
        raise HTTPException(status_code=400, detail=health.error_detail or "AI server health check failed")

    job_runner.start(job_id)
    return {"accepted": True}


def get_progress(session, job_id: str) -> dict[str, object]:
    job = JobRepository(session).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    payload = job_to_progress(job)
    group_repo = GroupRepository(session)
    eval_repo = EvaluationRepository(session)
    groups = group_repo.list_by_job(job_id)
    current = eval_repo.list_current_for_job(job_id)
    final_by_group: dict[str, list[str]] = {}
    for evaluation in current:
        if evaluation.group_id and evaluation.evaluation_status in {"final", "ai_eval_failed"}:
            final_by_group.setdefault(evaluation.group_id, []).append(evaluation.photo_id)
    group_done = 0
    for group in groups:
        members = group_repo.list_members(group.id)
        final_members = set(final_by_group.get(group.id, []))
        if members and all(member.photo_id in final_members for member in members):
            group_done += 1
    payload.update(
        {
            "ai_photo_done": job.semantically_scored_files,
            "ai_photo_total": job.total_files,
            "ai_group_done": group_done,
            "ai_group_total": len(groups),
        }
    )
    return payload


def request_cancel(session, job_id: str) -> dict[str, object]:
    job = JobRepository(session).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status in {"completed", "failed", "canceled"}:
        return {"accepted": False, "job_id": job_id, "status": job.status}
    job.cancel_requested = True
    job.status = "canceling"
    job.updated_at = datetime.now(timezone.utc)
    job_runner.cancel(job_id)
    session.commit()
    return {"accepted": True, "job_id": job_id, "status": job.status}


def retry_job(session, job_id: str) -> dict[str, object]:
    job = JobRepository(session).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status not in {"failed", "canceled"}:
        raise HTTPException(status_code=400, detail="only failed or canceled jobs can be retried")
    if job.project_id:
        return start_project_analysis(session, job.project_id, reuse_cache=True)
    project_id, retry_job_id, registered_count = create_import_job(session, job.root_path, True, [".arw", ".jpg", ".jpeg", ".png"], True)
    start_analysis(session, retry_job_id)
    return {"accepted": True, "project_id": project_id, "job_id": retry_job_id, "registered_count": registered_count}


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
