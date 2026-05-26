# SkySort TODO

このファイルは、`docs/plan.md` と現状実装の差異のうち、Codex がこのリポジトリ内で実装・自動テスト追加・ドキュメント整備として進められる作業を整理したものです。

実データの準備、3,000 枚規模の実測、Windows 11 実機確認、写真の主観評価、実機 ExifTool による原本近傍ファイルへの検証など、人間の環境・判断・データ提供が必要なタスクは含めません。

## 優先度の目安

- P0: テスト運用開始前に実装または自動検証できるようにすべきもの
- P1: テスト運用中の信頼性・作業効率に直結する実装改善
- P2: Phase 2 相当だが、早期に入れると検証が進めやすいもの

## P0: 受入前に必要な差異解消

### API 契約

- [x] `GET /api/groups` に `filter`、`sort`、`pagination` を実装する。
  - `docs/plan.md` の API-006 は大量件数前提で絞り込み・並び替え・ページングを想定している。
  - 現状は `job_id` のみで全件返却するため、件数増加時に UI/API ともに重くなりやすい。
- [x] `POST /api/export/results` の `filters` を実装する。
  - 現状はスキーマに `filters` があるが、実装では実質未使用。
  - reject、pick、best_cut、reviewed、rating、evaluation_status などで絞り込めるようにする。
- [x] `POST /api/export/xmp` の対象条件と `conflict_policy` を厳密化する。
  - `photo_ids` 以外に、rating/reject/pick/best/reviewed などの条件指定を扱えるようにする。
  - `conflict_policy` は `skip`、`fail`、`overwrite_safe_fields` の列挙値として API バリデーションする。
  - `fail` 指定時に競合検出後の応答と書き込み停止が明確になるようにする。

### AI 応答と監査

- [x] AI 応答 JSON の schema version を応答本文にも必須化し、保存時に検証する。
  - 現状は DB 側に `response_schema_version` を保存しているが、AI が返した JSON 自体の schema version は必須検証していない。
- [x] AI 応答の構造スキーマ検証を追加する。
  - `best_photo_id`、`ranking[]`、`drop_candidates[]`、`photo_id`、`semantic_score`、`reason` などを型付きで検証する。
  - 不正構造は `ai_eval_failed` として扱い、壊れた値で評価を確定しない。
- [x] AI JSON 失敗時のリトライ状態をテストで明確にする。
  - JSON ブロック抽出、最大2回再試行、`ai_eval_failed` 終端をそれぞれテストする。
  - `response_status = succeeded / retried / ai_eval_failed` が監査テーブルに残ることを確認する。

### 再開性・状態管理

- [x] ジョブ中断後の再開方針を明確化する。
  - 現状はキャッシュ再利用・前回ジョブ再利用はあるが、途中停止ジョブの本格 resume ではない。
  - 実装方針として「新規ジョブとして再実行し、キャッシュを再利用する」か、途中ジョブの resume を実装するかを `docs/` に明記する。
- [x] 入力ファイル更新・削除・設定変更時の stale 表示を強化する。
  - 更新済みファイル、missing、設定変更により再評価が必要な項目を UI で確認できるようにする。
  - stale 状態からの写真単位・グループ単位再解析導線を確認する。
- [x] 合成画像を使った取り込み・再取り込みの自動テストを追加する。
  - 新規追加、更新済み、削除済み、missing、キャッシュ再利用の判定をテストする。
  - 大量実データではなく、生成可能な小規模 fixture で差分検出ロジックを確認する。

### XMP 書き戻し安全性

- [x] ExifTool 呼び出しをモックし、ARW sidecar 書き戻しコマンドの自動テストを追加する。
  - ARW 本体を直接変更せず、`.xmp` sidecar 出力指定になることを確認する。
- [x] ExifTool 呼び出しをモックし、JPEG 埋め込み XMP 書き戻しコマンドの自動テストを追加する。
  - JPEG のみ `-overwrite_original` を使うことを確認する。
  - `dry_run=true` では書き込みコマンドが実行されないことを確認する。
- [x] XMP 競合検出の自動テストを追加する。
  - `inspect_existing_tags` をモックし、既存 `XMP:Rating`、`skysort:*` が異なる場合に `conflicts[]` へ出ることを確認する。
  - `skip`、`fail`、`overwrite_safe_fields` の API 応答を確認する。
- [x] PNG が XMP 書き戻し対象外であることを UI/API/テストで明確にする。
- [x] パス処理の単体テストを追加する。
  - 空白、日本語、相対パス、symlink 解決、存在しないパス、ディレクトリ以外のパスを確認する。
  - Windows 実機確認は対象外とし、可能な範囲で `pathlib` ベースのロジックを自動テストする。

## P1: テスト運用の信頼性向上

### ベンチマーク支援

- [x] ベンチマーク期待値ファイルのスキーマとテンプレートを追加する。
  - group 名または相対パス単位で、期待 best/reject/pick を記録できる形式にする。
  - 実データの選定や期待値入力は対象外とし、Codex はテンプレートと検証ロジックを用意する。
- [x] ベンチマーク結果の差分レポート生成スクリプトを追加する。
  - 期待値ファイルと API/export 結果を比較し、CSV/JSON/Markdown で差分を出力する。
  - 実行ログやローカル生成物は `var/` 配下に置く。

