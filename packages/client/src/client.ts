import type {
  AIHealthStatus,
  AnalyzeRequest,
  BatchPhotoMutationRequest,
  ExportResultsRequest,
  ExportResultsResponse,
  FailureListResponse,
  GroupDetail,
  GroupListItem,
  GroupMergeRequest,
  GroupListResponse,
  GroupSplitRequest,
  ImportRequest,
  ImportResponse,
  JobProgress,
  JobSummary,
  MutationResult,
  PhotoListResponse,
  PhotoReviewItem,
  PhotoMutationRequest,
  ProjectItem,
  ProjectJobsResponse,
  ProjectListResponse,
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

  listProjects(limit = 50) {
    return this.request<Record<string, unknown>>(`/projects?limit=${encodeURIComponent(String(limit))}`).then((raw): ProjectListResponse => {
      const items = Array.isArray(raw.items) ? (raw.items as Array<Record<string, unknown>>) : [];
      return { items: items.map((item) => this.normalizeProject(item)), total: Number(raw.total ?? items.length) };
    });
  }

  getProject(projectId: string) {
    return this.request<Record<string, unknown>>(`/projects/${projectId}`).then((raw) => this.normalizeProject(raw));
  }

  listProjectJobs(projectId: string) {
    return this.request<Record<string, unknown>>(`/projects/${projectId}/jobs`).then((raw): ProjectJobsResponse => {
      const items = Array.isArray(raw.items) ? (raw.items as Array<Record<string, unknown>>) : [];
      return { project_id: String(raw.project_id ?? projectId), items: items.map((item) => this.normalizeJobSummary(item)), total: Number(raw.total ?? items.length) };
    });
  }

  startProjectAnalyze(projectId: string, payload: AnalyzeRequest = {}) {
    return this.request<{ accepted: boolean; project_id: string; job_id: string; registered_count: number }>(`/projects/${projectId}/analyze`, {
      method: "POST",
      body: JSON.stringify({
        reuse_cache: payload.reuse_cache ?? payload.force_reuse_cache ?? true,
      }),
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
      project_id: (raw.project_id as string | null | undefined) ?? null,
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
      active_stage_label: String(raw.active_stage_label ?? raw.current_stage ?? "queued"),
      stage_done: Number(raw.stage_done ?? 0),
      stage_total: Number(raw.stage_total ?? raw.total_files ?? 0),
      percent: Number(raw.percent ?? 0),
      cancel_requested: Boolean(raw.cancel_requested),
      ai_photo_done: Number(raw.ai_photo_done ?? raw.semantically_scored_files ?? 0),
      ai_photo_total: Number(raw.ai_photo_total ?? raw.total_files ?? 0),
      ai_group_done: Number(raw.ai_group_done ?? 0),
      ai_group_total: Number(raw.ai_group_total ?? 0),
      errors: Array.isArray(raw.errors) ? (raw.errors as string[]) : raw.last_error ? [String(raw.last_error)] : [],
      started_at: (raw.started_at as string | null | undefined) ?? null,
      finished_at: (raw.finished_at as string | null | undefined) ?? null,
      canceled_at: (raw.canceled_at as string | null | undefined) ?? null,
      updated_at: (raw.updated_at as string | null | undefined) ?? null,
      last_error: (raw.last_error as string | null | undefined) ?? null,
    }));
  }

  cancelJob(jobId: string) {
    return this.request<{ accepted: boolean; job_id: string; status: JobProgress["status"] }>(`/jobs/${jobId}/cancel`, { method: "POST" });
  }

  retryJob(jobId: string) {
    return this.request<{ accepted: boolean; project_id: string; job_id: string; registered_count: number }>(`/jobs/${jobId}/retry`, { method: "POST" });
  }

  getFailures(jobId: string) {
    return this.request<Record<string, unknown>>(`/jobs/${jobId}/failures`).then((raw) => ({
      job_id: jobId,
      items: Array.isArray(raw.items)
        ? (raw.items as Array<Record<string, unknown>>).map((item) => ({
            id: item.id ? String(item.id) : undefined,
            photo_id: (item.photo_id as string | null | undefined) ?? null,
            group_id: (item.group_id as string | null | undefined) ?? null,
            file_name: (item.file_name as string | null | undefined) ?? null,
            stage: String(item.stage ?? "unknown"),
            reason_code: item.reason_code ? String(item.reason_code) : undefined,
            reason: String(item.reason ?? item.message ?? item.reason_code ?? "Unknown failure"),
            retryable: Boolean(item.retryable),
            retry_scope: item.retry_scope as ReanalyzeRequest["scope"] | undefined,
          }))
        : [],
    }));
  }

  retryFailure(jobId: string, failureId: string) {
    return this.request<{ accepted: boolean; failure_id: string; scope: ReanalyzeRequest["scope"]; photo_ids: string[] }>(
      `/jobs/${jobId}/failures/${failureId}/retry`,
      { method: "POST" },
    );
  }

  getAIHealth() {
    return this.request<Record<string, unknown>>("/ai/health").then((raw) => ({
      provider: (raw.provider as AIHealthStatus["provider"] | undefined) ?? "lm_studio",
      reachable: Boolean(raw.reachable),
      localhost_only: Boolean(raw.localhost_only ?? true),
      remote_allowed: Boolean(raw.remote_allowed ?? false),
      auth_configured: Boolean(raw.auth_configured ?? true),
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

  listGroups(jobId: string, options: { filter?: Record<string, unknown>; sort?: string; page?: number; pageSize?: number } = {}) {
    const params = new URLSearchParams({
      job_id: jobId,
      sort: options.sort ?? "created_at",
      page: String(options.page ?? 1),
      page_size: String(options.pageSize ?? 100),
    });
    if (options.filter && Object.keys(options.filter).length) {
      params.set("filter", JSON.stringify(options.filter));
    }
    return this.request<Record<string, unknown>>(`/groups?${params.toString()}`).then((raw): GroupListResponse => {
      const items = Array.isArray(raw.items) ? (raw.items as Array<Record<string, unknown>>) : [];
      return {
        items: items.map((item) => ({
          id: String(item.id),
          job_id: String(item.job_id ?? jobId),
          representative_photo_id: (item.representative_photo_id as string | null | undefined) ?? null,
          representative_thumb_url: (item.representative_thumb_url as string | null | undefined) ?? null,
          best_photo_id: (item.best_photo_id as string | null | undefined) ?? null,
          group_size: Number(item.group_size ?? 0),
          group_start_time: (item.group_start_time as string | null | undefined) ?? null,
          group_end_time: (item.group_end_time as string | null | undefined) ?? null,
          previous_gap_seconds: (item.previous_gap_seconds as number | undefined) ?? null,
          boundary_reason: (item.boundary_reason as string | null | undefined) ?? null,
          merge_suggested: Boolean(item.merge_suggested),
          merge_suggestion_reason: (item.merge_suggestion_reason as string | null | undefined) ?? null,
          stale_flag: Boolean(item.stale_flag),
          stale_reason: (item.stale_reason as string | null | undefined) ?? null,
          reviewed_count: Number(item.reviewed_count ?? (item.reviewed ? Number(item.group_size ?? 0) : 0)),
          unreviewed_count: Number(item.unreviewed_count ?? Math.max(0, Number(item.group_size ?? 0) - Number(item.reviewed_count ?? 0))),
          review_queue: String(item.review_queue ?? "unreviewed"),
          review_priority: Number(item.review_priority ?? 0),
          technical_score_total: (item.technical_score_total as number | undefined) ?? null,
          semantic_score: (item.semantic_score as number | undefined) ?? null,
          ai_confidence_score: (item.ai_confidence_score as number | undefined) ?? null,
          best_rating: (item.best_rating as number | undefined) ?? null,
          items: Array.isArray(item.items)
            ? (item.items as Array<Record<string, unknown>>).map((photo) => this.normalizePhoto(photo, String(item.id)))
            : undefined,
        })),
        total: Number(raw.total ?? items.length),
        page: Number(raw.page ?? options.page ?? 1),
        page_size: Number(raw.page_size ?? options.pageSize ?? 100),
        total_pages: Number(raw.total_pages ?? 1),
        review_summary: raw.review_summary && typeof raw.review_summary === "object"
          ? {
              total_groups: Number((raw.review_summary as Record<string, unknown>).total_groups ?? 0),
              reviewed_groups: Number((raw.review_summary as Record<string, unknown>).reviewed_groups ?? 0),
              accepted_ai_groups: Number((raw.review_summary as Record<string, unknown>).accepted_ai_groups ?? 0),
              manually_changed_groups: Number((raw.review_summary as Record<string, unknown>).manually_changed_groups ?? 0),
              unresolved_groups: Number((raw.review_summary as Record<string, unknown>).unresolved_groups ?? 0),
            }
          : undefined,
      };
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
        group_start_time: (raw.group_start_time as string | null | undefined) ?? null,
        group_end_time: (raw.group_end_time as string | null | undefined) ?? null,
        previous_gap_seconds: (raw.previous_gap_seconds as number | undefined) ?? null,
        boundary_reason: (raw.boundary_reason as string | null | undefined) ?? null,
        merge_suggested: Boolean(raw.merge_suggested),
        merge_suggestion_reason: (raw.merge_suggestion_reason as string | null | undefined) ?? null,
        stale_flag: Boolean(raw.stale_flag),
        stale_reason: (raw.stale_reason as string | null | undefined) ?? null,
        review_queue: String(raw.review_queue ?? "unreviewed"),
        review_priority: Number(raw.review_priority ?? 0),
        ai_confidence_score: (raw.ai_confidence_score as number | undefined) ?? null,
        photos: photos.map((item) => this.normalizePhoto(item, String(raw.id ?? groupId))),
      };
    });
  }

  listPhotos(jobId: string, options: { includeMissing?: boolean; filter?: Record<string, unknown>; page?: number; pageSize?: number } = {}) {
    const params = new URLSearchParams({ job_id: jobId });
    if (options.includeMissing) {
      params.set("include_missing", "true");
    }
    if (options.filter && Object.keys(options.filter).length) {
      params.set("filter", JSON.stringify(options.filter));
    }
    params.set("page", String(options.page ?? 1));
    params.set("page_size", String(options.pageSize ?? 100));
    return this.request<Record<string, unknown>>(`/photos?${params.toString()}`).then((raw) => ({
      items: Array.isArray(raw.items)
        ? (raw.items as Array<Record<string, unknown>>).map((item) => this.normalizePhoto(item))
        : [],
      total: Number(raw.total ?? 0),
      page: Number(raw.page ?? options.page ?? 1),
      page_size: Number(raw.page_size ?? options.pageSize ?? 100),
      total_pages: Number(raw.total_pages ?? 1),
    }));
  }

  private normalizePhoto(item: Record<string, unknown>, fallbackGroupId: string | null = null): PhotoReviewItem {
    return {
      photo_id: String(item.photo_id ?? item.id),
      id: String(item.id ?? item.photo_id),
      group_id: (item.group_id as string | null | undefined) ?? fallbackGroupId,
      file_name: String(item.file_name ?? ""),
      file_path: String(item.file_path ?? ""),
      capture_time: (item.capture_time as string | null | undefined) ?? null,
      camera_model: (item.camera_model as string | null | undefined) ?? null,
      lens_model: (item.lens_model as string | null | undefined) ?? null,
      thumb_url: (item.thumb_url as string | null | undefined) ?? null,
      preview_url: (item.preview_url as string | null | undefined) ?? null,
      is_missing: Boolean(item.is_missing),
      rating: (item.rating as number | null | undefined) ?? null,
      provisional_rating: (item.provisional_rating as number | null | undefined) ?? null,
      selection_status: (item.selection_status as PhotoReviewItem["selection_status"]) ?? "normal",
      evaluation_status: (item.evaluation_status as PhotoReviewItem["evaluation_status"]) ?? "provisional",
      ai_reason: (item.ai_reason as string | null | undefined) ?? null,
      ai_confidence_score: (item.ai_confidence_score as number | null | undefined) ?? null,
      problem_tags: Array.isArray(item.problem_tags) ? (item.problem_tags as string[]) : [],
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
      sharpness_rank: (item.sharpness_rank as number | undefined) ?? null,
      exposure_rank: (item.exposure_rank as number | undefined) ?? null,
      candidate_quality_score: (item.candidate_quality_score as number | undefined) ?? null,
      reject_risk_score: (item.reject_risk_score as number | undefined) ?? null,
      review_queue: String(item.review_queue ?? "unreviewed"),
      review_priority: Number(item.review_priority ?? 0),
      semantic_score: (item.semantic_score as number | undefined) ?? null,
      composition_score: (item.composition_score as number | undefined) ?? null,
      subject_state_score: (item.subject_state_score as number | undefined) ?? null,
      rarity_score: (item.rarity_score as number | undefined) ?? null,
    };
  }

  private normalizeProject(item: Record<string, unknown>): ProjectItem {
    return {
      project_id: String(item.project_id ?? item.id),
      id: String(item.id ?? item.project_id),
      name: String(item.name ?? "Untitled project"),
      root_path: String(item.root_path ?? ""),
      recursive: Boolean(item.recursive ?? true),
      file_types: Array.isArray(item.file_types) ? (item.file_types as string[]) : [],
      last_job_id: (item.last_job_id as string | null | undefined) ?? null,
      created_at: (item.created_at as string | null | undefined) ?? null,
      updated_at: (item.updated_at as string | null | undefined) ?? null,
      latest_job: item.latest_job && typeof item.latest_job === "object" ? this.normalizeJobSummary(item.latest_job as Record<string, unknown>) : null,
    };
  }

  private normalizeJobSummary(item: Record<string, unknown>): JobSummary {
    return {
      job_id: String(item.job_id ?? item.id),
      project_id: (item.project_id as string | null | undefined) ?? null,
      root_path: String(item.root_path ?? ""),
      status: item.status as JobSummary["status"],
      total_files: Number(item.total_files ?? 0),
      failed_files: Number(item.failed_files ?? 0),
      current_stage: String(item.current_stage ?? "queued"),
      active_stage_label: String(item.active_stage_label ?? item.current_stage ?? "queued"),
      percent: Number(item.percent ?? 0),
      started_at: (item.started_at as string | null | undefined) ?? null,
      finished_at: (item.finished_at as string | null | undefined) ?? null,
      canceled_at: (item.canceled_at as string | null | undefined) ?? null,
      updated_at: (item.updated_at as string | null | undefined) ?? null,
    };
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

  mergeGroup(groupId: string, payload: GroupMergeRequest) {
    return this.request<Record<string, unknown>>(`/groups/${groupId}/merge`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  splitGroup(groupId: string, payload: GroupSplitRequest) {
    return this.request<Record<string, unknown>>(`/groups/${groupId}/split`, {
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
      weights: {
        technical_quality: Number((raw.weights as Record<string, unknown> | undefined)?.technical_quality ?? 0.35),
        composition: Number((raw.weights as Record<string, unknown> | undefined)?.composition ?? 0.35),
        subject_state: Number((raw.weights as Record<string, unknown> | undefined)?.subject_state ?? 0.2),
        rarity: Number((raw.weights as Record<string, unknown> | undefined)?.rarity ?? 0.1),
      },
      rating_thresholds: {
        star_5: Number((raw.rating_thresholds as Record<string, unknown> | undefined)?.star_5 ?? 83),
        star_4: Number((raw.rating_thresholds as Record<string, unknown> | undefined)?.star_4 ?? 74),
        star_3: Number((raw.rating_thresholds as Record<string, unknown> | undefined)?.star_3 ?? 58),
        star_2: Number((raw.rating_thresholds as Record<string, unknown> | undefined)?.star_2 ?? 42),
        reject: Number((raw.rating_thresholds as Record<string, unknown> | undefined)?.reject ?? 22),
      },
      ai_provider: (raw.ai_provider as SettingsResponse["ai_provider"] | undefined) ?? "lm_studio",
      ai_base_url: String(raw.ai_base_url ?? ""),
      ai_model_name: String(raw.ai_model_name ?? ""),
      allow_remote_ai: Boolean(raw.allow_remote_ai ?? false),
      ai_timeout_seconds: Number(raw.ai_timeout_seconds ?? 60),
      ai_max_tokens: Number(raw.ai_max_tokens ?? 512),
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
      highlight_threshold: Number(raw.highlight_threshold ?? 252),
      shadow_threshold: Number(raw.shadow_threshold ?? 3),
      exiftool_path: String(raw.exiftool_path ?? "exiftool"),
      cache_dir: String(raw.cache_dir ?? ""),
    }));
  }

  updateSettings(payload: SettingsUpdateRequest) {
    return this.request<Record<string, unknown>>("/settings", {
      method: "PATCH",
      body: JSON.stringify(payload),
    }).then((raw) => ({
      weights: {
        technical_quality: Number((raw.weights as Record<string, unknown> | undefined)?.technical_quality ?? 0.35),
        composition: Number((raw.weights as Record<string, unknown> | undefined)?.composition ?? 0.35),
        subject_state: Number((raw.weights as Record<string, unknown> | undefined)?.subject_state ?? 0.2),
        rarity: Number((raw.weights as Record<string, unknown> | undefined)?.rarity ?? 0.1),
      },
      rating_thresholds: {
        star_5: Number((raw.rating_thresholds as Record<string, unknown> | undefined)?.star_5 ?? 83),
        star_4: Number((raw.rating_thresholds as Record<string, unknown> | undefined)?.star_4 ?? 74),
        star_3: Number((raw.rating_thresholds as Record<string, unknown> | undefined)?.star_3 ?? 58),
        star_2: Number((raw.rating_thresholds as Record<string, unknown> | undefined)?.star_2 ?? 42),
        reject: Number((raw.rating_thresholds as Record<string, unknown> | undefined)?.reject ?? 22),
      },
      ai_provider: (raw.ai_provider as SettingsResponse["ai_provider"] | undefined) ?? "lm_studio",
      ai_base_url: String(raw.ai_base_url ?? ""),
      ai_model_name: String(raw.ai_model_name ?? ""),
      allow_remote_ai: Boolean(raw.allow_remote_ai ?? false),
      ai_timeout_seconds: Number(raw.ai_timeout_seconds ?? 60),
      ai_max_tokens: Number(raw.ai_max_tokens ?? 512),
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
      highlight_threshold: Number(raw.highlight_threshold ?? 252),
      shadow_threshold: Number(raw.shadow_threshold ?? 3),
      exiftool_path: String(raw.exiftool_path ?? "exiftool"),
      cache_dir: String(raw.cache_dir ?? ""),
    }));
  }
}
