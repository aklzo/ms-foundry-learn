# Microsoft Foundry アーキテクチャ設計ガイド

> **最終更新:** 2026-07-30(公式ドキュメントとの突合検証で訂正)/ **版:** 初版
> SI の技術選定・アーキテクチャ選定基準の構築を目的に、**Microsoft Foundry を使ったシステムアーキテクチャ**を、インフラを含めた広い視点で整理したもの。機能単位の GA / プレビュー調査は [features/](../features/README.md) を参照。

## ドキュメント一覧

| # | ドキュメント | 内容 | こんなときに読む |
|---|---|---|---|
| — | **本ページ(TOP)** | アーキテクチャ一覧・選定早見表・全案件共通の前提 | まずここ |
| 01 | [公式ベストプラクティス](./01-official-baselines.md) | AAC リファレンスアーキテクチャ(Basic / Baseline / ALZ 版)、WAF for AI、CAF、アクセラレータ・AVM の現況 | 提案の根拠になる公式資料を探す |
| 02 | [構成要素カタログ](./02-building-blocks.md) | **16 レイヤーごとの「Foundry 機能を使う vs 自前実装する」全選択肢** | 個別の技術要素を比較する |
| 03 | [選定ガイド](./03-decision-guide.md) | 5 つの決定ゲート、デシジョンツリー、要件キーワード逆引き、提案チェックリスト | 何から決めればいいか分からない |
| 04 | [UC-A 社内ナレッジ検索・RAG](./04-usecase-chat-rag.md) | File Search / 自前索引 / AI Search ツール / SharePoint / Foundry IQ の 5 パターン | 文書検索チャットを作る |
| 05 | [UC-B 業務自動化・マルチエージェント](./05-usecase-agent-automation.md) | 基幹連携、HITL 承認フロー、長時間プロセス、マルチエージェント、業務フロー主導 | エージェントに業務処理をさせる |
| 06 | [UC-C 顧客向け公開・マルチテナント](./06-usecase-customer-facing.md) | WAF チューニング、BOLA 対策、テナント分離、チャージバック、大規模キャパシティ | 外部顧客に提供する |
| 07 | [UC-D 規制業種・閉域・データ主権](./07-usecase-regulated-edge.md) | 3 つの egress モデル、閉域で使えない機能一覧、CMK、Purview の限界、Gov クラウド、エッジ | 金融・公共・医療の案件 |
| 08 | [UC-E 音声・文書処理・バッチ・M365](./08-usecase-specialized.md) | Voice Live とテレフォニー、DI と Content Understanding の使い分け、Batch、マルチモーダル生成、Teams 公開、ファインチューニング運用 | チャット以外の類型 |
| 09 | [運用アーキテクチャ](./09-operations.md) | PTU サイジング、BCDR、可観測性、評価、コスト、CI/CD | 本番運用を設計する |
| 10 | [移行とアンチパターン](./10-migration-antipatterns.md) | 確定済み廃止スケジュール、移行パターン、**踏みやすい 11 のアンチパターン** | 既存資産があるとき / レビュー前 |
| 11 | [エージェント構成の判断フレームワーク](./11-decision-frameworks.md) | CAF デシジョンツリー、単一 vs マルチ判断、AAC オーケストレーション 5 パターン、**Copilot Studio の上限ライン** | プラットフォームとエージェント構成を根拠付きで決める / 「試作で比較するしかないか」と聞かれた |

**人間用 HTML:** `html/index.html`(Markdown が正。HTML は `python3 docs/survey/tools/md2html.py` で自動生成するので直接編集しない)

---

## アーキテクチャ一覧

### 公式リファレンスアーキテクチャ(Microsoft が検証済み)

**Foundry チャット系の「リファレンスアーキテクチャ」はこの 3 本しかない。**それ以外の公式ページは「ガイド」または「ソリューションアイデア」で検証レベルが下がるため、顧客提案での引用時は区別する。

