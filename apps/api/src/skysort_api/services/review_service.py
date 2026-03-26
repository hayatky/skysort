from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from skysort_api.api.schemas import MutationResult, PhotoMutationRequest, ReanalyzeRequest
from skysort_api.infra.models import Group, PhotoEvaluation, RatingHistory
from skysort_api.services.repositories import EvaluationRepository, GroupRepository
from skysort_api.workers.job_runner import job_runner


def mutate_photo(session, photo_id: str, payload: PhotoMutationRequest) -> MutationResult:
    eval_repo = EvaluationRepository(session)
    group_repo = GroupRepository(session)
    current = eval_repo.current_for_photo(photo_id, payload.job_id)
    if current is None:
        raise HTTPException(status_code=404, detail="photo evaluation not found")

    group = group_repo.get(current.group_id) if current.group_id else None
    rating = current.rating
    selection_status = current.selection_status
    if payload.selection_status is not None:
        selection_status = payload.selection_status
        if selection_status == "rejected":
            rating = None
    if payload.rating is not None:
        rating = payload.rating
        if payload.selection_status is None:
            selection_status = "normal"

    best_cut_flag = current.best_cut_flag if payload.best_cut_flag is None else payload.best_cut_flag
    if selection_status == "rejected":
        best_cut_flag = False

    updated = _clone_evaluation(
        current,
        rating=rating,
        selection_status=selection_status,
        pick_flag=current.pick_flag if payload.pick_flag is None else payload.pick_flag,
        best_cut_flag=best_cut_flag,
        reviewed_flag=current.reviewed_flag if payload.reviewed_flag is None else payload.reviewed_flag,
        user_override_flag=True,
        stale_flag=False,
        stale_reason=None,
    )
    eval_repo.add_evaluation(updated)

    if group is not None:
        _enforce_group_best_cut_invariants(session, eval_repo, group_repo, group, updated.photo_id, updated.best_cut_flag)

    eval_repo.record_history(
        RatingHistory(
            id=f"hist_{uuid.uuid4().hex[:10]}",
            photo_id=photo_id,
            job_id=payload.job_id,
            old_rating=current.rating,
            new_rating=updated.rating,
            old_selection_status=current.selection_status,
            new_selection_status=updated.selection_status,
            changed_by_user=True,
            changed_at=datetime.now(timezone.utc),
            reason="manual_override",
        )
    )
    session.flush()
    return MutationResult(updated_count=1, failed_count=0)


def batch_mutate_photos(session, payload) -> MutationResult:
    updated = 0
    for photo_id in payload.photo_ids:
        request = PhotoMutationRequest(job_id=payload.job_id)
        if payload.action == "set_rating":
            request.rating = int(payload.payload["rating"])
        elif payload.action == "set_selection_status":
            request.selection_status = str(payload.payload["selection_status"])
            if request.selection_status == "rejected":
                request.rating = None
        elif payload.action == "set_pick":
            request.pick_flag = bool(payload.payload["pick_flag"])
        elif payload.action == "set_reviewed":
            request.reviewed_flag = bool(payload.payload["reviewed_flag"])
        elif payload.action == "set_best_cut":
            request.best_cut_flag = bool(payload.payload["best_cut_flag"])
        mutate_photo(session, photo_id, request)
        updated += 1
    return MutationResult(updated_count=updated, failed_count=0)


def reanalyze_photo(session, photo_id: str, payload: ReanalyzeRequest) -> dict[str, bool]:
    evaluation = EvaluationRepository(session).current_for_photo(photo_id, payload.job_id)
    if evaluation is None:
        raise HTTPException(status_code=404, detail="photo evaluation not found")
    evaluation.stale_flag = True
    evaluation.stale_reason = payload.scope
    job_runner.start_photo_reanalysis(payload.job_id, [photo_id], payload.scope)
    return {"accepted": True}


