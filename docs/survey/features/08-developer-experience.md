# 08. 開発者サーフェス(SDK / CLI / API / フレームワーク)

[← 機能一覧 TOP](./README.md)

> **最終更新:** 2026-07-29(learn.microsoft.com、PyPI / NuGet / npm / Maven の現行ページ確認)

## 概要

API は「**推論系 = v1 API(月次 `api-version` 廃止、OpenAI SDK 直結)**」と「**プロジェクト操作系 = Foundry SDK(`azure-ai-projects` 2.x)+ Microsoft Foundry REST API(v1 / v1-preview)**」の二層構造に整理された。SDK overview では接続先として Foundry SDK(`services.ai.azure.com/api/projects/...`)、OpenAI SDK(`/openai/v1`)、**Anthropic SDK**(`services.ai.azure.com/anthropic`)、Agent Framework の4系統が明示されている(出典: https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/sdk-overview )。

## API

| 機能名 | 説明 | ステータス | 詳細(言語/サーフェス差異) | 出典 | 備考 |
|---|---|---|---|---|---|
| Foundry v1 API (`/openai/v1/`) | 月次の日付型 `api-version` を廃止した次世代 API。素の OpenAI クライアントをそのまま接続でき、DeepSeek / Grok 等の他プロバイダーモデルも同一構文で呼べる | GA(2025年8月に opt-in 開始。プレビュー機能はヘッダー例 `"aoai-evals":"preview"` またはパス内 `alpha` で個別 opt-in) | Python / C# / JS / Go / Java / REST すべて OpenAI 公式 SDK + `base_url` 指定。`openai.azure.com/openai/v1` と `services.ai.azure.com/openai/v1` の両形式可。プロジェクトエンドポイント経由 `{project_endpoint}/openai/v1/responses` も可(ただし embeddings はプロジェクトエンドポイント未ルーティング) | https://learn.microsoft.com/en-us/azure/foundry/openai/api-version-lifecycle | v1 OpenAPI 3.0 spec は azure-rest-api-specs リポジトリで公開 |
| Microsoft Foundry REST API | Foundry(プロジェクト/Agents/evals/Azure OpenAI)のデータプレーン REST リファレンス | GA (v1) + v1-preview の2ビュー並存 | REST 共通 | https://learn.microsoft.com/en-us/rest/api/microsoft-foundry/ | — |

## SDK(言語別)

| 機能名 | 説明 | ステータス | 詳細 | 出典 | 備考 |
|---|---|---|---|---|---|
| Python: `azure-ai-projects` 2.x | Foundry プロジェクトの統合クライアント(Agents 作成・実行、認証済み OpenAI クライアント取得、toolbox、fine-tuning、デプロイ/接続の列挙) | GA(2.4.0、2026-07-27、Production/Stable) | 1.x は Foundry classic 用として並存。プレビュー機能はクライアント構築時 `allow_preview=True` で明示 opt-in | https://pypi.org/project/azure-ai-projects/ ・ https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/sdk-overview | 4言語の中で最も更新頻度が高い |
| Python: `azure-ai-agents` | Agent Service 単体クライアント | GA(1.1.0、2025-08-05)だが更新停滞・実質集約 | 公式に「`azure-ai-projects` の利用を推奨」と明記 | https://pypi.org/project/azure-ai-agents/ | 非推奨表記はないが実質 `azure-ai-projects` 2.x へ |
| Python: `azure-ai-inference` | 旧・モデル推論統一クライアント | 非推奨 → **2026-08-26 廃止予定**(beta のまま GA せず。最終版 1.0.0b9) | Python / C#(`Azure.AI.Inference`)/ JS(`@azure/ai-inference`)/ Java 全言語対象。移行先は OpenAI SDK + v1 API | https://learn.microsoft.com/en-us/azure/foundry-classic/foundry-models/supported-languages ・ https://pypi.org/project/azure-ai-inference/ | 「deprecated and will be retired on August 26, 2026」と明記。移行ガイド: /azure/foundry/how-to/model-inference-to-openai-migration |
| Python: `azure-ai-evaluation` | 評価 SDK(ローカル評価。詳細は [05-observability-evaluation](./05-observability-evaluation.md)) | GA(1.18.2、2026-07-22、Production/Stable) | Python 中心 | https://pypi.org/project/azure-ai-evaluation/ | ドキュメントは classic 配下に移動済み(新 Foundry は projects SDK の evals へ) |
| `openai` パッケージ(プロジェクトエンドポイント利用) | Foundry での本番推論の公式推奨ルート。v1 API で Entra ID トークン自動リフレッシュ対応(`AzureOpenAI` クライアント不要に) | GA(v1 API 経由) | Python / JS / Java / Go / C#(OpenAI .NET)全対応 | https://learn.microsoft.com/en-us/azure/foundry/openai/api-version-lifecycle | `AzureOpenAI()` ではなく素の `OpenAI()` + `base_url` が新標準 |
| C#: `Azure.AI.Projects` | .NET 統合プロジェクトクライアント | GA(2.0.1、2026-04-23。プレリリース 2.1.0-beta.4) | .NET は3パッケージ構成: `Azure.AI.Projects` + `Azure.AI.Projects.Agents` + `Azure.AI.Extensions.OpenAI`(GA)。`Azure.AI.Projects.OpenAI`(preview)と `Azure.AI.Extensions.OpenAI`(GA)は同居不可(型重複) | https://www.nuget.org/packages/Azure.AI.Projects | 1.1.0 GA は classic 用として並存 |
| JS/TS: `@azure/ai-projects` | JS/TS 統合プロジェクトクライアント | GA(2.3.1、npm latest、stable) | docs 上の対応表は 2.0.1(新 Foundry)/ 1.0.1(classic) | https://www.npmjs.com/package/@azure/ai-projects | リリース日は要確認(npm ページ 403 のためレジストリ API で版のみ確認) |
| Java: `com.azure:azure-ai-projects` | Java 統合プロジェクトクライアント | GA(2.2.0、Maven Central、stable) | `com.azure:azure-ai-agents` 2.2.0 と OpenAI Java 4.14.0 に依存 | https://central.sonatype.com/artifact/com.azure/azure-ai-projects | 4言語(Python/C#/JS/Java)すべて 2.x GA でパリティほぼ達成 |

