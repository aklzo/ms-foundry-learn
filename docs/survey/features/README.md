# Microsoft Foundry 機能一覧・ステータス調査

> **最終更新:** 2026-09-07(全 8 カテゴリを What's new 2026-08 号 / GA 一覧表 2026-08-14 版 / リタイア表 2026-09-02 版+各出典ページで再検証。訂正・追記は更新履歴参照)/ **版:** 第3版
> 本ドキュメント群は SI の技術選定・アーキテクチャ選定基準の構築を目的に、Microsoft Foundry の機能と GA / プレビューのステータスを整理したものです。**定期更新を前提**としています(更新手順は本ページ末尾)。

**関連ドキュメント:** 本ページ群は「**その機能は使えるのか**」を引くためのもの。「**どう組むか**」は [アーキテクチャ設計ガイド](../architecture/README.md) を参照。

## このドキュメント群について

- **正(マスター)は Markdown**(生成 AI 用)。人間用 HTML は共有ビルダー `docs/survey/tools/md2html.py` で `html/` 配下に自動生成します。HTML を直接編集しないでください。
- 各機能について「全体ステータス」に加え、**サーフェス別(ポータル / Azure CLI / Python SDK / REST)の対応状況**を、公式ドキュメントに記載がある範囲で記録しています。記載がない場合は「記載なし」、確認できなかった場合は「要確認」と正直に書きます(推測でステータスを書かない)。
- すべての行に出典(learn.microsoft.com 等の公式 URL)を付けています。

## 前提知識: 2025年11月(Ignite)の大改編

調査の前提として、以下の再編を把握しておく必要があります(出典: [What is Microsoft Foundry?](https://learn.microsoft.com/en-us/azure/foundry/what-is-foundry)、[新旧ナビゲーションガイド](https://learn.microsoft.com/en-us/azure/foundry/how-to/navigate-from-classic))。

| 観点 | 旧 | 現行 |
| --- | --- | --- |
| ブランド | Azure AI Studio / Azure AI Foundry | **Microsoft Foundry** |
| ブランド | Azure AI Services | **Foundry Tools** |
| ポータル | Foundry (classic)(ハブベースプロジェクト) | **Foundry ポータル(新)= GA**(Foundry プロジェクト)。Home / Discover / Build / Operate / **Manage** / Docs の 6 セクション(Quota・プロジェクト詳細は Manage) |
| ドキュメント | /azure/ai-foundry/ | **/azure/foundry/**(新)+ /azure/foundry-classic/(旧) |
| エージェント API | Assistants API(Agents v0.5/v1) | **Responses API(Agents v2)** |
| API バージョニング | 月次 `api-version` | **v1 安定ルート(`/openai/v1/`)** |
| リソースモデル | Hub + Azure OpenAI + AI Services | **Foundry リソース**(単一。ARM 上は `Microsoft.CognitiveServices/accounts` を継続) |
| SDK | `azure-ai-inference` 等 複数パッケージ | **`azure-ai-projects` 2.x + `openai`** を単一プロジェクトエンドポイントへ |
| 用語 | Threads / Messages / Runs / Assistants | **Conversations / Items / Responses / Agent Versions** |

## ステータス凡例

| 表記 | 意味 |
| --- | --- |
| GA | 一般提供(General Availability)。SLA・サポート対象 |
| パブリックプレビュー | 公開プレビュー。SLA なし・仕様変更あり得る。本番利用は原則非推奨 |
| 限定プレビュー | 申請制・招待制のプレビュー(limited access / gated) |
| 非推奨 | Deprecated。廃止日が予告されている(新規利用を避ける) |
| 廃止 | Retired。利用不可 |
| 要確認 | 公式ページ上にライフサイクル明記が見つからなかったもの(確認した URL を併記) |

**注意:** 公式ドキュメント間でステータス表記が揺れている機能があります(例: **Toolbox**〈GA 一覧表=GA / 公式ブログ=public preview〉、**Voice Live**〈API 単体=GA / Agents 経由=Preview〉、**Content Understanding**〈GA 一覧表=classic 必須 / 新ポータルにプレイグラウンドあり〉、**Trace Replay**〈GA 一覧表=GA / 記事見出し=preview〉、**Agent optimizer**〈GA 一覧表=Limited preview / 記事=preview〉)。その場合は両方の出典を併記し、GA 一覧表を正とします。最も体系的な一次情報は [Feature readiness at GA(GA/プレビュー一覧表)](https://learn.microsoft.com/en-us/azure/foundry/concepts/general-availability) です。

## カテゴリ別ドキュメント

| # | ドキュメント | 内容 |
| --- | --- | --- |
| 01 | [プラットフォーム基盤・プロジェクト](./01-platform-projects.md) | Foundry リソース、プロジェクト(新旧)、ポータル、コントロールプレーン、RBAC、ネットワーク、CMK、Azure Policy、接続、IaC |
| 02 | [Foundry Models(モデル)](./02-models.md) | モデルカタログ、モデルファミリ別提供状況(OpenAI / Claude / Grok / DeepSeek 等)、デプロイタイプ、Model router、ライフサイクル、ファインチューニング、Foundry Local |
| 03 | [Foundry Agent Service](./03-agent-service.md) | Agents v2(Responses API)、prompt/hosted エージェント、ワークフロー、Memory、Routines、A2A、M365/Teams 公開、廃止スケジュール |
| 04 | [エージェントツール・ナレッジ(RAG)](./04-tools-knowledge.md) | ツールカタログ、File Search、AI Search、Web search、MCP、Toolbox、Work IQ / Fabric IQ、Foundry IQ(ナレッジベース) |
| 05 | [オブザーバビリティ・評価](./05-observability-evaluation.md) | トレーシング、Trace Replay、評価(評価器・クラウド評価・継続的評価)、AI Red Teaming、モニタリング、Purview / Defender 連携 |
| 06 | [安全性・ガードレール](./06-safety-guardrails.md) | Guardrails and controls 枠組み、コンテンツフィルター、Prompt Shields、Groundedness、PII、Task adherence、ブロックリスト |
| 07 | [Foundry Tools(旧 Azure AI Services)](./07-foundry-tools.md) | Speech(Voice Live)、Language、Translator、Vision / Face、Document Intelligence、Content Understanding の Foundry 統合状況 |
| 08 | [開発者サーフェス(SDK / CLI / API)](./08-developer-experience.md) | v1 API、各言語 SDK、Azure CLI / azd 拡張、Bicep / Terraform、VS Code 拡張、Foundry MCP Server、Microsoft Agent Framework、LangGraph 統合 |

## ハイライト(SI 選定観点の要点)

- **新ポータルは GA、ただし機能単位で GA / プレビューが混在。** [Feature readiness at GA](https://learn.microsoft.com/en-us/azure/foundry/concepts/general-availability) の表(2026-08-14 版)が唯一の体系的な一覧。Operate(コントロールプレーン)の大半・Monitoring・Workflows・Memory・AI Gateway 等はプレビュー継続。Quota・プロジェクト詳細は新設の **Manage** セクション(GA)に移った。
- **Agent Service はサービスとして GA**(Responses API ベースの v2)。hosted agents の初期プレビュー基盤は 2026-08-20 でサポート終了済(未移行なら再デプロイ)、ビジュアル Workflows は**プレビューのまま 2026-12-01 廃止**で Microsoft Agent Framework へ誘導。一方 2026-08 には **Autopilot(Agent 365 連携、hosted 専用。ステータス要確認)・長時間実行 hosted agents(preview)・Skills / private skill catalog(preview)・Agent optimizer の prompt agent 対応(ポータル、preview)**が追加され、「GA だが足元が動いている」状態は継続。
- **ハブベースプロジェクト(classic)は廃止日未発表のレガシー扱い。** 新規投資は Foundry プロジェクトに集中と明言。classic にしか残っていないのは **prompt flow(2027-04-20 廃止予定)**・serverless API デプロイ・Language の CLU / CQA / カスタム NER・Content Understanding のカスタム作成等(PII・言語検出・TA4H・CU の一部 prebuilt は新ポータルにプレイグラウンドあり)で、**マネージドコンピュートは新ポータルに対応済み**(パブリックプレビュー)。
- **CLI は一級市民ではない。** 専用の `az foundry` は存在せず、リソース管理は `az cognitiveservices`(GA。CMK・NSP・Managed VNet は CLI 手順あり)、エージェント開発・評価は azd 拡張(レジストリ表記は Beta)、それ以外の多くの機能は「ポータル + SDK/REST のみ」でドキュメントに CLI 手順がない。2026-08 以降は**コーディングエージェント経路(Foundry Skill / Foundry MCP Server〈preview、79 ツール〉/ Foundry Canvas〈preview〉/ DevPack)**が公式手段として整備されつつある。
- **Claude(Anthropic)が 2026 年に本格参入。** 「Hosted on Azure」形態の claude-opus-5 / sonnet-5 / opus-4-8 等は GA + Data Zone (US) 対応(Fable 5.1 / Mythos 5.1 は Preview)。2026-08-17 に Structured outputs / Web search / Web fetch / Tool search / MCP connector(Beta)も Hosted on Azure で利用可に。ただし Anthropic SDK + Marketplace 課金 + Foundry 組み込みコンテンツフィルター非適用という独自制約は継続。
- **GPT-6 Astra(`gpt-6-astra`)が 2026-09-03 に GA。** Standard / Provisioned × Global / US Data Zone のみで **EU Data Zone・Regional・Batch なし**、tool calling は Responses API 必須。EU データ境界が要件の案件は gpt-5.6 系(2028-01-11 まで)で設計する。リタイア日はリタイア表 2026-09-02 版に未掲載。
- **確定済みの廃止日程が多数**(下表)。移行設計を伴う提案では必読。

## 重要期限(廃止・移行スケジュール)

| 期限 | 対象 | 影響・移行先 | 出典 |
| --- | --- | --- | --- |
| ~~2026-08-20~~ **期限到来** | Hosted agents 初期プレビュー基盤 | サポート終了済。未移行の hosted agent は新基盤へ再デプロイ(移行ガイドは「supported only until August 20, 2026」の表現のまま) | https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/migrate-hosted-agent-preview |
| ~~2026-08-26~~ **廃止済** | Assistants API(Azure OpenAI) | 出典冒頭で「**The Assistants API is retired**」を確認(2026-09-07)。Responses API(Agents v2)へ移行 | https://learn.microsoft.com/en-us/azure/foundry-classic/openai/concepts/assistants |
| ~~2026-08-26~~ **廃止済** | `azure-ai-inference` SDK | supported-languages(2026-08-25 版)で「**retired on August 26, 2026**」(過去形)を確認。beta のまま GA せず終了。OpenAI SDK + v1 API へ移行。旧記載「2026-05-30 説の揺れ」は決着。**レジストリにはパッケージが残置され deprecated フラグもない**ため、依存関係に残っていても警告は出ない | https://learn.microsoft.com/en-us/azure/foundry-classic/foundry-models/supported-languages |
| ~~2026-09-01~~ **期限到来** | Content Safety **Custom categories (standard)** | 廃止予定日到来(出典は「is retiring on September 1, 2026」のままで retired 表記は未確認)。rapid には廃止予告なし。移行先 Custom text classification(Azure Language)自体も 2029-03-31 廃止予定 | https://learn.microsoft.com/en-us/azure/ai-services/content-safety/concepts/custom-categories |
| 2026-09-13 | Foundry IQ **Serverless(Developer tier)** | プレビューのまま**課金開始**(公式ブログ 2026-06-02)。PoC で無料前提にしない | https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/what-is-foundry-iq |
| 2026-09-15 | `MAI-Transcribe-1`(Speech 経由、Preview) | リタイア → `MAI-Transcribe-1.5`(最新は MAI-Transcribe-2 プレビュー) | https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirement-schedule |
| 2026-09-25 | Global Standard の **flex → standard 自動フォールバック** | 廃止。Flex 非対応モデルへの `service_tier: flex` 要求はエラーに | https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/deployment-types |
| 2026-09-25 | Azure AI Vision Image Analysis(3.2 / 4.0) | **移行計画策定の目安日**(migration-options の Next steps に明記。廃止本体は 2028-09-25) | https://learn.microsoft.com/en-us/azure/ai-services/computer-vision/migration-options |
| 2026-12-01 | ビジュアル Workflows(マルチエージェント) | 廃止。Microsoft Agent Framework / Logic Apps / A2A へ移行 | https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/workflow |
| 2027-03-31 | Agents (classic)(v1、Threads/Runs) | 廃止。Agents v2 へ移行(状態データは自動移行されない) | https://learn.microsoft.com/en-us/azure/foundry-classic/agents/whats-new |
| 2026-10-01 〜 10-21 | gpt-4o(2024-05-13)・o3-mini = 10-01 / o4-mini = 10-16 / claude-sonnet-4-5・opus-4-5・haiku-4-5 = 10-19 / o1・o1-pro・o3 = 10-21(後継 gpt-5.6-sol) | リタイア集中期間(詳細は [02-models](./02-models.md))。**gpt-4o の 2024-08-06 / 11-20 版は 2027-04-14 まで残る**ので版を確認 | https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirement-schedule |
| 2027-03-20 | **Language Studio** | 廃止。Foundry ポータルへ移行(Language の PII / 言語検出 / TA4H は新ポータル、CLU / CQA / カスタム NER は classic) | https://learn.microsoft.com/en-us/azure/ai-services/language-service/migration-studio-to-foundry |
| 2028-09-25 | Azure AI Vision Image Analysis 4.0/3.2 | 廃止(migration-options で **3.2 も対象**と確認、2026-07-30 の疑義は解消)。Document Intelligence / Content Understanding / Foundry Models へ移行 | https://learn.microsoft.com/en-us/azure/ai-services/computer-vision/overview ・ https://learn.microsoft.com/en-us/azure/ai-services/computer-vision/migration-options |
| ~~2026-08-31~~ **期限到来** | NTT Data `tsuzumi-7b`(Legacy) | リタイア日到来(リタイア表 2026-09-02 版では Legacy 表記のまま残存)。後継 `tsuzumi2` へ。**日本語特化モデルを検討する案件で効く** | https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirement-schedule |
| 2027-04-14 | `gpt-4.1` / `gpt-4.1-mini` / `gpt-4.1-nano` | リタイア。**nano は 2026-10-14 → 2027-04-14 に延長され 3 モデル同日に**(2026-09-02 版で確認。旧記載「nano は半年早い」は撤回) | https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirement-schedule |
| **2027-04-20** | prompt flow | 廃止。**新規開発に非推奨**でランタイムコンテナのセキュリティ更新も停止済み。Microsoft Agent Framework へ移行 | https://learn.microsoft.com/en-us/azure/foundry-classic/concepts/prompt-flow |
| **2026-10-14** | **Azure OpenAI On Your Data** | 「The service will be retired on October 14, 2026」(use-your-data ページ、2026-06-24 更新)。「モデルが直接データを読む」構成が終わる。Foundry Agent Service + Foundry IQ へ移行 | https://learn.microsoft.com/en-us/azure/foundry-classic/openai/concepts/use-your-data |
| **日付未公表(Planned/TBD)** | Agent Applications(旧 publishing モデル)/ コンテナプロトコル 1.0.0 | 詳細は [03-agent-service](./03-agent-service.md) | https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/migrate-agent-applications |
| 予告 **15 日**のみ | **Fireworks 系モデル(`FW-*`)** | 標準の 60 日前通知ではなく **15 日前通知**。本番の必須経路に置かない | https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirement-schedule |

## 更新運用ガイド(定期更新の手順)

**推奨頻度:** 月1回(Microsoft の What's new が月次更新のため)。Ignite(11月)・Build(5月)直後は必ず更新。

1. **一次情報の差分確認**(下記ウォッチリストを上から順に)
   - [What's new in Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/whats-new-foundry) — 月次の新機能・ステータス変更
   - [Feature readiness at GA(GA/プレビュー一覧)](https://learn.microsoft.com/en-us/azure/foundry/concepts/general-availability) — 機能別ステータスの最重要ページ
   - [Model retirement schedule](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirement-schedule) — モデルのリタイア日
   - [Microsoft Foundry Blog](https://devblogs.microsoft.com/foundry/) — 発表の背景・詳細。**月次まとめ記事「What's new in Microsoft Foundry」は 2026 年 6 月号(2026-07-07 公開)が最後で 7・8 月号は未発行**(2026-09-07 時点)。以降は個別記事(例: Claude 5 機能 2026-08-17、Content Understanding 2026-08-12)と learn 側 What's new で追う
   - [リージョン別 feature availability](https://learn.microsoft.com/en-us/azure/foundry/reference/region-support)
2. **各カテゴリ MD の該当行を更新**(ステータス変更・新機能追加・廃止済み行の整理)。出典 URL も再確認し、リンク切れ(ドキュメント再編)があれば新 URL に差し替える。
3. **各ページ冒頭の「最終更新」日付を更新**し、本ページの更新履歴に1行追記する。
4. **HTML を再生成:** リポジトリルートで `python3 docs/survey/tools/md2html.py features` を実行(引数なしなら architecture も含めて全ビルド)。
5. 生成 AI に更新作業を依頼する場合は、本ページと対象カテゴリ MD を読ませた上で「出典 URL を WebFetch で再確認し、ステータス変化のみ差分更新。推測でステータスを書かない」ことを指示する。**2026-09-07 の更新で効いた手順:** 親が一次情報 3 本(What's new / GA 一覧表 / リタイア表)を先に取得してスナップショット化 → カテゴリごとに 1 エージェントを並列起動し「担当 MD のみ編集・README は親が統合」と役割分担 → 各エージェントは表や日付を WebFetch の要約に頼らず `curl` で生 HTML から抽出(要約モデルは表を取り違える)→ 完了報告を「訂正 / 追記 / 期限到来 / 変化なし / README 波及 / 他ドキュメント波及 / URL 変更 / 要確認」の 8 項目で統一。

## 更新履歴

| 日付 | 内容 |
| --- | --- |
| 2026-07-29 | 初版作成(全8カテゴリ、learn.microsoft.com 現行ページを確認) |
| 2026-09-07 | **第3版: 全 8 カテゴリを一次情報(What's new 2026-08 号・GA 一覧表 2026-08-14 版・リタイア表 2026-09-02 版+各出典ページ約 250 本)で再検証。** **訂正:** 02 gpt-4.1-nano リタイア 2026-10-14 → **2027-04-14**(「nano は半年早い」は撤回)・gpt-5.6 系 2028-01-11・Mistral-Large-3 は Preview・Model router 32 リージョン(Japan East 含む)・FT の OSS 系は GA・カタログ 10,000+ / 03 Agent optimizer「hosted 専用」→ **prompt agent もポータルで可**・A2A agent card は SDK でも設定可・M365 公開の閉域手順確定 / 01 Azure Policy 適格性 GA・Managed VNet GA・ポータルは Manage を含む 6 セクション・CMK の CLI 対応・File Search 閉域 Supported / 04 tool-catalog ページ消失(toolbox-overview へ)・Tool search は preview・Toolbox SDK は非 beta・Work IQ API はコネクタライセンス不要(Copilot Credits)・Foundry IQ 接続 API 2026-08-01-preview・Azure Functions ツールは公式間矛盾で要確認 / 05 継続的評価は**プレビュー確定**(Recurring evaluations)・Prohibited Actions / Sensitive Data Leakage 評価器は preview・`azure-ai-evaluation` 1.18.5 / 06 Risks & safety モニタリングはプレビュー / 07 Voice Live **API 単体は GA(2025-11)**・Agents 経由は Preview・LLM speech GA・PII 匿名化 GA・Image Analysis は 3.2 も対象+2026-09-25 移行計画の出典確定・CU は新ポータルにプレイグラウンドあり / 08 Foundry MCP Server 79 ツール・MAF .NET Foundry コネクタは 1.5.0 が最終 stable・パッケージ版更新(`azure-ai-projects` 2.6.0 等)。**追記:** GPT-6 Astra GA(2026-09-03、EU Data Zone なし)・Claude 5 機能の Hosted on Azure 対応・Autopilot(要確認)・長時間実行 hosted agents(preview)・Skills / private skill catalog・BYO 外部レジストリ・Responses API マルチエージェント(GPT-5.6)・NSP GA・Network egress controls・サードパーティガードレール GA(日本リージョンなし)・Content provenance・Entra トレース取り込み・合成データ生成・azd 評価・Managed MCP servers・Foundry Skill / DevPack / Canvas。**期限到来:** hosted 旧基盤 08-20・Assistants API 08-26(retired 確認)・`azure-ai-inference` 08-26(retired 確認)・tsuzumi-7b 08-31・Custom categories (standard) 09-01。**新規期限:** On Your Data 2026-10-14 確定・Foundry IQ Serverless 課金 09-13・flex フォールバック廃止 09-25・Language Studio 2027-03-20。URL 変更 4 件(tool-catalog / cloud-evaluation / get-started-projects-vs-code / CU quickstart)を差し替え。横断: slides の期限表と architecture 04 / 05 の該当箇所を同期 |
| 2026-09-04 | **casebook 新設に合わせた一次情報の再確認**(GA 一覧 ms.date 2026-08-14 / configure-private-link 2026-08-14 / hosted-agents 2026-08-19)。hosted agents: idle timeout が 5〜60 分で設定可(既定 15 分)・private ACR は 2026-06-25 以降作成プロジェクトのみ / Foundry IQ は「Partial GA(API GA・ポータル Preview)」表記 / Tracing は prompt・hosted で GA、**Tracing VNet は Preview** / 閉域ツール表で File Search が「Through private endpoint」表記に変更(実測との差は [casebook 02](../casebook/02-pitfalls-index.md) P-N13)。現場の詰まりどころ(公開記事)は casebook 側に集約 |
| 2026-07-30 | **記載内容の検証と訂正。**引用 URL 165 件の生存確認(161 件が 200)、Agent Service の固定上限 8 項目・モデルのリタイア日約 20 件を一次情報と突合(いずれも一致)。**訂正:** managed compute を GA → **パブリックプレビュー**、かつ「classic 必須」を撤回(新ポータル対応済み)/ Voice Live を「GA 相当」→ **プレビュー**(GA 一覧表の明示表記)/ Toolbox の「要確認」→ **GA** 確定 / Agent optimizer を **限定プレビュー** に / ガードレール枠組みをモデル=GA・エージェント=プレビュー・コントロールと介入=プレビューの 3 分割に。**追記:** prompt flow の 2027-04-20 廃止、On Your Data の非推奨、hosted agent のツール直付け不可、Agent Applications の廃止予告、managed compute での Content Safety 非適用、Fireworks の 15 日予告、tsuzumi-7b と gpt-4.1-nano のリタイア日 |
| 2026-07-30 | **architecture 側のファクトチェックで判明した波及訂正3件+1件。**01: 「全パブリックアクセス遮断の PE 構成はポータル UI 不可」を撤回(configure-private-link 2026-07-28 更新版はポータルの Networking タブ手順を掲載)+ Azure Government の Agent Service は専用ページ(agents/concepts/azure-government)で**部分対応**(Prompt agents 対応 / Workflows プレビュー / Hosted agents 非対応。region-support 側の「Azure AI Agents 非対応」は古い)と注記 / 02: Foundry Local を「要確認」→ **GA(2026-04-09 公式ブログで GA 宣言、docs ページにはラベルなし)** / 06: 既定ガードレールの「画像は Low 閾値」→ **テキスト・画像とも Medium**(default-safety-policies 2026-05-31 更新の表で確認) |
| 2026-07-30 | **未検証範囲の追加検証(全8カテゴリの検証を完了)。****訂正:** 01 の「ロール割り当ては SDK 非対応と明記」は出典にその記述がなく「記載なし」に修正(記載サーフェスはポータル / Azure ポータル IAM / Azure CLI)/ 05 の評価器×ツール制約を公式の正確な記述に差し替え(**`groundedness` も対象**、対象ツールは 7 種、完全サポートは 4 種のみ)/ 07 の Image Analysis は overview が名指しするのは **4.0 のみ**(3.2 の記載なし)で、「2026-09-25 までに移行計画を」も overview には存在しないため出典未確定として扱う / 08 の `azure-ai-evaluation` を 1.18.2 → 1.18.3。**追記:** 01 に組み込みロールの GUID 5 件・使ってはいけないロール(`Cognitive Services*` と `Azure AI Developer`)・agent スコープの評価範囲・SDK/CLI デプロイ時は Foundry User が自動割り当てされない点 / 08 に `azure-ai-inference` 2026-08-26 の一次情報確認とパッケージ版の再確認結果。**正しかった項目:** 05 のエージェント評価器 11 種の GA/プレビュー区分は完全一致、07 の Language のコア/レガシー分類も完全一致、Vision の 2028-09-25 と Content Understanding の Foundry リソース必須・BYO モデル・新ポータル coming soon も一致 |
