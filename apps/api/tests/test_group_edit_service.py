from __future__ import annotations

from datetime import datetime, timezone

from skysort_api.api.schemas import GroupMergeRequest, GroupSplitRequest
from skysort_api.infra.models import Group, GroupMember, Job, Photo, PhotoEvaluation
from skysort_api.services.group_edit_service import merge_group, split_group
from skysort_api.services.repositories import GroupRepository


def _seed_group_edit_dataset(db_session) -> None:
    now = datetime.now(timezone.utc)
    db_session.add(
        Job(
            id="job_group_edit",
            root_path="/tmp/group-edit",
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
    )
    for index, photo_id in enumerate(["photo_a", "photo_b", "photo_c"]):
        db_session.add(
            Photo(
                id=photo_id,
                job_id="job_group_edit",
                file_path=f"/tmp/group-edit/{photo_id}.jpg",
                file_name=f"{photo_id}.jpg",
                file_hash=photo_id,
                file_size=10,
                file_mtime=float(index),
                capture_order_index=index,
                capture_time=now,
                created_at=now,
                updated_at=now,
            )
        )
        db_session.add(
            PhotoEvaluation(
                id=f"eval_{photo_id}",
                photo_id=photo_id,
                job_id="job_group_edit",
                group_id="group_a" if photo_id != "photo_c" else "group_b",
                rating=4,
                selection_status="normal",
                evaluation_status="final",
                pick_flag=False,
                best_cut_flag=photo_id == "photo_a",
                reviewed_flag=False,
                user_override_flag=False,
                stale_flag=False,
                version=1,
                is_current=True,
                created_at=now,
                updated_at=now,
            )
        )
    db_session.add_all(
        [
            Group(
                id="group_a",
                job_id="job_group_edit",
                representative_photo_id="photo_a",
                best_photo_id="photo_a",
                group_size=2,
                stale_flag=False,
                created_at=now,
                updated_at=now,
            ),
            Group(
                id="group_b",
                job_id="job_group_edit",
                representative_photo_id="photo_c",
                best_photo_id="photo_c",
                group_size=1,
                stale_flag=False,
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    db_session.add_all(
        [
            GroupMember(id="gm_a", group_id="group_a", photo_id="photo_a", sort_order=0, similarity_score=1.0, created_at=now, updated_at=now),
            GroupMember(id="gm_b", group_id="group_a", photo_id="photo_b", sort_order=1, similarity_score=0.9, created_at=now, updated_at=now),
            GroupMember(id="gm_c", group_id="group_b", photo_id="photo_c", sort_order=0, similarity_score=1.0, created_at=now, updated_at=now),
        ]
    )
    db_session.flush()


def test_merge_group_moves_members_and_marks_evaluations_stale(db_session) -> None:
    _seed_group_edit_dataset(db_session)

    response = merge_group(db_session, "group_b", GroupMergeRequest(target_group_id="group_a"))

    group_repo = GroupRepository(db_session)
    assert response["group_id"] == "group_a"
    assert response["group_size"] == 3
    assert group_repo.get("group_b") is None
    assert [member.photo_id for member in group_repo.list_members("group_a")] == ["photo_a", "photo_b", "photo_c"]
    evaluation = db_session.get(PhotoEvaluation, "eval_photo_c")
    assert evaluation is not None
    assert evaluation.group_id == "group_a"
    assert evaluation.stale_flag is True
    assert evaluation.stale_reason == "group_merged"


def test_split_group_creates_new_group_and_clears_best_cut(db_session) -> None:
    _seed_group_edit_dataset(db_session)

    response = split_group(db_session, "group_a", GroupSplitRequest(photo_ids=["photo_b"]))

    group_repo = GroupRepository(db_session)
    original = group_repo.get("group_a")
    new_group = group_repo.get(str(response["new_group_id"]))
    moved_eval = db_session.get(PhotoEvaluation, "eval_photo_b")
    kept_eval = db_session.get(PhotoEvaluation, "eval_photo_a")
    assert original is not None and original.group_size == 1
    assert new_group is not None and new_group.group_size == 1
    assert [member.photo_id for member in group_repo.list_members(new_group.id)] == ["photo_b"]
    assert moved_eval is not None and moved_eval.group_id == new_group.id
    assert moved_eval.stale_flag is True
    assert kept_eval is not None and kept_eval.best_cut_flag is False
