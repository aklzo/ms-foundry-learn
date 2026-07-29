# 05. ユースケース編 B — 業務自動化・マルチエージェント・基幹システム連携

[← アーキテクチャ TOP](./README.md)

> **最終更新:** 2026-07-29

「検索して答える」で終わらず、**エージェントが業務システムに対して実際にアクションを起こす**類型。RAG チャットとの決定的な違いは、**誤動作が実世界に不可逆な影響を与えうる**ことで、そのため承認・監査・冪等性・権限の設計が主題になる。

WAF が明示している通り:

> Tools layer のアクションは実世界に、場合によっては**不可逆な**結果をもたらす。**高リスク操作には人間の承認ステップを追加せよ。**統合前にすべてのツールを評価し、ガバナンスをワークロード境界の外まで拡張せよ。

## パターン一覧

| # | パターン | オーケストレーション | 決め手になる要件 |
|---|---|---|---|
| B1 | 単一エージェント + 基幹 API 呼び出し | Prompt agent + Toolbox | 参照系中心。更新は限定的 |
| B2 | **承認付き業務自動化(HITL)** | **MAF hosted agent** | 「担当者が承認してから実行」 |
| B3 | 長時間・確実な再開が要る業務プロセス | **MAF + Durable Extension + DTS** | 数時間〜数日停止して再開 |
| B4 | マルチエージェント(専門分化) | MAF workflows / A2A | 領域ごとにプロンプト・権限を分けたい |
| B5 | 業務フローエンジン主導 | Logic Apps / Copilot Studio | 業務部門がビジュアルで保守 |

**まず複雑度の段階を選ぶ**(公式の AI Agent Orchestration Patterns より):

| レベル | 使う条件 |
|---|---|
| Direct model call | 分類・要約・翻訳などの単発タスク。「**プロンプトエンジニアリングで解けるならエージェントは要らない**」 |
| **Single agent with tools** | **「エンタープライズユースケースではしばしばこれが正しい既定」** |
| Multiagent orchestration | 部門横断、**エージェントごとに異なるセキュリティ境界が必要**、並列特化が有利 |

**この順序を飛ばさない。**WAF も「タスクとモデル呼び出しの間に自動的にエージェントを挟むな。エージェント層はレイテンシを増やし、攻撃面を広げ、テストを複雑にする」と警告している。

---

## B1. 単一エージェント + 基幹 API(参照系中心)

**想定:** 在庫照会、受発注状況の確認、顧客情報の参照。更新は限定的か、行っても低リスク。

```
 [ユーザー(Teams / 自社ポータル)]
        │ Entra ID
        ▼
 [Foundry: Prompt agent]
        │
        ▼
 [Toolbox]  ← 単一の MCP 互換エンドポイント。バージョニングと集中認証
    ├ OpenAPI ツール ──> 基幹 API(社内 APIM 経由)
    ├ MCP ツール ─────> SaaS(ServiceNow / Salesforce 等)
    ├ Azure Functions ─> 独自ロジック(standard セットアップ必須)
    └ AI Search ─────> 手順書・マスタ定義のグラウンディング
```

### ツール接続の選択肢と制約

| 方式 | 認証 | 制約 |
|---|---|---|
| OpenAPI ツール(GA) | anonymous / API キー / マネージド ID | API キーは 1 スキーム / ツール |
| MCP ツール(GA) | キー / Entra(agent MI・project MI)/ **OAuth ID パススルー(OBO)** | 長時間実行はプレビュー |
| Azure Functions(GA) | キュー経由 | **standard セットアップのみ(basic 不可)** |
| Logic Apps コネクタ → MCP 変換(プレビュー) | コネクタ依存 | 1 コネクタ / ツール、**OAuth 2.0 コネクタ非対応**、マネージドコネクタのみ |

**公式の推奨:** 「迷ったら Microsoft Entra 認証から始めよ。」

