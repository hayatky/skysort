# SkySort

SkySort is a local-first AI photo culling tool for aviation photographers. This repository now contains the Phase 1 MVP scaffold defined in [docs/plan.md](docs/plan.md): import, preview generation, EXIF extraction, grouping, technical scoring, AI-assisted review, manual overrides, and dry-run-first XMP export.

## Repository Layout

```text
apps/
  api/   FastAPI + SQLite + Alembic backend
  web/   React + Vite review UI
packages/
  client/ shared TypeScript API client and DTOs
scripts/
var/      runtime outputs (cache, DB, logs, tmp)
```

## Prerequisites

- `uv` for Python environment and execution
- `pnpm` for the frontend workspace
- LM Studio or another OpenAI-compatible vision endpoint
- `ExifTool` for actual XMP write-back

Recommended startup order:

1. Copy `.env.example` to `.env`, then adjust the AI settings if you are not using the LM Studio defaults.
2. Start the API.
3. Start the web app.

OpenRouter example:

```dotenv
SKYSORT_AI_PROVIDER=openrouter
SKYSORT_AI_BASE_URL=https://openrouter.ai/api/v1
SKYSORT_AI_MODEL_NAME=openai/gpt-5-nano
SKYSORT_ALLOW_REMOTE_AI=true
SKYSORT_AI_API_KEY=your_api_key
SKYSORT_AI_REFERER=https://example.com/skysort
SKYSORT_AI_TITLE=SkySort
```

## Backend Setup

```bash
cd /path/to/skysort
uv sync --project apps/api
pnpm migrate:api
pnpm dev:api
```

`pnpm dev:api` loads `.env` automatically, applies the latest Alembic migration, and then starts the FastAPI dev server.

If you only want to apply the database migration without starting the server, run `pnpm migrate:api`.

API defaults:

- URL: `http://127.0.0.1:8000`
- OpenAPI: `http://127.0.0.1:8000/openapi.json`
- Media files: served from `var/cache`

Important runtime behavior:

- SQLite lives in `var/data/skysort.db`
- thumbnails and previews live in `var/cache`
- application logs live in `var/logs/app.log`
- `GET /api/groups` accepts JSON `filter`, `sort`, `page`, and `page_size` query parameters for large review sets
- `GET /api/photos` accepts JSON `filter`, `page`, `page_size`, and `include_missing=true` for server-side review filtering
- `filter` supports rating, reject, pick, best cut, reviewed, stale, AI-complete-only review, status, camera/lens, text search (`q`), filename, and capture date range conditions
- projects are persisted on the server; `GET /api/projects` returns recent projects with their latest job, and project retry/reanalysis creates a new cache-reusing job
- `POST /api/export/results` and `POST /api/export/xmp` apply the same review filters
- AI health is checked before `POST /api/jobs/{job_id}/analyze`
- remote AI endpoints are blocked unless `allow_remote_ai=true`
- XMP export defaults to `dry_run=true`
- XMP export validates `conflict_policy` as `skip`, `fail`, or `overwrite_safe_fields`; `fail` stops non-dry-run writes when conflicts are detected
- unchanged files reuse deterministic preview/thumbnail cache keys derived from path + hash + size + mtime
- ARW preview generation prefers the embedded JPEG preview and falls back to `rawpy` demosaic only when needed
- AI responses must include `schema_version` and the expected typed best/keep/reject ranking structure before values are applied
- Group comparison sends a labeled contact sheet and requires `best_photo_id`, `keep_photo_ids`, `reject_photo_ids`, ranking confidence, problem tags, and per-photo reasons to reduce photo ID mix-ups.
- Groups larger than six images are compared through overlapping contact-sheet windows and a final contender comparison; only obvious technical failures are removed before AI comparison.
- Groups marked as likely fragments are deferred as `merge_suggested` review items before AI best-cut selection, avoiding local best proliferation across split bursts.
- `ai_timeout_seconds` defaults to 60 seconds and is used for both health checks and evaluation calls. AI evaluation payloads also set `max_tokens` from `ai_max_tokens`, defaulting to 1024, so structured JSON responses have enough completion budget without running until the HTTP timeout.
- Review API responses include `review_queue` and `review_priority`; group queues include `merge_suggested`, `singleton`, `best_missing`, `ai_failed`, `low_confidence`, `reject_candidate`, `ai_review`, `stale`, and `unreviewed` for prioritized review.
- Photo and group list filters support review queues, confidence ranges, adjacent previous-gap ranges, problem tags, keep/reject recommendations, user overrides, group size ranges, merge suggestions, and missing best-cut groups.
- Group list responses include `review_summary` counts for total, reviewed, accepted-AI, manually changed, and unresolved groups.
- The `/burst-review` screen provides virtualized one-row-per-group burst review with horizontal thumbnail strips, queue filtering, group progress, best/keep/reject/review controls, merge/split actions, and arrow/Enter/B/K/P/X/M/S keyboard operations.
- `image_processing_concurrency` controls preview, metadata, and technical-score workers; it defaults to `min(16, os.cpu_count())` and `ai_concurrency` controls single-image AI calls while DB writes remain serialized
- Technical scoring stores absolute scores plus group-relative `sharpness_rank`, `exposure_rank`, `candidate_quality_score`, and `reject_risk_score`; provisional ratings and AI candidate selection use these calibrated values instead of raw technical totals.

