export type JobStatus = "queued" | "running" | "canceling" | "completed" | "failed" | "canceled";
export type EvaluationStatus = "provisional" | "final" | "ai_eval_failed" | "stale";
export type SelectionStatus = "normal" | "rejected";
export type ReanalyzeScope = "technical_only" | "ai_only" | "full";

export interface ImportRequest {
  root_path: string;
  recursive: boolean;
  file_types: string[];
  reuse_cache: boolean;
}

export interface ImportResponse {
  project_id: string;
  job_id: string;
  registered_count: number;
}

export interface AnalyzeRequest {
  reuse_cache?: boolean;
  force_reuse_cache?: boolean;
}

export interface JobProgress {
  id?: string;
  job_id: string;
  project_id?: string | null;
  status: JobStatus;
  total_files: number;
  imported_files: number;
  grouped_files: number;
  technically_scored_files: number;
  semantically_scored_files: number;
  provisional_rated_files: number;
  final_rated_files: number;
  failed_files: number;
  current_stage: string;
  active_stage_label: string;
  stage_done: number;
  stage_total: number;
  percent: number;
  cancel_requested: boolean;
  ai_photo_done: number;
  ai_photo_total: number;
  ai_group_done: number;
  ai_group_total: number;
  errors: string[];
  started_at?: string | null;
  finished_at?: string | null;
  canceled_at?: string | null;
  updated_at?: string | null;
  last_error?: string | null;
}

export interface JobSummary {
  job_id: string;
  project_id?: string | null;
  root_path: string;
  status: JobStatus;
  total_files: number;
  failed_files: number;
  current_stage: string;
  active_stage_label: string;
  percent: number;
  started_at?: string | null;
  finished_at?: string | null;
  canceled_at?: string | null;
  updated_at?: string | null;
}

export interface ProjectItem {
  project_id: string;
  id: string;
  name: string;
  root_path: string;
  recursive: boolean;
  file_types: string[];
  last_job_id?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  latest_job?: JobSummary | null;
}

export interface ProjectListResponse {
  items: ProjectItem[];
  total: number;
}

export interface ProjectJobsResponse {
  project_id: string;
  items: JobSummary[];
  total: number;
}

export interface AIHealthStatus {
  provider: "lm_studio" | "openrouter";
  reachable: boolean;
  localhost_only: boolean;
  remote_allowed: boolean;
  auth_configured: boolean;
  available_models: string[];
  configured_model: string;
  configured_model_exists: boolean;
  model_available?: boolean;
  model_loadable: boolean;
  model_loaded?: boolean;
  vision_capable: boolean;
  vision_available?: boolean;
  structured_json_capable: boolean;
  json_mode_available?: boolean;
  checked_at: string;
  error_detail?: string | null;
}

export interface ScoreSummary {
  technical_score_total?: number | null;
  sharpness_rank?: number | null;
  exposure_rank?: number | null;
  candidate_quality_score?: number | null;
  reject_risk_score?: number | null;
  review_queue?: string;
  review_priority?: number;
  semantic_score?: number | null;
  composition_score?: number | null;
  subject_state_score?: number | null;
  rarity_score?: number | null;
  ai_confidence_score?: number | null;
}

export interface GroupListItem extends ScoreSummary {
  id: string;
  job_id: string;
  representative_photo_id?: string | null;
  representative_thumb_url?: string | null;
  best_photo_id?: string | null;
  group_size: number;
  group_start_time?: string | null;
  group_end_time?: string | null;
  previous_gap_seconds?: number | null;
  boundary_reason?: string | null;
  merge_suggested: boolean;
  merge_suggestion_reason?: string | null;
  stale_flag: boolean;
  stale_reason?: string | null;
  reviewed_count: number;
  unreviewed_count: number;
  best_rating?: number | null;
  items?: PhotoReviewItem[];
}

export interface GroupReviewSummary {
  total_groups: number;
  reviewed_groups: number;
  accepted_ai_groups: number;
  manually_changed_groups: number;
  unresolved_groups: number;
}