**Toolbox を挟む理由:** ツール束を一度定義して単一の MCP 互換エンドポイントとして公開でき、バージョニング(バージョン別エンドポイントでテストしてから default に昇格)と集中認証(資格情報の注入・トークン更新・ポリシー適用)を担う。**任意の MCP 対応ランタイム(MAF / LangGraph / GitHub Copilot SDK / 自作)から同じツール群を消費できる**ため、後でオーケストレーションを載せ替えてもツール層が生き残る。

> **⚠ Hosted agent はツールを直付けできない。**「Adding tools directly to hosted agent's definition is not supported. We recommend using toolboxes in Foundry」と明記され、`create_version` の `tools` パラメータは削除済み。**コードファーストに進む予定があるなら、最初から Toolbox 前提で組む。**

**実行時のツール上書き:** `mcp.server_label` / `server_url` / `headers`、`file_search.vector_store_ids` などはリクエスト単位で差し替えられる。**dev/stg/prod で同じエージェント定義を使い回す、テナントごとにナレッジを切り替える**といった構成がバージョンを増やさずに組める。

### 認可の設計(このパターンの本命)

**「エージェントのマネージド ID で叩く(app-only)」か「ログインユーザーの権限で叩く(OBO)」か**で、監査要件の満たし方が変わる。

| パターン | フロー | 権限の源泉 |
|---|---|---|
| **Attended(OBO / 委任アクセス)** | ユーザーがアプリに認証 → アプリがユーザートークンを Agent Service に渡す → 「エージェント ID + ユーザーの委任権限」を持つトークンに交換 | **ユーザーが同意し認可されているリソースにしかアクセスできない** |
| **Unattended(アプリケーション専用)** | blueprint を Entra に認証 → agent identity のトークン取得 → ダウンストリーム向けスコープ付きトークン | エージェント自身の RBAC のみ。人間は不在 |

**Entra Agent ID は GA。**プロジェクトで最初のエージェントを作った時点で既定の blueprint と agent identity がプロビジョニングされる。

**⚠ 実装で詰まりやすい 3 点:**
1. **未公開エージェントはプロジェクト内で共通の ID を共有し、publish すると専用の agent identity が作られる。**このとき `agentIdentityId` が変わるため、**RBAC を再割り当てする必要がある**(共有 ID のロールは引き継がれない)。
2. **RBAC を割り当てるべきプリンシパルは agent identity であって、プロジェクトのマネージド ID ではない。**プロジェクト MI はインフラ操作用(ACR pull 等)であってランタイム ID ではない。
3. **audience は「MCP サーバーの URL」ではなく「ダウンストリームサービスのリソース識別子」**(例: Storage なら `https://storage.azure.com`)。**間違えると RBAC が正しくても認証に失敗する。**

**エージェント単位 RBAC** も使える(スコープ URI は `.../projects/<project>/agents/<agentName>`)。ただし**現時点ではエージェントエンドポイントへのアクセスにのみ評価され**、より広いコントロールプレーン権限は付与しない。エンドユーザーには `Foundry Agent Consumer` をエージェントスコープで割り当てるのが公式のペルソナ例。

**本番の資格情報:** blueprint の資格情報はクライアントシークレット / 証明書 / **フェデレーテッド資格情報(マネージド ID)** の 3 種で、**本番はフェデレーテッド一択**(シークレットを保存しない、Azure が自動ローテーション)。公式も「本番でクライアントシークレットを blueprint の資格情報に使うな」と明示的に警告している。

### 更新系を入れるときの必須事項

- **冪等性。**エージェントはリトライされうるし、非決定的に同じツールを 2 回呼ぶこともある。**更新系 API には冪等キーを持たせる。**
- **金額・権限・件数の上限チェックをツール側に置く。**プロンプトで「10 万円以上は承認を取れ」と書くのは統制ではない。
- **ガードレールの Tool call / Tool response 介入点**を設定する(**プレビュー**)。**エージェントに明示割当したガードレールは基盤モデル側の設定を完全に上書きする**ため、Tool 系のコントロールを置き忘れるとその経路が未スキャンになる。

