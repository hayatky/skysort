import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Sidebar } from "@/components/sidebar";
import { DeleteCandidatesRoute } from "@/routes/delete-candidates-route";
import { ExportRoute } from "@/routes/export-route";
import { GroupDetailRoute } from "@/routes/group-detail-route";
import { GroupsRoute } from "@/routes/groups-route";
import { ImportRoute } from "@/routes/import-route";
import { ProgressRoute } from "@/routes/progress-route";
import { ProjectsRoute } from "@/routes/projects-route";
import { ReviewRoute } from "@/routes/review-route";
import { SettingsRoute } from "@/routes/settings-route";

const mocks = vi.hoisted(() => ({
  aiHealth: { data: { provider: "lm_studio", reachable: true, localhost_only: true, remote_allowed: false, auth_configured: true, configured_model: "qwen", configured_model_exists: true, vision_capable: true, structured_json_capable: true } },
  importJob: { isPending: false, error: null, mutateAsync: vi.fn() },
  progress: { data: { current_stage: "semantically_scored", status: "running", failed_files: 1, total_files: 10, imported_files: 10, grouped_files: 8, technically_scored_files: 7, semantically_scored_files: 3, provisional_rated_files: 5, final_rated_files: 2 } },
  failures: { data: { items: [{ id: "fail_1", stage: "preview_exif", reason_code: "metadata_extraction_failed", reason: "broken metadata", photo_id: "photo_1", group_id: null, file_name: "alpha.jpg", retryable: true, retry_scope: "full" }] } },
  groups: { data: { items: [{ id: "group_1", group_size: 1, unreviewed_count: 1, stale_flag: true, items: [{ photo_id: "photo_1", selection_status: "normal", evaluation_status: "ai_eval_failed", pick_flag: false, stale_flag: true, is_missing: false }] }], total: 1, page: 1, page_size: 48, total_pages: 1 } },
  group: { data: { id: "group_1", photos: [{ photo_id: "photo_1", file_name: "alpha.jpg", preview_url: "/preview.jpg", thumb_url: "/thumb.jpg", rating: 4, provisional_rating: 3, technical_score_total: 88, semantic_score: 77, evaluation_status: "ai_eval_failed", selection_status: "normal", ai_reason: "best angle", pick_flag: true, best_cut_flag: true, reviewed_flag: true, stale_flag: true, stale_reason: "settings_changed", is_missing: false }] } },
  photos: { data: { items: [{ photo_id: "photo_1", group_id: "group_1", file_name: "alpha.jpg", thumb_url: "/thumb.jpg", rating: 1, selection_status: "normal", evaluation_status: "ai_eval_failed", pick_flag: true, best_cut_flag: true, reviewed_flag: false, stale_flag: true, stale_reason: "settings_changed", is_missing: false, technical_score_total: 90, semantic_score: 92 }], total: 1 } },
  photoMutation: { mutate: vi.fn() },
  reanalyzePhoto: { mutate: vi.fn() },
  reanalyzeGroup: { mutate: vi.fn() },
  retryFailure: { mutate: vi.fn() },
  cancelJob: { mutate: vi.fn(), isPending: false },
  retryJob: { mutateAsync: vi.fn(), isPending: false },
  mergeGroup: { mutate: vi.fn() },
  splitGroup: { mutate: vi.fn() },
  xmpExport: { mutate: vi.fn(), data: { target_count: 1, writable_count: 1, blocked_count: 0, conflict_count: 1, write_candidates: [{ photo_id: "photo_1", summary: "preview diff" }], conflicts: [{ photo_id: "photo_2", summary: "rating conflict", result_code: "conflict" }] } },
  resultsExport: { mutate: vi.fn(), data: { export_path: "/tmp/export.csv" } },
  settings: { data: { ai_provider: "openrouter", ai_base_url: "https://openrouter.ai/api/v1", ai_model_name: "google/gemini-2.5-flash-lite", allow_remote_ai: true, ai_concurrency: 1, image_processing_concurrency: 2, similarity_threshold: 0.86, time_proximity_seconds: 4, candidate_limit: 6, thumbnail_size: 512, preview_size: 1024, compare_preview_size: 512, preview_jpeg_quality: 90, highlight_threshold: 252, shadow_threshold: 3, exiftool_path: "exiftool", cache_dir: "/tmp/cache", weights: { technical_quality: 0.35, composition: 0.35, subject_state: 0.2, rarity: 0.1 }, rating_thresholds: { star_5: 83, star_4: 78, star_3: 64, star_2: 48, reject: 20 } } },
  updateSettings: { mutate: vi.fn() },
  projects: { data: { items: [{ project_id: "proj_1", id: "proj_1", name: "Haneda", root_path: "C:\\photos\\haneda", recursive: true, file_types: [".jpg"], last_job_id: "job_123", latest_job: { job_id: "job_123", project_id: "proj_1", root_path: "C:\\photos\\haneda", status: "running", total_files: 10, failed_files: 1, current_stage: "semantically_scored", active_stage_label: "AI analysis", percent: 30 } }], total: 1 } },
  startProjectAnalysis: { mutateAsync: vi.fn(), isPending: false },
}));