Windows note:

- Install ExifTool separately when you want real XMP write-back.
- If `exiftool` is not on `PATH`, set `SKYSORT_EXIFTOOL_PATH` in `.env` to the full executable path.

## Frontend Setup

```bash
cd /path/to/skysort
pnpm install
pnpm dev:web
```

The Vite dev server accepts both `http://127.0.0.1:5173` and `http://localhost:5173`, and proxies `/api` to the backend on port `8000`.

## Phase 1 Implemented Surfaces

### Backend

- `POST /api/import`
- `GET /api/projects`
- `GET /api/projects/{project_id}`
- `GET /api/projects/{project_id}/jobs`
- `POST /api/projects/{project_id}/analyze`
- `POST /api/jobs/{job_id}/analyze`
- `POST /api/jobs/{job_id}/cancel`
- `POST /api/jobs/{job_id}/retry`
- `GET /api/jobs/{job_id}/progress`
- `GET /api/jobs/{job_id}/failures`
- `POST /api/jobs/{job_id}/failures/{failure_id}/retry`
- `GET /api/ai/health`
- `GET /api/groups`
- `GET /api/groups/{group_id}`
- `POST /api/groups/{group_id}/merge`
- `POST /api/groups/{group_id}/split`
- `GET /api/photos`
- `PATCH /api/photos/{photo_id}`
- `POST /api/photos/batch`
- `POST /api/photos/{photo_id}/reanalyze`
- `POST /api/groups/{group_id}/reanalyze`
- `POST /api/export/xmp`
- `POST /api/export/results`
- `GET /api/settings`
- `PATCH /api/settings`
- `GET /api/media/{kind}/{photo_id}`

### Frontend

- Import screen with AI preflight
- Projects dashboard with server-backed project/job discovery
- Progress monitoring screen with stage, AI photo/group progress, graceful cancel, and retry into a new cache-reusing job
- Failure list with retryable item retry controls and separated reason codes for preview generation, metadata extraction, AI timeout, and JSON/schema failures
- Group overview
- Group detail review with keyboard shortcuts
- Group merge by source/target group ID and selected-photo split from group detail; affected evaluations are marked stale
- Global review with virtualized list
- Dedicated delete-candidate review that distinguishes `reject` from ★1 and provides quick remove/confirm actions
- Group and global review screens use API-backed filters, text/date search, page controls, and selectable reanalysis scope (`technical_only`, `ai_only`, `full`)
- Export screen for XMP dry-run and result export
- Settings screen for mutable runtime settings

