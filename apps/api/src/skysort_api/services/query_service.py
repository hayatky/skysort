from __future__ import annotations

from fastapi import HTTPException

from skysort_api.services.repositories import EvaluationRepository, GroupRepository, JobRepository, PhotoRepository
from skysort_api.services.serialization import group_to_item, photo_to_review_item


def list_groups(session, job_id: str) -> dict[str, object]:
    photo_repo = PhotoRepository(session)
    eval_repo = EvaluationRepository(session)
    group_repo = GroupRepository(session)
    groups = JobRepository(session).list_groups(job_id)
    results = []
    for group in groups:
        members = group_repo.list_members(group.id)
        photos = []
        for member in members:
            photo = photo_repo.get(member.photo_id)
            evaluation = eval_repo.current_for_photo(member.photo_id, job_id)
            technical = eval_repo.technical_for_photo(member.photo_id, job_id)
            if photo and not photo.is_missing:
                photos.append(photo_to_review_item(photo, evaluation, technical))
        results.append(group_to_item(group, photos))
    return {"items": results, "total": len(results)}


def get_group(session, group_id: str) -> dict[str, object]:
    group_repo = GroupRepository(session)
    photo_repo = PhotoRepository(session)
    eval_repo = EvaluationRepository(session)
    group = group_repo.get(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="group not found")

    members = group_repo.list_members(group_id)
    photos = []
    for member in members:
        photo = photo_repo.get(member.photo_id)
        if photo is None or photo.is_missing:
            continue
        photos.append(photo_to_review_item(photo, eval_repo.current_for_photo(photo.id, group.job_id), eval_repo.technical_for_photo(photo.id, group.job_id)))

    result = group_to_item(group, photos)
    result["photos"] = photos
    return result


def list_photos(session, job_id: str) -> dict[str, object]:
    photo_repo = PhotoRepository(session)
    eval_repo = EvaluationRepository(session)
    items = []
    for photo in photo_repo.list_by_job(job_id):
        items.append(photo_to_review_item(photo, eval_repo.current_for_photo(photo.id, job_id), eval_repo.technical_for_photo(photo.id, job_id)))
    return {"items": items, "total": len(items)}
