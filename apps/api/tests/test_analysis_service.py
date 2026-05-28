from __future__ import annotations

import time
from datetime import datetime, timezone
from threading import Lock

from skysort_api.domain.grouping import PhotoCandidate
from skysort_api.infra.models import Group, GroupMember, Job, Photo, TechnicalScore
from skysort_api.infra.settings import default_image_processing_concurrency
from skysort_api.services.analysis_service import (
    MetadataExtractionError,
    PreviewGenerationError,
    _apply_group_relative_technical_scores,
    _iter_with_concurrency,
    _map_with_concurrency,
    _reason_code_for_exception,
    _select_ai_candidate_pool,
    _sort_candidate_records,
)
from skysort_api.services.repositories import EvaluationRepository


def _photo(photo_id: str, file_path: str, order: int) -> Photo:
    return Photo(
        id=photo_id,
        job_id="job_test",
        file_path=file_path,
        file_name=file_path,
        file_hash=photo_id,
        file_size=10,
        file_mtime=1.0,
        capture_order_index=order,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def test_sort_candidate_records_prefers_capture_timestamp_then_import_order() -> None:
    late = (
        _photo("photo_late", "/tmp/b.jpg", 0),
        PhotoCandidate(photo_id="photo_late", capture_timestamp_ms=2000, capture_order_index=0, similarity_seed=0.1),
    )
    early = (
        _photo("photo_early", "/tmp/a.jpg", 2),
        PhotoCandidate(photo_id="photo_early", capture_timestamp_ms=1000, capture_order_index=2, similarity_seed=0.1),
    )
    same_time_lower_order = (
        _photo("photo_same_1", "/tmp/c.jpg", 1),
        PhotoCandidate(photo_id="photo_same_1", capture_timestamp_ms=2000, capture_order_index=1, similarity_seed=0.1),
    )

    ordered = _sort_candidate_records([late, early, same_time_lower_order])

    assert [photo.id for photo, _ in ordered] == ["photo_early", "photo_late", "photo_same_1"]


def _technical(photo_id: str, total: float) -> TechnicalScore:
    now = datetime.now(timezone.utc)
    return TechnicalScore(
        id=f"tech_{photo_id}",
        photo_id=photo_id,
        job_id="job_test",
        sharpness_score=total,
        motion_blur_score=total,
        highlight_clip_ratio=0,
        shadow_clip_ratio=0,
        technical_score_total=total,
        created_at=now,
        updated_at=now,
    )


def test_select_ai_candidate_pool_keeps_broad_pool_and_applies_candidate_limit() -> None:
    scores = {
        "low": _technical("low", 19),
        "middle": _technical("middle", 55),
        "high": _technical("high", 91),
    }

    ordered, candidate_pool, single_eval_ids = _select_ai_candidate_pool(
        ["low", "middle", "high"],
        scores,
        reject_threshold=20,
        candidate_limit=1,
    )

    assert ordered == ["high", "middle", "low"]
    assert candidate_pool == ["high", "middle", "low"]
    assert single_eval_ids == ["high"]


def test_select_ai_candidate_pool_keeps_top_candidate_when_all_below_reject_threshold() -> None:
    scores = {
        "lowest": _technical("lowest", 5),
        "less_low": _technical("less_low", 12),
    }

    ordered, candidate_pool, single_eval_ids = _select_ai_candidate_pool(
        ["lowest", "less_low"],
        scores,
        reject_threshold=20,
        candidate_limit=6,
    )

    assert ordered == ["less_low", "lowest"]
    assert candidate_pool == ["less_low"]
    assert single_eval_ids == ["less_low"]


def test_map_with_concurrency_preserves_order_and_uses_multiple_workers() -> None:
    lock = Lock()
    active = 0
    max_active = 0

    def worker(value: int) -> int:
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        return value * 10

    results = _map_with_concurrency([1, 2, 3, 4], max_workers=2, worker=worker)

    assert results == [(1, 10), (2, 20), (3, 30), (4, 40)]
    assert max_active == 2


def test_map_with_concurrency_clamps_invalid_worker_count_to_sequential() -> None:
    results = _map_with_concurrency([1, 2], max_workers=0, worker=lambda value: value + 1)

    assert results == [(1, 2), (2, 3)]


def test_iter_with_concurrency_streams_work_with_bounded_parallelism() -> None:
    lock = Lock()
    active = 0
    max_active = 0

    def worker(value: int) -> int:
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        return value * 10

    results = list(_iter_with_concurrency([1, 2, 3, 4, 5, 6], max_workers=3, worker=worker))

    assert sorted(results) == [(1, 10), (2, 20), (3, 30), (4, 40), (5, 50), (6, 60)]
    assert max_active == 3


def test_failure_reason_codes_distinguish_retry_categories() -> None:
    assert _reason_code_for_exception("preview_exif", PreviewGenerationError("preview failed")) == "preview_generation_failed"
    assert _reason_code_for_exception("preview_exif", MetadataExtractionError("exif failed")) == "metadata_extraction_failed"
    assert _reason_code_for_exception("semantically_scored", TimeoutError("timed out")) == "ai_timeout"


def test_default_image_processing_concurrency_scales_with_available_cpu(monkeypatch) -> None:
    monkeypatch.setattr("os.cpu_count", lambda: 32)

    assert default_image_processing_concurrency() == 16


def test_group_relative_technical_scores_rank_candidates(db_session) -> None:
    now = datetime.now(timezone.utc)
    job = Job(
        id="job_relative",
        root_path="/tmp/relative",
        status="running",
        total_files=2,
        current_stage="technically_scored",
        error_messages_json="[]",
        settings_snapshot_json="{}",
        app_version="test",
        model_name="test",
        prompt_template_hash="hash",
        response_schema_version="v1",
    )
    photos = [_photo("soft", "/tmp/soft.jpg", 0), _photo("sharp", "/tmp/sharp.jpg", 1)]
    for photo in photos:
        photo.job_id = job.id
    group = Group(
        id="group_relative",
        job_id=job.id,
        representative_photo_id="soft",
        best_photo_id=None,
        group_size=2,
        group_start_time=now,
        group_end_time=now,
        created_at=now,
        updated_at=now,
    )
    members = [
        GroupMember(id="gm_soft", group_id=group.id, photo_id="soft", sort_order=0, similarity_score=1.0),
        GroupMember(id="gm_sharp", group_id=group.id, photo_id="sharp", sort_order=1, similarity_score=1.0),
    ]
    scores = [
        TechnicalScore(
            id="tech_soft",
            photo_id="soft",
            job_id=job.id,
            sharpness_score=20,
            motion_blur_score=25,
            highlight_clip_ratio=0.01,
            shadow_clip_ratio=0.01,
            technical_score_total=35,
            created_at=now,
            updated_at=now,
        ),
        TechnicalScore(
            id="tech_sharp",
            photo_id="sharp",
            job_id=job.id,
            sharpness_score=90,
            motion_blur_score=85,
            highlight_clip_ratio=0.0,
            shadow_clip_ratio=0.0,
            technical_score_total=85,
            created_at=now,
            updated_at=now,
        ),
    ]
    db_session.add_all([job, *photos, group, *members, *scores])
    db_session.flush()

    _apply_group_relative_technical_scores(EvaluationRepository(db_session), job, [group], {group.id: members})
    soft = EvaluationRepository(db_session).technical_for_photo("soft", job.id)
    sharp = EvaluationRepository(db_session).technical_for_photo("sharp", job.id)

    assert soft and sharp
    assert sharp.sharpness_rank == 100
    assert soft.sharpness_rank == 0
    assert sharp.candidate_quality_score and soft.candidate_quality_score
    assert sharp.candidate_quality_score > soft.candidate_quality_score
    assert sharp.reject_risk_score is not None and soft.reject_risk_score is not None
    assert sharp.reject_risk_score < soft.reject_risk_score
