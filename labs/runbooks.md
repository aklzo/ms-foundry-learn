# labs 実行ガイド索引

> **最終更新:** 2026-09-30(Port 15 delegated-access-hosted を追加し、同日ライブ検証)/ 2026-09-29(全ラボに実行ガイドを新設。同日に全ラボを agent-framework 1.19 / openai 3.20 系でオフライン再検証)
> **正は各 `docs/runbook.md`(Markdown)。** 人間用 HTML(同じディレクトリの `runbook.html`、本ページは `runbooks.html`)は `python3 labs/tools/build_runbooks.py` で生成する。HTML は直接編集しない。

各ラボ・ポートの「どう動かすか」と「何が確認できれば OK か」をまとめた実行ガイドの一覧。設計判断や移植の学びは各 README にあり、実行ガイドはそこから**手順と確認観点だけ**を切り出している。

## 使い方

- **HTML で読む**: ブラウザで各 `runbook.html` を開く。「確認観点」の表と一覧のチェックボックスは**ブラウザ内に保存**される(ページ右上に「確認済み n / N」)。確認作業の途中経過用で、共有はされない
- **まずオフライン**: どのラボも Azure なしのオフラインテスト(またはオフライン検証)から始められる。ライブ実行は Azure リソースの再作成が必要で**課金が発生する**(検証後に全リソースを削除済みのため)
- **Markdown と HTML の同期確認**: `python3 labs/tools/build_runbooks.py --check`(差分があれば終了コード 1)

## 共通の前提

