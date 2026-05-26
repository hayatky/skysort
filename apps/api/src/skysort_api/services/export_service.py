from __future__ import annotations

import csv
import io
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from skysort_api.infra.file_scan import build_source_signature, compute_fast_hash, file_metadata
from skysort_api.infra.image_tools import asset_paths_for_signature
from skysort_api.infra.settings import get_settings
from skysort_api.infra.xmp import (
    build_desired_tags,
    build_xmp_summary,
    can_write,
    detect_conflict,
    exiftool_available,
    write_tags,
)
from skysort_api.services.query_service import list_photos
from skysort_api.services.repositories import PhotoRepository


def export_results(session, payload) -> dict[str, object]:
    photos = list_photos(session, payload.job_id, filters=payload.filters)["items"]
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


def export_xmp(session, payload) -> dict[str, object]:
    photos = list_photos(session, payload.job_id, filters=payload.filters)["items"]
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

    if conflicts and payload.conflict_policy == "fail" and not payload.dry_run:
        return {
            "target_count": len(target_items),
            "written_count": 0,
            "skipped_count": 0,
            "failed_count": len(conflicts),
            "written_items": [],
            "skipped_items": [],
            "failed_items": conflicts,
            "conflicts": conflicts,
        }

    available = exiftool_available()
    if payload.dry_run or not available:
        if not available:
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

    photo_repo = PhotoRepository(session)
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
        bucket.append(
            {
                "photo_id": item["photo_id"],
                "file_path": item["file_path"],
                "summary": build_xmp_summary(item["file_path"], item["rating"], item["selection_status"], item["pick_flag"], item["best_cut_flag"], item["reviewed_flag"]),
                "result_code": message,
            }
        )
        if success:
            _sync_photo_source_state_after_write(photo_repo, payload.job_id, item["photo_id"])
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


def _sync_photo_source_state_after_write(photo_repo: PhotoRepository, job_id: str, photo_id: str) -> None:
    photo = photo_repo.get(photo_id)
    if photo is None or photo.job_id != job_id:
        return

    target = Path(photo.file_path)
    if target.suffix.lower() not in {".jpg", ".jpeg"}:
        return

    previous_thumb = Path(photo.thumb_path) if photo.thumb_path else None
    previous_preview = Path(photo.preview_path) if photo.preview_path else None
    file_size, file_mtime = file_metadata(target)
    file_hash = compute_fast_hash(target)
    new_signature = build_source_signature(target, file_hash, file_size, file_mtime)
    new_thumb, new_preview = asset_paths_for_signature(new_signature)

    _copy_cached_asset(previous_thumb, new_thumb)
    _copy_cached_asset(previous_preview, new_preview)

    photo.file_hash = file_hash
    photo.file_size = file_size
    photo.file_mtime = file_mtime
    photo.thumb_path = str(new_thumb)
    photo.preview_path = str(new_preview)
    photo.updated_at = datetime.now(timezone.utc)


def _copy_cached_asset(source: Path | None, destination: Path) -> None:
    if source is None or not source.exists():
        return
    if source == destination:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return
    shutil.copy2(source, destination)
