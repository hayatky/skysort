from __future__ import annotations

from datetime import datetime, timezone

from skysort_api.infra.models import Job, JobFailure, Photo, PhotoEvaluation
from skysort_api.services.job_service import get_failures, retry_failure


def test_get_failures_includes_target_context_and_retryability(db_session) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(
        Job(
            id="job_failures",
            root_path="/tmp/failures",
            status="running",
            total_files=1,
            imported_files=0,
            grouped_files=0,
            technically_scored_files=0,
            semantically_scored_files=0,
            provisional_rated_files=0,
            final_rated_files=0,
            failed_files=1,
            current_stage="preview_exif",
            error_messages_json="[]",
            settings_snapshot_json="{}",
            app_version="0.1.0",
            model_name="qwen",
            prompt_template_hash="hash",
            response_schema_version="v1",
        )
    )
    db_session.add(
        Photo(
            id="photo_failed",
            job_id="job_failures",
            file_path="/tmp/failures/alpha.jpg",
            file_name="alpha.jpg",
            file_hash="hash",
            file_size=10,
            file_mtime=1.0,
            capture_order_index=0,
            created_at=now,
            updated_at=now,
        )
    )
    db_session.add(
        JobFailure(
            id="fail_preview",
            job_id="job_failures",
            photo_id="photo_failed",
            group_id=None,
            stage="preview_exif",
            reason_code="preview_exif",
            message="broken metadata",
            retryable=True,
            created_at=now,
        )
    )
    db_session.flush()

    response = get_failures(db_session, "job_failures")

    assert response["items"] == [
        {
            "stage": "preview_exif",
            "reason": "broken metadata",
            "reason_code": "preview_exif",
            "retryable": True,
            "retry_scope": "full",
            "photo_id": "photo_failed",
            "group_id": None,
            "file_name": "alpha.jpg",
            "id": "fail_preview",
        }
    ]


def test_retry_failure_marks_target_stale_and_starts_scoped_reanalysis(db_session, monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(
        Job(
            id="job_retry",
            root_path="/tmp/retry",
            status="running",
            total_files=1,
            imported_files=1,
            grouped_files=1,
            technically_scored_files=0,
            semantically_scored_files=0,
            provisional_rated_files=0,
            final_rated_files=0,
            failed_files=1,
            current_stage="technical_scoring",
            error_messages_json="[]",
            settings_snapshot_json="{}",
            app_version="0.1.0",
            model_name="qwen",
            prompt_template_hash="hash",
            response_schema_version="v1",
        )
    )
    db_session.add(
        Photo(
            id="photo_retry",
            job_id="job_retry",
            file_path="/tmp/retry/alpha.jpg",
            file_name="alpha.jpg",
            file_hash="hash",
            file_size=10,
            file_mtime=1.0,
            capture_order_index=0,
            created_at=now,
            updated_at=now,
        )
    )
    db_session.add(
        PhotoEvaluation(
            id="eval_retry",
            photo_id="photo_retry",
            job_id="job_retry",
            group_id=None,
            rating=None,
            selection_status="normal",
            evaluation_status="provisional",
            pick_flag=False,
            best_cut_flag=False,
            reviewed_flag=False,
            user_override_flag=False,
            stale_flag=False,
            version=1,
            is_current=True,
            created_at=now,
            updated_at=now,
        )
    )
    db_session.add(
        JobFailure(
            id="fail_retry",
            job_id="job_retry",
            photo_id="photo_retry",
            group_id=None,
            stage="technical_scoring",
            reason_code="technical_scoring",
            message="metric failed",
            retryable=True,
            created_at=now,
        )
    )
    db_session.flush()
    calls: list[tuple[str, list[str], str]] = []
    monkeypatch.setattr(
        "skysort_api.services.job_service.job_runner.start_photo_reanalysis",
        lambda job_id, photo_ids, scope: calls.append((job_id, photo_ids, scope)),
    )

    response = retry_failure(db_session, "job_retry", "fail_retry")

    evaluation = db_session.get(PhotoEvaluation, "eval_retry")
    assert response["accepted"] is True
    assert response["scope"] == "technical_only"
    assert calls == [("job_retry", ["photo_retry"], "technical_only")]
    assert evaluation is not None
    assert evaluation.stale_flag is True
    assert evaluation.stale_reason == "retry:technical_scoring"


def test_get_failures_maps_ai_reason_codes_to_ai_retry_scope(db_session) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(
        Job(
            id="job_ai_failure",
            root_path="/tmp/ai-failure",
            status="running",
            total_files=0,
            imported_files=0,
            grouped_files=0,
            technically_scored_files=0,
            semantically_scored_files=0,
            provisional_rated_files=0,
            final_rated_files=0,
            failed_files=1,
            current_stage="semantically_scored",
            error_messages_json="[]",
            settings_snapshot_json="{}",
            app_version="0.1.0",
            model_name="qwen",
            prompt_template_hash="hash",
            response_schema_version="v1",
        )
    )
    db_session.add(
        JobFailure(
            id="fail_ai",
            job_id="job_ai_failure",
            photo_id=None,
            group_id=None,
            stage="semantically_scored",
            reason_code="json_parse_failed",
            message="bad json",
            retryable=True,
            created_at=now,
        )
    )
    db_session.flush()

    response = get_failures(db_session, "job_ai_failure")

    assert response["items"][0]["reason_code"] == "json_parse_failed"
    assert response["items"][0]["retry_scope"] == "ai_only"
