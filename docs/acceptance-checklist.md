# SkySort Acceptance Checklist

このチェックリストは、テスト運用前に Codex または開発者がローカルで確認できる項目をまとめる。実データの主観評価、Windows 11 実機確認、3,000 枚規模の負荷測定は別の運用メモで扱う。

## Automated Checks

- Backend syntax: `uv run python -m compileall -q apps/api/src`
- Backend tests: `uv run --project apps/api pytest`
- Frontend tests: `pnpm --filter @skysort/web test`
- Frontend typecheck: `pnpm --filter @skysort/web typecheck`
- Frontend build: `pnpm --filter @skysort/web build`
- OpenAPI snapshot: `pnpm generate:client`

## API Contract

- `GET /api/groups` supports `filter`, `sort`, `page`, and `page_size`.
- `GET /api/photos` supports `filter`, `page`, `page_size`, and `include_missing=true`.
- `POST /api/export/results` applies review filters before writing JSON or CSV.
- `POST /api/export/xmp` validates `conflict_policy` and supports filter-based targets.

## AI Evaluation

- JSON block recovery succeeds without retry when recoverable JSON is embedded in text.
- Invalid JSON is retried up to two additional attempts.
- Parse failure or schema-invalid response is stored as `ai_eval_failed`.
- `schema_version`, `ranking[]`, `best_photo_id`, and `drop_candidates[]` are validated before values are applied.
- Large groups are compared in chunks and final winner selection preserves `target_photo_ids_json` audit data.

## XMP Dry Run And Safety

- Run XMP export with `dry_run=true` first.
- Confirm `target_count`, `writable_count`, `blocked_count`, `conflict_count`, `write_candidates[]`, `blocked_items[]`, and `conflicts[]`.
- ARW writes use `.xmp` sidecar output and never write the RAW file directly.
- JPEG writes use `-overwrite_original` only for evaluation-related fields.
- PNG files are blocked as `unsupported_format`.
- `conflict_policy=fail` stops non-dry-run writes when conflicts exist.

## Benchmark Diff

- Copy `docs/benchmark-expectations.example.json` and fill expected best/reject/pick entries.
- Export JSON results from `POST /api/export/results`.
- Run `python scripts/benchmark_diff.py --expectations <expectations.json> --results <results.json> --root <import-root> --output-dir var/tmp`.
- Review generated JSON, CSV, and Markdown reports under `var/tmp`.

## Manual Review In UI

- Progress failures show stage, file/photo/group target, reason, and retryability.
- Global Review shows stale, missing, and AI failed counts and filters.
- Group and Global Review filters are backed by API requests and expose page controls.
- Group Detail shows stale reason, missing status, AI failed status, and reanalysis actions.
- Settings explains that changes are snapshotted only into new analysis jobs.
- `apps/web/src` remains TypeScript-only after tests/builds; generated JS must not reappear there.