| 記号 | 名称 | 変種 | 実装コード | 詳細 |
|---|---|---|---|---|
| **公式-A** | Basic Microsoft Foundry Chat | パブリック・単一リージョン・ゾーン冗長なし。**記事自身が本番非推奨と明言** | `Azure-Samples/microsoft-foundry-basic` | [01 章](./01-official-baselines.md#a-basic-poc-専用-本番非推奨と記事自身が明言) |
| **公式-B** | **Baseline Microsoft Foundry Chat** | **ネットワーク分離・単一リージョン・ゾーン冗長。**WAF が「AI ワークロードの推奨アーキテクチャ」と名指し | `Azure-Samples/microsoft-foundry-baseline` | [01 章](./01-official-baselines.md#b-baseline-本番の出発点-waf-が-ai-ワークロードの推奨アーキテクチャ-と名指し) |
| **公式-C** | Baseline in an Azure Landing Zone | ネットワーク分離・hub-spoke | **記事から削除済み。**`Azure/AI-Landing-Zones`(Preview)または AVM を使う | [01 章](./01-official-baselines.md#c-baseline-in-azure-landing-zone-hub-spoke-版-ただしコードは記事から消えた) |

### 想定ユースケース別アーキテクチャ

| ID | パターン | オーケストレーション | RAG / ナレッジ | ネットワーク | 主な決め手 | 詳細 |
|---|---|---|---|---|---|---|
| **A1** | 部門内 FAQ チャット | Prompt agent | File Search | パブリック | 速度優先。権限制御なし | [04](./04-usecase-chat-rag.md#a1-部門内-faq-チャット-file-search・最小構成) |
| **A2** | 全社ナレッジ検索(本番) | Prompt / Hosted agent | **AI Search 自前索引** | Private Link | **ユーザーごとに見える文書が違う** | [04](./04-usecase-chat-rag.md#a2-全社ナレッジ検索-ai-search-自前索引・本番の標準形) |
| **A3** | 既存 AI Search 資産の活用 | Prompt agent | AI Search ツール直結 | 要件次第 | 索引設計を自分で持ち続けたい | [04](./04-usecase-chat-rag.md#a3-既存-ai-search-資産の活用-ai-search-ツール直結) |
| **A4** | M365 / SharePoint が主データ源 | Prompt agent | SharePoint ツール(OBO) | パブリック | 権限透過。**M365 Copilot ライセンス前提** | [04](./04-usecase-chat-rag.md#a4-m365-sharepoint-が主データソース) |
| **A5** | 複数ソース横断・高精度 | 任意(MCP 経由) | **Foundry IQ**(agentic retrieval) | 要件次第 | 複数エージェントでナレッジ共有 | [04](./04-usecase-chat-rag.md#a5-複数ソース横断・高精度-foundry-iq-agentic-retrieval) |
| **B1** | 単一エージェント + 基幹 API | Prompt agent + Toolbox | 補助的 | 社内網 | 参照系中心 | [05](./05-usecase-agent-automation.md#b1-単一エージェント-基幹-api-参照系中心) |
| **B2** | **承認付き業務自動化(HITL)** | **MAF hosted agent** | 調査工程で使用 | BYO VNet | 「担当者が承認してから実行」 | [05](./05-usecase-agent-automation.md#b2-承認付き業務自動化-hitl) |
| **B3** | 長時間・確実な再開 | **MAF + Durable Extension + DTS** | 任意 | 任意 | 数時間〜数日停止して再開 | [05](./05-usecase-agent-automation.md#b3-長時間・確実な再開が要る業務プロセス) |
| **B4** | マルチエージェント(専門分化) | MAF workflows / A2A | 領域別 | 任意 | 領域ごとに権限を分けたい | [05](./05-usecase-agent-automation.md#b4-マルチエージェント-専門分化) |
| **B5** | 業務フローエンジン主導 | Logic Apps / Copilot Studio | 任意 | 任意 | 業務部門がビジュアルで保守 | [05](./05-usecase-agent-automation.md#b5-業務フローエンジン主導-logic-apps-copilot-studio) |
| **C1** | 一般顧客向けチャット | 任意 | 任意 | 公開 + WAF + APIM | 不特定多数が使う | [06](./06-usecase-customer-facing.md#c1-一般顧客向けチャット-単一テナント) |
| **C2** | マルチテナント SaaS | Hosted agent(プロトコル 2.0.0) | テナント別索引 | 公開 + APIM | 複数顧客に販売する | [06](./06-usecase-customer-facing.md#c2-マルチテナント-saas) |
| **C3** | 大規模 / 複数部門への払い出し | 任意 | 任意 | APIM 必須 | 部門別按分・キャパシティ | [06](./06-usecase-customer-facing.md#c3-大規模トラフィック・複数部門への払い出し) |
| **D1** | 規制業種・閉域 | Hosted agent or 自前 | **AI Search 自前索引一択** | **BYO VNet** | 閉域・監査・データ主権 | [07](./07-usecase-regulated-edge.md) |
| **D2** | ソブリン(Azure Government) | **Prompt agent 対応**(Workflows はプレビュー、Hosted agents 非対応) | File Search / AI Search | Gov クラウド | **hosted agent・MCP・A2A が非対応**( https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/azure-government 2026-07-13 更新) | [07](./07-usecase-regulated-edge.md#8-ソブリンクラウド-azure-government) |
| **D3** | エッジ・オンプレ | Foundry 非依存 | 自前 | オフライン | **端末上 = Foundry Local / オンプレ K8s = Azure Local 版(プレビュー・申請制)/ エアギャップ = 切断コンテナ** | [07](./07-usecase-regulated-edge.md#9-エッジ・オンプレ・ハイブリッド) |
| **E1** | 音声エージェント | Voice Live API | 任意 | 要件次第 | リアルタイム音声対話 | [08](./08-usecase-specialized.md#e1-音声エージェント-コンタクトセンター) |
| **E2** | 文書処理・IDP | 非同期パイプライン | DI / Content Understanding | 要件次第 | 帳票・契約書の構造化抽出 | [08](./08-usecase-specialized.md#e2-文書処理・idp-intelligent-document-processing) |
| **E3** | 大量バッチ処理 | ジョブ実行基盤 | 不要 | 任意 | **Batch で 50% 割引** | [08](./08-usecase-specialized.md#e3-大量バッチ処理) |
| **E4** | マルチモーダル生成 | 非同期ジョブ | 不要 | 公開必須(閉域不可) | 画像・動画生成 | [08](./08-usecase-specialized.md#e4-マルチモーダル生成-画像・動画) |
| **E5** | M365 / Teams 連携 | Prompt / Hosted agent | Work IQ 等 | 要件次第 | 業務ツール内で使わせる | [08](./08-usecase-specialized.md#e5-m365-teams-連携) |
| **E6** | ファインチューニング運用 | MLOps パイプライン | 併用推奨 | 要件次第 | **挙動・文体をモデル側で変える**(知識追加は RAG) | [08](./08-usecase-specialized.md#e6-ファインチューニング-モデルカスタマイズの運用) |

### 「Foundry 機能を使う vs 自前実装する」の全組合せ

16 レイヤーそれぞれについて **M(フルマネージド)/ H(ハイブリッド)/ S(自前実装)** の選択肢を [02. 構成要素カタログ](./02-building-blocks.md) に整理してある。要約は下表。

| # | レイヤー | M(フルマネージド) | H(ハイブリッド) | S(自前実装) | 迷ったら |
|---|---|---|---|---|---|
| L1 | モデル提供 | Foundry モデルデプロイ | Foundry + APIM ゲートウェイ | 他クラウド / セルフホスト | M |
| L2 | オーケストレーション | Prompt agent / Workflows(廃止予定) | Hosted agent(MAF・LangGraph) | 自アプリ + Responses API | H |
| L3 | 会話状態 | Agent Service の Conversations | standard setup の BYO Cosmos DB | 自前 DB | M→S |
| L4 | 長期記憶 | Foundry Memory(プレビュー) | Memory + 自前フィルタ | 自前サマライズ + ベクトル検索 | S(本番) |
| L5 | ナレッジ / RAG | File Search / Foundry IQ | AI Search ツール + 自前索引 | 自前パイプライン + 任意ベクトル DB | H |
| L6 | ツール実行 | ツールカタログ / MCP / OpenAPI | Toolbox + 自前 MCP サーバー | アプリ内 function calling | H |
| L7 | コード実行 | Code Interpreter | Custom Code Interpreter | ACA dynamic sessions 直 | M |
| L8 | ガードレール | Guardrails(既定 DefaultV2) | カスタムガードレール | Content Safety API を自前で呼ぶ | M+S 併用 |
| L9 | ID・認可 | Foundry RBAC + Entra | OBO / Agent identity | 自前認可基盤 | M |
| L10 | ネットワーク | パブリック + Private Link | BYO VNet 注入 | 自前 VNet に全部置く | 要件次第 |
| L11 | ゲートウェイ | Foundry のクォータのみ | **APIM AI ゲートウェイ** | 自前プロキシ | H |
| L12 | 可観測性 | Foundry Tracing + Monitor | OTel 自前計装 → App Insights | 自前ログ基盤 | M+H |
| L13 | 評価 | Foundry Evaluations | evals API を CI から呼ぶ | 自前評価ハーネス | H |
| L14 | UI・チャネル | Teams / M365 公開 | 自作 Web + Responses API | 既存システムに組込み | 要件次第 |
| L15 | 実行基盤 | Hosted agents | Container Apps / App Service | AKS / オンプレ | H |
| L16 | IaC・CI/CD | ポータル手動 | Bicep / Terraform + azd | 既存 IaC 基盤に統合 | S |

---

## 選定早見表 — 3 分で当たりをつける

**決定は後戻りコストの大きい順に閉じていく**(詳細は [03. 選定ガイド](./03-decision-guide.md))。

```
 G1 データ・規制ゲート   「そのデータを、どこで、誰に処理させてよいか」
        │                → モデル・デプロイタイプ・外部ツール可否が決まる
        ▼
 G2 ネットワークゲート   「閉域か、パブリックか」
        │                → 使える Foundry 機能の一覧が決まる（後付け不可）
        ▼
 G3 制御ゲート           「明示的な状態遷移・承認・再開が要るか」
        │                → ポータル完結か、コードファーストかが決まる
        ▼
 G4 統合ゲート           「既存システムとの主従はどちらか」
        │                → プラットフォームとして使うか、部品として使うか
        ▼
 G5 ライフサイクルゲート 「いつまで、誰が保守するか」
                         → プレビュー機能の可否・IaC の作り込み度が決まる
```

| 要件の言葉 | 当たりをつけるパターン |
|---|---|
| 「社内文書を検索して答える」 | **A1** で PoC → 品質が出なければ **A2** |
| 「部署によって見える文書が違う」 | **A2**(AI Search + セキュリティフィルタ。GA 要件を満たす唯一の方式) |
| 「担当者の承認を経て実行」 | **B2**(MAF hosted agent)。承認待ちが数日なら **B3** |
| 「複数のエージェントが協調する」 | **B4**。**ポータルのビジュアル Workflows は 2026-12-01 廃止なので選ばない** |
| 「顧客向けに公開する」 | **C1**。WAF チューニングと BOLA 対策を工数に入れる |
| 「複数のお客様に SaaS として提供」 | **C2**。**APIM が事実上必須**(テナント別メータリング) |
| 「閉域で運用する」 | **D1**。**まず「閉域で使えない機能の一覧」から設計を始める** |
| 「日本国内でデータ処理を完結」 | `Standard`(リージョナル)または `ProvisionedManaged`。**APAC Data Zone は日本以外も含むので不可** |
| 「音声で対話したい」 | **E1**(Voice Live)。**SIP 非対応**、ガードレール非適用に注意 |
| 「請求書を読み取って」 | **E2**。定型帳票は DI プリビルト、非定型は Content Understanding |
| 「月間 N 万件を処理」 | **E3**(Batch で 50% 割引)+ [09 章](./09-operations.md)の PTU サイジング |
| 「既存システムに組み込む」 | オーケストレーションは自前(L2 の S)。**Foundry の運用機能は使えなくなる** |
| 「マルチクラウド / ロックイン回避」 | Foundry はモデル供給元として使い、抽象レイヤーを自前で持つ |

---

## 全案件に共通する前提 — Foundry が「やってくれないこと」

**提案時に必ず顧客と合意しておく項目。**個別の詳細は各章に散っているが、頻度と影響の大きい順に並べる。

| # | Foundry がやってくれないこと | 誰が埋めるか |
|---|---|---|
| 1 | **リージョン間の自動フェイルオーバー・DR。**Agent Service は状態のレプリケーション / バックアップ / PITR のいずれも持たず、「復旧は再構築で行う」 | アプリ層でのルーティング + Cosmos DB 継続バックアップ + 再構築パイプライン([09](./09-operations.md#2-信頼性・bcdr)) |
| 2 | **会話に対するユーザー単位の認可。**conversation ID を渡せば誰の会話でも読める(BOLA) | アプリ側で所有権をリクエストごとに検証([06](./06-usecase-customer-facing.md#会話-id-の認可-bola-脆弱性)) |
| 3 | **エージェントの blue-green / canary。**組み込みサポートがない | APIM 等のルーティング層を自前で用意([09](./09-operations.md#6-3-エージェントのバージョニングとリリース)) |
| 4 | **モデルデプロイのラウンドロビン・サーキットブレーカー** | APIM のバックエンドプール + circuit breaker |
| 5 | **部門別・テナント別のトークン計測と課金按分**(クォータはデプロイ単位、`project` タグはプレビューかつ Marketplace モデル非対応) | APIM の `llm-emit-token-metric` |
| 6 | **コストのハードリミット。**「Azure OpenAI には現状その機能がない」 | 予算アラート + 自作の自動化 |
| 7 | **プロジェクト内のエージェント単位のアクセス制御。**`Foundry User` を持てばプロジェクト内の全エージェントと対話できる | アプリの認証認可層、または hosted agent の Entra Agent ID |
| 8 | **`max_output_tokens` / `truncation` によるトークン制御。**「self-hosted orchestration でしか実現できない」 | 自前オーケストレーション |
| 9 | **閉域での Traces / Memory / File Search / Work IQ / Logic Apps / Browser Automation / Computer Use / Image Generation**(Memory は what-is-memory ページ、Work IQ は work-iq ページに VNet 非対応と明記) | 自前実装または機能除外([07](./07-usecase-regulated-edge.md#3-閉域で使えない機能の一覧-設計の出発点)) |
| 10 | **Claude モデルへのコンテンツフィルター**(組込みフィルターが適用されない) | APIM の `llm-content-safety` かアプリ層で Content Safety を呼ぶ |
| 11 | **音声モデルへのガードレール**(Whisper 等には適用されない) | テキスト化後の経路で Content Safety |
| 12 | **capabilityHost の更新。**作成後は変更不可で、変更は **capabilityHost 自体の削除・再作成**で行う(プロジェクト削除は不要。ただし削除で既存エージェントの会話・ファイルへのアクセスは失われる)。委任サブネット等アウトバウンド網の変更は Foundry リソースの再デプロイが必要( https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/capability-hosts ) | IaC を「作り直し前提」で設計 |

**加えて、コンテンツフィルターは「フェイルオープン」する。**フィルタリングシステムが利用不能な場合、リクエストはフィルタリングなしで HTTP 200 で完了する。`content_filter_results` 内のエラーオブジェクトでしか判別できないため、**規制業種では `finish_reason` と `content_filter_results` の検証を必須実装にする。**

---

## 重要な期限(アーキテクチャ判断に直結するもの)

| 期限 | 対象 | 設計への効き方 |
|---|---|---|
| **2026-07-31** | コンテナプロトコル 1.0.0 | **猶予期間後、この日からブロック開始と公表済み**( https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/isolate-sessions-per-user ) |
| **2026-08-20** | Hosted agents 初期プレビュー基盤 | **自動移行されない。**パッケージ・API・エンドポイント・ID・ライフサイクル管理がまとめて変わる([10 章 2.0](./10-migration-antipatterns.md#2-0-最優先-hosted-agent-初期プレビュー基盤-新基盤-期限-2026-08-20)) |
| **2026-08-26** | Assistants API / `azure-ai-inference` SDK | Threads / Runs 前提のアプリは全面改修。**状態データは移行されない** |
| **2026-10-14** | **Azure OpenAI On Your Data** | 「モデルが直接データを読む」構成が終わる。**RAG の既存提案書は要更新**。移行先は Foundry Agent Service + Foundry IQ( https://learn.microsoft.com/en-us/azure/foundry-classic/openai/concepts/use-your-data ) |
| **2026-12-01** | ビジュアル Workflows | **ポータルでマルチエージェントを組む構成が消える。**長期案件で提案不可 |
| **2027-03-31** | Agents (classic)(v1) | classic プロジェクト上のエージェント資産 |
| **2027-04-20** | prompt flow | **新規開発に非推奨。**Microsoft Agent Framework への移行を明示要求 |
| **2028-09-25** | Azure AI Vision Image Analysis | 「2026-09-25 までに移行計画を」と記載 |
| 2027-10 前後 | ファインチューン済みモデルの deployment | 学習停止の約 6 か月後に推論も停止。**FT は作り直しが前提** |
| 日付未公表 | Agent Applications | 廃止告知が予告済み |

全体表は [10 章](./10-migration-antipatterns.md#1-確定済み廃止スケジュールと設計への影響)と [features/README](../features/README.md) を参照。

---

## 本ドキュメント群について

- **正(マスター)は Markdown**(生成 AI 用)。人間用 HTML は `docs/survey/tools/md2html.py` で `html/` 配下に自動生成する。**HTML を直接編集しない。**
- 公式ドキュメントに書かれている事実と、本ドキュメントの判断・推測を区別して書いている。**公式に書かれていない判断には「本ドキュメントの判断」と明記**している。
- **公式ドキュメント間で記述が食い違っている箇所**(Data Zone の APAC 記載漏れ、hosted agents の GA / preview 表記、Reservation の交換可否など)は、その旨を併記している。
- **リンク切れ・削除済みリソース**(ALZ 版 baseline の実装リポジトリなど)も、探して見つからないことに時間を使わないよう明記している。
- **アーキテクチャ図(Azure 公式アイコン)は `images/*.png`(全 18 枚)。**生成スクリプトと再生成手順は [diagrams/](./diagrams/README.md)(maf-ports の描画ヘルパーを共有。図中テキストは英語)。公式-B と A〜E の主要パターンを整備済み。構成が既存図と実質同じもの(公式-A/C、A3/A4、C1/C3、D2)は作図せず理由を diagrams/README に記載。ASCII 図は生成 AI 用にそのまま残している。

### 更新運用

**推奨頻度:** 四半期に 1 回。Ignite(11 月)・Build(5 月)直後は必ず更新。[features/](../features/README.md) の月次更新とは別サイクルでよい(アーキテクチャの骨格は機能ステータスより変化が遅いため)。

**更新時のウォッチリスト:**

1. [Azure Architecture Center の AI アーキテクチャ索引](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/ai-get-started) — リファレンスアーキテクチャの追加・改称
2. [Baseline Microsoft Foundry Chat](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/architecture/baseline-microsoft-foundry-chat) — 本ガイドの土台。`ms.date` の変化を追う
3. [WAF for AI workloads](https://learn.microsoft.com/en-us/azure/well-architected/ai/get-started) — 特に `ai/architecture-pattern` と `ai/application-design`
4. [CAF AI Platform Sharing](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ai/platform/ai-platform-sharing-isolation-colocation) — リソース粒度の一次資料
5. [Agent Service の limits / quotas / regions](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/limits-quotas-regions) — 上限値とリージョン対応
6. [Private Link 構成](https://learn.microsoft.com/en-us/azure/foundry/how-to/configure-private-link) — **閉域で使えない機能の一覧が更新される**
7. [Feature readiness at GA](https://learn.microsoft.com/en-us/azure/foundry/concepts/general-availability) — GA / プレビューの一次情報
8. [`Azure/AI-Landing-Zones`](https://github.com/Azure/AI-Landing-Zones) — Preview から GA への昇格を追う
9. [`microsoft-foundry/foundry-samples`](https://github.com/microsoft-foundry/foundry-samples) — Bicep テンプレートの追加

**HTML の再生成:** リポジトリルートで `python3 docs/survey/tools/md2html.py`(引数なしで features と architecture の両方をビルド)。

### 更新履歴

| 日付 | 内容 |
|---|---|
| 2026-07-29 | 初版作成(全 10 章) |
| 2026-07-29 | 追補調査を反映。**08 章**に Voice Live のクォータ・テレフォニー統合(ACS)・日本リージョン制約、マルチモーダル生成の非同期ジョブと Sora 2 の RAI 制限、**E6 ファインチューニング運用**を追加。**07 章 9 節**をエッジ 3 形態(Foundry Local / Azure Local 版 / 切断コンテナ)に再構成し、**初版の誤り「オンプレ文書処理は DI コンテナが唯一の選択肢」を訂正**(Vision Read OCR も GA・切断対応)。**06 章**に公式のマルチテナンシー 4 方式比較と Responses API の分離課題を追加。**Azure OpenAI On Your Data の非推奨**を 04 / 10 章と期限表に反映 |
| 2026-07-30 | features 側の検証で判明した事実を反映: **08 章の Voice Live を「GA の明文なし」→「GA 一覧表で Preview と明記(ただし Voice Live 自身のページと表記不一致)」に更新** |
| 2026-08-01 | **Azure アイコンのアーキテクチャ図を導入。**代表 4 パターン(公式-B Baseline / A2 / B2 / D1)を `diagrams/*.py` → `images/*.png` で生成し 01・04・05・07 章に埋め込み。md2html.py に画像対応(`![...]` → `<img>`、html/ からの相対パス書き換え)を追加 |
| 2026-08-01 | **アーキテクチャ図を全 18 枚に拡充。**A1(A3/A4 統合)/ A5 / B1 / B3 / B4 / B5 / C2 / D3 / E1〜E6 の 14 枚を追加し全ユースケース章に埋め込み。構成が同型のパターン(公式-A/C、C1/C3、D2)は作図せず理由を diagrams/README に記載 |
| 2026-08-01 | **11 章(エージェント構成の判断フレームワーク)を新設。**「要件→エージェント構成の指標は事前に構築できるか、複数試作して比較するしかないか」への回答として、CAF ai-agents セクション(2025-12 新設: デシジョンツリー・単一 vs マルチの判断表)、AAC オーケストレーションパターン(複雑度の階段・5 パターン・アンチパターン)、Copilot Studio の公式上限ライン(30〜40 アクションで精度劣化・connected agents の多段連鎖不可・Foundry 接続はプレビュー)、業界指標(Anthropic 3 条件・LangChain 4 型)を整理。03 章・tech-selection-guide との対照表つき |
| 2026-07-30 | **全 11 ファイルのファクトチェック(公式ドキュメント突合)と訂正を適用。**確定日の反映: On Your Data 廃止 **2026-10-14**、コンテナプロトコル 1.0.0 ブロック開始 **2026-07-31**。古い記述の更新: **Foundry Local GA(2026-04-09 公式ブログ)**、Toolbox GA、FLUX.2 GA、tsuzumi-7b Legacy(2026-08-31 リタイア)、Groundedness detection 6→4 リージョン、SharePoint「ライセンス必須」→ pay-as-you-go 併記、全遮断 PE のポータル対応。誤りの訂正: capabilityHost 変更は「プロジェクト再作成」でなく「capability host の削除・再作成」、MACAE の org(microsoft)、FT デプロイ上限 10/リソース、Cosmos DB コンテナー 3〜5 個(追加関係)、agent identity とマネージド ID の混同、ガードレール既定閾値「画像 Low」→ テキスト・画像とも Medium、File Search「固定」→ 既定値。ミスリードの限定: 「国内処理必須 → Data Zone(APAC)」を Regional Standard(Japan East)に分離、A2A「ポータル未対応」を incoming 有効化に限定、Front Door パターンのベースライン記事への帰属を Front Door 一般ドキュメントに修正、Cost Analysis「約5時間遅延」を時間非特定に。公式間不整合の両論併記: AI Red Teaming リージョン(2 vs 5)、Traces VNet(非対応 vs プレビュー)、azd コマンド列挙 |
