# 継続評価(evaluation_rules)— 挙動発見メモ(2026-08-04 実測)

環境: gpt-5.4-mini / japaneast / azure-ai-projects 2.4.0
critique-loop はバッチ評価(その場でランを作る)を検証済み。ここはイベント駆動の自動評価。

## 発見(挙動)

- **継続評価ルールは prompt agent スコープ必須**。filter なしで作ると:
  `(UserError) Filter.AgentName is required and cannot be empty.`(target: filter.agentName)
  → survey には無い制約。**生の `responses.create` には掛けられない**。`EvaluationRuleFilter(agent_name=...)` で対象エージェントを指定し、その agent 経由の応答だけが評価対象になる。
- 配線自体は SDK で完結: `client.evals.create`(builtin.coherence)→ `project.evaluation_rules.create_or_update(id, EvaluationRule(event_type=RESPONSE_COMPLETED, filter=EvaluationRuleFilter(agent_name=...), action=ContinuousEvaluationRuleAction(eval_id, max_hourly_runs, sampling_rate)))`。
- 作成したルールは `list` に現れる(action.type=`continuousEvaluation`、enabled=True)。ただし **list の戻りで `event_type` が None**(create の戻りには入るのに list では欠ける)= SDK/サービスの表現揺れ。
- `systemData.createdAt` は `MM/DD/YYYY hh:mm:ss` 文字列(ISO ではない)。

## つまりどころ

- **自動評価ランは `client.evals.runs.list(eval_id)` では観測できなかった**(agent 経由の応答 3 件生成後 120 秒ポーリングして 0 件)。継続評価の結果は evals のラン一覧ではなく **Monitor ダッシュボード / App Insights 側に集計される**設計と推測(survey 05:「Monitoring 領域はプレビュー」)。バッチ評価(critique-loop)とは結果の見え先が違う。
- したがって「継続評価を SDK だけで結果取得してアサートする」CI 的な使い方は現状しにくい。設定は SDK、結果確認はポータル、という分業になる。
- `max_hourly_runs`(既定上限 100/時)があるので、高トラフィックの agent では全応答は評価されない(サンプリング)。`sampling_rate=1.0` でも hourly 上限が効く。

## SI 判断メモ

- 継続評価は「prompt agent を本番運用し、その品質を継続監視する」シナリオ専用。maf-ports のようなクライアント側(MAF)オーケストレーションの応答には掛けられないので、**継続評価を要件にするなら agent を prompt agent(サービス側)で建てる**という構成上の縛りが先に来る。
- PoC の品質確認はバッチ評価(critique-loop の evals API 直叩き)で十分。継続評価は「本番監視」フェーズの機能、と割り切る。

## 2026-09-29 追記(最新化チェック・ライブ未検証)

- **上の「自動ランは evals.runs.list で観測できない」は probe 側の設定不備だった可能性が高い。** 公式の継続評価手順(how-to-monitor-agents-dashboard 2026-09-03 版)と SDK サンプル `sample_continuous_evaluation_rule.py` は、eval を `data_source_config={"type": "azure_ai_source", "scenario": "responses"}`(data_mapping なし)で作り、ランは `openai_client.evals.runs.list(eval_id, order="desc")` に `continuousevalrun_*` として現れて `report_url` を持つ、としている。2026-08-04 の probe は critique-loop(バッチ評価)と同じ `custom` + `item_schema` + `data_mapping` で eval を作っていた。
- もう 1 つの前提「**プロジェクト MI に Foundry User(旧 Azure AI User)**」は roles.bicep で付与済みだったので、差分はデータソースの形のみ。App Insights 接続も main.bicep で作成済み。
- probe を公式の形に修正し、ポーリングを 300 秒に延長・`report_url` を表示するようにした。**再デプロイして再実測するまで、上の「つまりどころ」1〜2 点目は未確定として扱う。**
- 変わらない点: ルールの `filter.agent_name` 必須(公式サンプルも `EvaluationRuleFilter(agent_name=...)`)、既定 100 回/時の上限(公式トラブルシューティング表にも記載)、継続評価は Monitoring 領域ごとプレビュー。
- SDK 2.7.0 では `allow_preview=True` を付けると `evaluation_rules.create_or_update` に `Foundry-Features: Evaluations=V1Preview` が付く。付けずに 403 `preview_feature_required` が返った場合は `AIProjectClient(..., allow_preview=True)` にする(2026-09-03 版の公式サンプルは付けていない)。
- 出典: https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/how-to-monitor-agents-dashboard / https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/ai/azure-ai-projects/samples/evaluations/sample_continuous_evaluation_rule.py