### AI 評価品質

- [x] 6枚超バーストの段階比較をモック AI で自動テストする。
  - チャンクごとの winner 選出と最終比較が期待通りに呼ばれることを確認する。
  - 中間比較の対象集合が `target_photo_ids_json` に残ることを確認する。
- [x] AI 候補絞り込みの基準を設定・テストしやすくする。
  - 現状は技術スコア順と reject 閾値を中心に候補化している。
  - 候補選抜の境界条件を単体テストできるようにする。
- [x] AI 応答失敗時もレビュー継続できることを自動テストする。
  - `ai_eval_failed` の写真・グループが暫定評価のまま API レスポンスに残ることを確認する。

### 並列度と性能

- [x] `ai_concurrency` を実処理に反映する。
  - 初期値は 1 のままでよいが、設定値が無視されないようにする。
  - ローカル VLM の過負荷を避ける上限とキュー制御を入れる。
- [x] `image_processing_concurrency` を実処理に反映する。
  - プレビュー生成・メタデータ抽出・技術評価の並列度を AI 推論と分離する。
  - SQLite トランザクションは短く保つ。
- [x] 長時間ジョブの進捗粒度を改善する。
  - 現在処理中ステージ、処理済み件数、失敗件数が大きな入力でも追いやすいようにする。
  - 失敗一覧に photo/group ID、ファイル名、retryable を表示する。

### UI/UX

- [x] グループ一覧と全体レビューにページングまたは無限読み込みを導入する。
  - API の pagination と合わせて実装する。
- [x] review フィルタを API 側と揃える。
  - 現状の UI 内フィルタだけでなく、API で絞り込んで返せるようにする。
- [x] stale、missing、ai_eval_failed、conflict などの状態を UI で明確に表示する。
- [x] XMP export 画面で dry-run 差分、blocked、conflicts を確認しやすくする。
- [x] 設定変更後に「既存ジョブへは反映されず、新規解析ジョブで snapshot される」ことを UI で明示する。

### 開発運用

- [x] `apps/web/src` の `.ts/.tsx` と追跡済み `.js` 並存を整理する。
  - `pnpm --filter @skysort/web build` により追跡済み `.js` が再生成され、差分が出る。
  - TS を正本にして `.js` を生成物扱いにするか、追跡を続けるなら生成手順を明確化する。
- [x] frontend build/typecheck の副作用が出ない構成にする。
  - `noEmit`、`outDir`、`tsbuildinfo` などを確認する。
- [x] 受入チェックリストを `docs/` に追加する。
  - backend tests、frontend tests、OpenAPI generation、benchmark diff、XMP dry-run の自動確認を含める。
  - Windows 実機確認や実データ負荷試験など、人間が実施する項目はこの TODO ではなく別の運用メモへ分離する。

## P2: Phase 2 相当だがテスト運用で早めに欲しい機能

### グループ修正

- [x] グループ結合 API を実装する。
  - `POST /api/groups/{group_id}/merge`
  - 結合後は関連評価を自動確定せず `stale` にする。
- [x] グループ分割 API を実装する。
  - `POST /api/groups/{group_id}/split`
  - 分割後は best_cut を自動で安易に確定せず、再解析または手動確認へ誘導する。
- [x] グループ結合・分割 UI を実装する。
  - 操作前に dry-run 的な確認表示を出す。
- [x] グループからの除外または単独グループ化を実装する。
  - 明らかに別カットが混ざった場合の逃げ道として必要。

### 検索・絞り込み

- [x] 高速フィルタ・検索を実装する。
  - rating、reject、pick、best_cut、reviewed、ai_eval_failed、stale、camera/lens、日付範囲、ファイル名。
- [x] 削除候補レビュー専用ビューを強化する。
  - reject と ★1 を混同しない。
  - 削除候補としての確認・解除を高速に行えるようにする。

### 再試行・再解析

- [x] 失敗項目の個別 retry UI/API を追加する。
  - `retryable=true` の job failure から写真単位・グループ単位で再実行できるようにする。
- [x] AI timeout、JSON parse failure、preview/exif failure を分けて再試行できるようにする。
- [x] 再解析 scope の挙動を UI で選べるようにする。
  - `technical_only`
  - `ai_only`
  - `full`

### グルーピング精度

- [x] embedding-based grouping の拡張点を実装または明確化する。
  - 現状は撮影時刻と pHash 由来の簡易類似度が中心。
  - テスト運用で誤グループが多い場合の改善先として用意する。
- [x] グルーピング設定の検証ツールを作る。
  - time proximity、similarity threshold を変えたときの group 数、単独 group 数、平均 group size を比較できるようにする。

## 継続確認項目

- [x] `docs/plan.md` と `README.md` の差異を定期的に確認する。
- [x] API 変更時は `pnpm generate:client` を実行し、`packages/client/openapi.json` を更新する。
- [x] 仕様変更を伴う実装では `AGENTS.md` の固定ルールが古くなっていないか確認する。
- [x] ローカル完結、原本保護、remote AI opt-in、ARW 非破壊の方針を維持する。
