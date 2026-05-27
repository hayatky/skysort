from __future__ import annotations

from datetime import datetime, timezone

from skysort_api.api.schemas import PhotoMutationRequest
from skysort_api.infra.models import Group, GroupMember, Job, Photo, PhotoEvaluation
from skysort_api.services.repositories import EvaluationRepository, GroupRepository
from skysort_api.services.review_service import mutate_photo


def _seed_job() -> Job:
    return Job(
        id="job_review",
        root_path="/tmp/review",
        status="completed",
        total_files=2,
        imported_files=2,
        grouped_files=2,
        technically_scored_files=2,
        semantically_scored_files=2,
        provisional_rated_files=0,
        final_rated_files=2,
        failed_files=0,
        current_stage="finalized",
        error_messages_json="[]",
        settings_snapshot_json="{}",
        app_version="0.1.0",
        model_name="qwen",
        prompt_template_hash="hash",
        response_schema_version="v1",
    )


def _seed_photo(photo_id: str, order: int) -> Photo:
    now = datetime.now(timezone.utc)
    return Photo(
        id=photo_id,
        job_id="job_review",
        file_path=f"/tmp/{photo_id}.jpg",
        file_name=f"{photo_id}.jpg",
        file_hash=photo_id,
        file_size=10,
        file_mtime=float(order),
        capture_order_index=order,
        created_at=now,
        updated_at=now,
    )


def _seed_evaluation(photo_id: str, rating: int, best_cut_flag: bool) -> PhotoEvaluation:
    now = datetime.now(timezone.utc)
    return PhotoEvaluation(
        id=f"eval_{photo_id}",
        photo_id=photo_id,
        job_id="job_review",
        group_id="group_review",
        semantic_score=80,
        composition_score=80,
        subject_state_score=80,
        rarity_score=50,
        provisional_rating=rating,
        provisional_selection_status="normal",
        rating=rating,
        selection_status="normal",
        evaluation_status="final",
        pick_flag=False,
        best_cut_flag=best_cut_flag,
        reviewed_flag=False,
        ai_reason="seeded",
        user_override_flag=best_cut_flag,
        stale_flag=False,
        stale_reason=None,
        version=1,
        is_current=True,
        created_at=now,
        updated_at=now,
    )


def test_mutate_photo_updates_group_best_cut_and_recomputes_after_reject(db_session) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(_seed_job())
    db_session.add_all([_seed_photo("photo_1", 0), _seed_photo("photo_2", 1)])
    db_session.add(
        Group(
            id="group_review",
            job_id="job_review",
            representative_photo_id="photo_1",
            best_photo_id="photo_1",
            group_size=2,
            group_start_time=now,
            group_end_time=now,
            diversity_score=None,
            stale_flag=False,
            stale_reason=None,
            created_at=now,
            updated_at=now,
        )
    )
    db_session.add_all(
        [
            GroupMember(id="gm_1", group_id="group_review", photo_id="photo_1", sort_order=0, similarity_score=1.0, created_at=now, updated_at=now),
            GroupMember(id="gm_2", group_id="group_review", photo_id="photo_2", sort_order=1, similarity_score=1.0, created_at=now, updated_at=now),
        ]
    )
    repo = EvaluationRepository(db_session)
    repo.add_evaluation(_seed_evaluation("photo_1", 5, True))
    repo.add_evaluation(_seed_evaluation("photo_2", 4, False))
    db_session.flush()

    mutate_photo(db_session, "photo_2", PhotoMutationRequest(job_id="job_review", best_cut_flag=True))
    db_session.flush()

    group_repo = GroupRepository(db_session)
    assert group_repo.get("group_review").best_photo_id == "photo_2"
    assert repo.current_for_photo("photo_1", "job_review").best_cut_flag is False
    assert repo.current_for_photo("photo_2", "job_review").best_cut_flag is True

    mutate_photo(db_session, "photo_2", PhotoMutationRequest(job_id="job_review", selection_status="rejected"))
    db_session.flush()

    assert group_repo.get("group_review").best_photo_id == "photo_1"
    assert repo.current_for_photo("photo_1", "job_review").best_cut_flag is True
    assert repo.current_for_photo("photo_2", "job_review").selection_status == "rejected"
    assert repo.current_for_photo("photo_2", "job_review").best_cut_flag is False


def test_mutate_photo_creates_manual_evaluation_for_imported_photo(db_session) -> None:
    db_session.add(_seed_job())
    db_session.add(_seed_photo("photo_imported", 0))
    db_session.flush()

    result = mutate_photo(db_session, "photo_imported", PhotoMutationRequest(job_id="job_review", rating=4))
    db_session.flush()

    current = EvaluationRepository(db_session).current_for_photo("photo_imported", "job_review")
    assert result.updated_count == 1
    assert current is not None
    assert current.rating == 4
    assert current.selection_status == "normal"
    assert current.user_override_flag is True
    assert current.evaluation_status == "provisional"