vi.mock("@/features/import/use-import", () => ({
  useAIHealth: () => mocks.aiHealth,
  useImportJob: () => mocks.importJob,
}));

vi.mock("@/features/progress/use-progress", () => ({
  useProgress: () => mocks.progress,
  useFailures: () => mocks.failures,
  useCancelJob: () => mocks.cancelJob,
  useRetryJob: () => mocks.retryJob,
}));

vi.mock("@/features/projects/use-projects", () => ({
  useProjects: () => mocks.projects,
  useStartProjectAnalysis: () => mocks.startProjectAnalysis,
}));

vi.mock("@/features/groups/use-groups", () => ({
  useGroups: () => mocks.groups,
  useGroup: () => mocks.group,
  usePhotos: () => mocks.photos,
}));

vi.mock("@/features/review/use-review-actions", () => ({
  usePhotoMutation: () => mocks.photoMutation,
  useReanalyzePhoto: () => mocks.reanalyzePhoto,
  useReanalyzeGroup: () => mocks.reanalyzeGroup,
  useRetryFailure: () => mocks.retryFailure,
  useMergeGroup: () => mocks.mergeGroup,
  useSplitGroup: () => mocks.splitGroup,
}));

vi.mock("@/features/export/use-export", () => ({
  useXmpExport: () => mocks.xmpExport,
  useResultsExport: () => mocks.resultsExport,
}));

vi.mock("@/features/settings/use-settings", () => ({
  useSettings: () => mocks.settings,
  useUpdateSettings: () => mocks.updateSettings,
}));

vi.mock("@/hooks/use-review-shortcuts", () => ({
  useReviewShortcuts: () => undefined,
}));

vi.mock("@/hooks/use-job-id", () => ({
  useJobId: () => "job_123",
}));

vi.mock("@tanstack/react-virtual", () => ({
  useVirtualizer: () => ({
    getTotalSize: () => 260,
    getVirtualItems: () => [{ index: 0, start: 0 }],
  }),
}));

