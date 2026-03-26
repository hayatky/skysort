from __future__ import annotations

from fastapi import HTTPException

from skysort_api.infra.ai_client import AIHealthResult, VisionLanguageModelClient
from skysort_api.services.repositories import FailureRepository, JobRepository
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
    return {
        "job_id": job_id,
        "items": [
            {
                "stage": item.stage,
                "reason": item.message,
                "retryable": item.retryable,
                "photo_id": item.photo_id,
                "group_id": item.group_id,
            }
            for item in items
        ],
    }


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
