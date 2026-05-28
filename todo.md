# SkySort 実データテスト後の改善 TODO

約3,000枚規模の実データテストで確認された問題を、連写画像のグルーピング、AIによるベストカット選定、半自動レビューUIの実用性改善に向けてタスク化する。

## 0. 現状分析メモ

- 最新ジョブでは 2,846 枚が 903 グループに分割されている。
- 平均グループサイズは 3.15 枚。
- 1枚グループは 353 件。
- 4枚以下のグループは 709/903 件で、グループ全体の約 78.5%。
- 4枚以下のグループに含まれる写真は 1,289/2,846 枚で、写真全体の約 45.3%。
- 隣接グループ間の時間差が 4 秒以内の境界が 676/902 件あり、時間的には同一連写に見えるのに分割されている可能性が高い。
- 技術スコアは `technical_score_total` が 25.38 から 34.22 に集中し、中央値 30.84、90 パーセンタイル 32.08 で、星評価や候補選抜の材料として十分に差が出ていない。
- AI評価は最新ジョブ時点で `semantically_scored=107/2846` に留まり、`json_parse_failed=54`、`ai_timeout=27` が出ている。

## 1. P0: 計測と診断基盤

- [x] ジョブ完了後にグルーピング品質レポートを生成する
  - group 数
  - 1枚 group 数
  - 2から4枚 group 数
  - 平均 group size
  - group size 分布
  - 隣接 group 間の時間差分布
  - 時間差が閾値以内なのに分割された境界数
  - 分割理由が time gap か similarity gap かの内訳
- [x] `scripts/grouping_validate.py` を DB の実ジョブから直接 fixture を生成できるように拡張する
- [x] `time_proximity_seconds` と `similarity_threshold` のスイープ結果を比較できるレポートを追加する
- [x] 技術スコア分布レポートを生成する
  - sharpness
  - motion_blur
  - highlight/shadow clip
  - total score
  - group 内順位
- [x] AI評価レポートを生成する
  - phase 別成功/失敗数
  - json parse failure 数
  - timeout 数
  - ai_eval_failed 数
  - group_compare 成功率
  - single 評価成功率
- [x] 実データ検証時に `var/tmp` へ Markdown/JSON で診断結果を出力する

受入条件:

- [x] 2,000枚以上の既存ジョブに対して、写真本体を再解析せず DB から診断レポートを生成できる
- [x] 閾値変更前後の group 数、1枚 group 数、平均 group size を比較できる

## 2. P0: グルーピングの過分割修正

- [x] 現在の `similarity_seed` ベースの類似度判定を見直す
  - 現状は pHash の先頭16bitを 0-1 に潰しており、航空機連写の類似判定として不安定
  - full pHash の Hamming distance を保存・比較する
  - dHash/aHash など複数の軽量視覚特徴を併用する
  - 色ヒストグラム差分を追加する
- [x] グルーピングを「前の1枚との比較」だけで切らない方式に変更する
  - group 先頭との比較
  - group 代表との比較
  - 直近数枚の最大類似度
  - 連写中の一時的な見た目変化で鎖が切れないようにする
- [x] 初期グループは時間・撮影順を強く優先し、類似度は明らかな別シーン検出に使う方針へ変更する
- [x] `time_proximity_seconds` の初期値を再検討する
  - 現状 4 秒
  - 実データ診断では 8 秒、12 秒程度も比較対象にする
- [x] group 境界に `boundary_reason` を保存できるようにする
  - `time_gap`
  - `similarity_gap`
  - `metadata_gap`
  - `manual_split`
- [x] 隣接グループの自動結合候補検出を追加する
  - group 間時間差が短い
  - camera/lens/focal_length が近い
  - 代表画像同士が類似
  - group size が小さい
- [x] 自動結合候補を `merge_suggested` または stale reason として UI に出せるようにする

受入条件:

- [x] 実データで 1枚 group 数と 4枚以下 group 数が大幅に減る
- [ ] 明らかに別シーンの写真が不自然に結合されない
  - `var/tmp/human-review-packet.md` に 20 burst の視覚確認対象を集約。machine benchmark では `group_overmerged_count=0` だが、`human_overmerge_ok` は未確認のため未完了。
  - `scripts/human_review_packet.py --validate-packet` / `--apply-reviewed` を追加。全 group の `human_overmerge_ok=true` が揃うまで verified expectations を作れないようにした。
  - `scripts/review_montages.py` と `var/tmp/human-review-montages/` を追加。review packet から各 group の montage path を辿れるため、人間が over-merge を確認しやすくなった。
  - `var/tmp/human-review-packet.html` に montage 付きチェックフォームを出力し、JSON 直接編集なしで reviewed packet を作れるようにした。
- [x] 隣接4秒以内で細切れになった group をレポートで特定できる

## 3. P0: 技術評価スコアの再校正

- [x] `compute_technical_metrics` の sharpness/motion_blur スケールを見直す
  - 現状は sharpness が 0から5 程度に潰れ、100点スケールとして機能していない
