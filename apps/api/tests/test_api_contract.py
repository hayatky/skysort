from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from skysort_api.infra.ai_client import AIHealthResult
from skysort_api.main import create_app


def _write_jpeg(path: Path) -> None:
    Image.new("RGB", (24, 24), (255, 0, 0)).save(path, format="JPEG")


def test_patch_photo_rejects_rating_with_rejected_status(isolated_runtime) -> None:
    client = TestClient(create_app())

    response = client.patch(
        "/api/photos/photo_123",
        json={"job_id": "job_123", "selection_status": "rejected", "rating": 5},
    )

    assert response.status_code == 422


def test_import_job_can_be_analyzed_immediately(isolated_runtime, tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "photos"
    root.mkdir()
    _write_jpeg(root / "alpha.jpg")
    started: list[str] = []

    class FakeVisionLanguageModelClient:
        def health_check(self) -> AIHealthResult:
            return AIHealthResult(
                provider="lm_studio",
                reachable=True,
                localhost_only=True,
                remote_allowed=False,
                auth_configured=True,
                available_models=["local-vision"],
                configured_model="local-vision",
                configured_model_exists=True,
                model_loadable=True,
                vision_capable=True,
                structured_json_capable=True,
                checked_at="2026-05-27T00:00:00Z",
                error_detail=None,
            )

    monkeypatch.setattr("skysort_api.services.job_service.VisionLanguageModelClient", FakeVisionLanguageModelClient)
    monkeypatch.setattr("skysort_api.services.job_service.job_runner.start", lambda job_id: started.append(job_id))
    client = TestClient(create_app())

    import_response = client.post(
        "/api/import",
        json={"root_path": str(root), "recursive": True, "file_types": [".jpg"], "reuse_cache": True},
    )
    job_id = import_response.json()["job_id"]
    analyze_response = client.post(f"/api/jobs/{job_id}/analyze", json={"reuse_cache": True})

    assert import_response.status_code == 200
    assert analyze_response.status_code == 200
    assert analyze_response.json() == {"accepted": True}
    assert started == [job_id]


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
