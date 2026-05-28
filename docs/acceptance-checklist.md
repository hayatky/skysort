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

- Copy `docs/benchmark-expectations.example.json` and fill 10 to 20 representative bursts with expected best/reject/pick entries.
- Set `human_verified=true` only after visual review; machine-generated drafts must remain `human_verified=false`.
- Optionally run `python scripts/benchmark_seed.py --db var/data/skysort.db --limit 20 --output var/tmp/benchmark-expectations-draft.json` to create a draft from a completed job, then use the generated `var/tmp/benchmark-expectations-draft.html` thumbnail review page to visually verify and edit every expected value.
- If a current-code rescored diagnostics fixture exists, run `python scripts/benchmark_seed.py --db var/data/skysort.db --limit 20 --score-fixture var/tmp/realdata-rescored-diagnostics-fixture.json --output docs/benchmark-expectations.current-code-draft.json --html-output var/tmp/benchmark-expectations-current-code-draft.html --strip-review-items` to maintain a docs-compatible machine draft without local file review metadata.
- Prefer `match.relative_paths` for every burst so group over-fragment and over-merge metrics can be computed.
- Export JSON results from `POST /api/export/results`.
- Run `python scripts/benchmark_diff.py --expectations <expectations.json> --results <results.json> --root <import-root> --output-dir var/tmp`.
- Review generated JSON, CSV, and Markdown reports under `var/tmp`.
- Confirm the report metrics: `best_match_rate`, `reject_recall`, `missing_pick_count`, `unexpected_pick_count`, `group_overfragmented_count`, `group_overmerged_count`, `ai_failure_rate`, and `review_operation_count`.
- When persisted technical scores are from an old job, run `uv run --project apps/api python scripts/grouping_validate.py --db var/data/skysort.db --output-dir var/tmp --stem realdata-rescored-diagnostics --write-fixture --rescore-technical` to generate non-destructive current-code rating evidence from the DB photo paths.
- Review the same diagnostics report for replay-adjusted JSON/schema failure projections; stored failed responses that normalize successfully should lower the projected current-code failure rate before a fresh AI run.
- Run `python scripts/acceptance_gate.py --baseline-diagnostics var/tmp/baseline-diagnostics.json --diagnostics var/tmp/fresh-diagnostics.json --benchmark-diff var/tmp/benchmark-diff.json --review-packet var/tmp/human-review-packet.json --timeout-probe var/tmp/ai-timeout-probe.json --output-dir var/tmp` to summarize pass/fail/review-needed status for the remaining real-data acceptance gates. The baseline argument should point to the old run when validating reduced rating, JSON failure, and timeout rates.
- Run `uv run --project apps/api python scripts/review_montages.py --review-html var/tmp/benchmark-expectations-current-code-draft.html --output-dir var/tmp/human-review-montages`, then run `python scripts/human_review_packet.py --expectations docs/benchmark-expectations.current-code-draft.json --benchmark-diff var/tmp/benchmark-current-code-draft-diff.json --acceptance-gate var/tmp/acceptance-gate.json --review-html var/tmp/benchmark-expectations-current-code-draft.html --review-montage-dir var/tmp/human-review-montages --diagnostics var/tmp/realdata-rescored-diagnostics.json --output-dir var/tmp` to produce the final human-review checklist and static HTML review form for over-merge and subjective benchmark evidence. Timeout rerun instructions appear only while the current acceptance gate still fails `ai_timeout_rate`.
- After editing the packet JSON, run `python scripts/human_review_packet.py --validate-packet var/tmp/human-review-packet.json`. If ready, run `python scripts/human_review_packet.py --apply-reviewed var/tmp/human-review-packet.json --expectations docs/benchmark-expectations.current-code-draft.json --output-expectations docs/benchmark-expectations.verified.json`, then rerun benchmark diff and acceptance gate against the verified expectation file.
- For timeout smoke testing, run `python scripts/ai_timeout_probe.py --db var/data/skysort.db --diagnostics var/tmp/realdata-rescored-diagnostics.json --limit 10 --payload-mode current --output-dir var/tmp` first, then rerun with `uv run --project apps/api python scripts/ai_timeout_probe.py --db var/data/skysort.db --diagnostics var/tmp/realdata-rescored-diagnostics.json --limit 10 --payload-mode current --timeout-seconds 60 --execute --output-dir var/tmp` when the local VLM is available. The execute path refuses non-localhost AI endpoints unless `--allow-remote-ai-probe` is explicitly supplied.

## Manual Review In UI

- Progress failures show stage, file/photo/group target, reason, and retryability.
- Global Review shows stale, missing, and AI failed counts and filters.
- Global Review includes an AI Complete filter backed by `ai_complete=true` so final AI-scored items can be reviewed separately from provisional items.
- Group and Global Review filters are backed by API requests and expose page controls.
- Group Detail shows stale reason, missing status, AI failed status, and reanalysis actions.
- Settings explains that changes are snapshotted only into new analysis jobs.
- `apps/web/src` remains TypeScript-only after tests/builds; generated JS must not reappear there.