---

## B2. 承認付き業務自動化(HITL)

**想定:** 「エージェントが調査して実行案を提示 → 担当者が承認 → 実行 → 監査ログ」。SI で最頻出のパターン。

**この要件が入った時点で Prompt agent では足りない。**分岐・承認待ち・再開の明示制御が要るため、コードファーストに上がる。

```
 [業務画面 / Teams]
        │
        ▼
 [Foundry Hosted agent(MAF、Responses プロトコル)]
   ┌──────────────────────────────────────────┐
   │ MAF Workflow(グラフ)                     │
   │   [トリアージ] → [調査(RAG)] → [実行案生成] │
   │                        │                  │
   │                 [RequestInfoExecutor]     │ ← HITL。外部への問い合わせで停止
   │                        │                  │
   │                 承認 ──┴── 却下 → 終了     │
   │                        ▼                  │
   │                   [実行(ツール)] → [監査記録] │
   └──────────────────────────────────────────┘
        │ Toolbox(MCP)
        ▼
 [基幹システム / Logic Apps コネクタ / 社内 MCP(APIM 経由)]
```

**MAF が提供するもの:**
- **Type Safety** — メッセージ型の検証で実行時エラーを防ぐ
- **Flexible Control Flow** — executors と edges のグラフ。条件ルーティング、並列処理、動的パス
- **External Integration** — request/response パターンで外部 API 連携と **HITL**(`RequestInfoExecutor` / `ctx.request_info()`)
- **Checkpointing** — 「チェックポイントでワークフロー状態を保存し、長時間プロセスの回復と再開を可能にする」(Graph API では **superstep 境界**でチェックポイント)
- **Multi-Agent Orchestration** — sequential / concurrent / hand-off / magentic の組込みパターン

**API は 2 種類ある。**Graph API(`WorkflowBuilder`)が「完全サポート」で、Functional API(`@workflow`、Python)は **experimental** と明記されている。**本番は Graph API。**

**ホスティングの選択:** Hosted agent(Foundry が実行)か Container Apps / AKS(自分で実行)か。**Hosted agent はセッション単位のスケールで、アイドル 15 分で計算をデプロビジョンし状態は保持、30 日無活動で恒久削除。**課金はアクティブな全セッションの CPU + メモリ合計で、サイズは 0.5vCPU/1GiB・1vCPU/2GiB・2vCPU/4GiB の 3 種のみ。**オーバーサイジングは同時実行数の倍率でコストに効く。**

**⚠ Hosted agent を選んだ場合の可観測性の利点:** App Insights の接続文字列が自動注入され、プロトコルライブラリが **OpenTelemetry トレースを既定で出力する。**逆に自前オーケストレーション(App Service / ACA)にすると、**エージェントのメトリクスは Foundry のダッシュボードに出ない**(Foundry はマネージドエージェントしか見えない)。

**承認の「待ち時間」が問題になる場合:** Hosted agent のアイドル 15 分は**計算のデプロビジョンであって状態の消失ではない**が、承認が数日にわたるなら B3(Durable)に上げる。

### 監査ログの設計

Foundry の Tracing だけに依存しない。理由は 3 つ。

1. **Tracing はネットワーク分離に未対応**(プライベート App Insights での VNet サポートが未提供)。
2. ポータルで見られるのは**直近 90 日**。それ以上は App Insights / Log Analytics の保持設定に従う。
3. トレースは**プロンプト・出力・ツール引数を含みうる**ため、そのまま法定監査ログにすると機微情報の扱いが問題になる(公式も「テレメトリ到達前にマスクせよ」と推奨している)。

**業務監査ログはアプリ側に別途持つ**(誰が・いつ・何を承認し・どのパラメータで実行されたか)。MAF のミドルウェアで実行パイプラインに差し込むのが自然。