Keyboard shortcuts on review screens:

- `1` to `5`: set star rating
- `X`: reject
- `P`: toggle pick
- Arrow keys: move selection
- `Space`: toggle preview emphasis on group detail

## Tests And Checks

Backend syntax / basic unit checks:

```bash
cd /path/to/skysort
uv run python -m compileall -q apps/api/src
uv run --project apps/api pytest
pnpm --filter @skysort/web test
pnpm generate:client
```

The repository includes backend tests for import diffing, RAW preview selection, API validation, grouping order, and XMP helpers, plus frontend Vitest coverage for the main Phase 1 routes.

`pnpm generate:client` regenerates the canonical OpenAPI snapshot at `packages/client/openapi.json`.

Frontend source under `apps/web/src` is TypeScript-only. The web build runs `tsc --noEmit` for type checking and emits browser assets only through Vite into `dist/`.

Use [docs/acceptance-checklist.md](docs/acceptance-checklist.md) for the current local acceptance gate before test operation.

## Benchmark Validation

Before production use, validate against a benchmark burst set with expected best/reject examples.

1. Prepare 10 to 20 representative burst groups containing obvious best cuts, obvious reject frames, and at least one burst larger than 6 images.
2. Run a fresh import and analysis with the target LM Studio model and keep `dry_run=true` for XMP export.
3. Compare group best picks against the benchmark expectation list and review every expected reject frame in the global review screen.
4. Record mismatches with the group ID, expected outcome, actual outcome, and whether the issue came from grouping, technical scoring, or AI ranking.
5. Re-run one unchanged benchmark folder and confirm that previews and unchanged evaluations are reused instead of being recomputed.

Use [docs/benchmark-expectations.example.json](docs/benchmark-expectations.example.json) as the expectation template. Fill 10 to 20 representative bursts and include `match.relative_paths` so the benchmark can measure grouping quality as well as picks. After exporting JSON results from `POST /api/export/results`, generate JSON, CSV, and Markdown reports under `var/tmp` with:

```bash
python scripts/benchmark_diff.py --expectations docs/benchmark-expectations.example.json --results var/tmp/example_results.json --root /path/to/import/root --output-dir var/tmp
```

The benchmark report includes best-match rate, reject recall, missing/unexpected keep counts, over-fragmented and over-merged group counts, AI failure rate, and review-operation counts.

To bootstrap a human-review expectation file from a completed local job, generate a draft and then visually verify/edit every expected value:

```bash
python scripts/benchmark_seed.py --db var/data/skysort.db --limit 20 --output var/tmp/benchmark-expectations-draft.json
```

When current-code rescored technical diagnostics are available, seed expected best/pick/reject from that fixture instead of stale persisted ratings:

```bash
python scripts/benchmark_seed.py --db var/data/skysort.db --limit 20 --score-fixture var/tmp/realdata-rescored-diagnostics-fixture.json --output docs/benchmark-expectations.current-code-draft.json --html-output var/tmp/benchmark-expectations-current-code-draft.html --strip-review-items
```

This also writes a static thumbnail strip review page for visually checking the draft before treating it as human-verified ground truth. The current maintained machine draft is `docs/benchmark-expectations.current-code-draft.json` and keeps `human_verified=false` until a person verifies the expected values.

To summarize whether the remaining real-data acceptance gates are actually satisfied, run:

```bash
python scripts/acceptance_gate.py --diagnostics var/tmp/realdata-diagnostics.json --output-dir var/tmp
```

For a fresh rerun, keep the old diagnostics as the baseline and compare the new report against it. After a reviewed packet, human-verified benchmark diff, or executed timeout probe exists, include those artifacts too:

```bash
python scripts/acceptance_gate.py --baseline-diagnostics var/tmp/baseline-diagnostics.json --diagnostics var/tmp/fresh-diagnostics.json --benchmark-diff var/tmp/benchmark-diff.json --review-packet var/tmp/human-review-packet.json --timeout-probe var/tmp/ai-timeout-probe.json --output-dir var/tmp
```

