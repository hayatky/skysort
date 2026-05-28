from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import select

from skysort_api.domain.evaluation import SemanticMetrics
from skysort_api.infra.models import AIResponse, Group, GroupMember, Job, Photo, PhotoEvaluation, TechnicalScore
from skysort_api.services.analysis_service import _compare_chunk, _evaluate_group, _evaluate_single_photo, normalize_and_validate_ai_payload
from skysort_api.services.repositories import EvaluationRepository, FailureRepository, GroupRepository, PhotoRepository


class FakeAIClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0
        self.payloads = []

    def evaluate(self, _phase: str, _payload: dict[str, object]):
        self.calls += 1
        self.payloads.append(_payload)
        return self._responses.pop(0)


def _response(parsed_json: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(
        payload={"messages": []},
        parsed_json=parsed_json,
        raw_response_text="{}",
        status="succeeded",
        latency_ms=1,
    )


def _contact_sheet_stub(items, *_args, **_kwargs):
    return "data:image/jpeg;base64,stub", {chr(ord("A") + index): photo_id for index, (photo_id, _path) in enumerate(items)}


def _group_payload(best_photo_id: str, ranking: list[dict[str, object]], reject_photo_ids: list[str] | None = None, keep_photo_ids: list[str] | None = None) -> dict[str, object]:
    return {
        "schema_version": "v1",
        "best_photo_id": best_photo_id,
        "keep_photo_ids": keep_photo_ids or [best_photo_id],
        "reject_photo_ids": reject_photo_ids or [],
        "confidence": 0.86,
        "ranking": [
            {
                "confidence": 0.8,
                "problem_tags": [],
                **item,
            }
            for item in ranking
        ],
        "reason_by_photo_id": {str(item["photo_id"]): str(item["reason"]) for item in ranking},
    }


def test_single_payload_normalizes_unambiguous_target_photo_id_typo() -> None:
    payload = {
        "schema_version": "v1",
        "ranking": [
            {
                "photo_id": "photo_abc_typo",
                "semantic_score": 40,
                "composition_score": 30,
                "subject_state_score": 30,
                "rarity_score": 20,
                "reason": "single target",
            }
        ],
    }

    normalized = normalize_and_validate_ai_payload("single", payload, ["photo_abc"])

    assert normalized is not None
    assert normalized["ranking"][0]["photo_id"] == "photo_abc"


def test_group_compare_normalizes_legacy_single_target_payload() -> None:
    payload = {
        "schema_version": "v1",
        "best_photo_id": "photo_one",
        "ranking": [
            {
                "photo_id": "photo_one_typo",
                "rank": 1,
                "semantic_score": 80,
                "rarity_score": 30,
                "reason": "legacy response",
            }
        ],
        "drop_candidates": [],
    }

    normalized = normalize_and_validate_ai_payload("group_compare", payload, ["photo_one"])

    assert normalized is not None
    assert normalized["ranking"][0]["photo_id"] == "photo_one"
    assert normalized["keep_photo_ids"] == ["photo_one"]
    assert normalized["reject_photo_ids"] == []
    assert normalized["confidence"] == 0.0
    assert normalized["reason_by_photo_id"] == {"photo_one": "legacy response"}


def test_group_compare_normalizes_contact_sheet_labels_to_photo_ids() -> None:
    payload = {
        "schema_version": "v1",
        "best_photo_id": "B",
        "keep_photo_ids": ["B"],
        "reject_photo_ids": ["A"],
        "confidence": 0.8,
        "reason_by_photo_id": {
            "A": "soft focus",
            "B": "cleaner aircraft detail",
        },
        "ranking": [
            {
                "photo_id": "B",
                "rank": 1,
                "semantic_score": 86,
                "rarity_score": 35,
                "confidence": 0.8,
                "problem_tags": [],
                "reason": "cleaner aircraft detail",
            },
            {
                "photo_id": "A",
                "rank": 2,
                "semantic_score": 60,
                "rarity_score": 30,
                "confidence": 0.7,
                "problem_tags": ["soft_focus"],
                "reason": "soft focus",
            },
        ],
    }

    normalized = normalize_and_validate_ai_payload("group_compare", payload, ["photo_one", "photo_two"])

    assert normalized is not None
    assert normalized["best_photo_id"] == "photo_two"
    assert normalized["keep_photo_ids"] == ["photo_two"]
    assert normalized["reject_photo_ids"] == ["photo_one"]
    assert normalized["reason_by_photo_id"] == {
        "photo_one": "soft focus",
        "photo_two": "cleaner aircraft detail",
    }
    assert [item["photo_id"] for item in normalized["ranking"]] == ["photo_two", "photo_one"]


def test_group_compare_normalizes_unambiguous_corrupted_photo_ids() -> None:
    payload = _group_payload(
        "photo_6286d317f11b",
        [
            {
                "photo_id": "photo_6286d317f11b",
                "rank": 1,
                "semantic_score": 90,
                "rarity_score": 40,
                "reason": "best",
            },
            {
                "photo_id": "photo_443dc1b76////",
                "rank": 2,
                "semantic_score": 50,
                "rarity_score": 20,
                "reason": "soft",
            },
        ],
        reject_photo_ids=["un//s/photo_443dc1b7146b"],
    )
    payload["reason_by_photo_id"] = {
        "photo_6286d317f_11b": "best",
        "photo_443dc1b7146b": "soft",
    }

    normalized = normalize_and_validate_ai_payload("group_compare", payload, ["photo_6286d317f11b", "photo_443dc1b7146b"])

    assert normalized is not None
    assert normalized["reason_by_photo_id"] == {
        "photo_6286d317f11b": "best",
        "photo_443dc1b7146b": "soft",
    }
    assert normalized["reject_photo_ids"] == ["photo_443dc1b7146b"]
    assert [item["photo_id"] for item in normalized["ranking"]] == ["photo_6286d317f11b", "photo_443dc1b7146b"]


def test_group_compare_maps_corrupted_rank_one_photo_id_to_valid_best() -> None:
    payload = _group_payload(
        "photo_d3fde0f33565",
        [
            {
                "photo_id": "photo_ patriotismy",
                "rank": 1,
                "semantic_score": 90,
                "rarity_score": 40,
                "reason": "best",
            },
            {
                "photo_id": "photo_1da3ee194052",
                "rank": 2,
                "semantic_score": 70,
                "rarity_score": 35,
                "reason": "runner up",
            },
            {
                "photo_id": "photo_4d6757e01f56",
                "rank": 3,
                "semantic_score": 30,
                "rarity_score": 20,
                "reason": "soft",
            },
        ],
        reject_photo_ids=["photo_4d6757e01f56"],
        keep_photo_ids=["photo_1da3ee194052"],
    )
    payload["reason_by_photo_id"] = {
        "photo_d3fde0f33_//": "best",
    }

    normalized = normalize_and_validate_ai_payload(
        "group_compare",
        payload,
        ["photo_d3fde0f33565", "photo_1da3ee194052", "photo_4d6757e01f56"],
    )

    assert normalized is not None
    assert [item["photo_id"] for item in normalized["ranking"]] == [
        "photo_d3fde0f33565",
        "photo_1da3ee194052",
        "photo_4d6757e01f56",
    ]
    assert normalized["reason_by_photo_id"]["photo_d3fde0f33565"] == "best"


def test_group_compare_maps_single_invalid_ranking_item_to_missing_candidate() -> None:
    payload = _group_payload(
        "photo_6286d317f11b",
        [
            {
                "photo_id": "photo_6286d317f11b",
                "rank": 1,
                "semantic_score": 90,
                "rarity_score": 40,
                "reason": "best",
            },
            {
                "photo_id": "//",
                "rank": 2,
                "semantic_score": 50,
                "rarity_score": 20,
                "reason": "soft",
            },
        ],
        reject_photo_ids=["photo_443dc1b7146b"],
    )

    normalized = normalize_and_validate_ai_payload("group_compare", payload, ["photo_6286d317f11b", "photo_443dc1b7146b"])

    assert normalized is not None
    assert [item["photo_id"] for item in normalized["ranking"]] == ["photo_6286d317f11b", "photo_443dc1b7146b"]
    assert normalized["reason_by_photo_id"]["photo_443dc1b7146b"] == "soft"


def test_single_payload_collapses_duplicate_unambiguous_target_rankings() -> None:
    payload = {
        "schema_version": "v1",
        "ranking": [
            {
                "photo_id": "photo_c3de34308931",
                "semantic_score": 0,
                "composition_score": 0,
                "subject_state_score": 0,
                "rarity_score": 10,
                "reason": "partial answer",
            },
            {
                "photo_id": "photo_c3de34308931",
                "semantic_score": 75,
                "composition_score": 70,
                "subject_state_score": 80,
                "rarity_score": 50,
                "reason": "complete answer",
            },
        ],
    }

    normalized = normalize_and_validate_ai_payload("single", payload, ["photo_c3de34308931"])

    assert normalized is not None
    assert normalized["ranking"] == [
        {
            "photo_id": "photo_c3de34308931",
            "semantic_score": 75,
            "composition_score": 70,
            "subject_state_score": 80,
            "rarity_score": 50,
            "reason": "complete answer",
        }
    ]


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
    monkeypatch.setattr("skysort_api.services.analysis_service.build_contact_sheet_data_url", _contact_sheet_stub)

    ai_client = FakeAIClient(
        [
            _response(
                _group_payload(
                    "photo_3",
                    [
                        {"photo_id": "photo_3", "rank": 1, "semantic_score": 91, "rarity_score": 82, "reason": "first chunk best"},
                        {"photo_id": "photo_6", "rank": 6, "semantic_score": 20, "rarity_score": 5, "reason": "drop this", "problem_tags": ["motion_blur"]},
                    ],
                    reject_photo_ids=["photo_6"],
                )
            ),
            _response(
                _group_payload(
                    "photo_7",
                    [{"photo_id": "photo_7", "rank": 1, "semantic_score": 95, "rarity_score": 90, "reason": "solo winner"}],
                )
            ),
            _response(
                _group_payload(
                    "photo_7",
                    [
                        {"photo_id": "photo_7", "rank": 1, "semantic_score": 97, "rarity_score": 92, "reason": "overall best"},
                        {"photo_id": "photo_3", "rank": 2, "semantic_score": 90, "rarity_score": 80, "reason": "runner up"},
                    ],
                    keep_photo_ids=["photo_7", "photo_3"],
                )
            ),
        ]
    )

    _evaluate_group(db_session, eval_repo, photo_repo, failure_repo, job, group, photo_ids, ai_client)
    db_session.flush()

    assert ai_client.calls == 3
    assert all(payload["max_tokens"] == 1024 for payload in ai_client.payloads)
    assert group_repo.get("group_ai").best_photo_id == "photo_7"
    assert eval_repo.current_for_photo("photo_7", "job_ai").best_cut_flag is True
    assert eval_repo.current_for_photo("photo_3", "job_ai").pick_flag is True
    assert eval_repo.current_for_photo("photo_6", "job_ai").selection_status == "rejected"
    assert eval_repo.current_for_photo("photo_6", "job_ai").rating is None
    assert eval_repo.current_for_photo("photo_6", "job_ai").ai_confidence_score == 0.8
    assert json.loads(eval_repo.current_for_photo("photo_6", "job_ai").problem_tags_json) == ["motion_blur"]


def test_merge_suggested_group_is_deferred_for_review_before_ai_eval(db_session) -> None:
    now = datetime.now(timezone.utc)
    job = Job(
        id="job_merge_review",
        root_path="/tmp/merge-review",
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
    group = Group(
        id="group_merge_review",
        job_id="job_merge_review",
        representative_photo_id="merge_photo_1",
        best_photo_id="merge_photo_1",
        group_size=2,
        group_start_time=now,
        group_end_time=now,
        diversity_score=None,
        merge_suggested=True,
        merge_suggestion_reason="adjacent fragment",
        stale_flag=False,
        stale_reason=None,
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([job, group])
    eval_repo = EvaluationRepository(db_session)
    photo_repo = PhotoRepository(db_session)
    failure_repo = FailureRepository(db_session)
    photo_ids = ["merge_photo_1", "merge_photo_2"]
    for index, photo_id in enumerate(photo_ids):
        db_session.add(
            Photo(
                id=photo_id,
                job_id="job_merge_review",
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
        eval_repo.add_technical(
            TechnicalScore(
                id=f"tech_merge_{index + 1}",
                photo_id=photo_id,
                job_id="job_merge_review",
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
                id=f"eval_merge_{index + 1}",
                photo_id=photo_id,
                job_id="job_merge_review",
                group_id="group_merge_review",
                semantic_score=70,
                composition_score=70,
                subject_state_score=70,
                rarity_score=50,
                provisional_rating=3,
                provisional_selection_status="normal",
                rating=3,
                selection_status="normal",
                evaluation_status="provisional",
                pick_flag=True,
                best_cut_flag=index == 0,
                reviewed_flag=False,
                ai_reason="prior",
                ai_confidence_score=0.42,
                problem_tags_json='["fragmented_group"]',
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

    ai_client = FakeAIClient([])
    _evaluate_group(db_session, eval_repo, photo_repo, failure_repo, job, group, photo_ids, ai_client)
    db_session.flush()

    assert ai_client.calls == 0
    assert group.best_photo_id is None
    assert group.stale_flag is True
    assert group.stale_reason == "merge_suggested"
    for photo_id in photo_ids:
        current = eval_repo.current_for_photo(photo_id, "job_merge_review")
        assert current.stale_flag is True
        assert current.stale_reason == "merge_suggested"
        assert current.best_cut_flag is False
        assert current.ai_confidence_score == 0.42
        assert json.loads(current.problem_tags_json) == ["fragmented_group"]


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
    monkeypatch.setattr("skysort_api.services.analysis_service.build_contact_sheet_data_url", _contact_sheet_stub)
    ai_client = FakeAIClient(
        [
            _response(
                {
                    "best_photo_id": "invalid_photo_1",
                    "ranking": [{"photo_id": "invalid_photo_1", "rank": 1, "semantic_score": 90, "reason": "missing schema version"}],
                    "reject_photo_ids": [],
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