---

## B3. 長時間・確実な再開が要る業務プロセス

**想定:** 承認が数時間〜数日かかる、外部システムのバッチ完了を待つ、途中で失敗したステップだけ再開したい。

**「MAF では長時間処理が無理だから LangGraph へ」と結論する前に、Durable Extension を確認する。**

**Durable Extension for MAF** はエージェント / マルチエージェントオーケストレーション / MAF workflows に**耐久実行**を付与する。エージェントセッションの永続化、進捗チェックポイント、障害回復、分散ホスト間スケールを、**コアのエージェントロジックを変更せずに**適用できる。MAF workflows については「グラフの各ステップを自動的にチェックポイントし、**ワークフロー定義を変更せずに**障害から回復する」と明記されている。

**ホスティングモデルは 2 つ:**

| モデル | 内容 |
|---|---|
| **Azure Functions** | マネージド・サーバーレス。スケールアウトと scale-to-zero、Functions のトリガー / バインディング、HTTP エンドポイント自動生成、**MCP server trigger** |
| **Bring-your-own-compute** | 自前ワーカープロセス、サービス、コンテナ、Kubernetes、既存アプリ基盤 |

**バックエンドは Durable Task Scheduler (DTS) が推奨**(最高性能、フルマネージド、**UI ダッシュボードによる組込みの可観測性**)。DTS ダッシュボードでは agent session insights(会話履歴)と orchestration insights を可視化でき、**ローカル開発用のエミュレータもある**ため CI でのテストがしやすい。

**ステートフルなエージェントスレッド:** thread ID ごとに会話履歴全体を耐久ストレージに保持し、プロセス再起動や別インスタンスでの再開でも保持される。

**注意:** 分散ホストで**信頼性のあるストリーミング**を行うには Redis 等の reliable stream broker が別途必要。また、**Hosted agent の中から DTS を使う公式パターンは本調査では確認できなかった** — Durable を使うなら Functions か自前コンピュートにホストする構成が確実。

**代替案としての Logic Apps / Durable Functions 単体:** 「AI は業務フローの 1 ステップにすぎず、承認・長時間待機・既存業務フロー統合が主役」ならこちら(→ B5)。

---

## B4. マルチエージェント(専門分化)

**まず「本当に必要か」を問う。**多くの案件は単一エージェント + 複数ツールで足りる。マルチエージェントが要るのは「担当領域ごとにプロンプト・ナレッジ・**権限**を分けたい」「並列に調査させたい」場合。

### ⚠ ポータルのビジュアル Workflows は選択肢から外れた

**2026-12-01 に廃止。**「デザイナーとポータル内でのワークフロー実行はサポートされなくなるが、**YAML ベースのワークフロー定義は hosted agent としてデプロイすれば実行を継続する**」。さらに GA 一覧の rollout pitfalls に「**Workflows に新しい本番依存を作ること**」が明記されている。

**移行先は 3 つ:**

| やりたいこと | 移行先 |
|---|---|
| コードファーストに移す | **Microsoft Agent Framework(推奨)。**エクスポートした YAML を宣言的ワークフローとしてほぼそのまま持ち込める |
| ビジュアルデザイナーを維持したい | **Azure Logic Apps。**決定論的ステップと Foundry エージェントの確率的推論を同一実行内で混在させられる |
| 1 エージェントが別エージェントを呼ぶだけ | **A2A** |

**廃止前にやるべきこと:** **YAML ビューに切り替えて定義をエクスポートする**(デザイナーが消える前に)。

**Connected agents について:** 新 Foundry 側のドキュメントが見当たらず classic 側にのみ存在するため、**新ポータルでの GA / プレビュー位置づけが不明瞭。**移行ガイドは A2A ツールを推奨している。**新規設計では A2A か MAF に寄せるのが安全。**