## CLI / IaC

| 機能名 | 説明 | ステータス | 詳細 | 出典 | 備考 |
|---|---|---|---|---|---|
| Azure CLI: `az cognitiveservices` | Foundry リソース(account)・プロジェクト・接続・モデルデプロイの管理コマンド群 | account / project / connection / deployment / commitment-plan: GA。`az cognitiveservices agent`(hosted agent 管理)・managed-compute-deployment・managed-network: プレビュー | Azure CLI (Core)。**専用の `az foundry` 拡張は存在しない**(2026-07 時点) | https://learn.microsoft.com/en-us/cli/azure/cognitiveservices | ms.service は foundry-tools に変更済み ※Agent Service 側ドキュメントには `az cognitiveservices agent` 削除済みとの記載もあり表記揺れ([03-agent-service](./03-agent-service.md) 参照) |
| Azure Developer CLI (azd) Foundry 拡張群 | `azd ai` 名前空間で agent のビルド/デプロイ/評価/運用。`microsoft.foundry`(メタパッケージ)+ `azure.ai.agents` / `connections` / `inspector` / `projects` / `routines` / `skills` / `toolboxes` | パブリックプレビュー | azd 1.25.2+、Python 3.10+ または .NET 8+ | https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/install-cli-foundry-extensions | `azd ai agent run`(ローカル実行)/ `invoke` 等 |
| `az ml`(classic ハブ用) | 旧ハブベースプロジェクト(`--kind hub` / `--kind project`)の管理 | GA(ただし Foundry classic 限定の位置づけ) | 新 Foundry プロジェクトは `az cognitiveservices account project` 側 | https://learn.microsoft.com/en-us/azure/foundry-classic/how-to/develop/create-hub-project-sdk | — |
| Bicep / ARM | `Microsoft.CognitiveServices/accounts`(kind AIServices)+ 子リソース `accounts/projects`、`accounts/deployments` で IaC 管理 | GA(projects は API version 2025-06-01 で利用可。最新プレビュー版 2026-05-15-preview) | capabilityHosts 等はプレビュー API version | https://learn.microsoft.com/en-us/azure/templates/microsoft.cognitiveservices/accounts | 旧 hub は Microsoft.MachineLearningServices 側のまま |
| Terraform (AzureRM/AzAPI) | `azurerm_cognitive_account`(kind AIServices + `project_management_enabled = true`)+ `azurerm_cognitive_account_project`(新 Foundry プロジェクト) | GA相当(AzureRM で新リソースタイプ対応済み。プレビュー機能は AzAPI 併用) | 旧 hub 用 `azurerm_ai_foundry` / `azurerm_ai_foundry_project` も存続。AVM モジュール `Azure/avm-ptn-aiml-ai-foundry` あり | https://learn.microsoft.com/en-us/azure/foundry/how-to/create-resource-terraform ・ https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/cognitive_account_project | Terraform 作成プロジェクトが Agent Framework から使えない既知トラブル報告あり(learn Q&A) |

