from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from skysort_api.services.export_service import export_results as export_results_service
from skysort_api.services.export_service import export_xmp as export_xmp_service
from skysort_api.services.import_service import create_import_job
from skysort_api.services.job_service import get_ai_health as get_ai_health_service
from skysort_api.services.job_service import get_failures as get_failures_service
from skysort_api.services.job_service import get_progress as get_progress_service
from skysort_api.services.job_service import start_analysis
from skysort_api.services.query_service import get_group as get_group_service
from skysort_api.services.query_service import list_groups as list_groups_service
from skysort_api.services.query_service import list_photos as list_photos_service
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
        job_id, count = create_import_job(session, payload.root_path, payload.recursive, payload.file_types, payload.reuse_cache)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ImportResponse(job_id=job_id, registered_count=count)


@router.post("/jobs/{job_id}/analyze")
def analyze_job(job_id: str, _: AnalyzeRequest, session: Session = Depends(get_session)) -> dict[str, bool]:
    return start_analysis(session, job_id)


@router.get("/jobs/{job_id}/progress", response_model=JobProgressResponse)
def get_progress(job_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    return get_progress_service(session, job_id)


@router.get("/jobs/{job_id}/failures")
def get_failures(job_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    return get_failures_service(session, job_id)


@router.get("/ai/health", response_model=AIHealthResponse)
def get_ai_health() -> AIHealthResponse:
    return AIHealthResponse(**get_ai_health_service().__dict__)


@router.get("/groups")
def list_groups(job_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    return list_groups_service(session, job_id)


@router.get("/groups/{group_id}")
def get_group(group_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    return get_group_service(session, group_id)


@router.get("/photos")
def list_photos(job_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    return list_photos_service(session, job_id)


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
