import type {
  AIHealthStatus,
  AnalyzeRequest,
  BatchPhotoMutationRequest,
  ExportResultsRequest,
  ExportResultsResponse,
  FailureListResponse,
  GroupDetail,
  GroupListItem,
  ImportRequest,
  ImportResponse,
  JobProgress,
  MutationResult,
  PhotoListResponse,
  PhotoReviewItem,
  PhotoMutationRequest,
  ReanalyzeRequest,
  SettingsResponse,
  SettingsUpdateRequest,
  XmpExportRequest,
  XmpExportResponse,
} from "./types";

export class SkySortApiClient {
  constructor(private readonly baseUrl = "/api") {}

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
      ...init,
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `Request failed: ${response.status}`);
    }
    if (response.status === 204) {
      return undefined as T;
    }
    return response.json() as Promise<T>;
  }

  importFolder(payload: ImportRequest) {
    return this.request<ImportResponse>("/import", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  startAnalyze(jobId: string, payload: AnalyzeRequest = {}) {
    return this.request<{ accepted: boolean }>(`/jobs/${jobId}/analyze`, {
      method: "POST",
      body: JSON.stringify({
        reuse_cache: payload.reuse_cache ?? payload.force_reuse_cache ?? true,
      }),
    });
  }

  getProgress(jobId: string) {
    return this.request<Record<string, unknown>>(`/jobs/${jobId}/progress`).then((raw) => ({
      id: String(raw.id ?? jobId),
      job_id: String(raw.job_id ?? raw.id ?? jobId),
      status: raw.status as JobProgress["status"],
      total_files: Number(raw.total_files ?? 0),
      imported_files: Number(raw.imported_files ?? 0),
      grouped_files: Number(raw.grouped_files ?? 0),
      technically_scored_files: Number(raw.technically_scored_files ?? 0),
      semantically_scored_files: Number(raw.semantically_scored_files ?? 0),
      provisional_rated_files: Number(raw.provisional_rated_files ?? raw.provisional_files ?? 0),
      final_rated_files: Number(raw.final_rated_files ?? raw.finalized_files ?? 0),
      failed_files: Number(raw.failed_files ?? 0),
      current_stage: String(raw.current_stage ?? "queued"),
      errors: Array.isArray(raw.errors) ? (raw.errors as string[]) : raw.last_error ? [String(raw.last_error)] : [],
      started_at: (raw.started_at as string | null | undefined) ?? null,
      finished_at: (raw.finished_at as string | null | undefined) ?? null,
      last_error: (raw.last_error as string | null | undefined) ?? null,
    }));
  }

  getFailures(jobId: string) {
    return this.request<Record<string, unknown>>(`/jobs/${jobId}/failures`).then((raw) => ({
      job_id: jobId,
      items: Array.isArray(raw.items)
        ? (raw.items as Array<Record<string, unknown>>).map((item) => ({
            photo_id: (item.photo_id as string | null | undefined) ?? null,
            group_id: (item.group_id as string | null | undefined) ?? null,
            stage: String(item.stage ?? "unknown"),
            reason: String(item.reason ?? item.message ?? item.reason_code ?? "Unknown failure"),
            retryable: Boolean(item.retryable),
          }))
        : [],
    }));
  }

  getAIHealth() {
    return this.request<Record<string, unknown>>("/ai/health").then((raw) => ({
      reachable: Boolean(raw.reachable),
      localhost_only: Boolean(raw.localhost_only ?? true),
      available_models: Array.isArray(raw.available_models) ? (raw.available_models as string[]) : [],
      configured_model: String(raw.configured_model ?? ""),
      configured_model_exists: Boolean(raw.configured_model_exists ?? raw.model_available ?? false),
      model_available: Boolean(raw.model_available ?? raw.configured_model_exists ?? false),
      model_loadable: Boolean(raw.model_loadable ?? raw.model_loaded ?? false),
      model_loaded: Boolean(raw.model_loaded ?? raw.model_loadable ?? false),
      vision_capable: Boolean(raw.vision_capable ?? raw.vision_available ?? false),
      vision_available: Boolean(raw.vision_available ?? raw.vision_capable ?? false),
      structured_json_capable: Boolean(raw.structured_json_capable ?? raw.json_mode_available ?? false),
      json_mode_available: Boolean(raw.json_mode_available ?? raw.structured_json_capable ?? false),
      checked_at: String(raw.checked_at ?? new Date().toISOString()),
      error_detail: (raw.error_detail as string | null | undefined) ?? null,
    }));
  }

  listGroups(jobId: string) {
    return this.request<Record<string, unknown>>(`/groups?job_id=${encodeURIComponent(jobId)}`).then((raw) => {
      const items = Array.isArray(raw.items) ? (raw.items as Array<Record<string, unknown>>) : [];
      return items.map((item) => ({
        id: String(item.id),
        job_id: String(item.job_id ?? jobId),
        representative_photo_id: (item.representative_photo_id as string | null | undefined) ?? null,
        representative_thumb_url: (item.representative_thumb_url as string | null | undefined) ?? null,
        best_photo_id: (item.best_photo_id as string | null | undefined) ?? null,
        group_size: Number(item.group_size ?? 0),
        stale_flag: Boolean(item.stale_flag),
        stale_reason: (item.stale_reason as string | null | undefined) ?? null,
        reviewed_count: Number(item.reviewed_count ?? (item.reviewed ? Number(item.group_size ?? 0) : 0)),
        unreviewed_count: Number(item.unreviewed_count ?? Math.max(0, Number(item.group_size ?? 0) - Number(item.reviewed_count ?? 0))),
        technical_score_total: (item.technical_score_total as number | undefined) ?? null,
        semantic_score: (item.semantic_score as number | undefined) ?? null,
        best_rating: (item.best_rating as number | undefined) ?? null,
        items: Array.isArray(item.items)
          ? (item.items as Array<Record<string, unknown>>).map((photo) => ({
              photo_id: String(photo.photo_id ?? photo.id),
              id: String(photo.id ?? photo.photo_id),
              group_id: (photo.group_id as string | null | undefined) ?? String(item.id),
              file_name: String(photo.file_name ?? ""),
              file_path: String(photo.file_path ?? ""),
              capture_time: (photo.capture_time as string | null | undefined) ?? null,
              thumb_url: (photo.thumb_url as string | null | undefined) ?? null,
              preview_url: (photo.preview_url as string | null | undefined) ?? null,
              rating: (photo.rating as number | null | undefined) ?? null,
              provisional_rating: (photo.provisional_rating as number | null | undefined) ?? null,
              selection_status: (photo.selection_status as PhotoReviewItem["selection_status"]) ?? "normal",
              evaluation_status: (photo.evaluation_status as PhotoReviewItem["evaluation_status"]) ?? "provisional",
              ai_reason: (photo.ai_reason as string | null | undefined) ?? null,
              pick_flag: Boolean(photo.pick_flag),
              best_cut_flag: Boolean(photo.best_cut_flag),
              reviewed_flag: Boolean(photo.reviewed_flag),
              user_override_flag: Boolean(photo.user_override_flag),
              stale_flag: Boolean(photo.stale_flag),
              stale_reason: (photo.stale_reason as string | null | undefined) ?? null,
              technical_score_total: (photo.technical_score_total as number | undefined) ?? null,
              semantic_score: (photo.semantic_score as number | undefined) ?? null,
              composition_score: (photo.composition_score as number | undefined) ?? null,
              subject_state_score: (photo.subject_state_score as number | undefined) ?? null,
              rarity_score: (photo.rarity_score as number | undefined) ?? null,
            }))
          : undefined,
      }));
    });
  }

  getGroup(groupId: string) {
    return this.request<Record<string, unknown>>(`/groups/${groupId}`).then((raw) => {
      const photos = Array.isArray(raw.photos ?? raw.items) ? (raw.photos ?? raw.items) as Array<Record<string, unknown>> : [];
      return {
        id: String(raw.id ?? groupId),
        job_id: String(raw.job_id ?? ""),
        representative_photo_id: (raw.representative_photo_id as string | null | undefined) ?? null,
        best_photo_id: (raw.best_photo_id as string | null | undefined) ?? null,
        group_size: Number(raw.group_size ?? photos.length),
        stale_flag: Boolean(raw.stale_flag),
        stale_reason: (raw.stale_reason as string | null | undefined) ?? null,
        photos: photos.map((item) => ({
          photo_id: String(item.photo_id ?? item.id),
          id: String(item.id ?? item.photo_id),
          group_id: (item.group_id as string | null | undefined) ?? String(raw.id ?? groupId),
          file_name: String(item.file_name ?? ""),
          file_path: String(item.file_path ?? ""),
          capture_time: (item.capture_time as string | null | undefined) ?? null,
          thumb_url: (item.thumb_url as string | null | undefined) ?? null,
          preview_url: (item.preview_url as string | null | undefined) ?? null,
          rating: (item.rating as number | null | undefined) ?? null,
          provisional_rating: (item.provisional_rating as number | null | undefined) ?? null,
          selection_status: (item.selection_status as PhotoReviewItem["selection_status"]) ?? "normal",
          evaluation_status: (item.evaluation_status as PhotoReviewItem["evaluation_status"]) ?? "provisional",
          ai_reason: (item.ai_reason as string | null | undefined) ?? null,
          pick_flag: Boolean(item.pick_flag),
          best_cut_flag: Boolean(item.best_cut_flag),
          reviewed_flag: Boolean(item.reviewed_flag),
          user_override_flag: Boolean(item.user_override_flag),
          stale_flag: Boolean(item.stale_flag),
          stale_reason: (item.stale_reason as string | null | undefined) ?? null,
          technical_score_total:
            (item.technical_score_total as number | undefined) ??
            ((item.technical as Record<string, unknown> | undefined)?.technical_score_total as number | undefined) ??
            null,
          semantic_score: (item.semantic_score as number | undefined) ?? null,
          composition_score: (item.composition_score as number | undefined) ?? null,
          subject_state_score: (item.subject_state_score as number | undefined) ?? null,
          rarity_score: (item.rarity_score as number | undefined) ?? null,
        })),
      };
    });
  }

  listPhotos(jobId: string) {
    return this.request<Record<string, unknown>>(`/photos?job_id=${encodeURIComponent(jobId)}`).then((raw) => ({
      items: Array.isArray(raw.items)
        ? (raw.items as Array<Record<string, unknown>>).map((item) => ({
            photo_id: String(item.photo_id ?? item.id),
            id: String(item.id ?? item.photo_id),
            group_id: (item.group_id as string | null | undefined) ?? null,
            file_name: String(item.file_name ?? ""),
            file_path: String(item.file_path ?? ""),
            capture_time: (item.capture_time as string | null | undefined) ?? null,
            thumb_url: (item.thumb_url as string | null | undefined) ?? null,
            preview_url: (item.preview_url as string | null | undefined) ?? null,
            rating: (item.rating as number | null | undefined) ?? null,
            provisional_rating: (item.provisional_rating as number | null | undefined) ?? null,
            selection_status: (item.selection_status as PhotoReviewItem["selection_status"]) ?? "normal",
            evaluation_status: (item.evaluation_status as PhotoReviewItem["evaluation_status"]) ?? "provisional",
            ai_reason: (item.ai_reason as string | null | undefined) ?? null,
            pick_flag: Boolean(item.pick_flag),
            best_cut_flag: Boolean(item.best_cut_flag),
            reviewed_flag: Boolean(item.reviewed_flag),
            user_override_flag: Boolean(item.user_override_flag),
            stale_flag: Boolean(item.stale_flag),
            stale_reason: (item.stale_reason as string | null | undefined) ?? null,
            technical_score_total:
              (item.technical_score_total as number | undefined) ??
              ((item.technical as Record<string, unknown> | undefined)?.technical_score_total as number | undefined) ??
              null,
            semantic_score: (item.semantic_score as number | undefined) ?? null,
            composition_score: (item.composition_score as number | undefined) ?? null,
            subject_state_score: (item.subject_state_score as number | undefined) ?? null,
            rarity_score: (item.rarity_score as number | undefined) ?? null,
          }))
        : [],
      total: Number(raw.total ?? 0),
    }));
  }

  updatePhoto(photoId: string, payload: PhotoMutationRequest) {
    return this.request<MutationResult>(`/photos/${photoId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  }

  batchUpdatePhotos(payload: BatchPhotoMutationRequest) {
    return this.request<MutationResult>("/photos/batch", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  reanalyzePhoto(photoId: string, payload: ReanalyzeRequest) {
    return this.request<{ accepted: boolean }>(`/photos/${photoId}/reanalyze`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  reanalyzeGroup(groupId: string, payload: ReanalyzeRequest) {
    return this.request<{ accepted: boolean }>(`/groups/${groupId}/reanalyze`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  exportXmp(payload: XmpExportRequest) {
    return this.request<XmpExportResponse>("/export/xmp", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  exportResults(payload: ExportResultsRequest) {
    return this.request<Record<string, unknown>>("/export/results", {
      method: "POST",
      body: JSON.stringify(payload),
    }).then((raw) => ({
      export_path: String(raw.export_path ?? raw.output_path ?? ""),
      format: (raw.format as "csv" | "json" | undefined) ?? payload.format,
      item_count: Number(raw.item_count ?? raw.count ?? 0),
    }));
  }

  getSettings() {
    return this.request<Record<string, unknown>>("/settings").then((raw) => ({
      ai_base_url: String(raw.ai_base_url ?? ""),
      ai_model_name: String(raw.ai_model_name ?? ""),
      ai_concurrency: Number(raw.ai_concurrency ?? 1),
      image_processing_concurrency: Number(raw.image_processing_concurrency ?? raw.image_concurrency ?? 2),
      image_concurrency: Number(raw.image_concurrency ?? raw.image_processing_concurrency ?? 2),
      similarity_threshold: Number(raw.similarity_threshold ?? 0.8),
      time_proximity_seconds: Number(raw.time_proximity_seconds ?? 8),
      candidate_limit: Number(raw.candidate_limit ?? 6),
      thumbnail_size: Number(raw.thumbnail_size ?? 512),
      preview_size: Number(raw.preview_size ?? 1024),
      compare_preview_size: Number(raw.compare_preview_size ?? 512),
      preview_jpeg_quality: Number(raw.preview_jpeg_quality ?? raw.jpeg_quality ?? 90),
      jpeg_quality: Number(raw.jpeg_quality ?? raw.preview_jpeg_quality ?? 90),
      exiftool_path: String(raw.exiftool_path ?? "exiftool"),
      cache_dir: String(raw.cache_dir ?? ""),
    }));
  }

  updateSettings(payload: SettingsUpdateRequest) {
    return this.request<Record<string, unknown>>("/settings", {
      method: "PATCH",
      body: JSON.stringify(payload),
    }).then((raw) => ({
      ai_base_url: String(raw.ai_base_url ?? ""),
      ai_model_name: String(raw.ai_model_name ?? ""),
      ai_concurrency: Number(raw.ai_concurrency ?? 1),
      image_processing_concurrency: Number(raw.image_processing_concurrency ?? raw.image_concurrency ?? 2),
      image_concurrency: Number(raw.image_concurrency ?? raw.image_processing_concurrency ?? 2),
      similarity_threshold: Number(raw.similarity_threshold ?? 0.8),
      time_proximity_seconds: Number(raw.time_proximity_seconds ?? 8),
      candidate_limit: Number(raw.candidate_limit ?? 6),
      thumbnail_size: Number(raw.thumbnail_size ?? 512),
      preview_size: Number(raw.preview_size ?? 1024),
      compare_preview_size: Number(raw.compare_preview_size ?? 512),
      preview_jpeg_quality: Number(raw.preview_jpeg_quality ?? raw.jpeg_quality ?? 90),
      jpeg_quality: Number(raw.jpeg_quality ?? raw.preview_jpeg_quality ?? 90),
      exiftool_path: String(raw.exiftool_path ?? "exiftool"),
      cache_dir: String(raw.cache_dir ?? ""),
    }));
  }
}