- [x] 絶対スコアだけでなく group 内相対スコアを導入する
  - group 内 sharpness rank
  - group 内 exposure rank
  - group 内 reject risk
- [x] 中央固定領域だけでなく、航空機が存在しそうな高エッジ領域を優先して sharpness を計算する
- [x] 露出破綻は白飛び/黒つぶれ率の単純減点だけでなく、航空機写真で許容される背景白飛びと被写体破綻を分ける方針を検討する
- [x] 技術評価から直接★評価を決めるのではなく、暫定の `candidate_quality` と `reject_risk` を出す
- [x] rating 閾値を実データ分布に合わせて再設計する

受入条件:

- [x] 同一連写内で、明らかにブレた写真とシャープな写真の順位差が出る
- [x] 技術スコアが候補選抜に使える程度に分散する
- [x] ほぼ全画像が★1相当になる状態を解消する
  - `var/tmp/realdata-rescored-diagnostics.md` の非破壊 current-code rescore で、2,846枚の simulated current-code ratings が `star1_or_reject_rate=0.137` まで改善（旧 persisted job は `0.9986` のまま）

## 4. P0: AI比較入力とプロンプト改善

- [x] group compare 用に contact sheet 生成を追加する
  - 各画像に A/B/C などの視覚ラベルを焼き込む
  - ラベルと photo_id の対応表をプロンプトに含める
  - 画像順と JSON の ID 対応が崩れないようにする
- [x] `group_compare_v1` を航空機連写比較向けに全面改訂する
  - 機体切れ
  - ピント/ブレ
  - 構図
  - 機体姿勢
  - 背景や障害物
  - 同一構図内で残す価値
  - best と keep と reject の違い
- [x] AI応答 schema を拡張する
  - `best_photo_id`
  - `keep_photo_ids`
  - `reject_photo_ids`
  - `ranking`
  - `confidence`
  - `problem_tags`
  - `reason_by_photo_id`
- [x] JSON parse failure を減らすため、schema とプロンプトの整合を再確認する
- [x] timeout を実用値に見直す
  - 現状 `ai_timeout_seconds=10.0`
  - ローカルVLMの group compare では短すぎる可能性が高い
- [x] AI評価失敗時に暫定評価のまま残すだけでなく、review queue で優先表示する

受入条件:

- [x] group compare の photo_id 取り違えが起きにくい
- [x] JSON/schema failure 率が実データで低下する
  - `var/tmp/realdata-rescored-diagnostics.md` の stored failed response replay で、current-code normalization 後の projected json/schema failure が `54/220 = 0.2455` から `30/220 = 0.1364` へ低下（24件を schema-valid として回復）
  - current-payload probe `var/tmp/ai-timeout-probe-current-max-tokens.md` では、current prompt/schema/normalization と `ai_max_tokens=1024` で `json_schema_failure_rate=0.0`（0/10）まで低下。
- [x] AIが best だけでなく keep/reject を区別して返せる

## 5. P1: AI評価フローの再設計

- [x] 現在の「技術スコア上位を最大6枚比較」方式を見直す
- [x] 連写 group 全体を対象に、明らかな失敗だけ事前除外し、候補は広めに残す
- [x] 6枚超 group では非重複 chunk 勝者だけでなく、重複窓または上位候補再比較を行う
- [x] group が細切れ疑いの場合、AI評価前に結合候補として扱う
- [x] `best_cut` は group 内で1枚のみ維持し、複数 keep/pick と明確に分ける
- [x] AI信頼度が低い group は自動確定せず review priority を上げる
- [x] AI評価完了前でもレビューできるが、final と provisional の表示をより明確に分ける

受入条件:

- [x] 大きな連写 group でも best 候補が chunk 境界に依存しない
- [x] 細切れ group に対して AI が局所最適な best を量産しない
- [x] AI未完了/失敗/低信頼が UI で明確に区別される

## 6. P1: Burst Review UI の新設

- [x] グループ単位レビューを主画面にした `Burst Review` 画面を追加する
- [x] 1行1グループの横長サムネイルストリップを表示する
  - AI best を強調
  - keep/pick を強調
  - reject 候補を暗転
  - stale/AI failed/merge suggested を表示
- [x] group size、撮影時間幅、隣接 group との時間差、AI confidence を同じ行で確認できるようにする
- [x] ワンクリック操作を追加する
  - Accept AI
  - Set Best
  - Keep Also
  - Reject
  - Mark Reviewed
  - Merge Prev
  - Merge Next
  - Split Here
- [x] キーボード操作を group review 向けに拡張する
  - 上下: group 移動
  - 左右: group 内 photo 移動
  - Enter: AI判断を承認
  - B: best 指定
  - K/P: keep/pick
  - X: reject
  - M: 隣接結合
  - S: split
- [x] 現在の ID 手入力 merge UI を補助機能に下げ、隣接 group 操作を優先する
- [x] 3,000枚規模で一覧性が落ちないよう仮想スクロールを使う

