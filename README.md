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
- `filter` supports rating, reject, pick, best cut, reviewed, stale, status, camera/lens, text search (`q`), filename, and capture date range conditions
- `POST /api/export/results` and `POST /api/export/xmp` apply the same review filters
- AI health is checked before `POST /api/jobs/{job_id}/analyze`
- remote AI endpoints are blocked unless `allow_remote_ai=true`
- XMP export defaults to `dry_run=true`
- XMP export validates `conflict_policy` as `skip`, `fail`, or `overwrite_safe_fields`; `fail` stops non-dry-run writes when conflicts are detected
- unchanged files reuse deterministic preview/thumbnail cache keys derived from path + hash + size + mtime
- ARW preview generation prefers the embedded JPEG preview and falls back to `rawpy` demosaic only when needed
- AI responses must include `schema_version` and the expected typed ranking/drop-candidate structure before values are applied
- `image_processing_concurrency` controls preview, metadata, and technical-score workers; `ai_concurrency` controls single-image AI calls while DB writes remain serialized

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
- `POST /api/jobs/{job_id}/analyze`
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
- Progress monitoring screen
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

Use [docs/benchmark-expectations.example.json](docs/benchmark-expectations.example.json) as the expectation template. After exporting JSON results from `POST /api/export/results`, generate diff reports with:

```bash
python scripts/benchmark_diff.py --expectations docs/benchmark-expectations.example.json --results var/tmp/example_results.json --root /path/to/import/root --output-dir var/tmp
```

To compare grouping thresholds before changing runtime settings, prepare a lightweight candidate fixture and run:

```bash
python scripts/grouping_validate.py --fixture docs/grouping-validation.example.json --output-dir var/tmp
```

## Current Constraints

- Group merge/split is available as a Phase 2 operation surface and marks affected results stale instead of auto-finalizing them.
- SSE progress events are not implemented; progress polling is the primary path.
- The grouping heuristic currently uses capture proximity plus image hash similarity behind a swappable similarity backend; embedding generation and storage are deferred.
- AI responses retry JSON recovery up to two times and then settle as `ai_eval_failed` instead of fabricating fallback scores.
- Schema-invalid AI responses are also saved as `ai_eval_failed` and do not finalize semantic scores.
- ExifTool is required for actual write-back. Without it, export remains in preview mode.
- PNG is display-only in Phase 1 and excluded from XMP write-back.
- ARW metadata is sourced from the embedded preview when available; tags not present there remain `null` rather than blocking the job.
- Settings changes that affect scoring are snapshotted per job, so a full re-run with new thresholds creates a new analysis job instead of mutating old results.
- OpenRouter credentials are env-only and are never returned by `GET /api/settings` or stored in `settings.json`.
- Phase 1 resume policy is new-job rerun with cache/result reuse; same-job mid-stage resume is deferred.

## XMP Safety Policy

- ARW files are written via XMP sidecar only.
- JPEG files are limited to evaluation-related XMP tags.
- Existing metadata is preserved; only SkySort evaluation fields are targeted.
- `reject` maps to `xmp:Rating = -1`.
- `pick`, `best_cut`, and `reviewed` use `skysort:*` namespace fields.

## Notes For Further Work

- Phase 2 targets group merge/split, stronger filtering/search, improved retry behavior, and performance tuning.
- For acceptance-style validation, keep a reusable benchmark set with expected best and reject examples under versioned review notes.