def reanalyze_group(session, group_id: str, payload: ReanalyzeRequest) -> dict[str, bool]:
    group_repo = GroupRepository(session)
    group = group_repo.get(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="group not found")
    group.stale_flag = True
    group.stale_reason = payload.scope
    photo_ids = [member.photo_id for member in group_repo.list_members(group_id)]
    job_runner.start_photo_reanalysis(payload.job_id, photo_ids, payload.scope)
    return {"accepted": True}


def _enforce_group_best_cut_invariants(session, eval_repo: EvaluationRepository, group_repo: GroupRepository, group: Group, selected_photo_id: str, selected_best_cut_flag: bool) -> None:
    current_evaluations = eval_repo.current_for_group(group.id, group.job_id)
    for evaluation in current_evaluations:
        desired_flag = evaluation.best_cut_flag
        if evaluation.photo_id == selected_photo_id:
            desired_flag = selected_best_cut_flag and evaluation.selection_status != "rejected"
        elif selected_best_cut_flag:
            desired_flag = False
        if desired_flag == evaluation.best_cut_flag:
            continue
        eval_repo.add_evaluation(_clone_evaluation(evaluation, best_cut_flag=desired_flag))

    session.flush()
    refreshed = eval_repo.current_for_group(group.id, group.job_id)
    replacement = _select_group_best_photo_id(group_repo, group, refreshed)

    for evaluation in refreshed:
        desired_flag = replacement is not None and evaluation.photo_id == replacement and evaluation.selection_status != "rejected"
        if desired_flag == evaluation.best_cut_flag:
            continue
        eval_repo.add_evaluation(_clone_evaluation(evaluation, best_cut_flag=desired_flag))

    group.best_photo_id = replacement
    group.updated_at = datetime.now(timezone.utc)
    session.flush()


def _select_group_best_photo_id(group_repo: GroupRepository, group: Group, evaluations: list[PhotoEvaluation]) -> str | None:
    non_rejected = [evaluation for evaluation in evaluations if evaluation.selection_status != "rejected"]
    if not non_rejected:
        return None

    manual_best = [evaluation for evaluation in non_rejected if evaluation.user_override_flag and evaluation.best_cut_flag]
    if manual_best:
        return sorted(manual_best, key=lambda item: (item.updated_at, item.version), reverse=True)[0].photo_id

    rated = [evaluation for evaluation in non_rejected if evaluation.rating is not None]
    if rated:
        return sorted(rated, key=lambda item: (item.rating or 0, item.provisional_rating or 0, -item.version), reverse=True)[0].photo_id

    provisional = [evaluation for evaluation in non_rejected if evaluation.provisional_rating is not None]
    if provisional:
        return sorted(provisional, key=lambda item: (item.provisional_rating or 0, -item.version), reverse=True)[0].photo_id

    representative_photo_id = group.representative_photo_id
    if representative_photo_id and any(evaluation.photo_id == representative_photo_id for evaluation in non_rejected):
        return representative_photo_id

    order = {member.photo_id: member.sort_order for member in group_repo.list_members(group.id)}
    return sorted(non_rejected, key=lambda item: order.get(item.photo_id, 10**9))[0].photo_id


def _clone_evaluation(current: PhotoEvaluation, **overrides) -> PhotoEvaluation:
    data = {
        "id": f"eval_{uuid.uuid4().hex[:10]}",
        "photo_id": current.photo_id,
        "job_id": current.job_id,
        "group_id": current.group_id,
        "semantic_score": current.semantic_score,
        "composition_score": current.composition_score,
        "subject_state_score": current.subject_state_score,
        "rarity_score": current.rarity_score,
        "provisional_rating": current.provisional_rating,
        "provisional_selection_status": current.provisional_selection_status,
        "rating": current.rating,
        "selection_status": current.selection_status,
        "evaluation_status": current.evaluation_status,
        "pick_flag": current.pick_flag,
        "best_cut_flag": current.best_cut_flag,
        "reviewed_flag": current.reviewed_flag,
        "ai_reason": current.ai_reason,
        "user_override_flag": current.user_override_flag,
        "stale_flag": current.stale_flag,
        "stale_reason": current.stale_reason,
        "version": 1,
        "is_current": True,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    data.update(overrides)
    return PhotoEvaluation(**data)