受入条件:

- [x] AIが残す/ベストとした判断を group 単位で連続確認できる
- [x] 細切れ group を UI 上で効率よく結合できる
- [x] 1 group あたりのレビュー操作が数秒で完了できる

## 7. P1: レビューキューとフィルタ改善

- [x] レビュー対象を目的別 queue に分ける
  - AI判断を確認
  - 細切れ疑い
  - 1枚 group
  - AI失敗
  - 低信頼
  - reject候補
  - best未確定
  - stale
- [x] group filter に以下を追加する
  - [x] min/max group size
  - [x] merge_suggested
  - [x] best missing
  - [x] ai confidence range
  - [x] adjacent time gap range
- [x] photo filter に以下を追加する
  - [x] problem tag
  - [x] keep/reject recommendation
  - [x] user override only
- [x] review progress を group 単位で表示する
  - [x] reviewed groups
  - [x] accepted AI groups
  - [x] manually changed groups
  - [x] unresolved groups

受入条件:

- [x] 大量写真でも「次に確認すべきもの」が明確になる
- [x] 1枚 group や細切れ疑いをまとめて処理できる

## 8. P2: ベンチマークと受入基準

- [x] 実データから 10から20 個の代表 burst を選び、期待 best/reject/keep を `docs/benchmark-expectations.example.json` 互換形式で管理する
  - `docs/benchmark-expectations.current-code-draft.json` に実データ由来 20 burst を管理。`var/tmp/realdata-rescored-diagnostics-fixture.json` の current-code technical score を使い、20/20 が expected_best/expected_pick、9/20 が expected_reject を持つ。主観 ground truth 化は別受入条件として未完了。
- [x] 既存の `scripts/benchmark_diff.py` に group 品質評価を追加する
- [x] ベンチマーク指標を定義する
  - [x] best 一致率
  - [x] reject 再現率
  - [x] keep 過不足
  - [x] group 過分割率
  - [x] group 過結合率
  - [x] AI失敗率
  - [x] review 操作数
- [x] 実データ再実行時の比較レポートを `var/tmp` に保存する
- [x] README または docs に実データ検証手順を追記する

受入条件:

- [x] グルーピング変更、プロンプト変更、UI変更の効果を同じ指標で比較できる
- [ ] 主観評価の改善を、最低限の期待セットで再現確認できる
  - `var/tmp/human-review-packet.md` と `var/tmp/benchmark-expectations-current-code-draft.html` で確認対象を生成済み。`docs/benchmark-expectations.current-code-draft.json` は `human_verified=false` のため未完了。
  - `var/tmp/human-review-montages/` の group 別 contact sheet を packet に紐づけ、expected_best/reject/pick の視覚確認を進めやすくした。
  - HTML form から各 group の `human_subjective_ok` と notes を記録し、download した packet を validation/promotion に使える。
  - `human_subjective_ok=true` が全 group で揃った packet だけを `docs/benchmark-expectations.verified.json` へ昇格できるようにした。

## 9. 暫定運用メモ

実装改修前に再テストする場合は、以下を診断目的で試す。ただし、現在の類似度実装自体が弱いため根本解決ではない。

- [x] `similarity_threshold` を下げて過分割がどの程度減るか確認する
- [x] `time_proximity_seconds` を 8 秒または 12 秒に広げて比較する
- [x] `ai_timeout_seconds` を 60 秒以上に設定して AI timeout の減少を確認する
  - 設定既定値は 60 秒へ変更済み。旧診断の timeout rate は `0.1227`。
  - `scripts/ai_timeout_probe.py` を追加。stored request payload replay と current payload rebuild の両方で replayable sample を作り、LM Studio 起動時に `--execute` で timeout rate を測定できる。
  - stale stored payload replay は `var/tmp/ai-timeout-probe.md` で `timeout_rate=0.2`（2/10）、120秒でも `var/tmp/ai-timeout-probe-120s.md` で `timeout_rate=0.2`（2/10）だった。
  - current payload に `max_tokens=1024` を付け、`var/tmp/ai-timeout-probe-current-max-tokens.md` の 10 payload 実行で `timeout_rate=0.0`（0/10）と `json_schema_failure_rate=0.0`（0/10）を確認。旧診断 timeout `0.1227` より低下。
- [x] AI評価完了前の暫定評価と最終評価を混同しないよう、レビュー対象を AI 完了済みに絞って確認する

## 10. 実装順序案

1. 診断レポートと閾値スイープを追加する
2. グルーピング類似度を full hash / 複数特徴に置き換える
3. 隣接 group の merge suggestion を追加する
4. 技術スコアを group 内相対評価へ再校正する
5. contact sheet と新 group compare prompt を追加する
6. AI応答 schema を keep/reject/confidence/problem_tags 対応に拡張する
7. Burst Review UI を追加する
8. レビューキューと実データベンチマークを整備する
