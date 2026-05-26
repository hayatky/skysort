from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from skysort_api.api.schemas import ExportResultsRequest, XmpExportRequest
from skysort_api.infra.models import Group, GroupMember, Job, Photo, PhotoEvaluation
from skysort_api.services.export_service import export_results, export_xmp
from skysort_api.services.query_service import list_groups, list_photos
from skysort_api.services.repositories import EvaluationRepository


def _seed_job() -> Job:
    return Job(
        id="job_filters",
        root_path="/tmp/filters",
        status="completed",
        total_files=3,
        imported_files=3,
        grouped_files=3,
        technically_scored_files=3,
        semantically_scored_files=3,
        provisional_rated_files=0,
        final_rated_files=3,
        failed_files=0,
        current_stage="finalized",
        error_messages_json="[]",
        settings_snapshot_json="{}",
        app_version="0.1.0",
        model_name="qwen",
        prompt_template_hash="hash",
        response_schema_version="v1",
    )


def _seed_photo(photo_id: str, order: int, path: Path) -> Photo:
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc) + timedelta(days=order)
    path.write_bytes(b"image")
    return Photo(
        id=photo_id,
        job_id="job_filters",
        file_path=str(path),
        file_name=path.name,
        file_hash=photo_id,
        file_size=10,
        file_mtime=float(order),
        capture_order_index=order,
        capture_time=now,
        capture_timestamp_ms=int(now.timestamp() * 1000),
        camera_model="Alpha",
        lens_model="Tele",
        created_at=now,
        updated_at=now,
    )


def _seed_evaluation(
    photo_id: str,
    group_id: str,
    *,
    rating: int | None,
    selection_status: str = "normal",
    pick_flag: bool = False,
    best_cut_flag: bool = False,
    reviewed_flag: bool = False,
    evaluation_status: str = "final",
) -> PhotoEvaluation:
    now = datetime.now(timezone.utc)
    return PhotoEvaluation(
        id=f"eval_{photo_id}",
        photo_id=photo_id,
        job_id="job_filters",
        group_id=group_id,
        semantic_score=80,
        composition_score=80,
        subject_state_score=80,
        rarity_score=50,
        provisional_rating=rating,
        provisional_selection_status=selection_status,
        rating=rating,
        selection_status=selection_status,
        evaluation_status=evaluation_status,
        pick_flag=pick_flag,
        best_cut_flag=best_cut_flag,
        reviewed_flag=reviewed_flag,
        ai_reason="seeded",
        user_override_flag=False,
        stale_flag=False,
        stale_reason=None,
        version=1,
        is_current=True,
        created_at=now,
        updated_at=now,
    )


