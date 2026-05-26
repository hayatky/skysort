from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import select

from skysort_api.domain.evaluation import SemanticMetrics
from skysort_api.infra.models import AIResponse, Group, GroupMember, Job, Photo, PhotoEvaluation, TechnicalScore
from skysort_api.services.analysis_service import _compare_chunk, _evaluate_group, _evaluate_single_photo
from skysort_api.services.repositories import EvaluationRepository, FailureRepository, GroupRepository, PhotoRepository


class FakeAIClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def evaluate(self, _phase: str, _payload: dict[str, object]):
        self.calls += 1
        return self._responses.pop(0)


def _response(parsed_json: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(
        payload={"messages": []},
        parsed_json=parsed_json,
        raw_response_text="{}",
        status="succeeded",
        latency_ms=1,
    )


def test_group_compare_aggregates_large_groups_and_applies_drop_candidates(db_session, monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    job = Job(
        id="job_ai",
        root_path="/tmp/ai",
        status="running",
        total_files=7,
        imported_files=7,
        grouped_files=7,
        technically_scored_files=7,
        semantically_scored_files=0,
        provisional_rated_files=7,
        final_rated_files=0,
        failed_files=0,
        current_stage="semantically_scored",
        error_messages_json="[]",
        settings_snapshot_json="{}",
        app_version="0.1.0",
        model_name="qwen",
        prompt_template_hash="hash",
        response_schema_version="v1",
    )
    group = Group(
        id="group_ai",
        job_id="job_ai",
        representative_photo_id="photo_1",
        best_photo_id=None,
        group_size=7,
        group_start_time=now,
        group_end_time=now,
        diversity_score=None,
        stale_flag=False,
        stale_reason=None,
        created_at=now,
        updated_at=now,
    )
    db_session.add(job)
    db_session.add(group)

    eval_repo = EvaluationRepository(db_session)
    photo_repo = PhotoRepository(db_session)
    failure_repo = FailureRepository(db_session)
    group_repo = GroupRepository(db_session)

    photo_ids = []
    for index in range(7):
        photo_id = f"photo_{index + 1}"
        photo_ids.append(photo_id)
        db_session.add(
            Photo(
                id=photo_id,
                job_id="job_ai",
                file_path=f"/tmp/{photo_id}.jpg",
                file_name=f"{photo_id}.jpg",
                file_hash=photo_id,
                file_size=100,
                file_mtime=float(index),
                capture_order_index=index,
                preview_path=f"/tmp/{photo_id}.jpg",
                thumb_path=f"/tmp/{photo_id}.thumb.jpg",
                created_at=now,
                updated_at=now,
            )
        )
        db_session.add(
            GroupMember(
                id=f"gm_{index + 1}",
                group_id="group_ai",
                photo_id=photo_id,
                sort_order=index,
                similarity_score=1.0,
                created_at=now,
                updated_at=now,
            )
        )
        eval_repo.add_technical(
            TechnicalScore(
                id=f"tech_{index + 1}",
                photo_id=photo_id,
                job_id="job_ai",
                sharpness_score=80,
                motion_blur_score=80,
                highlight_clip_ratio=0.01,
                shadow_clip_ratio=0.01,
                technical_score_total=80 - index,
                created_at=now,
                updated_at=now,
            )
        )
        eval_repo.add_evaluation(
            PhotoEvaluation(
                id=f"eval_{index + 1}",
                photo_id=photo_id,
                job_id="job_ai",
                group_id="group_ai",
                semantic_score=None,
                composition_score=None,
                subject_state_score=None,
                rarity_score=None,
                provisional_rating=3,
                provisional_selection_status="normal",
                rating=3,
                selection_status="normal",
                evaluation_status="provisional",
                pick_flag=False,
                best_cut_flag=False,
                reviewed_flag=False,
                ai_reason=None,
                user_override_flag=False,
                stale_flag=False,
                stale_reason=None,
                version=1,
                is_current=True,
                created_at=now,
                updated_at=now,
            )
        )
    db_session.flush()

    monkeypatch.setattr(
        "skysort_api.services.analysis_service._evaluate_single_photo",
        lambda *_args, **_kwargs: SemanticMetrics(
            semantic_score=80,
            composition_score=80,
            subject_state_score=80,
            rarity_score=50,
            reason="single",
        ),
    )
    monkeypatch.setattr("skysort_api.services.analysis_service.build_data_url", lambda *_args, **_kwargs: "data:image/jpeg;base64,stub")

    ai_client = FakeAIClient(
        [
            _response(
                {
                    "schema_version": "v1",
                    "best_photo_id": "photo_3",
                    "ranking": [
                        {"photo_id": "photo_3", "rank": 1, "semantic_score": 91, "rarity_score": 82, "reason": "first chunk best"},
                        {"photo_id": "photo_6", "rank": 6, "semantic_score": 20, "rarity_score": 5, "reason": "drop this"},
                    ],
                    "drop_candidates": ["photo_6"],
                }
            ),
            _response(
                {
                    "schema_version": "v1",
                    "best_photo_id": "photo_7",
                    "ranking": [{"photo_id": "photo_7", "rank": 1, "semantic_score": 95, "rarity_score": 90, "reason": "solo winner"}],
                    "drop_candidates": [],
                }
            ),
            _response(
                {
                    "schema_version": "v1",
                    "best_photo_id": "photo_7",
                    "ranking": [
                        {"photo_id": "photo_7", "rank": 1, "semantic_score": 97, "rarity_score": 92, "reason": "overall best"},
                        {"photo_id": "photo_3", "rank": 2, "semantic_score": 90, "rarity_score": 80, "reason": "runner up"},
                    ],
                    "drop_candidates": [],
                }
            ),
        ]
    )

    _evaluate_group(db_session, eval_repo, photo_repo, failure_repo, job, group, photo_ids, ai_client)
    db_session.flush()

    assert ai_client.calls == 3
    assert group_repo.get("group_ai").best_photo_id == "photo_7"
    assert eval_repo.current_for_photo("photo_7", "job_ai").best_cut_flag is True
    assert eval_repo.current_for_photo("photo_6", "job_ai").selection_status == "rejected"
    assert eval_repo.current_for_photo("photo_6", "job_ai").rating is None


def test_group_compare_invalid_schema_is_saved_as_ai_eval_failed(db_session, monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    job = Job(
        id="job_invalid_ai",
        root_path="/tmp/invalid-ai",
        status="running",
        total_files=2,
        imported_files=2,
        grouped_files=2,
        technically_scored_files=2,
        semantically_scored_files=0,
        provisional_rated_files=2,
        final_rated_files=0,
        failed_files=0,
        current_stage="semantically_scored",
        error_messages_json="[]",
        settings_snapshot_json="{}",
        app_version="0.1.0",
        model_name="qwen",
        prompt_template_hash="hash",
        response_schema_version="v1",
    )
    db_session.add(job)
    for index in range(2):
        photo_id = f"invalid_photo_{index + 1}"
        db_session.add(
            Photo(
                id=photo_id,
                job_id="job_invalid_ai",
                file_path=f"/tmp/{photo_id}.jpg",
                file_name=f"{photo_id}.jpg",
                file_hash=photo_id,
                file_size=100,
                file_mtime=float(index),
                capture_order_index=index,
                preview_path=f"/tmp/{photo_id}.jpg",
                created_at=now,
                updated_at=now,
            )
        )
    db_session.flush()
    monkeypatch.setattr("skysort_api.services.analysis_service.build_data_url", lambda *_args, **_kwargs: "data:image/jpeg;base64,stub")
    ai_client = FakeAIClient(
        [
            _response(
                {
                    "best_photo_id": "invalid_photo_1",
                    "ranking": [{"photo_id": "invalid_photo_1", "rank": 1, "semantic_score": 90, "reason": "missing schema version"}],
                    "drop_candidates": [],
                }
            )
        ]
    )

    result = _compare_chunk(EvaluationRepository(db_session), PhotoRepository(db_session), "group_invalid", ["invalid_photo_1", "invalid_photo_2"], ai_client)
    stored = db_session.scalars(select(AIResponse)).one()

    assert result.best_photo_id is None
    assert result.ranking_by_photo_id == {}
    assert stored.response_status == "ai_eval_failed"
    assert stored.response_json is None


def test_single_photo_invalid_ranking_schema_is_saved_as_ai_eval_failed(db_session, monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(
        Job(
            id="job_invalid_single",
            root_path="/tmp/invalid-single",
            status="running",
            total_files=1,
            imported_files=1,
            grouped_files=1,
            technically_scored_files=1,
            semantically_scored_files=0,
            provisional_rated_files=1,
            final_rated_files=0,
            failed_files=0,
            current_stage="semantically_scored",
            error_messages_json="[]",
            settings_snapshot_json="{}",
            app_version="0.1.0",
            model_name="qwen",
            prompt_template_hash="hash",
            response_schema_version="v1",
        )
    )
    photo = Photo(
        id="invalid_single_photo",
        job_id="job_invalid_single",
        file_path="/tmp/invalid_single_photo.jpg",
        file_name="invalid_single_photo.jpg",
        file_hash="invalid_single_photo",
        file_size=100,
        file_mtime=1.0,
        capture_order_index=0,
        preview_path="/tmp/invalid_single_photo.jpg",
        created_at=now,
        updated_at=now,
    )
    db_session.add(photo)
    db_session.flush()
    monkeypatch.setattr("skysort_api.services.analysis_service.build_data_url", lambda *_args, **_kwargs: "data:image/jpeg;base64,stub")
    ai_client = FakeAIClient(
        [
            _response(
                {
                    "schema_version": "v1",
                    "ranking": [{"photo_id": "invalid_single_photo", "semantic_score": "high", "reason": "wrong score type"}],
                }
            )
        ]
    )

    result = _evaluate_single_photo(EvaluationRepository(db_session), photo, None, None, ai_client)
    stored = db_session.scalars(select(AIResponse)).one()

    assert result.ai_failed is True
    assert stored.response_status == "ai_eval_failed"
    assert stored.response_json is None