export interface PhotoReviewItem extends ScoreSummary {
  photo_id: string;
  id?: string;
  group_id?: string | null;
  file_name: string;
  file_path: string;
  capture_time?: string | null;
  camera_model?: string | null;
  lens_model?: string | null;
  thumb_url?: string | null;
  preview_url?: string | null;
  is_missing: boolean;
  provisional_rating?: number | null;
  provisional_selection_status?: SelectionStatus | null;
  rating?: number | null;
  selection_status: SelectionStatus;
  evaluation_status: EvaluationStatus;
  ai_reason?: string | null;
  problem_tags?: string[];
  pick_flag: boolean;
  best_cut_flag: boolean;
  reviewed_flag: boolean;
  user_override_flag: boolean;
  stale_flag: boolean;
  stale_reason?: string | null;
}

export interface GroupDetail extends GroupListItem {
  photos: PhotoReviewItem[];
}

export interface GroupListResponse {
  items: GroupListItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  review_summary?: GroupReviewSummary;
}

export interface PhotoListResponse {
  items: PhotoReviewItem[];
  total: number;
  page?: number;
  page_size?: number;
  total_pages?: number;
}

export interface PhotoMutationRequest {
  job_id: string;
  rating?: number | null;
  selection_status?: SelectionStatus | null;
  pick_flag?: boolean | null;
  best_cut_flag?: boolean | null;
  reviewed_flag?: boolean | null;
}

export interface BatchPhotoMutationRequest {
  job_id: string;
  photo_ids: string[];
  action: "set_rating" | "set_selection_status" | "set_pick" | "set_reviewed" | "set_best_cut";
  payload: Record<string, unknown>;
}

export interface MutationResult {
  updated_count: number;
  failed_count: number;
}

export interface ReanalyzeRequest {
  job_id: string;
  scope: ReanalyzeScope;
}

export interface GroupMergeRequest {
  target_group_id: string;
  stale_policy?: "mark_stale";
}

export interface GroupSplitRequest {
  photo_ids: string[];
  new_group_rule?: "selected_to_new_group";
  stale_policy?: "mark_stale";
  best_cut_policy?: "clear";
}

export interface FailureItem {
  id?: string;
  photo_id?: string | null;
  group_id?: string | null;
  file_name?: string | null;
  stage: string;
  reason_code?: string;
  reason: string;
  retryable: boolean;
  retry_scope?: ReanalyzeScope;
}

export interface FailureListResponse {
  job_id?: string;
  items: FailureItem[];
}

export interface ExportResultsRequest {
  job_id: string;
  format: "csv" | "json";
  filters?: Record<string, unknown>;
}

export interface ExportResultsResponse {
  export_path: string;
  format: "csv" | "json";
  item_count: number;
}

export interface XmpExportRequest {
  job_id: string;
  photo_ids?: string[];
  filters?: Record<string, unknown>;
  dry_run?: boolean;
  conflict_policy?: "skip" | "fail" | "overwrite_safe_fields";
}

export interface XmpCandidateItem {
  photo_id: string;
  file_path: string;
  summary: string;
  result_code?: string;
}

export interface XmpExportResponse {
  target_count: number;
  writable_count?: number;
  blocked_count?: number;
  conflict_count?: number;
  written_count?: number;
  skipped_count?: number;
  failed_count?: number;
  write_candidates?: XmpCandidateItem[];
  blocked_items?: XmpCandidateItem[];
  conflicts?: XmpCandidateItem[];
  written_items?: XmpCandidateItem[];
  skipped_items?: XmpCandidateItem[];
  failed_items?: XmpCandidateItem[];
}

export interface SettingsResponse {
  weights: {
    technical_quality: number;
    composition: number;
    subject_state: number;
    rarity: number;
  };
  rating_thresholds: {
    star_5: number;
    star_4: number;
    star_3: number;
    star_2: number;
    reject: number;
  };
  ai_provider: "lm_studio" | "openrouter";
  ai_base_url: string;
  ai_model_name: string;
  allow_remote_ai: boolean;
  ai_timeout_seconds: number;
  ai_max_tokens: number;
  ai_concurrency: number;
  image_processing_concurrency: number;
  image_concurrency?: number;
  similarity_threshold: number;
  time_proximity_seconds: number;
  candidate_limit: number;
  thumbnail_size: number;
  preview_size: number;
  compare_preview_size: number;
  preview_jpeg_quality: number;
  jpeg_quality?: number;
  highlight_threshold: number;
  shadow_threshold: number;
  exiftool_path: string;
  cache_dir: string;
}

export type SettingsUpdateRequest = Partial<SettingsResponse>;