The current local gate report is `var/tmp/acceptance-gate.md`; it intentionally leaves visual benchmark review unresolved until the corresponding reviewed expectation evidence exists.

To hand off the remaining visual checks as a single packet, generate:

```bash
uv run --project apps/api python scripts/review_montages.py --review-html var/tmp/benchmark-expectations-current-code-draft.html --output-dir var/tmp/human-review-montages
python scripts/human_review_packet.py --expectations docs/benchmark-expectations.current-code-draft.json --benchmark-diff var/tmp/benchmark-current-code-draft-diff.json --acceptance-gate var/tmp/acceptance-gate.json --review-html var/tmp/benchmark-expectations-current-code-draft.html --review-montage-dir var/tmp/human-review-montages --diagnostics var/tmp/realdata-rescored-diagnostics.json --output-dir var/tmp
```

This writes `var/tmp/human-review-packet.md`, `.json`, and `.html` with the exact groups to inspect, current benchmark issues, montage paths, and over-merge/subjective review placeholders. Open the HTML form locally to check each montage and download a reviewed packet JSON; timeout rerun instructions are included only if the current acceptance gate still fails `ai_timeout_rate`.

After filling `human_overmerge_ok` and `human_subjective_ok` for every group, either by editing the packet JSON or downloading it from the HTML form, validate it and promote the expectation file:

```bash
python scripts/human_review_packet.py --validate-packet var/tmp/human-review-packet.json
python scripts/human_review_packet.py --apply-reviewed var/tmp/human-review-packet.json --expectations docs/benchmark-expectations.current-code-draft.json --output-expectations docs/benchmark-expectations.verified.json
```

Only the promoted file should have `human_verified=true`.

For a smaller AI timeout smoke test before re-running a full analysis job, prepare a dry-run probe from stored request payloads:

```bash
python scripts/ai_timeout_probe.py --db var/data/skysort.db --diagnostics var/tmp/realdata-rescored-diagnostics.json --limit 10 --payload-mode current --output-dir var/tmp
```

When LM Studio is running and the configured model is loaded, add `--execute` and run through the API project environment so image dependencies are available. Execution is blocked unless the configured AI base URL is `localhost`, `127.0.0.1`, or `::1`; use `--allow-remote-ai-probe` only for an explicitly approved remote-AI test.

```bash
uv run --project apps/api python scripts/ai_timeout_probe.py --db var/data/skysort.db --diagnostics var/tmp/realdata-rescored-diagnostics.json --limit 10 --payload-mode current --timeout-seconds 60 --execute --output-dir var/tmp
```

This writes `var/tmp/ai-timeout-probe.md` and `.json`. Stored replay remains available with `--payload-mode stored` for regression diagnosis, but acceptance evidence should use `--payload-mode current` so the probe measures the current contact-sheet prompt/schema/image shape. The latest current-payload probe with `ai_timeout_seconds=60` and `ai_max_tokens=1024` is `var/tmp/ai-timeout-probe-current-max-tokens.md`; it executed 10/10 payloads locally with `timeout_rate=0.0` and `json_schema_failure_rate=0.0`, improving over the old diagnostic timeout baseline `0.1227`.

To compare grouping thresholds before changing runtime settings, prepare a lightweight candidate fixture and run:

```bash
python scripts/grouping_validate.py --fixture docs/grouping-validation.example.json --output-dir var/tmp
```

After a real analysis job has completed, generate the same comparison plus DB-backed diagnostics without re-reading the original photos:

```bash
python scripts/grouping_validate.py --db var/data/skysort.db --job-id job_xxx --output-dir var/tmp --stem grouping-diagnostics --write-fixture
```

Omit `--job-id` to use the latest job. Add `--rescore-technical` and run through the API project environment when you need non-destructive current-code technical/rating diagnostics from the original photo paths:

