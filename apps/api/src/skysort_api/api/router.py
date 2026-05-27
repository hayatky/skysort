from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from skysort_api.services.export_service import export_results as export_results_service
from skysort_api.services.export_service import export_xmp as export_xmp_service
from skysort_api.services.group_edit_service import merge_group as merge_group_service
from skysort_api.services.group_edit_service import split_group as split_group_service
from skysort_api.services.import_service import create_import_job
from skysort_api.services.job_service import get_ai_health as get_ai_health_service
from skysort_api.services.job_service import get_failures as get_failures_service
from skysort_api.services.job_service import get_progress as get_progress_service
from skysort_api.services.job_service import get_project as get_project_service
from skysort_api.services.job_service import list_project_jobs as list_project_jobs_service
from skysort_api.services.job_service import list_projects as list_projects_service
from skysort_api.services.job_service import request_cancel as request_cancel_service
from skysort_api.services.job_service import retry_job as retry_job_service
from skysort_api.services.job_service import retry_failure as retry_failure_service
from skysort_api.services.job_service import start_project_analysis as start_project_analysis_service
from skysort_api.services.job_service import start_analysis
from skysort_api.services.query_service import get_group as get_group_service
from skysort_api.services.query_service import list_groups as list_groups_service
from skysort_api.services.query_service import list_photos as list_photos_service
from skysort_api.services.query_service import parse_filters as parse_filter_query_service
from skysort_api.services.repositories import PhotoRepository
from skysort_api.services.review_service import batch_mutate_photos
from skysort_api.services.review_service import mutate_photo as mutate_photo_service
from skysort_api.services.review_service import reanalyze_group as reanalyze_group_service
from skysort_api.services.review_service import reanalyze_photo as reanalyze_photo_service
from skysort_api.services.settings_service import get_settings_response, update_settings

from .deps import get_session
from .schemas import (
    AIHealthResponse,
    AnalyzeRequest,
    BatchMutationRequest,
    ExportResultsRequest,
    GroupMergeRequest,
    GroupSplitRequest,
    ImportRequest,
    ImportResponse,
    JobProgressResponse,
    ProjectListResponse,
    ProjectResponse,
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
        project_id, job_id, count = create_import_job(session, payload.root_path, payload.recursive, payload.file_types, payload.reuse_cache)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ImportResponse(project_id=project_id, job_id=job_id, registered_count=count)


@router.get("/projects", response_model=ProjectListResponse)
def list_projects(limit: int = Query(default=50, ge=1, le=200), session: Session = Depends(get_session)) -> dict[str, object]:
    return list_projects_service(session, limit=limit)


@router.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    return get_project_service(session, project_id)


@router.get("/projects/{project_id}/jobs")
def list_project_jobs(project_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    return list_project_jobs_service(session, project_id)


@router.post("/projects/{project_id}/analyze")
def analyze_project(project_id: str, payload: AnalyzeRequest, session: Session = Depends(get_session)) -> dict[str, object]:
    return start_project_analysis_service(session, project_id, reuse_cache=payload.reuse_cache)


@router.post("/jobs/{job_id}/analyze")
def analyze_job(job_id: str, _: AnalyzeRequest, session: Session = Depends(get_session)) -> dict[str, bool]:
    return start_analysis(session, job_id)


@router.get("/jobs/{job_id}/progress", response_model=JobProgressResponse)
def get_progress(job_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    return get_progress_service(session, job_id)


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    return request_cancel_service(session, job_id)


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    return retry_job_service(session, job_id)


@router.get("/jobs/{job_id}/failures")
def get_failures(job_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    return get_failures_service(session, job_id)


@router.post("/jobs/{job_id}/failures/{failure_id}/retry")
def retry_failure(job_id: str, failure_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    return retry_failure_service(session, job_id, failure_id)


@router.get("/ai/health", response_model=AIHealthResponse)
def get_ai_health() -> AIHealthResponse:
    result = get_ai_health_service()
    payload = asdict(result) if is_dataclass(result) else vars(result)
    return AIHealthResponse(**payload)


@router.get("/groups")
def list_groups(
    job_id: str,
    filter_query: Annotated[str | None, Query(alias="filter")] = None,
    sort: str = "created_at",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    return list_groups_service(session, job_id, filter_query=filter_query, sort=sort, page=page, page_size=page_size)


@router.get("/groups/{group_id}")
def get_group(group_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    return get_group_service(session, group_id)


@router.post("/groups/{group_id}/merge")
def merge_group(group_id: str, payload: GroupMergeRequest, session: Session = Depends(get_session)) -> dict[str, object]:
    return merge_group_service(session, group_id, payload)


@router.post("/groups/{group_id}/split")
def split_group(group_id: str, payload: GroupSplitRequest, session: Session = Depends(get_session)) -> dict[str, object]:
    return split_group_service(session, group_id, payload)


@router.get("/photos")
def list_photos(
    job_id: str,
    include_missing: bool = False,
    filter_query: Annotated[str | None, Query(alias="filter")] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    return list_photos_service(
        session,
        job_id,
        filters=parse_filter_query_service(filter_query),
        include_missing=include_missing,
        page=page,
        page_size=page_size,
    )


@router.patch("/photos/{photo_id}", response_model=MutationResult)
def patch_photo(photo_id: str, payload: PhotoMutationRequest, session: Session = Depends(get_session)) -> MutationResult:
    return mutate_photo_service(session, photo_id, payload)


@router.post("/photos/batch", response_model=MutationResult)
def batch_patch_photos(payload: BatchMutationRequest, session: Session = Depends(get_session)) -> MutationResult:
    return batch_mutate_photos(session, payload)


@router.post("/photos/{photo_id}/reanalyze")
def reanalyze_photo(photo_id: str, payload: ReanalyzeRequest, session: Session = Depends(get_session)) -> dict[str, bool]:
    return reanalyze_photo_service(session, photo_id, payload)


@router.post("/groups/{group_id}/reanalyze")
def reanalyze_group(group_id: str, payload: ReanalyzeRequest, session: Session = Depends(get_session)) -> dict[str, bool]:
    return reanalyze_group_service(session, group_id, payload)


@router.post("/export/results")
def export_results(payload: ExportResultsRequest, session: Session = Depends(get_session)) -> dict[str, object]:
    return export_results_service(session, payload)


@router.post("/export/xmp")
def export_xmp(payload: XmpExportRequest, session: Session = Depends(get_session)) -> dict[str, object]:
    return export_xmp_service(session, payload)


@router.get("/settings", response_model=SettingsResponse)
def get_settings_route() -> SettingsResponse:
    return get_settings_response()


@router.patch("/settings", response_model=SettingsResponse)
def patch_settings_route(payload: SettingsUpdateRequest) -> SettingsResponse:
    return update_settings(payload)


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