### 5 つのオーケストレーションパターン

| パターン | ルーティング | 適する対象 | 注意点 |
|---|---|---|---|
| Sequential | 決定的・事前定義順 | 段階的な品質向上、明確な依存関係 | 前段の失敗が伝播、並列性なし |
| Concurrent | 決定的 or 動的選択 | 複数視点の独立分析、レイテンシ重視 | 結果矛盾時の解決が必要、リソース消費大 |
| Group chat | chat manager がターン制御 | 合意形成、maker-checker 検証 | 会話ループ、多数エージェントで制御困難 |
| Handoff | エージェントが移譲を判断 | 適切な専門家が処理中に判明する場合 | **無限 handoff ループ**、経路が予測不能 |
| Magentic | manager が task ledger を動的に構築 | 解法が事前に定まらない open-ended 問題 | 収束が遅い、曖昧なゴールで停滞 |

**MAF は 5 パターンすべてを組込みでサポートする。**一方 Foundry Agent Service は「ワークフローが主に非決定的で、**完全に実装できるパターンの範囲が限られる**」と明記されている。

**アンチパターン(公式列挙):** 単純な sequential / concurrent で足りるのに複雑なパターンを使う / 意味ある特化のないエージェント追加 / 多段ホップのレイテンシ軽視 / **並列エージェント間で可変状態を共有(トランザクション不整合)** / **本質的に非決定的なワークフローに決定的パターンを使う(およびその逆)** / コンテキストウィンドウ肥大によるモデルリソースの過剰消費。

### セキュリティ上の必須事項

> エージェントは全ユーザーの要求を扱うためナレッジストアへの広いアクセスを持たざるを得ないが、**ユーザーがアクセスできないデータを返してはならない。セキュリティトリミングはパターン内のすべてのエージェントで実装しなければならない。**

**1 プロジェクト内の全 prompt agent は同一マネージド ID を共有する。**アクセスパターンが異なるならプロジェクトを分ける。**hosted agent は個別の Entra Agent ID を持つ**ので、プロジェクトを分けずに per-agent の権限と監査ができる — **マルチエージェントで権限を分けたいなら hosted agent が有利。**

### A2A を使う場合の制約(プレビュー)

- **Prompt agent は既定で A2A エンドポイントを公開できる。Hosted agent は Responses プロトコルを実装している場合のみ。**
- プロトコル v1.0 と v0.3 の両方をサポートし、**バージョン未指定時は既定で v0.3。**
- **ポータル未対応**(REST または Python SDK のみ)。agent card 設定は REST のみ。
- **Entra ID 認証必須**(キー認証・匿名アクセス不可)。呼び出し側に `Foundry Agent Consumer` ロール以上が必要。
- **制限が厳しい:** テキストモダリティのみ(ファイル等不可)、**ストリーミング(SSE)非対応**、v1.0 は JSONRPC のみ、gRPC 非対応、本番非推奨。

**→ A2A は「組織をまたぐ疎結合な委譲」には筋が良いが、リッチな入出力やストリーミングが要るなら現時点では使えない。**

### エージェント数が多い場合

エージェントが数十〜数百になるなら、公式のソリューションアイデア「Dynamic AI Agents at Scale」が参考になる。AKS 上のオーケストレータ + **AI Search をセマンティックキャッシュとして使い、ベクトル類似検索で候補エージェントを絞る**(単一エージェントが信頼度閾値を超えれば orchestrator の LLM をバイパスして直接呼ぶ)+ Azure Managed Redis で会話コンテキストを TTL 管理、という構成。**ただし「エージェントが 5 未満なら使うな」と明記されている。**

---

## B5. 業務フローエンジン主導(Logic Apps / Copilot Studio)

**想定:** 業務部門がフローを保守したい。承認・通知・既存 SaaS 連携が処理の主役で、AI は判断の一部を担う。

