from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from skysort_api.api.schemas import XmpExportRequest
from skysort_api.infra.models import PhotoEvaluation
from skysort_api.services.export_service import export_xmp
from skysort_api.services.import_service import create_import_job
from skysort_api.services.repositories import EvaluationRepository, PhotoRepository


def _write_jpeg(path: Path, color: tuple[int, int, int]) -> None:
    Image.new("RGB", (24, 24), color).save(path, format="JPEG")


def test_export_xmp_updates_jpeg_signature_for_next_import(db_session, monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "photos"
    root.mkdir()
    alpha = root / "alpha.jpg"
    _write_jpeg(alpha, (255, 0, 0))

    _, job_id, _ = create_import_job(db_session, str(root), True, [".jpg"], True)
    db_session.flush()
    photo_repo = PhotoRepository(db_session)
    first_photo = photo_repo.list_by_job(job_id)[0]
    first_photo.camera_model = "Alpha Cam"
    Path(first_photo.thumb_path).parent.mkdir(parents=True, exist_ok=True)
    Path(first_photo.preview_path).parent.mkdir(parents=True, exist_ok=True)
    Path(first_photo.thumb_path).write_bytes(b"thumb")
    Path(first_photo.preview_path).write_bytes(b"preview")
    original_hash = first_photo.file_hash

    EvaluationRepository(db_session).add_evaluation(
        PhotoEvaluation(
            id="eval_alpha",
            photo_id=first_photo.id,
            job_id=job_id,
            group_id=None,
            semantic_score=80,
            composition_score=80,
            subject_state_score=80,
            rarity_score=50,
            provisional_rating=4,
            provisional_selection_status="normal",
            rating=4,
            selection_status="normal",
            evaluation_status="final",
            pick_flag=False,
            best_cut_flag=False,
            reviewed_flag=False,
            ai_reason="seeded",
            user_override_flag=False,
            stale_flag=False,
            stale_reason=None,
            version=1,
            is_current=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    db_session.flush()

    monkeypatch.setattr("skysort_api.services.export_service.exiftool_available", lambda: True)
    monkeypatch.setattr("skysort_api.services.export_service.can_write", lambda _path: (True, None))
    monkeypatch.setattr("skysort_api.services.export_service.detect_conflict", lambda _path, _tags: None)

    def fake_write_tags(file_path: str, *_args) -> tuple[bool, str]:
        with Path(file_path).open("ab") as handle:
            handle.write(b"skysort-xmp")
        return True, "written"

    monkeypatch.setattr("skysort_api.services.export_service.write_tags", fake_write_tags)

    export_xmp(db_session, XmpExportRequest(job_id=job_id, dry_run=False))
    db_session.flush()

    updated = photo_repo.get(first_photo.id)
    assert updated.file_hash != original_hash
    assert Path(updated.preview_path).exists()
    assert Path(updated.thumb_path).exists()

    _, second_job_id, _ = create_import_job(db_session, str(root), True, [".jpg"], True)
    db_session.flush()
    second_photo = photo_repo.list_by_job(second_job_id)[0]

    assert second_photo.camera_model == "Alpha Cam"
    assert second_photo.preview_path == updated.preview_path
