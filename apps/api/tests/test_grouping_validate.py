from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from skysort_api.infra.models import AIResponse, Group, GroupMember, Job, JobFailure, Photo, PhotoEvaluation, TechnicalScore


_SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "grouping_validate.py"
_SPEC = importlib.util.spec_from_file_location("grouping_validate", _SCRIPT_PATH)
assert _SPEC and _SPEC.loader
grouping_validate = importlib.util.module_from_spec(_SPEC)
sys.modules["grouping_validate"] = grouping_validate
_SPEC.loader.exec_module(grouping_validate)

validate_grouping = grouping_validate.validate_grouping
build_validation_report = grouping_validate.build_validation_report
load_fixture_from_db = grouping_validate.load_fixture_from_db
write_report = grouping_validate.write_report


def test_grouping_validate_compares_settings_metrics(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.json"
    fixture.write_text(
        json.dumps(
            {
                "schema_version": "v1",
                "photos": [
                    {"photo_id": "a", "capture_timestamp_ms": 1000, "capture_order_index": 0, "similarity_seed": 0.10},
                    {"photo_id": "b", "capture_timestamp_ms": 2000, "capture_order_index": 1, "similarity_seed": 0.11},
                    {"photo_id": "c", "capture_timestamp_ms": 9000, "capture_order_index": 2, "similarity_seed": 0.12},
                ],
                "scenarios": [
                    {"name": "loose", "time_proximity_seconds": 10, "similarity_threshold": 0.80},
                    {"name": "strict-time", "time_proximity_seconds": 2, "similarity_threshold": 0.80},
                ],
            }
        ),
        encoding="utf-8",
    )

    report = validate_grouping(fixture)

    assert report["photo_count"] == 3
    assert report["scenarios"][0]["group_count"] == 1
    assert report["scenarios"][0]["average_group_size"] == 3
    assert report["scenarios"][1]["group_count"] == 2
    assert report["scenarios"][1]["single_group_count"] == 1


def test_grouping_validate_writes_reports(tmp_path: Path) -> None:
    report = {
        "schema_version": "v1",
        "generated_at": "2026-05-27T00:00:00+00:00",
        "photo_count": 2,
        "scenarios": [
            {
                "name": "default",
                "time_proximity_seconds": 4,
                "similarity_threshold": 0.86,
                "group_count": 1,
                "single_group_count": 0,
                "average_group_size": 2,
                "groups": [["a", "b"]],
            }
        ],
    }

    paths = write_report(report, tmp_path, stem="grouping")

    assert Path(paths["json"]).exists()
    assert Path(paths["markdown"]).read_text(encoding="utf-8").startswith("# SkySort Grouping Validation")


def test_grouping_validate_replays_failed_ai_responses() -> None:
    report = build_validation_report(
        {
            "schema_version": "v1",
            "photos": [],
            "ai_responses": [
                {
                    "phase": "single",
                    "response_status": "ai_eval_failed",
                    "target_photo_ids_json": '["photo_1"]',
                    "raw_response_text": json.dumps(
                        {
                            "schema_version": "v1",
                            "ranking": [
                                {
                                    "photo_id": "photo_1_typo",
                                    "semantic_score": 70,
                                    "composition_score": 60,
                                    "subject_state_score": 50,
                                    "rarity_score": 40,
                                    "reason": "recoverable single response",
                                }
                            ],
                        }
                    ),
                }
            ],
            "job_failures": [{"reason_code": "json_parse_failed"}],
        }
    )

    ai = report["ai_evaluation"]
    assert ai["failed_response_replay"]["json_recovered_count"] == 1
    assert ai["failed_response_replay"]["schema_valid_count"] == 1
    assert ai["projected_json_schema_failure_count_after_replay"] == 0


def test_grouping_validate_loads_real_job_fixture_and_diagnostics(db_session, isolated_runtime: Path) -> None:
    now = datetime.now(timezone.utc)
    job = Job(
        id="job_diagnostics",
        project_id=None,
        root_path=str(isolated_runtime / "photos"),
        status="completed",
        total_files=3,
        imported_files=3,
        grouped_files=3,
        technically_scored_files=3,
        semantically_scored_files=1,
        provisional_rated_files=2,
        final_rated_files=1,
        failed_files=1,
        current_stage="finalized",
        error_messages_json="[]",
        cancel_requested=False,
        started_at=now,
        finished_at=now,
        updated_at=now,
        settings_snapshot_json=json.dumps({"time_proximity_seconds": 4, "similarity_threshold": 0.86}),
        app_version="test",
        model_name="test-model",
        prompt_template_hash="hash",
        response_schema_version="v1",
    )
    photos = [
        Photo(
            id=f"photo_{index}",
            job_id=job.id,
            file_path=str(isolated_runtime / f"photo_{index}.jpg"),
            file_name=f"photo_{index}.jpg",
            file_hash=f"hash_{index}",
            file_size=100,
            file_mtime=1.0,
            capture_time=now,
            capture_timestamp_ms=1000 + index * 1500,
            capture_order_index=index,
            camera_model="camera",
            lens_model="lens",
            focal_length=400.0,
            shutter_speed="1/2000",
            aperture=8.0,
            iso=400,
            width=100,
            height=100,
            orientation=1,
            is_missing=False,
        )
        for index in range(3)
    ]
    groups = [
        Group(id="group_a", job_id=job.id, representative_photo_id="photo_0", best_photo_id="photo_0", group_size=2, group_start_time=now, group_end_time=now),
        Group(id="group_b", job_id=job.id, representative_photo_id="photo_2", best_photo_id=None, group_size=1, group_start_time=now, group_end_time=now),
    ]
    members = [
        GroupMember(id="gm_0", group_id="group_a", photo_id="photo_0", sort_order=0, similarity_score=1.0),
        GroupMember(id="gm_1", group_id="group_a", photo_id="photo_1", sort_order=1, similarity_score=0.95),
        GroupMember(id="gm_2", group_id="group_b", photo_id="photo_2", sort_order=0, similarity_score=1.0),
    ]
    scores = [
        TechnicalScore(
            id=f"tech_{index}",
            photo_id=f"photo_{index}",
            job_id=job.id,
            sharpness_score=30 + index,
            motion_blur_score=70 - index,
            highlight_clip_ratio=0.01 * index,
            shadow_clip_ratio=0.02 * index,
            technical_score_total=60 + index * 5,
        )
        for index in range(3)
    ]
    evaluations = [
        PhotoEvaluation(
            id=f"eval_{index}",
            photo_id=f"photo_{index}",
            job_id=job.id,
            group_id="group_a" if index < 2 else "group_b",
            semantic_score=80.0 if index == 0 else None,
            evaluation_status="ai_eval_failed" if index == 2 else "final",
            selection_status="normal",
            is_current=True,
        )
        for index in range(3)
    ]
    db_session.add_all([job, *photos, *groups, *members, *scores, *evaluations])
    db_session.add(
        AIResponse(
            id="ai_1",
            job_id=job.id,
            photo_id=None,
            group_id="group_a",
            phase="group_compare",
            model_name="test-model",
            prompt_template_name="group_compare_v1",
            prompt_template_hash="hash",
            response_schema_version="v1",
            request_payload="{}",
            response_json="{}",
            raw_response_text=None,
            target_photo_ids_json="[]",
            response_status="success",
            latency_ms=100,
        )
    )
    db_session.add(JobFailure(id="fail_1", job_id=job.id, stage="semantically_scored", reason_code="json_parse_failed", message="bad json", retryable=True))
    db_session.commit()

    fixture = load_fixture_from_db(isolated_runtime / "skysort.db", job_id=job.id)
    latest_fixture = load_fixture_from_db(isolated_runtime / "skysort.db")
    report = build_validation_report(fixture)

    assert fixture["source"]["job_id"] == job.id
    assert latest_fixture["source"]["job_id"] == job.id
    assert report["current_grouping"]["group_count"] == 2
    assert report["current_grouping"]["internal_gap_risk"]["groups_with_internal_gap_over_4s"] == 0
    assert report["technical_scores"]["scored_photo_count"] == 3
    assert report["ai_evaluation"]["json_parse_failure_count"] == 1
    assert report["rating_distribution"]["evaluated_photo_count"] == 3
    assert report["rating_distribution"]["star1_or_reject_count"] == 0
    assert report["simulated_rating_distribution"]["source"] == "current_scoring_from_stored_technical_scores"
    assert report["simulated_rating_distribution"]["evaluated_photo_count"] == 3
    assert report["simulated_rating_distribution"]["star1_or_reject_count"] == 0
