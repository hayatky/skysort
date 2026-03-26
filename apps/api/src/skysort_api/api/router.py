from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from skysort_api.infra.ai_client import VisionLanguageModelClient
from skysort_api.infra.file_scan import normalize_root_path
from skysort_api.infra.models import PhotoEvaluation, RatingHistory
from skysort_api.infra.settings import UI_MUTABLE_FIELDS, get_settings, persist_settings
from skysort_api.infra.xmp import (
    build_desired_tags,
    build_xmp_summary,
    can_write,
    detect_conflict,
    exiftool_available,
    write_tags,
)
from skysort_api.services.import_service import create_import_job
from skysort_api.services.repositories import EvaluationRepository, FailureRepository, GroupRepository, JobRepository, PhotoRepository
from skysort_api.services.serialization import group_to_item, job_to_progress, photo_to_review_item
from skysort_api.workers.job_runner import job_runner

from .deps import get_session
from .schemas import (
    AIHealthResponse,
    AnalyzeRequest,
    BatchMutationRequest,
    ExportResultsRequest,
    ImportRequest,
    ImportResponse,
    JobProgressResponse,
    MutationResult,
    PhotoMutationRequest,
    ReanalyzeRequest,
    SettingsResponse,
    SettingsUpdateRequest,
    XmpExportRequest,
)

router = APIRouter(prefix="/api")