def _seed_filter_dataset(db_session, tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(_seed_job())
    db_session.add_all(
        [
            _seed_photo("photo_keep", 0, tmp_path / "keep.jpg"),
            _seed_photo("photo_reject", 1, tmp_path / "reject.jpg"),
            _seed_photo("photo_pick", 2, tmp_path / "pick.jpg"),
        ]
    )
    db_session.add_all(
        [
            Group(
                id="group_a",
                job_id="job_filters",
                representative_photo_id="photo_keep",
                best_photo_id="photo_keep",
                group_size=2,
                group_start_time=now,
                group_end_time=now,
                stale_flag=False,
                stale_reason=None,
                created_at=now,
                updated_at=now,
            ),
            Group(
                id="group_b",
                job_id="job_filters",
                representative_photo_id="photo_pick",
                best_photo_id="photo_pick",
                group_size=1,
                group_start_time=now,
                group_end_time=now,
                stale_flag=True,
                stale_reason="settings_changed",
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    db_session.add_all(
        [
            GroupMember(id="gm_keep", group_id="group_a", photo_id="photo_keep", sort_order=0, similarity_score=1.0, created_at=now, updated_at=now),
            GroupMember(id="gm_reject", group_id="group_a", photo_id="photo_reject", sort_order=1, similarity_score=0.9, created_at=now, updated_at=now),
            GroupMember(id="gm_pick", group_id="group_b", photo_id="photo_pick", sort_order=0, similarity_score=1.0, created_at=now, updated_at=now),
        ]
    )
    repo = EvaluationRepository(db_session)
    repo.add_evaluation(_seed_evaluation("photo_keep", "group_a", rating=5, best_cut_flag=True, reviewed_flag=True))
    repo.add_evaluation(_seed_evaluation("photo_reject", "group_a", rating=None, selection_status="rejected"))
    repo.add_evaluation(_seed_evaluation("photo_pick", "group_b", rating=4, pick_flag=True, reviewed_flag=True, evaluation_status="ai_eval_failed"))
    db_session.flush()


def test_list_groups_filters_sorts_and_paginates(db_session, tmp_path: Path) -> None:
    _seed_filter_dataset(db_session, tmp_path)

    response = list_groups(
        db_session,
        "job_filters",
        filter_query=json.dumps({"reviewed": True}),
        sort="-group_size",
        page=1,
        page_size=1,
    )

    assert response["total"] == 2
    assert response["page"] == 1
    assert response["page_size"] == 1
    assert response["total_pages"] == 2
    assert [item["id"] for item in response["items"]] == ["group_a"]


def test_export_results_applies_filters(db_session, tmp_path: Path) -> None:
    _seed_filter_dataset(db_session, tmp_path)

    response = export_results(db_session, ExportResultsRequest(job_id="job_filters", format="json", filters={"reject": True}))
    payload = json.loads(Path(response["export_path"]).read_text(encoding="utf-8"))

    assert response["item_count"] == 1
    assert [item["photo_id"] for item in payload] == ["photo_reject"]


def test_list_photos_keeps_ai_eval_failed_items_reviewable(db_session, tmp_path: Path) -> None:
    _seed_filter_dataset(db_session, tmp_path)

    response = list_photos(db_session, "job_filters", filters={"evaluation_status": "ai_eval_failed"})

    assert response["total"] == 1
    assert response["items"][0]["photo_id"] == "photo_pick"
    assert response["items"][0]["rating"] == 4


def test_list_photos_filters_delete_candidates_and_paginates(db_session, tmp_path: Path) -> None:
    _seed_filter_dataset(db_session, tmp_path)

    response = list_photos(db_session, "job_filters", filters={"delete_candidate": True}, page=1, page_size=1)

    assert response["total"] == 1
    assert response["page"] == 1
    assert response["page_size"] == 1
    assert response["total_pages"] == 1
    assert response["items"][0]["photo_id"] == "photo_reject"


def test_search_filter_matches_photo_filename_and_metadata(db_session, tmp_path: Path) -> None:
    _seed_filter_dataset(db_session, tmp_path)

    by_name = list_photos(db_session, "job_filters", filters={"q": "pick"})
    by_metadata = list_photos(db_session, "job_filters", filters={"q": "alpha"})
    by_date = list_photos(db_session, "job_filters", filters={"date_from": "2026-01-02T00:00:00+00:00", "date_to": "2026-01-02T23:59:59+00:00"})
    by_group = list_groups(db_session, "job_filters", filter_query=json.dumps({"q": "reject"}))

    assert [item["photo_id"] for item in by_name["items"]] == ["photo_pick"]
    assert by_metadata["total"] == 3
    assert [item["photo_id"] for item in by_date["items"]] == ["photo_reject"]
    assert [item["id"] for item in by_group["items"]] == ["group_a"]


def test_export_xmp_filters_targets_and_fail_policy_stops_writes(db_session, monkeypatch, tmp_path: Path) -> None:
    _seed_filter_dataset(db_session, tmp_path)
    writes: list[str] = []

    monkeypatch.setattr("skysort_api.services.export_service.exiftool_available", lambda: True)
    monkeypatch.setattr("skysort_api.services.export_service.can_write", lambda _path: (True, None))
    monkeypatch.setattr(
        "skysort_api.services.export_service.detect_conflict",
        lambda _path, _tags: {"diff": {"XMP:Rating": {"existing": 3, "desired": 4}}},
    )
    monkeypatch.setattr("skysort_api.services.export_service.write_tags", lambda file_path, *_args: writes.append(file_path) or (True, "written"))

    response = export_xmp(
        db_session,
        XmpExportRequest(job_id="job_filters", filters={"pick": True}, dry_run=False, conflict_policy="fail"),
    )

    assert response["target_count"] == 1
    assert response["written_count"] == 0
    assert response["failed_count"] == 1
    assert response["failed_items"][0]["photo_id"] == "photo_pick"
    assert writes == []


def test_export_xmp_skip_policy_skips_conflicts(db_session, monkeypatch, tmp_path: Path) -> None:
    _seed_filter_dataset(db_session, tmp_path)
    writes: list[str] = []

    monkeypatch.setattr("skysort_api.services.export_service.exiftool_available", lambda: True)
    monkeypatch.setattr("skysort_api.services.export_service.can_write", lambda _path: (True, None))
    monkeypatch.setattr(
        "skysort_api.services.export_service.detect_conflict",
        lambda _path, _tags: {"diff": {"XMP:Rating": {"existing": 3, "desired": 5}}},
    )
    monkeypatch.setattr("skysort_api.services.export_service.write_tags", lambda file_path, *_args: writes.append(file_path) or (True, "written"))

    response = export_xmp(
        db_session,
        XmpExportRequest(job_id="job_filters", filters={"best": True}, dry_run=False, conflict_policy="skip"),
    )

    assert response["target_count"] == 1
    assert response["written_count"] == 0
    assert response["skipped_count"] == 1
    assert response["skipped_items"][0]["photo_id"] == "photo_keep"
    assert writes == []


def test_export_xmp_overwrite_safe_fields_writes_despite_conflicts(db_session, monkeypatch, tmp_path: Path) -> None:
    _seed_filter_dataset(db_session, tmp_path)
    writes: list[str] = []

    monkeypatch.setattr("skysort_api.services.export_service.exiftool_available", lambda: True)
    monkeypatch.setattr("skysort_api.services.export_service.can_write", lambda _path: (True, None))
    monkeypatch.setattr(
        "skysort_api.services.export_service.detect_conflict",
        lambda _path, _tags: {"diff": {"XMP-skysort:Pick": {"existing": "False", "desired": "True"}}},
    )
    monkeypatch.setattr("skysort_api.services.export_service.write_tags", lambda file_path, *_args: writes.append(file_path) or (True, "written"))

    response = export_xmp(
        db_session,
        XmpExportRequest(job_id="job_filters", filters={"pick": True}, dry_run=False, conflict_policy="overwrite_safe_fields"),
    )

    assert response["target_count"] == 1
    assert response["written_count"] == 1
    assert response["conflicts"][0]["photo_id"] == "photo_pick"
    assert writes == [str(tmp_path / "pick.jpg")]


def test_export_xmp_dry_run_does_not_write(db_session, monkeypatch, tmp_path: Path) -> None:
    _seed_filter_dataset(db_session, tmp_path)
    writes: list[str] = []

    monkeypatch.setattr("skysort_api.services.export_service.exiftool_available", lambda: True)
    monkeypatch.setattr("skysort_api.services.export_service.can_write", lambda _path: (True, None))
    monkeypatch.setattr("skysort_api.services.export_service.detect_conflict", lambda _path, _tags: None)
    monkeypatch.setattr("skysort_api.services.export_service.write_tags", lambda file_path, *_args: writes.append(file_path) or (True, "written"))

    response = export_xmp(db_session, XmpExportRequest(job_id="job_filters", filters={"rating": 5}, dry_run=True))

    assert response["target_count"] == 1
    assert response["writable_count"] == 1
    assert writes == []