**Logic Apps の agent loop** は 2 形態ある:
- **Autonomous agentic workflows** — agent loop と LLM で反復的に判断・実行、人間の介入なし
- **Conversational agentic workflows** — 対話型

**Foundry Agent Service をモデルソースとして選択でき**(マネージド ID 認証)、逆に **Foundry エージェントから Logic Apps のワークフローをアクションとして呼ぶ**こともできる。**1,400+ のコネクタ**をそのまま使えるのが最大の価値。

**Copilot Studio との棲み分け:** CAF は SaaS(Copilot Studio)vs PaaS(Foundry)として整理し、ハイブリッド運用も推奨している。ただし **Copilot Studio から Foundry エージェントへの接続はプレビュー**(新 Foundry ポータルで作成されたエージェントのみ接続可)。逆方向の **Foundry エージェントを M365 Copilot / Teams に publish するフローは GA。**

**採用モデルとしての位置づけ(CAF):** 「Low-code SaaS 開発は業務部門に開発を開放できるが、**重いカスタマイズは限界に達しマネージドプラットフォームへの移行が必要になる**」。**最初から複雑さが見えているなら Logic Apps / Copilot Studio で始めない。**

---

## オーケストレーション方式の比較

| 軸 | Prompt agent | Hosted agent + MAF | MAF + Durable | Logic Apps | 自アプリ + Responses API |
|---|---|---|---|---|---|
| ステータス | GA | GA(**旧基盤は 2026-08-20 EOS**) | GA(拡張単体の GA 表記は未確認) | GA | GA |
| 状態管理 | サービスが完全管理 | Responses ならプラットフォーム管理 | **thread ID 単位で耐久ストレージに全履歴** | ワークフロー実行状態を保持 | **完全に自前** |
| HITL | ツール承認中心 | `RequestInfoExecutor` を自コードで | **HITL が組込みパターン** | 承認アクション多数 | 自前実装 |
| 長時間実行 | `background: true` + ポーリング | セッション最大 30 日。**アイドル 15 分で計算停止**(状態は保持) | **チェックポイント・障害回復・分散スケール** | Logic Apps ランタイム | 自前 |
| テスト容易性 | Playground 中心 | **`azd ai agent run` でローカル実行可** | **DTS エミュレータでローカル完結** | デザイナー / テストキャンバス | 容易 |
| 可搬性 | Foundry 固有 | **コードは可搬**(ホスティングブリッジのみ Foundry 固有) | Durable Task 依存 | Logic Apps 固有 | 最も高い |
| ネットワーク分離 | private networking 対応 | **BYO VNet。ただしエンドポイント自体は公開のまま** | 自前 VNet で完全制御 | ISE / VNet 統合 | 自アプリ側で制御 |
| 可観測性 | Foundry Tracing(GA) | App Insights 自動注入 + OTel 既定出力 | **DTS ダッシュボード** | Logic Apps 実行履歴 | **Foundry には出ない** |
| コスト構造 | 推論 + ツールのみ(**コンピュート課金なし**) | + セッション単位の CPU/メモリ | Functions / DTS 課金 | Logic Apps 実行課金 | インフラ課金 |

---

## 決定表

| 状況 | 選ぶもの |
|---|---|
| PoC / 社内ツール / 独自オーケストレーション不要 | **Prompt agent**(GA、コンピュート課金なし、最速) |
| 業務ロジックをコードで書きたい / 既存フレームワーク資産あり | **MAF でコードを書き Hosted agent としてデプロイ。**Workflows 廃止の公式移行先で、Microsoft が最も投資している経路 |
| 数時間〜数日の長時間プロセス、確実な再開が要件 | **MAF + Durable Extension + Durable Task Scheduler** |
| ビジュアルデザイナーが業務要件(業務部門が触る) | **Logic Apps**。Copilot Studio は M365 業務エージェント向け |
| LLM 生成コード / 顧客提供コードを実行 | **ACA Dynamic Sessions**(Hyper-V 分離)。Foundry 内で完結させるなら Custom Code Interpreter(プレビュー) |
| マルチクラウド / ロックイン回避が要件 | **自アプリ + Responses API**、または MAF を Container Apps で自己ホスト |