```bash
uv run --project apps/api python scripts/grouping_validate.py --db var/data/skysort.db --output-dir var/tmp --stem realdata-rescored-diagnostics --write-fixture --rescore-technical
```

The DB report includes current group counts, single/small group counts, adjacent group time-gap distributions, threshold sweep comparisons, technical score distributions, simulated current-code rating distribution, group-level technical score spread, AI response status by phase, JSON parse failures, replay-adjusted current-parser JSON/schema failure projections, timeouts, and `ai_eval_failed` counts.

Custom threshold sweeps can be passed repeatedly:

```bash
python scripts/grouping_validate.py --db var/data/skysort.db --scenario current:8:0.8 --scenario time-12s:12:0.8 --output-dir var/tmp
```

Latest local DB diagnostic (`var/tmp/realdata-diagnostics.md`, job `job_36530e48ab`, 2,846 photos) shows the new simulated grouping path reducing the old DB grouping from 903 groups / 353 single groups / 356 two-to-four-photo groups to 227 groups / 71 single groups / 50 two-to-four-photo groups under the current sweep. The non-destructive rescore diagnostic (`var/tmp/realdata-rescored-diagnostics.md`) recomputes current technical metrics from the DB photo paths and shows simulated current-code ratings at `star1_or_reject_rate=0.137` versus the persisted old-job `0.9986`. The same report replays stored failed AI responses through the current parser and normalization path, projecting JSON/schema failures down from `54/220 = 0.2455` to `30/220 = 0.1364`; the current-payload probe is the acceptance evidence for current prompt/schema behavior and passes at `json_schema_failure_rate=0.0`. The current-payload timeout probe (`var/tmp/ai-timeout-probe-current-max-tokens.md`) also passes with `timeout_rate=0.0` after setting `max_tokens=1024` on AI evaluation payloads. Visual confirmation is still required before accepting that no separate scenes were over-merged.

## Current Constraints

- Group merge/split is available as a Phase 2 operation surface and marks affected results stale instead of auto-finalizing them.
- SSE progress events are not implemented; progress polling is the primary path.
- The grouping heuristic uses capture proximity plus stored lightweight visual features: full pHash/dHash/aHash Hamming similarity and color histogram similarity. Group boundaries store a `boundary_reason`, and adjacent small groups can be marked `merge_suggested` for review.
- Technical scores are calibrated for burst review with high-edge-region sharpness, subject-weighted clipping ratios, group-relative ranks, candidate quality, and reject risk. Real-data acceptance still needs a benchmark run to confirm distribution spread and reject behavior.
- AI responses retry JSON recovery up to two times and then settle as `ai_eval_failed` instead of fabricating fallback scores.
- Schema-invalid AI responses are also saved as `ai_eval_failed` and do not finalize semantic scores.
- ExifTool is required for actual write-back. Without it, export remains in preview mode.
- PNG is display-only in Phase 1 and excluded from XMP write-back.
- ARW metadata is sourced from the embedded preview when available; tags not present there remain `null` rather than blocking the job.
- Settings changes that affect scoring are snapshotted per job, so a full re-run with new thresholds creates a new analysis job instead of mutating old results.
- OpenRouter credentials are env-only and are never returned by `GET /api/settings` or stored in `settings.json`.
- Phase 1 resume policy is new-job rerun with cache/result reuse; same-job mid-stage resume is deferred. Running jobs support graceful cancel, which preserves partial results and marks the job `canceled`.

## XMP Safety Policy

- ARW files are written via XMP sidecar only.
- JPEG files are limited to evaluation-related XMP tags.
- Existing metadata is preserved; only SkySort evaluation fields are targeted.
- `reject` maps to `xmp:Rating = -1`.
- `pick`, `best_cut`, and `reviewed` use `skysort:*` namespace fields.

## Notes For Further Work

- Phase 2 targets group merge/split, stronger filtering/search, improved retry behavior, and performance tuning.
- For acceptance-style validation, keep a reusable benchmark set with expected best and reject examples under versioned review notes.
