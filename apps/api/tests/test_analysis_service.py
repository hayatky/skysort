from __future__ import annotations

from datetime import datetime, timezone

from skysort_api.domain.grouping import PhotoCandidate
from skysort_api.infra.models import Photo
from skysort_api.services.analysis_service import _sort_candidate_records


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