**現時点で最も安全な既定解**は「**Foundry には GA 済みの土台(ホスティング・ID・ツールゲートウェイ・可観測性)だけを任せ、オーケストレーションは GA 済みの MAF コードで持つ**」構成。Foundry 側でプレビューのまま動いている機能(Workflows / Memory / Routines)に業務ロジックの中核を預けずに済む。

```
 [クライアント / Teams / M365 Copilot]
        │ Responses または Activity プロトコル
        ▼
 [Foundry Hosted agent]  ← MAF or LangGraph のコンテナ(Python / C#)
   ├ モデル: Responses API(プロジェクトエンドポイント)
   ├ ツール: Foundry Toolbox(単一 MCP エンドポイント / 集中認証 / バージョニング)
   │    └ 背後: AI Search / OpenAPI / Azure Functions / 社内 MCP(APIM 経由)
   ├ 長時間処理: Durable Extension + DTS(別ワーカー or Functions)
   ├ 非信頼コード実行: ACA Dynamic Sessions
   └ 可観測性: 自動注入の App Insights + OTel(GenAI セマンティック規約)
```

---

## 定期実行・イベント駆動をどうするか

| 選択肢 | 適する場面 | 制約 |
|---|---|---|
| **Routines**(プレビュー) | 「いつこのエージェントを走らせるか」だけを解きたい | **1 トリガー + 1 アクション。**トリガーは timer / recurring(cron 風)/ event(プレビューでは `github_issue` のみ)。**マルチエージェント非対応。**リージョン限定 |
| Logic Apps | 既存の業務トリガーと統合したい | Logic Apps の課金と運用 |
| Azure Functions / Durable | 独自のトリガーロジックが要る | 自前実装 |

Routines の位置づけは公式に明快で、「**Routines がなければ、チームはスケジューラ・Logic Apps・Azure Functions・キュー・カスタムストレージ・認証コードを組み合わせてこのトリガー層を自作することになる**」。実行履歴(入力・出力・ステータス・トレースへのリンク)を Foundry プロジェクト内に保持する点も運用上の利点。**ただしプレビューなので、本番の必須経路に置くなら代替を用意しておく。**

---

## このパターン特有のチェックリスト

- [ ] 更新系ツールに**冪等キー**を持たせたか
- [ ] 金額 / 権限 / 件数の上限チェックを**ツール側**(プロンプトではなく)に置いたか
- [ ] 高リスク操作に**人間の承認ステップ**を入れたか
- [ ] app-only と OBO のどちらで基幹を叩くか決め、監査要件と整合するか確認したか
- [ ] **agent identity に RBAC を割り当てたか**(プロジェクト MI ではなく)
- [ ] publish 時に `agentIdentityId` が変わることを運用手順に入れたか
- [ ] **ガードレールの Tool call / Tool response 介入点**を設定したか(未設定だとその経路が未スキャン)
- [ ] Hosted agent の**セッションサイズをオーバーサイジングしていないか**(同時実行数の倍率でコストに効く)
- [ ] **2026-08-20 の hosted agent 旧基盤 EOS** への対応が済んでいるか([10 章](./10-migration-antipatterns.md))
- [ ] **2026-12-01 の Workflows 廃止**を前提にした構成か
- [ ] 業務監査ログを Foundry の Tracing とは別にアプリ側で持ったか
- [ ] マルチエージェントなら**すべてのエージェント**にセキュリティトリミングを実装したか
- [ ] AI Red Teaming で **Prohibited actions / Sensitive data leakage / Task adherence** を検証したか(**Function tool 呼び出し・Connected Agent・Computer Use は Red Teaming 非対応**な点も認識)