## 開発ツール・フレームワーク

| 機能名 | 説明 | ステータス | 詳細 | 出典 | 備考 |
|---|---|---|---|---|---|
| VS Code 拡張: Foundry Toolkit | 旧 AI Toolkit + 旧 Microsoft Foundry 拡張を1つに統合。プロジェクト作成、モデルカタログ/デプロイ、プレイグラウンド、宣言型/ホスト型エージェント管理、ローカルデバッグ | GA(マーケットプレイスに Preview マークなし。v1.6.5、2026-06-28 更新) | VS Code(ID: ms-windows-ai-studio.windows-ai-studio) | https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/get-started-projects-vs-code ・ https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio | 名称変遷: AI Toolkit → Foundry Toolkit |
| Foundry MCP Server | クラウドホスト型 MCP サーバー(`https://mcp.ai.azure.com`)。エージェント/データセット/評価/モデルデプロイ等を 38 ツール・10 カテゴリで会話的に操作 | パブリックプレビュー | VS Code / Visual Studio / Foundry Tools から利用。**ネットワーク分離未対応**(Private Link 裏のリソース不可) | https://learn.microsoft.com/en-us/azure/foundry/mcp/get-started ・ https://learn.microsoft.com/en-us/azure/foundry/mcp/available-tools | — |
| Microsoft Agent Framework (MAF) | Semantic Kernel + AutoGen の直接後継(同一チーム開発)。Agents / Harness / Workflows の3本柱。`FoundryChatClient` で Foundry プロジェクトエンドポイント(Responses API)に統合 | GA(1.0、2026-04-02/03)。Python `agent-framework` 1.12.1 stable(2026-07-23)、.NET `Microsoft.Agents.AI.Foundry` 1.5.0 stable。**Go はパブリックプレビュー** | Python / .NET が GA、Go がプレビュー。サブパッケージ: agent-framework-core / -foundry / -copilotstudio(copilotstudio はプレビュー) | https://learn.microsoft.com/en-us/agent-framework/overview/agent-framework-overview ・ https://pypi.org/project/agent-framework/ ・ https://devblogs.microsoft.com/agent-framework/microsoft-agent-framework-version-1-0/ | Build 2026 で Agent Harness、Hosted Agents、CodeAct 発表 |
| LangGraph / LangChain 統合 | `langchain-azure-ai` パッケージ経由。`AgentServiceFactory` で Foundry Agent Service を LangGraph ノード化、`langchain_azure_ai.agents.hosting` で LangGraph グラフを Foundry ホスト型エージェントとして公開。OpenTelemetry トレース、Foundry Memory 統合も | 公式ドキュメント整備済み(統合自体のステータス表記は要確認。パッケージ: https://pypi.org/project/langchain-azure-ai/ ) | Python(LangChain / LangGraph) | https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/langchain-agents ・ https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/langchain-hosted-agents | ホスティング/メモリ/トレースの各記事が 2026-06 に更新 |

## 補足ノート(SI 判断に効く要点)

1. **SDK パリティ**: 統合プロジェクトクライアント 2.x は Python (2.4.0) / .NET (2.0.1) / JS (2.3.1) / Java (2.2.0) の4言語すべて GA。Python が最も先行。
2. **`azure-ai-inference` の廃止が確定日付付き**(2026-08-26)。一度も GA せず beta のまま終了し、全言語で OpenAI SDK + v1 API へ移行する構図。既存資産の棚卸しが必要。
3. **CLI は3系統に分裂**: (a) `az cognitiveservices`(リソース/プロジェクト/デプロイ管理、GA)、(b) azd の Foundry 拡張群(エージェント開発ライフサイクル、プレビュー)、(c) `az ml`(classic ハブ専用に格下げ)。**独立した `az foundry` コマンド群は存在しない** — 「Foundry の CLI」は azd 側に寄っている。
4. **MAF が Foundry ネイティブのコードファースト経路として GA**。ビジュアル Workflows 廃止(2026-12-01)の公式移行先でもあり、「portal(prompt agents)vs MAF(コードファースト)vs LangGraph(サードパーティ、hosted agents として持ち込み可)」という技術選定の3経路が明確化した。
5. 検索結果中の「`azure-ai-inference` 2026-05-30 リタイア」説は learn 本文の 2026-08-26 と食い違うため、learn 明記の 8/26 を採用(揺れとして記録)。
