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


def test_import_creates_reusable_project_and_distinct_jobs(isolated_runtime, tmp_path: Path) -> None:
    root = tmp_path / "photos"
    root.mkdir()
    _write_jpeg(root / "alpha.jpg")
    client = TestClient(create_app())

    first = client.post("/api/import", json={"root_path": str(root), "recursive": True, "file_types": [".jpg"], "reuse_cache": True})
    second = client.post("/api/import", json={"root_path": str(root), "recursive": True, "file_types": [".jpg"], "reuse_cache": True})
    projects = client.get("/api/projects")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["project_id"] == second.json()["project_id"]
    assert first.json()["job_id"] != second.json()["job_id"]
    assert projects.status_code == 200
    assert projects.json()["total"] == 1
    assert projects.json()["items"][0]["latest_job"]["job_id"] == second.json()["job_id"]


def test_project_jobs_list_persists_job_history(isolated_runtime, tmp_path: Path) -> None:
    root = tmp_path / "photos"
    root.mkdir()
    _write_jpeg(root / "alpha.jpg")
    client = TestClient(create_app())

    first = client.post("/api/import", json={"root_path": str(root), "recursive": True, "file_types": [".jpg"], "reuse_cache": True}).json()
    second = client.post("/api/import", json={"root_path": str(root), "recursive": True, "file_types": [".jpg"], "reuse_cache": True}).json()
    response = client.get(f"/api/projects/{first['project_id']}/jobs")

    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert [item["job_id"] for item in response.json()["items"]] == [second["job_id"], first["job_id"]]


def test_cancel_request_and_retry_create_new_job(isolated_runtime, tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "photos"
    root.mkdir()
    _write_jpeg(root / "alpha.jpg")
    client = TestClient(create_app())
    imported = client.post("/api/import", json={"root_path": str(root), "recursive": True, "file_types": [".jpg"], "reuse_cache": True}).json()

    from skysort_api.infra.database import session_scope
    from skysort_api.services.repositories import JobRepository

    with session_scope() as session:
        job = JobRepository(session).get(imported["job_id"])
        assert job is not None
        job.status = "running"
        session.commit()

    cancel_response = client.post(f"/api/jobs/{imported['job_id']}/cancel")
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "canceling"

    with session_scope() as session:
        job = JobRepository(session).get(imported["job_id"])
        assert job is not None
        job.status = "canceled"
        session.commit()

    monkeypatch.setattr("skysort_api.services.job_service.start_analysis", lambda session, job_id: {"accepted": True})
    retry_response = client.post(f"/api/jobs/{imported['job_id']}/retry")

    assert retry_response.status_code == 200
    assert retry_response.json()["accepted"] is True
    assert retry_response.json()["project_id"] == imported["project_id"]
    assert retry_response.json()["job_id"] != imported["job_id"]


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
