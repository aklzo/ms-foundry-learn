# maf-ports — awesome-llm-apps を MAF + Foundry へ移植する検証ラボ

[awesome-llm-apps](https://github.com/Shubhamsaboo/awesome-llm-apps)(ローカル: `~/oss/awesome-llm-apps`)のエージェント構成を **Microsoft Agent Framework (MAF)** に書き換え、**Foundry のトレーシング・評価**を組み込み、**Bicep でデプロイ可能**にする長期ラボ。

目的は網羅移植ではなく、**「MAF/Foundry で楽になること・苦しくなること」の境界を、多様な協調パターンで体感して記録する**こと(→ [docs/learning-plan.md](../../docs/learning-plan.md) の技術選定判断力)。

## ドキュメント

| ファイル | 内容 |
| --- | --- |
| [INVENTORY.md](./INVENTORY.md) | 元リポジトリ 156 プロジェクトの棚卸しと移植ロードマップ(Wave 1/2) |
| [PORTING.md](./PORTING.md) | 移植規約(FW 対応表、テスト・トレース・評価・Bicep の必須要件、1サイクル手順) |
| [infra/shared.bicep](./infra/shared.bicep) | 共有基盤(Foundry リソース+プロジェクト+モデル+App Insights)。**課金あり・1回だけデプロイ** |
| [infra/docs/architecture.png](./infra/docs/architecture.png) | 共有基盤のアーキテクチャ図(各ポートの図は `ports/<port>/docs/architecture.png`。再生成手順は [tools/README.md](./tools/README.md)) |

## 進捗(Wave 1: #1-7 / Wave 2: #8-12 / Wave 3: #13-14 / 新規パターン: #15)

**実行ガイド(runbook):** 各ポートの実行手順と確認観点は `ports/<port>/docs/runbook.md`(人間用 HTML は同じディレクトリの `runbook.html`、全ラボの索引は [../runbooks.md](../runbooks.md))。**2026-09-29 に全ポートを agent-framework 1.19 / openai 3.20 でオフライン再検証済み**(ライブ再検証は未実施。改修点は各 README の「検証結果(2026-09-29 最新化チェック)」)。

| # | ポート | 元 | パターン | 実装 | オフラインテスト | Bicep | ライブスモーク | 学び記録 | 実行ガイド |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 共有基盤 | — | — | — | — | 済 | 検証完了後 **2026-07-31 に削除済み**(コスト停止。Bicep+スクリプトで再現可) | — | [runbook](./infra/docs/runbook.md) |
| 1 | trend-analysis | starter/ai_startup_trend_analysis_agent | 逐次WF | 済 | 済(9件) | 済 | 済(3段完走+トレース) | [済](./ports/trend-analysis/README.md) | [runbook](./ports/trend-analysis/docs/runbook.md) |
| 2 | mixture-of-agents | starter/mixture_of_agents | 並列+集約 | 済 | 済(13件) | 済 | 済(4並列+集約+トレース) | [済](./ports/mixture-of-agents/README.md) | [runbook](./ports/mixture-of-agents/docs/runbook.md) |
| 3 | research-handoff | starter/openai_research_agent | handoff | 済 | 済(31件) | 済 | 済(handoff+レポート+トレース) | [済](./ports/research-handoff/README.md) | [runbook](./ports/research-handoff/docs/runbook.md) |
| 4 | corrective-rag | rag/corrective_rag | 補正ループ+AI Search | 済 | 済(37件) | 済(AI Search Free+埋め込み) | 済(両経路+トレース) | [済](./ports/corrective-rag/README.md) | [runbook](./ports/corrective-rag/docs/runbook.md) |
| 5 | travel-memory | memory/ai_travel_agent_memory | Foundry Memory | 済 | 済(23件) | 済 | 済(記憶往復139s+RBAC知見) | [済](./ports/travel-memory/README.md) | [runbook](./ports/travel-memory/docs/runbook.md) |
| 6 | github-mcp | mcp/github_mcp_agent | リモート MCP | 済 | 済(21件) | 済 | 済(リモートMCP接続+クエリ18.8s) | [済](./ports/github-mcp/README.md) | [runbook](./ports/github-mcp/docs/runbook.md) |
| 7 | game-design-team | agent_teams/ai_game_design_agent_team | Swarm ハンドオフ | 済 | 済(30件) | 済 | 済(リング+ループ完走+トレース) | [済](./ports/game-design-team/README.md) | [runbook](./ports/game-design-team/docs/runbook.md) |
| 8 | data-analysis-ci | starter/ai_data_analysis_agent | Code Interpreter | 済 | 済(24件) | 済 | 済(CSV分析14.7s+正答検証) | [済](./ports/data-analysis-ci/README.md) | [runbook](./ports/data-analysis-ci/docs/runbook.md) |
| 9 | critique-loop | advanced_llm/gpt_oss_critique_improvement_loop | 評価駆動ループ | 済 | 済(44件) | 済 | 済(ループ+クラウド評価完走) | [済](./ports/critique-loop/README.md) | [runbook](./ports/critique-loop/docs/runbook.md) |
| 10 | db-routing-iq | rag/rag_database_routing | Foundry IQ | 済 | 済(54件) | 済(AI Search Basic) | 済(4問ルーティング37.3s) | [済](./ports/db-routing-iq/README.md) | [runbook](./ports/db-routing-iq/docs/runbook.md) |
| 11 | hn-briefing-hosted | always_on/hn_briefing | hosted agent+Routines | 済 | 済(48件) | 済 | 済(デプロイ+invoke+ルーチンFinished) | [済](./ports/hn-briefing-hosted/README.md) | [runbook](./ports/hn-briefing-hosted/docs/runbook.md) |
| 12 | claim-voice-live | voice/insurance_claim_live_agent_team | Voice Live | 済 | 済(77件) | 済 | 済(3本: コア/WS接続/ツールループ) | [済](./ports/claim-voice-live/README.md) | [runbook](./ports/claim-voice-live/docs/runbook.md) |
| 13 | services-agency | agent_teams/ai_services_agency | 通信グラフ制約(agent-as-tool) | 済 | 済(69件) | 済 | 済(グラフ内通信75s+入れ子トレース) | [済](./ports/services-agency/README.md) | [runbook](./ports/services-agency/docs/runbook.md) |
| 14 | governed-agent | advanced_ai_agents/single_agent_apps/ai_agent_governance + multi_agent_apps/trust_gated_agent_team | ガバナンス(middleware 3 種+監査) | 済 | 済(65件) | 済 | 済(スモーク 2 本: 承認完走/実行前遮断) | [済](./ports/governed-agent/README.md) | [runbook](./ports/governed-agent/docs/runbook.md) |
| 15 | delegated-access-hosted | なし(新規パターン — hosted agent の OBO 公式手順 2026-09-28 に基づく) | 利用者の委任権限でのアクセス制御(アプリ管理 OBO+`x-client-*` 転送、判定点 APIM / MCP サーバーの比較) | 済 | 済(239件) | 済 | 済(2026-09-30: 方式 A / B × 利用者 2 人の出し分け+迂回 403+会話分離 404。検証後に全削除) | [済](./ports/delegated-access-hosted/README.md) | [runbook](./ports/delegated-access-hosted/docs/runbook.md) |

## 実行の前提

1. **共有基盤デプロイ(課金発生。Wave 1 検証後に削除済み — 再実行時は新しい RG 名で)**: `az group create -n rg-maf-ports -l japaneast` → `az deployment group create -g rg-maf-ports -f infra/shared.bicep -p baseName=... modelName=... modelVersion=...`(モデルは [features/02-models.md](../../docs/survey/features/02-models.md) で現行の安価 GA モデルを確認して指定)
2. 各ポートは `uv sync` → `uv run pytest`(オフライン)→ `.env` 設定後 `uv run pytest -m live`(ライブスモーク)
3. 使わない期間は `az group delete -n rg-maf-ports` で全撤去可(ステートレス設計)

共有基盤の詳細な実行手順と確認観点(第 2 段 roles.bicep・RBAC 伝播待ち・`.env` への転記・soft delete の purge)は [infra/docs/runbook.md](./infra/docs/runbook.md)(人間用 HTML: `infra/docs/runbook.html`)。

## 関連

- 実装パターンの先行例: [labs/agentic-search-maf](../agentic-search-maf/)(Rust 製リサーチエージェントの MAF 移植。ScriptedAgent テストパターンの出典)
- Foundry 機能の可否判断: [docs/survey/features/](../../docs/survey/features/README.md)
