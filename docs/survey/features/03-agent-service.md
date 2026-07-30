# 03. Foundry Agent Service

[← 機能一覧 TOP](./README.md)

> **最終更新:** 2026-07-30(2026-07-29 の初版を一次情報に当てて検証・訂正。訂正内容は [TOP の更新履歴](./README.md#更新履歴)参照)

## 概要

Foundry Agent Service は Responses API を単一エントリポイントとするエージェント構築・実行のマネージドプラットフォーム。**サービス本体は GA**(「Foundry Agent Service is generally available (GA). Some sub-features are in public preview.」)。ただし旧世代(Agents v1 / Assistants API)の廃止と、Memory・Routines 等の新プレビュー機能の追加が同時進行しており、**「GA だが足元が動いている」状態**である点に注意。

**用語マッピング(v1 → v2)**(出典: https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/migrate ):

| 旧(v1 / Assistants) | 新(v2) | 補足 |
|---|---|---|
| Threads | Conversations | メッセージだけでなく item のストリームを格納 |
| Messages | Conversation Items | `conversations.items.create()` が `messages.create()` を置換 |
| Runs | Responses | 入力 item→出力 item。ツールコールループは明示管理 |
| Assistants | Agents(Agent Versions) | エージェント定義は `create_version()`。自動バージョンスナップショット |

## 機能一覧

| 機能名 | 説明 | ステータス | ポータル | CLI | Python SDK | 出典 | 備考 |
|---|---|---|---|---|---|---|---|
| Foundry Agent Service(v2、新 Foundry) | Responses API ベースのエージェント構築・実行マネージドプラットフォーム | GA(一部サブ機能はパブリックプレビュー) | 対応(新ポータル、New Foundry トグル) | 専用 `az` 拡張なし(`az rest` / azd で代替) | `azure-ai-projects` 2.x(>=2.3.0) | https://learn.microsoft.com/en-us/azure/foundry/agents/overview ・ https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/limits-quotas-regions | v1 (classic) とは別物。SDK は 1.x と非互換 |
| Agents v1 / classic | 旧 Assistants API ベースのエージェント(Threads/Runs) | 非推奨 → **2027-03-31 廃止** | classic ポータルのみ | — | `azure-ai-projects` 1.x / `azure-ai-agents` | https://learn.microsoft.com/en-us/azure/foundry-classic/agents/whats-new | 「Agents (classic) are now deprecated and will be retired on March 31, 2027」 |
| Assistants API (Azure OpenAI) | ステートフルな Assistants/Threads API | 非推奨 → **2026-08-26 廃止** | classic のみ | — | OpenAI SDK beta | https://learn.microsoft.com/en-us/azure/foundry-classic/openai/concepts/assistants | 新 Agent Service(Responses API)へ移行 |
| Prompt agents | 宣言的(instructions+model+tools)に定義するエージェント。ランタイムコード不要 | GA | 対応 | REST / `az rest` | 対応(`PromptAgentDefinition`。C#/TS/Java/REST も) | https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/prompt-agent | エージェントは自動でバージョンスナップショット |
| Hosted agents | 自前コード(Agent Framework / LangGraph / OpenAI Agents SDK / Anthropic SDK 等)をコンテナ/zip で持ち込み Foundry が実行 | GA(「As of azure-ai-projects 2.3.0 on the GA v1 API, hosted agents are generally available」) | 対応(playground)。デプロイは azd / VS Code / SDK 中心 | **azd** `microsoft.foundry` 拡張(`az cognitiveservices agent` は廃止) | 対応(`create_version_from_code` 等) | https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents ・ https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/quickstart-hosted-agent | **初期プレビュー基盤は 2026-08-20 でサポート終了(要再デプロイ)**。Python / C# のみ。31 リージョン。コンテナプロトコル 1.0.0 は非推奨(2.0.0 へ)。**⚠ hosted agent はエージェント定義にツールを直付けできない**(「Adding tools directly to hosted agent's definition is not supported. We recommend using toolboxes in Foundry」。`create_version` の `tools` パラメータは削除済み)→ **Toolbox 経由が前提** |
| Multi-agent workflows(ビジュアル) | ポータルの視覚的ワークフロービルダー(sequential / group chat / human-in-the-loop、Power Fx) | プレビュー、かつ **2026-12-01 廃止予定** | 対応(新ポータル) | 記載なし | 記載なし(YAML エクスポート→Agent Framework へ) | https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/workflow | 「Microsoft Foundry is retiring workflows on December 1, 2026」。移行先: Microsoft Agent Framework(推奨)/ Logic Apps / A2A |
| Connected agents | 主エージェントからサブエージェント呼び出し(v1 機能) | 新 Foundry では**提供なし**(classic はパブリックプレビューのまま廃止対象) | classic のみ | — | — | https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/migrate | 移行ガイドに「Connected Agents: No(Recommendation: A2A tool)」 |
| A2A 対応(受信エンドポイント+A2A ツール) | エージェントを A2A protocol (v1.0/v0.3) エンドポイントとして公開/呼び出し | パブリックプレビュー | 未対応(「isn't yet configurable in the Foundry portal」) | REST (`az rest`) | 対応(agent card 設定は REST のみ) | https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/enable-agent-to-agent-endpoint | v1.0 は JSONRPC のみ、テキストのみ、ストリーミング非対応、Entra 認証必須 |
| Memory | 長期記憶のマネージドサービス(user profile / chat summary / procedural の3種、抽出→統合→検索) | パブリックプレビュー | メモリ検索ツールのアタッチは可(ストア管理のポータル画面は記載なし) | 記載なし | 対応(C#/TS/Java/REST も。API version `2025-11-15-preview`) | https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/what-is-memory ・ https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/memory-usage | 2026年6月にプレビュー拡充。VNet 非対応。19 リージョン。クォータ: 100 scope/store、10,000 memories/scope。プレビュー中は課金体系変更の可能性明記 |
| Routines | タイマー/cron/イベント(GitHub issue)トリガーでエージェントを自動起動。1トリガー+1アクション | パブリックプレビュー | 対応 | **azd** routines 拡張(プレビュー) | 対応(C#/JS SDK プレビュー版。REST は `Foundry-Features: Routines=V1Preview` ヘッダー必須) | https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/routines ・ https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/use-routines | リージョン限定。多段オーケストレーションは対象外(→workflow / Agent Framework) |
| Agent optimizer | 評価データセットに対して hosted agent の instructions / skills / tool 説明 / モデル選定を自動改善 | **限定プレビュー(Limited preview)** — GA 一覧表の表記。単なる public preview ではなく利用可否が絞られる | 対応(Agents > Optimize タブで結果閲覧) | **azd**(`azd ai agent optimize`) | 記載なし(azd 中心) | https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agent-optimizer-overview | **hosted agents(Responses protocol)専用**。Norway East 以外の hosted agent リージョン |
| M365 Copilot / Teams への公開 | 安定エンドポイントを Teams アプリマニフェスト化して M365 / Teams のエージェントストアへ公開 | GA(「the generally available publish flow」) | 対応(公開はポータルか REST) | 記載なし | 記載なし(公開自動化は REST) | https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/publish-copilot | Bot Service リソース必要(`Microsoft.BotService`)。組織公開は M365 管理者承認。パブリックネットワーク無効時の扱いは公式間で表記揺れ(publish-copilot ページは「ポータル不可・REST のみ」、configure-private-link〈2026-07-28 更新〉は「公開ネットワーク無効でも公開可」)。旧 Agent Applications 形式は新規公開不可(要フォーマット移行) |
| Agent catalog(テンプレート) | 事前構築エージェントマニフェスト集(旧: Discover > Agents) | 要確認 — 確認 URL: https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agent-catalog | — | — | — | 同左 | 当該 URL は現在プロンプトエージェントのクイックスタートへリダイレクトされ、新旧両ドキュメントの TOC からも消失(tool catalog のみ残存)。azd の `agent.manifest.yaml` も非推奨化済み |
| バージョニング / デプロイ・公開フロー | 自動バージョンスナップショット、version selector によるトラフィック割当、安定エンドポイント、Entra Agent Registry 配布 | GA(サービス本体の一部) | 対応(Details タブ / Publish ボタン) | azd / `az rest` | 対応(`update_details`+`FixedRatioVersionSelectionRule`) | https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents ・ https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/publish-copilot | prompt agent は FixedRatio でトラフィック%指定可。hosted agent は 1 バージョン 100% のみ(分割不可)。有効リビジョン上限 1,000/agent |

## 廃止・移行期限(このカテゴリ分)

| 期限 | 対象 | 対応 |
|---|---|---|
| 2026-08-20 | Hosted agents 初期プレビュー基盤 | 新基盤へ再デプロイ( https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/migrate-hosted-agent-preview ) |
| 2026-08-26 | Assistants API | Responses API(Agents v2)へ移行 |
| 2026-12-01 | ビジュアル Workflows | Microsoft Agent Framework 等へ移行(YAML は hosted agent としてなら実行継続可) |
| 2027-03-31 | Agents (classic) | Agents v2 へ移行 |
| **日付未公表(Planned / TBD)** | **Agent Applications(旧 publishing モデル)** | 新オブジェクトモデル(Agent に統合。作成時点で安定エンドポイント・プロトコル構成・エージェント ID・agent card を持つ)へ移行。**レガシー ID のエージェント(`agent.identity == null`)はインプレース昇格不可で作り直しが必要。**旧モデルはステートレスな `POST /responses` のみ利用可で `/conversations`・`/files`・`/vector_stores`・`/containers` にアクセスできない( https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/migrate-agent-applications ) |
| **日付未公表(猶予期間あり)** | コンテナプロトコル 1.0.0 | 2.0.0 へ。猶予期間後は 1.0.0 のエージェントへのリクエストがブロックされる。2.0.0 でないと 1 セッション内の複数ユーザー多重化(`x-agent-user-id`)ができない |

## 補足ノート

**1. v1→v2 移行の実務ポイント**
移行ツール( https://aka.ms/agent/migrate/tool )はコード構造を変換するが、**状態データ(過去の runs / threads / messages)は移行されない**(新 API 側で会話を作り直す)。新 API では会話/レスポンスは OpenAI クライアント(`project.get_openai_client()`)、エージェント作成・バージョン管理はプロジェクトクライアント、という**2クライアント構成**。旧 `create_agent()` は SDK v2.0.0 で削除済み。

**2. ツールの GA/プレビュー差(移行ガイドの対比より)**
新 Foundry では MCP=GA、Web Search=GA(limits ページに preview 扱いの記述もありリージョン依存)、A2A=パブリックプレビュー、Image Generation=パブリックプレビュー、Work IQ=プレビュー。**Azure Functions ツールと Deep Research ツールは新 Foundry の対比表上「なし」扱い**の記述があるが、ツールカタログ側の詳細は [04-tools-knowledge](./04-tools-knowledge.md) を参照(Deep Research は非推奨が確定、後継は `o3-deep-research` モデル+Web search)。

**3. CLI サーフェスの注意**
`az cognitiveservices agent` は公式間で表記揺れ: Agent Service ドキュメントは削除済みとして azd を案内する一方、**Azure CLI リファレンスには Core・Preview として現存**(hosted agent の create/logs/start/stop 等。 https://learn.microsoft.com/en-us/cli/azure/cognitiveservices )。開発フローの主線は **azd**(`azd ai agent init/run/invoke` 等 — コマンド列挙もページ間で揺れあり)、管理操作は `az rest`。ほかに VS Code の Foundry Toolkit、コーディングエージェント用 Microsoft Foundry Skill がクイックスタートの正式手段。

**4. 課金・クォータ概要**
- Prompt agents: 呼び出しごとの推論+ツール使用分(コンピュート課金なし)。
- Hosted agents: 上記+**アクティブセッション中の CPU/メモリ消費**で課金(セッション毎サンドボックス、アイドル 15 分でスケールゼロ)。
- サービス固定リミット(引き上げ不可): ファイル 512MB・計 300GB、メッセージ 10 万/スレッド、ツール 128/agent、リビジョン 1,000/agent など。
- セットアップは basic(Microsoft 管理ストレージ)/ standard(BYO Cosmos DB・AI Search・Storage)の2種。
- 料金: https://azure.microsoft.com/pricing/details/foundry-agent-service/

**5. その他**
Azure Government (US Gov Virginia/Arizona) でも一部機能利用可。RBAC ロール名改称中(Azure AI User → Foundry User 等。ID・権限は不変)。
