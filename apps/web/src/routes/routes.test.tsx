import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Sidebar } from "@/components/sidebar";
import { ExportRoute } from "@/routes/export-route";
import { GroupDetailRoute } from "@/routes/group-detail-route";
import { ImportRoute } from "@/routes/import-route";
import { ProgressRoute } from "@/routes/progress-route";
import { ReviewRoute } from "@/routes/review-route";
import { SettingsRoute } from "@/routes/settings-route";

const mocks = vi.hoisted(() => ({
  aiHealth: { data: { provider: "lm_studio", reachable: true, localhost_only: true, remote_allowed: false, auth_configured: true, configured_model: "qwen", configured_model_exists: true, vision_capable: true, structured_json_capable: true } },
  importJob: { isPending: false, error: null, mutateAsync: vi.fn() },
  progress: { data: { current_stage: "semantically_scored", status: "running", failed_files: 1, total_files: 10, imported_files: 10, grouped_files: 8, technically_scored_files: 7, semantically_scored_files: 3, provisional_rated_files: 5, final_rated_files: 2 } },
  failures: { data: { items: [{ stage: "preview_exif", reason: "broken metadata" }] } },
  groups: { data: [{ id: "group_1", group_size: 1, unreviewed_count: 1, items: [{ photo_id: "photo_1", selection_status: "normal", pick_flag: false }] }] },
  group: { data: { id: "group_1", photos: [{ photo_id: "photo_1", file_name: "alpha.jpg", preview_url: "/preview.jpg", thumb_url: "/thumb.jpg", rating: 4, provisional_rating: 3, technical_score_total: 88, semantic_score: 77, evaluation_status: "final", selection_status: "normal", ai_reason: "best angle", pick_flag: true, best_cut_flag: true, reviewed_flag: true }] } },
  photos: { data: { items: [{ photo_id: "photo_1", group_id: "group_1", file_name: "alpha.jpg", thumb_url: "/thumb.jpg", rating: 5, selection_status: "normal", evaluation_status: "final", pick_flag: true, best_cut_flag: true, reviewed_flag: false, technical_score_total: 90, semantic_score: 92 }], total: 1 } },
  photoMutation: { mutate: vi.fn() },
  reanalyzePhoto: { mutate: vi.fn() },
  reanalyzeGroup: { mutate: vi.fn() },
  xmpExport: { mutate: vi.fn(), data: { target_count: 1, writable_count: 1, blocked_count: 0, write_candidates: [{ photo_id: "photo_1", summary: "preview diff" }] } },
  resultsExport: { mutate: vi.fn(), data: { export_path: "/tmp/export.csv" } },
  settings: { data: { ai_provider: "openrouter", ai_base_url: "https://openrouter.ai/api/v1", ai_model_name: "google/gemini-2.5-flash-lite", allow_remote_ai: true, ai_concurrency: 1, image_processing_concurrency: 2, similarity_threshold: 0.86, time_proximity_seconds: 4, candidate_limit: 6, thumbnail_size: 512, preview_size: 1024, compare_preview_size: 512, preview_jpeg_quality: 90, highlight_threshold: 252, shadow_threshold: 3, exiftool_path: "exiftool", cache_dir: "/tmp/cache", weights: { technical_quality: 0.35, composition: 0.35, subject_state: 0.2, rarity: 0.1 }, rating_thresholds: { star_5: 83, star_4: 78, star_3: 64, star_2: 48, reject: 20 } } },
  updateSettings: { mutate: vi.fn() },
}));

vi.mock("@/features/import/use-import", () => ({
  useAIHealth: () => mocks.aiHealth,
  useImportJob: () => mocks.importJob,
}));

vi.mock("@/features/progress/use-progress", () => ({
  useProgress: () => mocks.progress,
  useFailures: () => mocks.failures,
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

    expect(markup).toContain("Burst intake with local AI preflight.");
    expect(markup).toContain("qwen");
  });

  it("renders progress route counts and failures", () => {
    const markup = renderToStaticMarkup(
      <MemoryRouter>
        <ProgressRoute />
      </MemoryRouter>,
    );

    expect(markup).toContain("Pipeline telemetry for long local runs.");
    expect(markup).toContain("broken metadata");
  });

  it("renders group detail route review state", () => {
    const markup = renderToStaticMarkup(
      <MemoryRouter initialEntries={["/groups/group_1?job=job_123"]}>
        <Routes>
          <Route path="/groups/:groupId" element={<GroupDetailRoute />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(markup).toContain("Frame-by-frame burst review.");
    expect(markup).toContain("alpha.jpg");
    expect(markup).toContain("best angle");
  });

  it("renders global review and export routes", () => {
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

    expect(reviewMarkup).toContain("Global review for star tiers and reject lanes.");
    expect(reviewMarkup).toContain("alpha.jpg");
    expect(reviewMarkup).toContain("/groups/group_1?job=job_123");
    expect(exportMarkup).toContain("Dry-run first, then commit metadata writes.");
    expect(exportMarkup).toContain("/tmp/export.csv");
  });

  it("preserves active job in sidebar navigation", () => {
    const markup = renderToStaticMarkup(
      <MemoryRouter initialEntries={["/review?job=job_123"]}>
        <Sidebar />
      </MemoryRouter>,
    );

    expect(markup).toContain("/groups?job=job_123");
    expect(markup).toContain("/review?job=job_123");
    expect(markup).toContain("/export?job=job_123");
    expect(markup).toContain("/settings?job=job_123");
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
  });
});
