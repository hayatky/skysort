# SkySort

SkySort is a local-first AI photo culling tool for aviation photographers. This repository now contains the Phase 1 MVP scaffold defined in [docs/plan.md](/Users/yuta/Git/skysort/docs/plan.md): import, preview generation, EXIF extraction, grouping, technical scoring, AI-assisted review, manual overrides, and dry-run-first XMP export.

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

1. Start LM Studio and load the configured model, or export OpenRouter settings.
2. Start the API.
3. Start the web app.

OpenRouter example:

```bash
export SKYSORT_AI_PROVIDER=openrouter
export SKYSORT_AI_BASE_URL=https://openrouter.ai/api/v1
export SKYSORT_AI_MODEL_NAME=openai/gpt-5-nano
export SKYSORT_ALLOW_REMOTE_AI=true
export SKYSORT_AI_API_KEY=your_api_key
export SKYSORT_AI_REFERER=https://example.com/skysort
export SKYSORT_AI_TITLE=SkySort
```

## Backend Setup

```bash
cd /Users/yuta/Git/skysort
uv sync --project apps/api
uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head
./scripts/dev-api.sh
```

API defaults:

- URL: `http://127.0.0.1:8000`
- OpenAPI: `http://127.0.0.1:8000/openapi.json`
- Media files: served from `var/cache`

Important runtime behavior:

- SQLite lives in `var/data/skysort.db`
- thumbnails and previews live in `var/cache`
- application logs live in `var/logs/app.log`
- AI health is checked before `POST /api/jobs/{job_id}/analyze`
- remote AI endpoints are blocked unless `allow_remote_ai=true`
- XMP export defaults to `dry_run=true`
- unchanged files reuse deterministic preview/thumbnail cache keys derived from path + hash + size + mtime
- ARW preview generation prefers the embedded JPEG preview and falls back to `rawpy` demosaic only when needed

## Frontend Setup

```bash
cd /Users/yuta/Git/skysort
pnpm install
./scripts/dev-web.sh
```

The Vite dev server runs on `http://127.0.0.1:5173` and proxies `/api` to the backend on port `8000`.

## Phase 1 Implemented Surfaces

### Backend

- `POST /api/import`
- `POST /api/jobs/{job_id}/analyze`
- `GET /api/jobs/{job_id}/progress`
- `GET /api/jobs/{job_id}/failures`
- `GET /api/ai/health`
- `GET /api/groups`
- `GET /api/groups/{group_id}`
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
- Group overview
- Group detail review with keyboard shortcuts
- Global review with virtualized list
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
cd /Users/yuta/Git/skysort
uv run python -m compileall -q apps/api/src
uv run --project apps/api pytest
pnpm --filter @skysort/web test
pnpm generate:client
```

The repository includes backend tests for import diffing, RAW preview selection, API validation, grouping order, and XMP helpers, plus frontend Vitest coverage for the main Phase 1 routes.

`pnpm generate:client` regenerates the canonical OpenAPI snapshot at `packages/client/openapi.json`.

## Benchmark Validation

Before production use, validate against a benchmark burst set with expected best/reject examples.

1. Prepare 10 to 20 representative burst groups containing obvious best cuts, obvious reject frames, and at least one burst larger than 6 images.
2. Run a fresh import and analysis with the target LM Studio model and keep `dry_run=true` for XMP export.
3. Compare group best picks against the benchmark expectation list and review every expected reject frame in the global review screen.
4. Record mismatches with the group ID, expected outcome, actual outcome, and whether the issue came from grouping, technical scoring, or AI ranking.
5. Re-run one unchanged benchmark folder and confirm that previews and unchanged evaluations are reused instead of being recomputed.

## Current Constraints

- Group merge/split is intentionally excluded from Phase 1.
- SSE progress events are not implemented; progress polling is the primary path.
- The grouping heuristic currently uses capture proximity plus image hash similarity. The embedding-based extension point is deferred.
- AI responses retry JSON recovery up to two times and then settle as `ai_eval_failed` instead of fabricating fallback scores.
- ExifTool is required for actual write-back. Without it, export remains in preview mode.
- PNG is display-only in Phase 1 and excluded from XMP write-back.
- ARW metadata is sourced from the embedded preview when available; tags not present there remain `null` rather than blocking the job.
- Settings changes that affect scoring are snapshotted per job, so a full re-run with new thresholds creates a new analysis job instead of mutating old results.
- OpenRouter credentials are env-only and are never returned by `GET /api/settings` or stored in `settings.json`.

## XMP Safety Policy

- ARW files are written via XMP sidecar only.
- JPEG files are limited to evaluation-related XMP tags.
- Existing metadata is preserved; only SkySort evaluation fields are targeted.
- `reject` maps to `xmp:Rating = -1`.
- `pick`, `best_cut`, and `reviewed` use `skysort:*` namespace fields.

## Notes For Further Work

- Phase 2 targets group merge/split, stronger filtering/search, improved retry behavior, and performance tuning.
- For acceptance-style validation, keep a reusable benchmark set with expected best and reject examples under versioned review notes.