describe("route rendering", () => {
  beforeEach(() => {
    mocks.importJob.mutateAsync.mockReset();
    mocks.photoMutation.mutate.mockReset();
    mocks.reanalyzePhoto.mutate.mockReset();
    mocks.reanalyzeGroup.mutate.mockReset();
    mocks.retryFailure.mutate.mockReset();
    mocks.cancelJob.mutate.mockReset();
    mocks.retryJob.mutateAsync.mockReset();
    mocks.startProjectAnalysis.mutateAsync.mockReset();
    mocks.mergeGroup.mutate.mockReset();
    mocks.splitGroup.mutate.mockReset();
    mocks.xmpExport.mutate.mockReset();
    mocks.resultsExport.mutate.mockReset();
    mocks.updateSettings.mutate.mockReset();
  });

  it("renders import route with AI health summary", () => {
    const markup = renderToStaticMarkup(
      <MemoryRouter>
        <ImportRoute />
      </MemoryRouter>,
    );

    expect(markup).toContain("Import");
    expect(markup).toContain("qwen");
  });

  it("renders projects dashboard with persisted latest job", () => {
    const markup = renderToStaticMarkup(
      <MemoryRouter>
        <ProjectsRoute />
      </MemoryRouter>,
    );

    expect(markup).toContain("Projects");
    expect(markup).toContain("Haneda");
    expect(markup).toContain("AI analysis");
    expect(markup).toContain("/progress?job=job_123");
  });

  it("renders progress route counts and failures", () => {
    const markup = renderToStaticMarkup(
      <MemoryRouter>
        <ProgressRoute />
      </MemoryRouter>,
    );

    expect(markup).toContain("Progress");
    expect(markup).toContain("broken metadata");
    expect(markup).toContain("alpha.jpg");
    expect(markup).toContain("Retryable");
    expect(markup).toContain("Reason metadata_extraction_failed");
    expect(markup).toContain("Scope full");
    expect(markup).toContain("Retry Item");
    expect(markup).toContain("Cancel Job");
    expect(markup).toContain("Retry Job");
  });

  it("renders group detail route review state", () => {
    const markup = renderToStaticMarkup(
      <MemoryRouter initialEntries={["/groups/group_1?job=job_123"]}>
        <Routes>
          <Route path="/groups/:groupId" element={<GroupDetailRoute />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(markup).toContain("Group Detail");
    expect(markup).toContain("alpha.jpg");
    expect(markup).toContain("best angle");
    expect(markup).toContain("Stale settings_changed");
    expect(markup).toContain("AI Failed");
    expect(markup).toContain("Split Selected");
  });

  it("renders global review and export routes", () => {
    const groupsMarkup = renderToStaticMarkup(
      <MemoryRouter>
        <GroupsRoute />
      </MemoryRouter>,
    );
    const reviewMarkup = renderToStaticMarkup(
      <MemoryRouter>
        <ReviewRoute />
      </MemoryRouter>,
    );
    const exportMarkup = renderToStaticMarkup(
      <MemoryRouter>
        <ExportRoute />
      </MemoryRouter>,
    );

    expect(groupsMarkup).toContain("Merge Groups");
    expect(reviewMarkup).toContain("Review");
    expect(reviewMarkup).toContain("alpha.jpg");
    expect(reviewMarkup).toContain("/groups/group_1?job=job_123");
    expect(reviewMarkup).toContain("Stale");
    expect(reviewMarkup).toContain("Missing");
    expect(reviewMarkup).toContain("AI Failed");
    expect(exportMarkup).toContain("Export");
    expect(exportMarkup).toContain("/tmp/export.csv");
    expect(exportMarkup).toContain("Conflict Policy");
    expect(exportMarkup).toContain("Conflicts");
    expect(exportMarkup).toContain("rating conflict");
  });

  it("renders delete candidate review separately from global review", () => {
    const markup = renderToStaticMarkup(
      <MemoryRouter>
        <DeleteCandidatesRoute />
      </MemoryRouter>,
    );

    expect(markup).toContain("Delete Candidates");
    expect(markup).toContain("★1");
    expect(markup).toContain("Remove Candidate");
    expect(markup).toContain("Confirm Reject");
  });

  it("preserves active job in sidebar navigation", () => {
    const markup = renderToStaticMarkup(
      <MemoryRouter initialEntries={["/review?job=job_123"]}>
        <Sidebar />
      </MemoryRouter>,
    );

    expect(markup).toContain("/groups?job=job_123");
    expect(markup).toContain("Haneda");
    expect(markup).toContain("/review?job=job_123");
    expect(markup).toContain("/delete-candidates?job=job_123");
    expect(markup).toContain("/export?job=job_123");
    expect(markup).toContain("/settings");
  });

  it("renders settings route with threshold controls", () => {
    const markup = renderToStaticMarkup(
      <MemoryRouter>
        <SettingsRoute />
      </MemoryRouter>,
    );

    expect(markup).toContain("weights.technical_quality");
    expect(markup).toContain("rating_thresholds.reject");
    expect(markup).toContain("allow_remote_ai");
    expect(markup).toContain("SKYSORT_AI_API_KEY");
    expect(markup).toContain("Settings apply to new jobs only.");
  });
});
