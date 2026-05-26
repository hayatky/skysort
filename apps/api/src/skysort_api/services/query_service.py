from __future__ import annotations

import json
from datetime import datetime, timezone
from math import ceil
from typing import Any

from fastapi import HTTPException

from skysort_api.services.repositories import EvaluationRepository, GroupRepository, JobRepository, PhotoRepository
from skysort_api.services.serialization import group_to_item, photo_to_review_item


def list_groups(
    session,
    job_id: str,
    *,
    filter_query: str | None = None,
    sort: str = "created_at",
    page: int = 1,
    page_size: int = 100,
) -> dict[str, object]:
    photo_repo = PhotoRepository(session)
    eval_repo = EvaluationRepository(session)
    group_repo = GroupRepository(session)
    groups = JobRepository(session).list_groups(job_id)
    filters = parse_filters(filter_query)
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
        item = group_to_item(group, photos)
        if group_matches_filters(item, filters):
            results.append(item)
    results = sort_items(results, sort)
    total = len(results)
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "items": results[start:end],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": ceil(total / page_size) if total else 0,
        "sort": sort,
        "filters": filters,
    }


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


def list_photos(
    session,
    job_id: str,
    filters: dict[str, Any] | None = None,
    *,
    include_missing: bool = False,
    page: int | None = None,
    page_size: int | None = None,
) -> dict[str, object]:
    photo_repo = PhotoRepository(session)
    eval_repo = EvaluationRepository(session)
    items = []
    for photo in photo_repo.list_by_job(job_id, include_missing=include_missing):
        item = photo_to_review_item(photo, eval_repo.current_for_photo(photo.id, job_id), eval_repo.technical_for_photo(photo.id, job_id))
        if photo_matches_filters(item, filters or {}):
            items.append(item)
    total = len(items)
    if page is None or page_size is None:
        return {"items": items, "total": total}
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "items": items[start:end],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": ceil(total / page_size) if total else 0,
        "filters": filters or {},
    }


def parse_filters(filter_query: str | None) -> dict[str, Any]:
    if not filter_query:
        return {}
    try:
        parsed = json.loads(filter_query)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="filter must be a JSON object") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=422, detail="filter must be a JSON object")
    return parsed


def sort_items(items: list[dict[str, object]], sort: str) -> list[dict[str, object]]:
    descending = sort.startswith("-")
    key = sort[1:] if descending else sort
    allowed = {
        "created_at",
        "group_start_time",
        "group_size",
        "reviewed_count",
        "unreviewed_count",
        "technical_score_total",
        "semantic_score",
        "composition_score",
        "subject_state_score",
        "rarity_score",
    }
    if key not in allowed:
        raise HTTPException(status_code=422, detail=f"unsupported sort: {sort}")

    def sort_key(item: dict[str, object]) -> tuple[bool, object]:
        value = item.get(key)
        return (value is None, value if value is not None else "")

    return sorted(items, key=sort_key, reverse=descending)


def group_matches_filters(group: dict[str, object], filters: dict[str, Any]) -> bool:
    if not filters:
        return True
    group_filters = {key: value for key, value in filters.items() if key in {"stale", "stale_flag", "min_group_size", "max_group_size"}}
    if group_filters:
        stale = group_filters.get("stale", group_filters.get("stale_flag"))
        if stale is not None and group.get("stale_flag") is not bool(stale):
            return False
        min_group_size = group_filters.get("min_group_size")
        if min_group_size is not None and int(group["group_size"]) < int(min_group_size):
            return False
        max_group_size = group_filters.get("max_group_size")
        if max_group_size is not None and int(group["group_size"]) > int(max_group_size):
            return False
    photo_filters = {key: value for key, value in filters.items() if key not in group_filters}
    return not photo_filters or any(photo_matches_filters(photo, photo_filters) for photo in group.get("items", []))


def photo_matches_filters(item: dict[str, object], filters: dict[str, Any]) -> bool:
    for key, expected in filters.items():
        if key in {"reject", "rejected"}:
            if (item.get("selection_status") == "rejected") is not bool(expected):
                return False
            continue
        if key in {"pick", "pick_flag"}:
            if item.get("pick_flag") is not bool(expected):
                return False
            continue
        if key in {"best", "best_cut", "best_cut_flag"}:
            if item.get("best_cut_flag") is not bool(expected):
                return False
            continue
        if key in {"reviewed", "reviewed_flag"}:
            if item.get("reviewed_flag") is not bool(expected):
                return False
            continue
        if key in {"stale", "stale_flag"}:
            if item.get("stale_flag") is not bool(expected):
                return False
            continue
        if key == "rating":
            if not _matches_value(item.get("rating"), expected):
                return False
            continue
        if key in {"selection_status", "evaluation_status", "camera_model", "lens_model"}:
            if not _matches_value(item.get(key), expected):
                return False
            continue
        if key in {"q", "search", "text"}:
            if not _matches_text_query(item, expected):
                return False
            continue
        if key in {"date_from", "capture_time_from"}:
            if not _matches_capture_time(item, minimum=expected):
                return False
            continue
        if key in {"date_to", "capture_time_to"}:
            if not _matches_capture_time(item, maximum=expected):
                return False
            continue
        if key == "file_name":
            if str(expected).lower() not in str(item.get("file_name") or "").lower():
                return False
            continue
        if key == "delete_candidate":
            is_candidate = item.get("rating") == 1 or item.get("selection_status") == "rejected"
            if is_candidate is not bool(expected):
                return False
            continue
        if key == "is_missing":
            if item.get("is_missing") is not bool(expected):
                return False
            continue
        raise HTTPException(status_code=422, detail=f"unsupported filter: {key}")
    return True


def _matches_value(actual: object, expected: object) -> bool:
    if isinstance(expected, list):
        return actual in expected
    return actual == expected


def _matches_text_query(item: dict[str, object], expected: object) -> bool:
    query = str(expected or "").strip().lower()
    if not query:
        return True
    fields = ("file_name", "file_path", "camera_model", "lens_model", "ai_reason")
    return any(query in str(item.get(field) or "").lower() for field in fields)


def _matches_capture_time(
    item: dict[str, object],
    *,
    minimum: object | None = None,
    maximum: object | None = None,
) -> bool:
    actual = _parse_datetime(item.get("capture_time"))
    if actual is None:
        return False
    lower = _parse_datetime(minimum)
    upper = _parse_datetime(maximum)
    if lower is not None and actual < lower:
        return False
    return not (upper is not None and actual > upper)


def _parse_datetime(value: object | None) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=422, detail=f"invalid datetime filter: {text}") from None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