| 項目 | 内容 |
| --- | --- |
| ツール | [uv](https://docs.astral.sh/uv/)(Python は uv が取得)。ライブ実行は Azure CLI(`az login`)も |
| Azure | maf-ports は**共有基盤を先に作る**([共有基盤の実行ガイド](./maf-ports/infra/docs/runbook.md))。他のラボは各ラボの `infra/` で個別に作る。検証後は RG ごと削除する運用(ステートレス設計) |
| 接続情報 | maf-ports は `labs/maf-ports/.env`(雛形 `.env.example`。git 管理外)。他のラボは各ラボの README / 実行ガイドを参照 |
| 検証状態 | オフライン: 2026-09-29 に全ラボ再検証済み。ライブ: 2026-07〜09 の各ラボ初回検証時のみ(**最新依存でのライブ再検証は未実施** — 各ガイドの「ライブ未検証で残るリスク」参照)。例外は Port 15 と共有基盤で、2026-09-30 に最新依存(agent-framework 1.19)でライブ確認済み |

## 一覧

### maf-ports(awesome-llm-apps の MAF + Foundry 移植 14 パターン+新規パターン 1)

| # | 対象 | パターン | Azure 固有リソース(共有基盤以外) | オフライン検証 | 実行ガイド |
| --- | --- | --- | --- | --- | --- |
| 0 | 共有基盤 | Foundry+プロジェクト+モデル+App Insights | —(これ自体が共有基盤) | `az bicep build` | [runbook](./maf-ports/infra/docs/runbook.md) |
| 1 | trend-analysis | 逐次ワークフロー | なし | 9 passed | [runbook](./maf-ports/ports/trend-analysis/docs/runbook.md) |
| 2 | mixture-of-agents | 並列+集約(fan-out / fan-in) | なし | 13 passed | [runbook](./maf-ports/ports/mixture-of-agents/docs/runbook.md) |
| 3 | research-handoff | ルーティング(構造化出力+switch-case) | なし | 31 passed | [runbook](./maf-ports/ports/research-handoff/docs/runbook.md) |
| 4 | corrective-rag | 補正ループ RAG | AI Search(Free)+埋め込みデプロイ | 37 passed | [runbook](./maf-ports/ports/corrective-rag/docs/runbook.md) |
| 5 | travel-memory | Foundry Memory | Memory ストア(スクリプトで作成) | 23 passed | [runbook](./maf-ports/ports/travel-memory/docs/runbook.md) |
| 6 | github-mcp | リモート MCP | なし(GitHub PAT) | 21 passed | [runbook](./maf-ports/ports/github-mcp/docs/runbook.md) |
| 7 | game-design-team | Swarm 型ハンドオフ | なし | 30 passed(orchestrations extra 込み) | [runbook](./maf-ports/ports/game-design-team/docs/runbook.md) |
| 8 | data-analysis-ci | Code Interpreter | なし | 24 passed | [runbook](./maf-ports/ports/data-analysis-ci/docs/runbook.md) |
| 9 | critique-loop | 評価駆動ループ+クラウド評価 | なし(評価はプロジェクト上) | 44 passed | [runbook](./maf-ports/ports/critique-loop/docs/runbook.md) |
| 10 | db-routing-iq | Foundry IQ(ナレッジベース) | AI Search(Basic)+ナレッジベース | 54 passed | [runbook](./maf-ports/ports/db-routing-iq/docs/runbook.md) |
| 11 | hn-briefing-hosted | hosted agent+Routines | hosted agent・Routine | 48 passed | [runbook](./maf-ports/ports/hn-briefing-hosted/docs/runbook.md) |
| 12 | claim-voice-live | Voice Live | なし(マネージドモデル) | 77 passed | [runbook](./maf-ports/ports/claim-voice-live/docs/runbook.md) |
| 13 | services-agency | 通信グラフ制約(agent-as-tool) | なし | 69 passed | [runbook](./maf-ports/ports/services-agency/docs/runbook.md) |
| 14 | governed-agent | middleware によるガバナンス・監査 | なし | 65 passed | [runbook](./maf-ports/ports/governed-agent/docs/runbook.md) |
| 15 | delegated-access-hosted | hosted agent × 利用者の委任権限(アプリ管理の OBO)で文書・基幹 API を制御。判定点 APIM と MCP サーバー自身を比較 | Container Apps(MCP サーバー 2 系統)+APIM Consumption+AI Search Free+ACR / Entra アプリ登録 2 つ・カスタムロール | 239 passed(ライブ 2026-09-30 済) | [runbook](./maf-ports/ports/delegated-access-hosted/docs/runbook.md) |

### その他の検証ラボ

| 対象 | 内容 | オフライン検証 | 実行ガイド |
| --- | --- | --- | --- |
| agentic-search-maf | 自己評価型リサーチエージェント(Rust 版の MAF 移植。ScriptedAgent テストパターンの出典) | 50 passed | [runbook](./agentic-search-maf/docs/runbook.md) |
| foundry-probes | maf-ports に乗らなかった Foundry 機能 9 本の挙動確認 probe | 静的検証(py_compile・ruff・SDK シグネチャ照合) | [runbook](./foundry-probes/docs/runbook.md) |
| cu-video-rag | Content Understanding 動画 × AI Search × RAG の精度検証 | コーパス検証+オフライン指標の再計算(2026-09-03 版とバイト一致) | [runbook](./cu-video-rag/docs/runbook.md) |

## 2026-09-29 の最新化チェックで変わったこと(要点)

- **依存**: agent-framework-core 1.12〜1.13 → **1.19**、openai 2.5x → **3.20**(cu-video-rag は langchain 0.3 系の制約で openai 2.x のまま)。`mcp<2` は MAF 1.19 自身の要求で維持。`agent-framework-foundry` 1.13.1 は `azure-ai-projects<2.7.0` を要求するため、hn-briefing-hosted は 2.6.1 止まり
- **コード改修**: Routines の `Foundry-Features: Routines=V1Preview` ヘッダーを削除(Port 11。Routines は GA)/ MCP の認証ヘッダーを MAF 1.19 の `static_headers` に移行(Port 6・10)/ Foundry IQ の Search API を `2026-08-01-preview` に(Port 10)/ hosted agent のコンテナ依存を明示ピン(Port 11)/ Claude・Ollama を Chat Completions クライアントに(agentic-search-maf の潜在バグ)/ 継続評価 probe を公式の形に修正(foundry-probes 09、要再実測)
- **記述の訂正**: AI Search Free でもセマンティックランカーの無料枠が使える(Port 4)/ `AgentThread` → `AgentSession`(Port 13)ほか。詳細は各 README の「検証結果(2026-09-29 最新化チェック)」
- **アーキ図**: 各ポートの `docs/architecture.png` を日本語+処理番号の v2 スタイルに更新(ヘルパーは [tools/README](./maf-ports/tools/README.md))
