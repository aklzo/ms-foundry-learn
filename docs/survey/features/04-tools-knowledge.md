# 04. エージェントツール・ナレッジ(RAG)

[← 機能一覧 TOP](./README.md)

> **最終更新:** 2026-07-30(2026-07-29 の初版を一次情報に当てて検証・訂正。訂正内容は [TOP の更新履歴](./README.md#更新履歴)参照)

## 概要

Foundry Agent Service のツール群とナレッジ(RAG)機構を扱う。ツールカタログのページ冒頭に「**The Foundry tool catalog and the core tools framework are generally available. Some individual tools are still in preview**」と明記されており、**カタログとコアツール基盤は GA、個別ツールは一部プレビュー**という構図(出典: https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/tool-catalog )。

カタログのエントリ種別は Remote MCP server / Local MCP server / Custom(Logic Apps コネクタから変換した MCP サーバー)の3種。組織限定の Private tool catalog あり。ポータル操作は新ポータルの Build > Tools。

## ツールカタログ掲載ツールとステータス(カタログ表記ベース)

| 分類 | ツール | カタログ上の表記 |
|---|---|---|
| Built-in | Web search | GA(表記なし) |
| Built-in | Code Interpreter | GA(表記なし) |
| Built-in | Custom Code Interpreter | プレビュー |
| Built-in | File Search | GA(表記なし) |
| Built-in | Azure AI Search | GA(表記なし) |
| Built-in | Azure Functions | GA(表記なし) |
| Built-in | Function calling | GA(表記なし) |
| Built-in | Image Generation | プレビュー |
| Built-in | Browser Automation | プレビュー |
| Built-in | Computer Use | プレビュー |
| Built-in | Microsoft Fabric (data agent) | プレビュー |
| Built-in | SharePoint | プレビュー |
| Custom | Model Context Protocol (MCP) | GA(表記なし) |
| Custom | OpenAPI tool | GA(表記なし) |
| Custom | Agent-to-Agent (A2A) | プレビュー |
| Custom | Toolbox | **GA**(カタログ表に preview ラベルなし。GA 一覧表でも「Toolboxes = GA」と明記) |

※ 旧来の「Grounding with Bing Search」は built-in 表から外れ **Web search が推奨経路**。高度シナリオ向けに「Grounding with Bing tools」ページが別途存在。**Deep Research と Logic Apps 専用ツールはカタログに存在しない**(後述)。

## ツール個別詳細

凡例: SDK 列は Python SDK の対応(各ページの Usage support 表に基づく。多くは C#/JS/Java/REST も対応)。Azure CLI はツール実行用の記載はどのページにもなし(接続作成に `az cognitiveservices` を使う例のみ)。

| 機能名 | 説明 | ステータス | ポータル | CLI | Python SDK | 出典 | 備考 |
|---|---|---|---|---|---|---|---|
| File Search | アップロードしたファイルをベクトルストア化しハイブリッド検索で回答を根拠付ける | GA | 記載なし(コード中心) | 記載なし | 対応(basic/standard 両対応) | https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/file-search | モデル利用料と別に**追加課金**。埋め込みは text-embedding-3-large(256次元)、チャンク 800 / オーバーラップ 400 トークン。standard セットアップでは自前の AI Search + Blob にデータ保持 |
| Azure AI Search | 既存の Azure AI Search インデックスで回答をグラウンディング(引用付き) | GA | 接続作成はポータル可 | 接続作成のみ `az cognitiveservices ... connection create` | 対応 | https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/ai-search | 1ツール1インデックスのみ。同一テナント必須。private VNet では Entra 認証必須。「マネージドなナレッジベース体験は Foundry IQ 参照」と誘導あり |
| Web search | パブリック Web をリアルタイム検索し引用付き回答(Web グラウンディングの**推奨手段**) | GA | 記載なし | 管理者用に `az feature register`(サブスクリプション単位で無効化可) | 対応 | https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/web-search | 内部は Grounding with Bing (Custom) Search を使用。**追加課金あり・DPA 対象外・データはコンプライアンス境界外へ**。`o3-deep-research` モデル+Web search が旧 Deep Research ツールの後継 |
| Grounding with Bing Search | Bing 検索による Web グラウンディング(市場指定などの高度シナリオ向け) | GA | 記載なし | 記載なし | 対応 | https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/bing-tools | 課金あり。モデル制限あり(limits-quotas-regions の「Tool support by region and model」参照)。送信されるのは検索クエリ・ツールパラメータ・リソースキーのみ |
| Grounding with Bing Custom Search | 指定ドメイン集合に限定した Web グラウンディング | パブリックプレビュー(tool type: `bing_custom_search_preview`) | 記載なし | 記載なし | 対応 | https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/bing-tools | Web search の `custom_search_configuration` としても利用可。Bing がインデックス済みの公開ページのみ |
| Code Interpreter | サンドボックスで Python を書き実行(データ分析・グラフ生成) | GA | 記載なし | 記載なし | 対応 | https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/code-interpreter | セッション単位の**追加課金**(アクティブ1時間/アイドル30分)。Azure Container Apps dynamic sessions 基盤・Hyper-V 分離・アウトバウンド通信不可。リージョン制限あり |
| Custom Code Interpreter | Code Interpreter のパッケージ/リソース/Container Apps 環境をカスタマイズ | パブリックプレビュー(カタログ表記) | 要確認 | 要確認 | 要確認 | https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/custom-code-interpreter (確認URL) | カタログ表記に基づく。個別ページ詳細は未取得 |
| OpenAPI tool | OpenAPI 3.0/3.1 仕様で外部 HTTP API に接続 | GA | 記載なし | 記載なし | 対応(basic/standard 両対応) | https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/openapi | 認証: anonymous / API key / managed identity(Bearer トークンは Custom keys 接続で)。API key 1スキーム/ツール |
| Azure Functions | Storage キュー経由で Azure Functions をツールとして非同期呼び出し | GA | 記載なし | 記載なし | 対応 | https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/azure-functions | **standard セットアップのみ(basic 非対応)**。応答に CorrelationId 必須。MCP サーバーとして Functions をホストする選択肢も併記 |
| Azure Logic Apps(コネクタ→MCP 変換) | Logic Apps コネクタ(1,400+)のアクションを **MCP サーバーに変換**してツール化 | パブリックプレビュー(Logic Apps 側ページに「This capability is in preview」) | 新 Foundry ポータルのみ(classic 不可)+ Azure ポータルの登録ウィザード | 記載なし | 記載なし(ポータル操作) | https://learn.microsoft.com/en-us/azure/logic-apps/add-agent-tools-connector-actions | 旧来の専用「Logic Apps ツール」は新ポータルのカタログに存在せず、「Custom(Logic Apps connectors)」枠に移行。現状 1コネクタ/ツール、OAuth 2.0 コネクタ非対応、マネージドコネクタのみ |
| SharePoint | SharePoint サイト/フォルダーの文書を OBO(ID パススルー)で検索しグラウンディング | パブリックプレビュー(`sharepoint_grounding_preview`) | セットアップ手順あり(接続作成) | 記載なし | 対応 | https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/sharepoint | **M365 Copilot ライセンスまたは Retrieval API 従量課金が必須**。同一テナント必須・app-only 不可・1エージェント1ツール。基盤は M365 Copilot Retrieval API |
| Microsoft Fabric (data agent) | Fabric データエージェントに委任して企業データを対話分析(NL2SQL 等) | パブリックプレビュー(`fabric_dataagent_preview`) | 接続作成はポータル | 記載なし | 対応 | https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/fabric | ID パススルー(OBO)必須、サービスプリンシパル不可。同一テナント必須。データソースごとに最低権限要件あり(PBI semantic model は Build 権限) |
| Browser Automation | Playwright Workspaces 基盤のリモートブラウザで自然言語からブラウザ操作 | パブリックプレビュー(`browser_automation_preview`) | 対応(Build > Tools > Create a toolbox 経由で接続) | 記載なし | 対応 | https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/browser-automation | 基盤の Playwright Workspaces 自体は GA サービス(課金はそちらで発生)。プライベートサイト対応は限定プレビュー。重大なセキュリティリスク警告あり |
| Computer Use | スクリーンショットを解釈しクリック/入力等の UI 操作を提案 | パブリックプレビュー(`computer-use-preview` モデル必須) | 記載なし | 記載なし | 対応 | https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/computer-use | **限定アクセス(登録申請制、o3 アクセス済みでも要申請)**。対応リージョン限定(モデル配置に依存)。safety checks 内蔵 |
| Deep Research | Web ベースの多段リサーチ(旧ツール) | 非推奨(「The Deep Research tool is deprecated. We recommend that you use the `o3-deep-research` model with web search or an MCP tool instead.」) | classic のみ(コードオンリー) | — | 対応(旧 SDK) | https://learn.microsoft.com/en-us/azure/foundry-classic/agents/how-to/tools-classic/deep-research | 新パス(/azure/foundry/agents/how-to/tools/deep-research)は 404。`2025-05-15-preview` API 限定。後継 = Web search ツール + `o3-deep-research` モデル(web-search ページに移行例あり) |
| MCP ツール(リモート MCP サーバー接続) | MCP サーバーエンドポイント上のツールにエージェントを接続 | GA | 対応(カタログから構成) | 記載なし | 対応(basic/standard 両対応) | https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/model-context-protocol | 認証: キー / Entra(マネージド ID)/ OAuth ID パススルー。**長時間実行(long-running operations)はプレビュー**。カタログ個別サーバーにプレビューあり(例: Azure DevOps MCP Server)。classic 版 MCP ページは「(Preview) (classic)」のまま |
| Toolbox(intent-based toolbox) | 複数ツールを1つの MCP 互換エンドポイントに束ね、バージョニング・集中認証を提供。MAF / LangGraph / GitHub Copilot SDK 等の外部ランタイムからも消費可 | **GA**(GA 一覧表に「Build > Toolboxes = GA」と明記。ツールカタログ表にも preview ラベルなし) | 対応(Build > Tools > Create a toolbox。作成手順は VS Code Foundry Toolkit 中心) | **azd**(`microsoft.foundry` 拡張)対応。Azure CLI 記載なし | 対応(`client.beta.toolboxes.create_version` — beta 名前空間) | https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/toolbox | バージョン作成→バージョン別エンドポイントでテスト→default へ昇格。Code Interpreter / File Search を toolbox 経由で使うと**ユーザー分離なし**。unnamed ツールは各タイプ1個まで |
| Tool search(`toolbox_search`) | Toolbox 内ツールを隠し、`tool_search` / `call_tool` の2メタツールで意図ベース発見(BM25) | Toolbox に準ずる(対応表で「Available」・preview 表記なしだが、Toolbox 本体と同じ V1Preview フィーチャーヘッダー配下) | VS Code Foundry Toolkit 対応(「Tool search」チェックボックス) | azd 対応 | 対応 | https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/tool-search | `pin` / `additional_search_text` / 自動ピン(利用頻度ベース)で調整可。limit 既定5・最大10。Responses API 版の tool search は別ページ(/azure/foundry/openai/how-to/tool-search) |
| Work IQ | M365(メール・会議・ファイル・チャット)を横断するインテリジェンス層に A2A で委任。全リクエストがサインインユーザー文脈で実行 | パブリックプレビュー(`work_iq_preview`) | 接続作成はポータル(Settings > Connections > Work IQ)。ツール追加は VS Code Toolkit / コード | 記載なし | 対応(C#/JS/REST 対応、Java 非対応) | https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/work-iq | **M365 Copilot ライセンス必須**(エンドユーザーも)。BYO Entra アプリ + `WorkIQAgent.Ask` 委任権限 + Global Admin の同意が必須。**VNet 統合非対応**。データは M365 テナント内・モデル学習に不使用 |
| Fabric IQ | Fabric のオントロジー/データエージェント/PBI セマンティックモデルに MCP で接続し、業務語彙(NL2Ontology)でデータ推論 | パブリックプレビュー(`fabric_iq_preview`。Fabric IQ ワークロード自体もプレビュー) | VS Code Toolkit 対応(OneLake Catalog 接続はポータルで作成)+ ポータル playground 手順あり | azd で接続作成例あり | 対応(C#/JS/REST 対応、Java 非対応) | https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/fabric-iq | Fabric ライセンス必須。OBO のみ(app-only 不可)。data agent エンドポイントのみ background mode(長時間実行)対応。VNet 対応はアイテム種別で異なる |
| Foundry IQ / ナレッジベース (knowledge bases) | Azure AI Search を基盤とするマネージドナレッジ層。複数ナレッジソース(Blob・SharePoint・OneLake・Web 等)を束ねた knowledge base を agentic retrieval(クエリ分解→並列検索→再ランク→統合)で照会。複数エージェントで共有可 | 一部 GA / 一部プレビュー: 「Some Foundry IQ features are now generally available, while others remain in preview.」agentic retrieval の一部は **2026-04-01 REST API で GA**、フル機能は 2026-05-01-preview。**ポータル体験は全機能プレビュー扱い** | 対応(新ポータル Build > Knowledge タブで KB 作成・エージェント接続) | 記載なし(接続作成に az CLI トークン取得例のみ) | 対応(接続ページの Usage support: Python + REST のみ。C#/JS/Java 未対応) | https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/what-is-foundry-iq ・ https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/foundry-iq-connect | エージェントからは **MCP ツールとして接続**(`{search-endpoint}/knowledgebases/{name}/mcp?api-version=2026-05-01-preview`、公開ツールは `knowledge_base_retrieve` のみ)。GA/プレビューの内訳は移行ガイド(/azure/search/agentic-retrieval-how-to-migrate)参照 |
| ベクトルストア / 埋め込み(ナレッジ接続基盤) | File search を支えるベクトルストア(解析→チャンク→埋め込み→索引を自動実行) | GA相当(preview 表記なし。File search に付随) | 記載なし | 記載なし | 対応(OpenAI 互換 `vector_stores` API 経由) | https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/vector-stores | 10,000 ファイル/ストア、エージェント・会話に各1ストアまで。会話由来ストアは既定7日で失効。basic = Microsoft 管理ストレージ、standard = 自前 Blob + Azure AI Search。埋め込みは text-embedding-3-large(256次元)固定(既定) |

## 補足ノート(SI 判断に効く要点)

**(a) Deep Research の廃止と後継**
「Deep Research をツールとして使う」構成は今後組めない。web-search ページが「This approach replaces the deprecated Deep Research tool」と明言し、`o3-deep-research` モデル + Web search ツール(Responses API)への移行コードを掲載。

**(b) Web search と Grounding with Bing の関係**
Web search(GA)が推奨経路で、Bing リソース接続不要のシンプル構成。市場フィルタ等の細かい制御が要るときのみ Grounding with Bing Search(GA)/ Bing Custom Search(プレビュー)。**いずれも DPA 対象外・コンプライアンス境界外へのデータ送信・別課金**という制約は共通で、規制業種の SI では要注意。

**(c) Toolbox は GA(2026-07-30 に確定)**
初版では「明確な GA 宣言が確認できない」としていたが、[GA 一覧表](https://learn.microsoft.com/en-us/azure/foundry/concepts/general-availability)に **「Build > Toolboxes = GA」** と明記されているのを確認した。ツールカタログ表にも preview ラベルはない。ただし **REST/MCP の検証例に `Foundry-Features: Toolboxes=V1Preview` ヘッダーが残り、Python SDK も `client.beta.toolboxes` 名前空間**という実装上のねじれは残っている(GA 宣言と SDK の成熟度は別物として扱う)。

なお **hosted agent はエージェント定義にツールを直付けできず、Toolbox 経由が前提**になる([03-agent-service](./03-agent-service.md))。コードファーストを選ぶ案件では Toolbox が必須要素になる。

**(c-2) ⚠ Azure OpenAI On Your Data は非推奨でリタイア間近**
Azure Architecture Center の Secure Multitenant RAG 記事に Important として「**Azure OpenAI On Your Data is deprecated and approaching retirement.** We recommend that you migrate Azure OpenAI On Your Data workloads to **Foundry Agent Service** with **Foundry IQ** to retrieve content and generate grounded answers from your data.」と明記されている(具体的なリタイア日は未公表)。
**含意:** 「オーケストレーターを挟まず、モデルが直接データストアを読む」構成は新規設計で選べない。下記(d)の3層はいずれもオーケストレーター型(エージェントまたは自前アプリ)を前提にする。既存の On Your Data ベースの提案書・PoC は棚卸しが必要。
出典: https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/secure-multitenant-rag

**(d) ナレッジ(RAG)の3層構造**
1. **File search + ベクトルストア**(GA)— 手軽なマネージド RAG。1ストア/エージェント制限あり。
2. **Azure AI Search ツール**(GA)— 既存インデックス直結。1インデックス制限。
3. **Foundry IQ knowledge bases**(一部 GA / 一部プレビュー)— マルチソース+agentic retrieval+ACL/Purview 対応の上位層。接続は MCP 経由で、**Foundry Agent Service 以外(Microsoft Agent Framework、カスタムアプリ)からも同じ KB を利用可能** — MAF / LangGraph 比較の観点では、ナレッジ層をエージェントフレームワークから切り離せるのが設計上のポイント。

**(e) IQ ファミリーの整理**
Foundry IQ = エンタープライズデータのナレッジ層(一部 GA)、Fabric IQ = Fabric の分析データ層(プレビュー)、Work IQ = M365 のコラボレーション文脈層(プレビュー)。3つは独立だが併用可能。

**(f) サーフェス全般の傾向**
ツール個別ページの Usage support 表は「Python / C# / JS / Java SDK + REST + basic/standard setup」形式で、**Azure CLI 列は存在しない**。Work IQ・Fabric IQ 接続は Java SDK 非対応、Foundry IQ 接続は C#/JS SDK も未対応(Python + REST のみ)という偏りがある。
