from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from PIL import Image

from skysort_api.infra.database import session_scope
from skysort_api.infra.models import Job
from skysort_api.infra.file_scan import normalize_root_path
from skysort_api.services.import_service import create_import_job
from skysort_api.services.repositories import PhotoRepository


def _write_jpeg(path: Path, color: tuple[int, int, int]) -> None:
    Image.new("RGB", (24, 24), color).save(path, format="JPEG")


def test_create_import_job_reuses_unchanged_metadata_and_marks_missing(db_session, tmp_path: Path) -> None:
    root = tmp_path / "photos"
    root.mkdir()
    alpha = root / "alpha.jpg"
    bravo = root / "bravo.jpg"
    charlie = root / "charlie.jpg"
    _write_jpeg(alpha, (255, 0, 0))
    _write_jpeg(bravo, (0, 255, 0))
    _write_jpeg(charlie, (0, 0, 255))

    _, first_job_id, _ = create_import_job(db_session, str(root), True, [".jpg"], True)
    db_session.flush()
    photo_repo = PhotoRepository(db_session)
    first_photos = {photo.file_name: photo for photo in photo_repo.list_by_job(first_job_id, include_missing=True)}
    first_alpha = first_photos["alpha.jpg"]
    first_alpha.capture_time = datetime(2026, 3, 26, 10, 0, tzinfo=timezone.utc)
    first_alpha.capture_timestamp_ms = int(first_alpha.capture_time.timestamp() * 1000)
    first_alpha.camera_model = "Alpha Cam"
    first_alpha.width = 6000
    first_alpha.height = 4000
    db_session.commit()

    _write_jpeg(bravo, (123, 45, 67))
    updated_timestamp = bravo.stat().st_mtime + 5
    os.utime(bravo, (updated_timestamp, updated_timestamp))
    charlie.unlink()
    delta = root / "delta.jpg"
    _write_jpeg(delta, (64, 64, 64))

    _, second_job_id, second_count = create_import_job(db_session, str(root), True, [".jpg"], True)
    db_session.flush()
    assert second_count == 4

    second_photos = photo_repo.list_by_job(second_job_id, include_missing=True)
    second_by_name = {photo.file_name: photo for photo in second_photos}

    assert second_by_name["alpha.jpg"].camera_model == "Alpha Cam"
    assert second_by_name["alpha.jpg"].capture_timestamp_ms == first_alpha.capture_timestamp_ms
    assert second_by_name["alpha.jpg"].width == 6000
    assert second_by_name["alpha.jpg"].preview_path == first_alpha.preview_path

    assert second_by_name["bravo.jpg"].camera_model is None
    assert second_by_name["bravo.jpg"].width is None

    assert second_by_name["charlie.jpg"].is_missing is True
    assert second_by_name["delta.jpg"].is_missing is False


def test_create_import_job_commits_job_before_return(isolated_runtime, tmp_path: Path) -> None:
    root = tmp_path / "photos"
    root.mkdir()
    _write_jpeg(root / "alpha.jpg", (255, 0, 0))

    with session_scope() as import_session:
        _, job_id, count = create_import_job(import_session, str(root), True, [".jpg"], True)
        with session_scope() as read_session:
            persisted = read_session.get(Job, job_id)

    assert count == 1
    assert persisted is not None
    assert persisted.id == job_id


def test_normalize_root_path_handles_spaces_japanese_relative_and_symlink(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "写真 folder"
    root.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(root, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable in this Windows test environment: {exc}")
    monkeypatch.chdir(tmp_path)

    assert normalize_root_path("写真 folder") == root.resolve()
    assert normalize_root_path(str(link)) == root.resolve()


def test_normalize_root_path_rejects_missing_and_non_directory(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.jpg"
    file_path.write_bytes(b"image")

    with pytest.raises(FileNotFoundError):
        normalize_root_path(str(tmp_path / "missing"))

    with pytest.raises(NotADirectoryError):
        normalize_root_path(str(file_path))
