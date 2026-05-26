from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from skysort_api.api.schemas import GroupMergeRequest, GroupSplitRequest
from skysort_api.infra.models import Group, GroupMember

from .repositories import EvaluationRepository, GroupRepository, PhotoRepository


def merge_group(session, group_id: str, payload: GroupMergeRequest) -> dict[str, object]:
    if group_id == payload.target_group_id:
        raise HTTPException(status_code=400, detail="source and target groups must differ")
    group_repo = GroupRepository(session)
    source = group_repo.get(group_id)
    target = group_repo.get(payload.target_group_id)
    if source is None or target is None:
        raise HTTPException(status_code=404, detail="group not found")
    if source.job_id != target.job_id:
        raise HTTPException(status_code=400, detail="groups must belong to the same job")

    target_members = group_repo.list_members(target.id)
    source_members = group_repo.list_members(source.id)
    if not source_members:
        raise HTTPException(status_code=400, detail="source group has no members")
    offset = len(target_members)
    for index, member in enumerate(source_members):
        member.group_id = target.id
        member.sort_order = offset + index
        member.updated_at = datetime.now(timezone.utc)
    _refresh_group_from_members(session, target, target_members + source_members)
    _mark_group_evaluations_stale(session, target.job_id, [member.photo_id for member in target_members + source_members], target.id, "group_merged")
    target.best_photo_id = None
    target.stale_flag = True
    target.stale_reason = "group_merged"
    session.delete(source)
    session.commit()
    return {"group_id": target.id, "merged_group_id": group_id, "group_size": target.group_size, "stale": True}


def split_group(session, group_id: str, payload: GroupSplitRequest) -> dict[str, object]:
    if not payload.photo_ids:
        raise HTTPException(status_code=400, detail="photo_ids is required")
    group_repo = GroupRepository(session)
    photo_repo = PhotoRepository(session)
    group = group_repo.get(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="group not found")
    members = group_repo.list_members(group_id)
    selected = [member for member in members if member.photo_id in set(payload.photo_ids)]
    remaining = [member for member in members if member.photo_id not in set(payload.photo_ids)]
    if not selected:
        raise HTTPException(status_code=400, detail="selected photos are not in the group")
    if not remaining:
        raise HTTPException(status_code=400, detail="split must leave at least one photo in the original group")

    new_group = Group(
        id=f"group_{uuid.uuid4().hex[:10]}",
        job_id=group.job_id,
        representative_photo_id=selected[0].photo_id,
        best_photo_id=None,
        group_size=len(selected),
        group_start_time=None,
        group_end_time=None,
        diversity_score=None,
        stale_flag=True,
        stale_reason="group_split",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.add(new_group)
    for index, member in enumerate(selected):
        member.group_id = new_group.id
        member.sort_order = index
        member.updated_at = datetime.now(timezone.utc)
    for index, member in enumerate(remaining):
        member.sort_order = index
        member.updated_at = datetime.now(timezone.utc)
    _refresh_group_from_members(session, group, remaining)
    _refresh_group_from_members(session, new_group, selected)
    group.best_photo_id = None
    group.stale_flag = True
    group.stale_reason = "group_split"
    _mark_group_evaluations_stale(session, group.job_id, [member.photo_id for member in remaining], group.id, "group_split")
    _mark_group_evaluations_stale(session, group.job_id, [member.photo_id for member in selected], new_group.id, "group_split")
    session.commit()
    return {"group_id": group.id, "new_group_id": new_group.id, "moved_photo_ids": [member.photo_id for member in selected], "stale": True}


def _refresh_group_from_members(session, group: Group, members: list[GroupMember]) -> None:
    photo_repo = PhotoRepository(session)
    photos = [photo for photo in (photo_repo.get(member.photo_id) for member in members) if photo is not None]
    group.group_size = len(members)
    group.representative_photo_id = members[0].photo_id if members else None
    capture_times = [photo.capture_time for photo in photos if photo.capture_time is not None]
    group.group_start_time = min(capture_times) if capture_times else None
    group.group_end_time = max(capture_times) if capture_times else None
    group.updated_at = datetime.now(timezone.utc)


def _mark_group_evaluations_stale(session, job_id: str, photo_ids: list[str], group_id: str, reason: str) -> None:
    eval_repo = EvaluationRepository(session)
    for photo_id in photo_ids:
        evaluation = eval_repo.current_for_photo(photo_id, job_id)
        if evaluation is None:
            continue
        evaluation.group_id = group_id
        evaluation.best_cut_flag = False
        evaluation.stale_flag = True
        evaluation.stale_reason = reason
        evaluation.updated_at = datetime.now(timezone.utc)
