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
    results = [
        item
        for item in _group_items_with_photos(photo_repo, eval_repo, group_repo, groups)
        if group_matches_filters(item, filters)
    ]
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
        "review_summary": _group_review_summary(results),
    }


def _group_items_with_photos(
    photo_repo: PhotoRepository,
    eval_repo: EvaluationRepository,
    group_repo: GroupRepository,
    groups,
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    previous_item: dict[str, object] | None = None
    for group in groups:
        item = _group_item_with_photos(photo_repo, eval_repo, group_repo, group)
        item["previous_gap_seconds"] = _previous_gap_seconds(previous_item, item)
        items.append(item)
        previous_item = item
    return items


def _group_item_with_photos(
    photo_repo: PhotoRepository,
    eval_repo: EvaluationRepository,
    group_repo: GroupRepository,
    group,
) -> dict[str, object]:
    photos = []
    for member in group_repo.list_members(group.id):
        photo = photo_repo.get(member.photo_id)
        evaluation = eval_repo.current_for_photo(member.photo_id, group.job_id)
        technical = eval_repo.technical_for_photo(member.photo_id, group.job_id)
        if photo and not photo.is_missing:
            photos.append(photo_to_review_item(photo, evaluation, technical, group.id))
    return group_to_item(group, photos)


def _previous_gap_seconds(previous: dict[str, object] | None, current: dict[str, object]) -> float | None:
    if previous is None:
        return None
    previous_end = _parse_datetime(previous.get("group_end_time"))
    current_start = _parse_datetime(current.get("group_start_time"))
    if previous_end is None or current_start is None:
        return None
    return max(0.0, (current_start - previous_end).total_seconds())


def _group_review_summary(groups: list[dict[str, object]]) -> dict[str, int]:
    reviewed_groups = 0
    accepted_ai_groups = 0
    manually_changed_groups = 0
    unresolved_groups = 0
    for group in groups:
        photos = group.get("items", [])
        photo_items = photos if isinstance(photos, list) else []
        if group.get("review_queue") == "reviewed":
            reviewed_groups += 1
        if photo_items and all(photo.get("reviewed_flag") for photo in photo_items if isinstance(photo, dict)):
            accepted_ai_groups += 1
        if any(isinstance(photo, dict) and photo.get("user_override_flag") for photo in photo_items):
            manually_changed_groups += 1
        if group.get("review_queue") != "reviewed":
            unresolved_groups += 1
    return {
        "total_groups": len(groups),
        "reviewed_groups": reviewed_groups,
        "accepted_ai_groups": accepted_ai_groups,
        "manually_changed_groups": manually_changed_groups,
        "unresolved_groups": unresolved_groups,
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
        photos.append(photo_to_review_item(photo, eval_repo.current_for_photo(photo.id, group.job_id), eval_repo.technical_for_photo(photo.id, group.job_id), group.id))

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
    group_repo = GroupRepository(session)
    photo_group_ids = _photo_group_ids(group_repo, job_id)
    items = []
    for photo in photo_repo.list_by_job(job_id, include_missing=include_missing):
        item = photo_to_review_item(photo, eval_repo.current_for_photo(photo.id, job_id), eval_repo.technical_for_photo(photo.id, job_id), photo_group_ids.get(photo.id))
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


def _photo_group_ids(group_repo: GroupRepository, job_id: str) -> dict[str, str]:
    photo_group_ids: dict[str, str] = {}
    for group in group_repo.list_by_job(job_id):
        for member in group_repo.list_members(group.id):
            photo_group_ids[member.photo_id] = group.id
    return photo_group_ids


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
        "previous_gap_seconds",
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
    group_filter_keys = {
        "stale",
        "stale_flag",
        "merge_suggested",
        "min_group_size",
        "max_group_size",
        "singleton",
        "best_missing",
        "review_queue",
        "ai_confidence_min",
        "ai_confidence_max",
        "previous_gap_seconds_min",
        "previous_gap_seconds_max",
        "adjacent_gap_min",
        "adjacent_gap_max",
    }
    group_filters = {key: value for key, value in filters.items() if key in group_filter_keys}
    if group_filters:
        stale = group_filters.get("stale", group_filters.get("stale_flag"))
        if stale is not None and group.get("stale_flag") is not bool(stale):
            return False
        merge_suggested = group_filters.get("merge_suggested")
        if merge_suggested is not None and group.get("merge_suggested") is not bool(merge_suggested):
            return False
        min_group_size = group_filters.get("min_group_size")
        if min_group_size is not None and int(group["group_size"]) < int(min_group_size):
            return False
        max_group_size = group_filters.get("max_group_size")
        if max_group_size is not None and int(group["group_size"]) > int(max_group_size):
            return False
        singleton = group_filters.get("singleton")
        if singleton is not None and (int(group["group_size"]) == 1) is not bool(singleton):
            return False
        best_missing = group_filters.get("best_missing")
        if best_missing is not None and (group.get("best_photo_id") is None) is not bool(best_missing):
            return False
        review_queue = group_filters.get("review_queue")
        if review_queue is not None and not _matches_value(group.get("review_queue"), review_queue):
            return False
        confidence_min = group_filters.get("ai_confidence_min")
        if confidence_min is not None:
            confidence = group.get("ai_confidence_score")
            expected_number = _as_float(confidence_min)
            if expected_number is None or not isinstance(confidence, int | float) or confidence < expected_number:
                return False
        confidence_max = group_filters.get("ai_confidence_max")
        if confidence_max is not None:
            confidence = group.get("ai_confidence_score")
            expected_number = _as_float(confidence_max)
            if expected_number is None or not isinstance(confidence, int | float) or confidence > expected_number:
                return False
        gap_min = group_filters.get("previous_gap_seconds_min", group_filters.get("adjacent_gap_min"))
        if gap_min is not None:
            gap = group.get("previous_gap_seconds")
            expected_number = _as_float(gap_min)
            if expected_number is None or not isinstance(gap, int | float) or gap < expected_number:
                return False
        gap_max = group_filters.get("previous_gap_seconds_max", group_filters.get("adjacent_gap_max"))
        if gap_max is not None:
            gap = group.get("previous_gap_seconds")
            expected_number = _as_float(gap_max)
            if expected_number is None or not isinstance(gap, int | float) or gap > expected_number:
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
        if key in {"user_override", "user_override_only", "user_override_flag"}:
            if item.get("user_override_flag") is not bool(expected):
                return False
            continue
        if key in {"stale", "stale_flag"}:
            if item.get("stale_flag") is not bool(expected):
                return False
            continue
        if key in {"ai_complete", "ai_completed"}:
            is_complete = (
                item.get("evaluation_status") == "final"
                and item.get("semantic_score") is not None
                and item.get("stale_flag") is not True
            )
            if is_complete is not bool(expected):
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
        if key == "keep_recommendation":
            if item.get("pick_flag") is not bool(expected):
                return False
            continue
        if key == "reject_recommendation":
            is_recommended = item.get("selection_status") == "rejected" or item.get("rating") == 1
            if is_recommended is not bool(expected):
                return False
            continue
        if key == "review_queue":
            if not _matches_value(item.get("review_queue"), expected):
                return False
            continue
        if key == "problem_tag":
            tags = item.get("problem_tags")
            if not isinstance(tags, list) or str(expected) not in tags:
                return False
            continue
        if key == "ai_confidence_min":
            confidence = item.get("ai_confidence_score")
            expected_number = _as_float(expected)
            if expected_number is None or not isinstance(confidence, int | float) or confidence < expected_number:
                return False
            continue
        if key == "ai_confidence_max":
            confidence = item.get("ai_confidence_score")
            expected_number = _as_float(expected)
            if expected_number is None or not isinstance(confidence, int | float) or confidence > expected_number:
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


def _as_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
