# maf-ports — awesome-llm-apps を MAF + Foundry へ移植する検証ラボ

[awesome-llm-apps](https://github.com/Shubhamsaboo/awesome-llm-apps)(ローカル: `~/oss/awesome-llm-apps`)のエージェント構成を **Microsoft Agent Framework (MAF)** に書き換え、**Foundry のトレーシング・評価**を組み込み、**Bicep でデプロイ可能**にする長期ラボ。

目的は網羅移植ではなく、**「MAF/Foundry で楽になること・苦しくなること」の境界を、多様な協調パターンで体感して記録する**こと(→ [docs/learning-plan.md](../../docs/learning-plan.md) の技術選定判断力)。

## ドキュメント

| ファイル | 内容 |
| --- | --- |
| [INVENTORY.md](./INVENTORY.md) | 元リポジトリ 156 プロジェクトの棚卸しと移植ロードマップ(Wave 1/2) |
| [PORTING.md](./PORTING.md) | 移植規約(FW 対応表、テスト・トレース・評価・Bicep の必須要件、1サイクル手順) |
| [infra/shared.bicep](./infra/shared.bicep) | 共有基盤(Foundry リソース+プロジェクト+モデル+App Insights)。**課金あり・1回だけデプロイ** |

## 進捗(Wave 1)

| # | ポート | 元 | パターン | 実装 | オフラインテスト | Bicep | ライブスモーク | 学び記録 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 共有基盤 | — | — | — | — | 済 | **デプロイ済**(rg-maf-ports / gpt-5.4-mini / 疎通確認済) | — |
| 1 | trend-analysis | starter/ai_startup_trend_analysis_agent | 逐次WF | 済 | 済(9件) | 済 | 済(3段完走+トレース) | [済](./ports/trend-analysis/README.md) |
| 2 | mixture-of-agents | starter/mixture_of_agents | 並列+集約 | 済 | 済(13件) | 済 | 済(4並列+集約+トレース) | [済](./ports/mixture-of-agents/README.md) |
| 3 | research-handoff | starter/openai_research_agent | handoff | 済 | 済(31件) | 済 | 済(handoff+レポート+トレース) | [済](./ports/research-handoff/README.md) |
| 4 | corrective-rag | rag/corrective_rag | 補正ループ+AI Search | 済 | 済(37件) | 済(AI Search Free+埋め込み) | 済(両経路+トレース) | [済](./ports/corrective-rag/README.md) |
| 5 | travel-memory | memory/ai_travel_agent_memory | Foundry Memory | 済 | 済(23件) | 済 | 済(記憶往復139s+RBAC知見) | [済](./ports/travel-memory/README.md) |
| 6 | github-mcp | mcp/github_mcp_agent | リモート MCP | 済 | 済(21件) | 済 | **要 GITHUB_TOKEN**(手順は port README) | [済](./ports/github-mcp/README.md) |
| 7 | game-design-team | agent_teams/ai_game_design_agent_team | Swarm ハンドオフ | — | — | — | — | — |

## 実行の前提

1. **共有基盤デプロイ(Phase 0・課金発生)**: `az group create -n rg-maf-ports -l japaneast` → `az deployment group create -g rg-maf-ports -f infra/shared.bicep -p baseName=... modelName=... modelVersion=...`(モデルは [features/02-models.md](../../docs/survey/features/02-models.md) で現行の安価 GA モデルを確認して指定)
2. 各ポートは `uv sync` → `uv run pytest`(オフライン)→ `.env` 設定後 `uv run pytest -m live`(ライブスモーク)
3. 使わない期間は `az group delete -n rg-maf-ports` で全撤去可(ステートレス設計)

## 関連

- 実装パターンの先行例: [labs/agentic-search-maf](../agentic-search-maf/)(Rust 製リサーチエージェントの MAF 移植。ScriptedAgent テストパターンの出典)
- Foundry 機能の可否判断: [docs/survey/features/](../../docs/survey/features/README.md)
