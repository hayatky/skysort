from __future__ import annotations

from fastapi.testclient import TestClient

from skysort_api.main import create_app


def test_patch_photo_rejects_rating_with_rejected_status(isolated_runtime) -> None:
    client = TestClient(create_app())

    response = client.patch(
        "/api/photos/photo_123",
        json={"job_id": "job_123", "selection_status": "rejected", "rating": 5},
    )

    assert response.status_code == 422


def test_patch_photo_rejects_out_of_range_rating(isolated_runtime) -> None:
    client = TestClient(create_app())

    response = client.patch(
        "/api/photos/photo_123",
        json={"job_id": "job_123", "rating": 6},
    )

    assert response.status_code == 422


def test_export_xmp_rejects_unknown_conflict_policy(isolated_runtime) -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/export/xmp",
        json={"job_id": "job_123", "conflict_policy": "overwrite_all"},
    )

    assert response.status_code == 422


def test_export_results_rejects_unknown_format(isolated_runtime) -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/export/results",
        json={"job_id": "job_123", "format": "xlsx"},
    )

    assert response.status_code == 422