@router.post("/import", response_model=ImportResponse)
def import_folder(payload: ImportRequest, session: Session = Depends(get_session)) -> ImportResponse:
    try:
        normalize_root_path(payload.root_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    job_id, count = create_import_job(session, payload.root_path, payload.recursive, payload.file_types, payload.reuse_cache)
    return ImportResponse(job_id=job_id, registered_count=count)


@router.post("/jobs/{job_id}/analyze")
def analyze_job(job_id: str, _: AnalyzeRequest, session: Session = Depends(get_session)) -> dict[str, bool]:
    job = JobRepository(session).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    health = VisionLanguageModelClient().health_check()
    if not (health.reachable and health.configured_model_exists and health.model_loadable and health.vision_capable and health.structured_json_capable):
        raise HTTPException(status_code=400, detail=health.error_detail or "AI server health check failed")
    job_runner.start(job_id)
    return {"accepted": True}


@router.get("/jobs/{job_id}/progress", response_model=JobProgressResponse)
def get_progress(job_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    job = JobRepository(session).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job_to_progress(job)


@router.get("/jobs/{job_id}/failures")
def get_failures(job_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    job = JobRepository(session).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    items = FailureRepository(session).list_for_job(job_id)
    return {
        "job_id": job_id,
        "items": [
            {
                "stage": item.stage,
                "reason": item.message,
                "retryable": item.retryable,
                "photo_id": item.photo_id,
                "group_id": item.group_id,
            }
            for item in items
        ],
    }


@router.get("/ai/health", response_model=AIHealthResponse)
def get_ai_health() -> AIHealthResponse:
    return AIHealthResponse(**VisionLanguageModelClient().health_check().__dict__)


@router.get("/groups")
def list_groups(job_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
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


@router.get("/groups/{group_id}")
def get_group(group_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
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


@router.get("/photos")
def list_photos(job_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    photo_repo = PhotoRepository(session)
    eval_repo = EvaluationRepository(session)
    items = []
    for photo in photo_repo.list_by_job(job_id):
        items.append(photo_to_review_item(photo, eval_repo.current_for_photo(photo.id, job_id), eval_repo.technical_for_photo(photo.id, job_id)))
    return {"items": items, "total": len(items)}


@router.patch("/photos/{photo_id}", response_model=MutationResult)
def patch_photo(photo_id: str, payload: PhotoMutationRequest, session: Session = Depends(get_session)) -> MutationResult:
    repo = EvaluationRepository(session)
    current = repo.current_for_photo(photo_id, payload.job_id)
    if current is None:
        raise HTTPException(status_code=404, detail="photo evaluation not found")
    rating = current.rating
    selection_status = current.selection_status
    if payload.selection_status is not None:
        selection_status = payload.selection_status
        if payload.selection_status == "rejected":
            rating = None
    if payload.rating is not None:
        rating = payload.rating
        if payload.selection_status is None:
            selection_status = "normal"
    pick_flag = current.pick_flag if payload.pick_flag is None else payload.pick_flag
    best_cut_flag = current.best_cut_flag if payload.best_cut_flag is None else payload.best_cut_flag
    reviewed_flag = current.reviewed_flag if payload.reviewed_flag is None else payload.reviewed_flag

    if best_cut_flag and current.group_id:
        for evaluation in repo.current_for_group(current.group_id, payload.job_id):
            if evaluation.photo_id == photo_id or not evaluation.best_cut_flag:
                continue
            repo.add_evaluation(_clone_evaluation(evaluation, best_cut_flag=False))

    repo.add_evaluation(
        _clone_evaluation(
            current,
            rating=rating,
            selection_status=selection_status,
            pick_flag=pick_flag,
            best_cut_flag=best_cut_flag,
            reviewed_flag=reviewed_flag,
            user_override_flag=True,
            stale_flag=False,
            stale_reason=None,
        )
    )
    repo.record_history(
        RatingHistory(
            id=f"hist_{uuid.uuid4().hex[:10]}",
            photo_id=photo_id,
            job_id=payload.job_id,
            old_rating=current.rating,
            new_rating=rating,
            old_selection_status=current.selection_status,
            new_selection_status=selection_status,
            changed_by_user=True,
            changed_at=datetime.now(timezone.utc),
            reason="manual_override",
        )
    )
    return MutationResult(updated_count=1, failed_count=0)


@router.post("/photos/batch", response_model=MutationResult)
def batch_patch_photos(payload: BatchMutationRequest, session: Session = Depends(get_session)) -> MutationResult:
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
        patch_photo(photo_id, request, session)
        updated += 1
    return MutationResult(updated_count=updated, failed_count=0)


@router.post("/photos/{photo_id}/reanalyze")
def reanalyze_photo(photo_id: str, payload: ReanalyzeRequest, session: Session = Depends(get_session)) -> dict[str, bool]:
    evaluation = EvaluationRepository(session).current_for_photo(photo_id, payload.job_id)
    if evaluation is None:
        raise HTTPException(status_code=404, detail="photo evaluation not found")
    evaluation.stale_flag = True
    evaluation.stale_reason = payload.scope
    job_runner.start_photo_reanalysis(payload.job_id, [photo_id], payload.scope)
    return {"accepted": True}


@router.post("/groups/{group_id}/reanalyze")
def reanalyze_group(group_id: str, payload: ReanalyzeRequest, session: Session = Depends(get_session)) -> dict[str, bool]:
    group_repo = GroupRepository(session)
    group = group_repo.get(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="group not found")
    group.stale_flag = True
    group.stale_reason = payload.scope
    photo_ids = [member.photo_id for member in group_repo.list_members(group_id)]
    job_runner.start_photo_reanalysis(payload.job_id, photo_ids, payload.scope)
    return {"accepted": True}


@router.post("/export/results")
def export_results(payload: ExportResultsRequest, session: Session = Depends(get_session)) -> dict[str, object]:
    photos = list_photos(payload.job_id, session)["items"]
    settings = get_settings()
    export_path = settings.tmp_dir / f"{payload.job_id}_results.{payload.format}"
    if payload.format == "json":
        export_path.write_text(json.dumps(photos, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(photos[0].keys()) if photos else ["photo_id"])
        writer.writeheader()
        for item in photos:
            writer.writerow(item)
        export_path.write_text(buffer.getvalue(), encoding="utf-8")
    return {"export_path": str(export_path), "format": payload.format, "item_count": len(photos)}


@router.post("/export/xmp")
def export_xmp(payload: XmpExportRequest, session: Session = Depends(get_session)) -> dict[str, object]:
    photos = list_photos(payload.job_id, session)["items"]
    target_items = [item for item in photos if not payload.photo_ids or item["photo_id"] in payload.photo_ids]
    write_candidates = []
    blocked_items = []
    conflicts = []

    for item in target_items:
        allowed, reason = can_write(item["file_path"])
        summary = build_xmp_summary(
            item["file_path"],
            item["rating"],
            item["selection_status"],
            item["pick_flag"],
            item["best_cut_flag"],
            item["reviewed_flag"],
        )
        enriched = {
            "photo_id": item["photo_id"],
            "file_path": item["file_path"],
            "summary": summary,
            "result_code": reason,
        }
        if not allowed:
            blocked_items.append(enriched)
            continue
        desired_tags = build_desired_tags(
            item["rating"],
            item["selection_status"],
            item["pick_flag"],
            item["best_cut_flag"],
            item["reviewed_flag"],
        )
        conflict = detect_conflict(item["file_path"], desired_tags)
        if conflict is not None:
            enriched["summary"] = json.dumps(conflict["diff"], ensure_ascii=False)
            conflicts.append(enriched)
            if payload.conflict_policy in {"skip", "fail"}:
                continue
        write_candidates.append(enriched)

    if payload.dry_run or not exiftool_available():
        if not exiftool_available():
            blocked_items.append({"photo_id": "", "file_path": "", "summary": "ExifTool is not available", "result_code": "exiftool_not_available"})
        return {
            "target_count": len(target_items),
            "writable_count": len(write_candidates),
            "blocked_count": len(blocked_items),
            "conflict_count": len(conflicts),
            "write_candidates": write_candidates,
            "blocked_items": blocked_items,
            "conflicts": conflicts,
        }

    written_items = []
    failed_items = []
    for item in target_items:
        if not any(candidate["photo_id"] == item["photo_id"] for candidate in write_candidates):
            continue
        success, message = write_tags(
            item["file_path"],
            item["rating"],
            item["selection_status"],
            item["pick_flag"],
            item["best_cut_flag"],
            item["reviewed_flag"],
        )
        bucket = written_items if success else failed_items
        bucket.append({"photo_id": item["photo_id"], "file_path": item["file_path"], "summary": build_xmp_summary(item["file_path"], item["rating"], item["selection_status"], item["pick_flag"], item["best_cut_flag"], item["reviewed_flag"]), "result_code": message})
    return {
        "target_count": len(target_items),
        "written_count": len(written_items),
        "skipped_count": len(conflicts) if payload.conflict_policy == "skip" else 0,
        "failed_count": len(failed_items),
        "written_items": written_items,
        "skipped_items": conflicts if payload.conflict_policy == "skip" else [],
        "failed_items": failed_items,
        "conflicts": conflicts,
    }


@router.get("/settings", response_model=SettingsResponse)
def get_settings_route() -> SettingsResponse:
    settings = get_settings()
    return SettingsResponse(
        ai_base_url=settings.ai_base_url,
        ai_model_name=settings.ai_model_name,
        ai_concurrency=settings.ai_concurrency,
        image_processing_concurrency=settings.image_processing_concurrency,
        similarity_threshold=settings.similarity_threshold,
        time_proximity_seconds=settings.time_proximity_seconds,
        candidate_limit=settings.candidate_limit,
        thumbnail_size=settings.thumbnail_size,
        preview_size=settings.preview_size,
        compare_preview_size=settings.compare_preview_size,
        preview_jpeg_quality=settings.preview_jpeg_quality,
        highlight_threshold=settings.highlight_threshold,
        shadow_threshold=settings.shadow_threshold,
        exiftool_path=settings.exiftool_path,
        cache_dir=str(settings.cache_dir),
        weights=SettingsResponse.WeightSettingsPayload(**settings.weights.model_dump()),
        rating_thresholds=SettingsResponse.RatingThresholdsPayload(**settings.rating_thresholds.model_dump()),
    )


@router.patch("/settings", response_model=SettingsResponse)
def patch_settings_route(payload: SettingsUpdateRequest) -> SettingsResponse:
    updates = {}
    for key, value in payload.model_dump(exclude_none=True).items():
        if key not in UI_MUTABLE_FIELDS:
            continue
        updates[key] = value
    if updates:
        persist_settings(updates)
    return get_settings_route()


@router.get("/media/{kind}/{photo_id}")
def get_media(kind: str, photo_id: str, session: Session = Depends(get_session)) -> FileResponse:
    photo = PhotoRepository(session).get(photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="photo not found")
    asset_path = photo.thumb_path if kind == "thumbs" else photo.preview_path
    if not asset_path:
        raise HTTPException(status_code=404, detail="asset not found")
    path = Path(asset_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="asset not found")
    return FileResponse(path, headers={"Cache-Control": "public, max-age=3600, must-revalidate"})


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
