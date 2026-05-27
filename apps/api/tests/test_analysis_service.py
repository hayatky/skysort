from __future__ import annotations

import time
from datetime import datetime, timezone
from threading import Lock

from skysort_api.domain.grouping import PhotoCandidate
from skysort_api.infra.models import Photo, TechnicalScore
from skysort_api.infra.settings import default_image_processing_concurrency
from skysort_api.services.analysis_service import (
    MetadataExtractionError,
    PreviewGenerationError,
    _iter_with_concurrency,
    _map_with_concurrency,
    _reason_code_for_exception,
    _select_ai_candidate_pool,
    _sort_candidate_records,
)


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


def test_select_ai_candidate_pool_applies_reject_threshold_and_candidate_limit() -> None:
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
    assert candidate_pool == ["high", "middle"]
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
