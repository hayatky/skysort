from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

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

    first_job_id, _ = create_import_job(db_session, str(root), True, [".jpg"], True)
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

    second_job_id, second_count = create_import_job(db_session, str(root), True, [".jpg"], True)
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
