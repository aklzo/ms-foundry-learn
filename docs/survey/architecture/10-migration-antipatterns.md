# 10. 移行アーキテクチャとアンチパターン集

[← アーキテクチャ TOP](./README.md)

> **最終更新:** 2026-07-30(公式ドキュメントとの突合検証で訂正)

Foundry は「GA だが足元が動いている」プラットフォームで、**2026 年後半から 2027 年にかけて確定済みの廃止が集中している**。新規設計であっても、廃止スケジュールを知らずに選ぶと 1 年以内に作り直しになる。本ページは (1) 既存資産からの移行アーキテクチャ、(2) 廃止期限の設計への効き方、(3) 提案時に踏みやすいアンチパターン、をまとめる。

## 1. 確定済み廃止スケジュールと設計への影響

| 期限 | 対象 | 設計への効き方 | 移行先 |
|---|---|---|---|
| **2026-08-20** | Hosted agents 初期プレビュー基盤 | 既にプレビュー期に構築した hosted agent は**再デプロイ必須**。コンテナプロトコル 1.0.0 → 2.0.0 | 新基盤へ再デプロイ |
| **2026-08-26** | Assistants API(Azure OpenAI) | Threads / Runs 前提のアプリは全面改修。**状態データは自動移行されない** | Responses API(Agents v2) |
| **2026-08-26** | `azure-ai-inference` SDK | 全言語対象。beta のまま GA せず終了 | OpenAI SDK + v1 API |
| **2026-12-01** | ビジュアル Workflows | **ポータルでマルチエージェントを組む構成が消える。**長期案件で提案不可 | Microsoft Agent Framework(推奨)/ Logic Apps / A2A |
| **2027-03-31** | Agents (classic)(v1) | classic プロジェクト上のエージェント資産 | Agents v2 |
| **2026-10 前後** | gpt-4o / o1 / o3 / o4-mini 等 | モデル固定でチューニングしたプロンプトの再検証が必要 | gpt-5.x 系 |
| **2028-09-25** | Azure AI Vision Image Analysis 4.0/3.2 | 画像解析パイプラインの作り替え | Document Intelligence / Content Understanding / Foundry Models |
| **2026-07-31** | コンテナプロトコル 1.0.0 | **2026-07-31 からブロック開始と公表済み。**1.0.0 のエージェントへのリクエストが**ブロックされる**。2.0.0 でないと 1 セッション内の複数ユーザー多重化ができない | プロトコル 2.0.0 |
| **日付未公表(Planned/TBD)** | Agent Applications(旧 publishing モデル) | 廃止告知と EOS が予告済み。レガシー ID のエージェントは**インプレース昇格不可**(作り直し) | 新オブジェクトモデル(Agent に統合) |
| **2026-10-14** | **Azure OpenAI On Your Data** | 廃止日が公表済み。「モデルが直接データを読む(オーケストレーター不要)」構成が終わる。RAG の既存提案書は要更新 | **Foundry Agent Service + Foundry IQ** |
| 2027-04-20 | prompt flow | **新規開発に非推奨。**ランタイムコンテナはセキュリティ更新も停止済み | Microsoft Agent Framework |
| 2027-10 前後 | ファインチューン済みモデル(gpt-4o / 4.1 / o4-mini 系)の **deployment** | 学習停止(2027-04 前後)の約 6 か月後に推論も停止。**FT は作り直しが前提** | 後継ベースモデルで再ファインチューニング |
| 未発表(投資停止) | ハブベースプロジェクト(classic) | 廃止日は未発表だが新規投資は停止。**新規案件で選ぶ理由はほぼない** | Foundry プロジェクト |

出典・詳細は [features/README の重要期限表](../features/README.md)。

### 設計判断への翻訳

- **「ポータルだけで完結するマルチエージェント」を提案してはいけない。** 2026-12-01 で消える。単一の Prompt agent + ツールは廃止対象外なので、そこまでで足りるかを先に確認する。
- **PTU を使うなら、モデル更改が手動である前提の運用設計を入れる。** Standard は自動アップグレードされるが Provisioned は手動。リタイア通知は GA モデルで 60 日前。
- **classic(ハブベース)にしかない機能に依存すると出口がない。** prompt flow、マネージドコンピュートのモデルデプロイ、serverless API デプロイ、Azure Language リソース連携、Risks & safety モニタリングは classic 側にしか無い。これらが要件に入るなら、classic を選ぶ判断ではなく**代替手段で要件を満たす設計**を先に検討する。

## 2. 移行パターン別アーキテクチャ

### 2.0 【最優先】Hosted agent 初期プレビュー基盤 → 新基盤(期限 2026-08-20)

**本ドキュメント作成時点(2026-07-29)で残り約 3 週間。** 2026 年 4 月より前に `azure-ai-agentserver-agentframework` / `azure-ai-agentserver-langgraph` またはプレビュー hosting API で作った hosted agent が対象で、**自動移行されない**。

「SDK のバージョンを上げる」レベルの話ではなく、パッケージ構成・API・エンドポイント・ID・ライフサイクル管理がまとめて変わる。

| 項目 | 旧(初期プレビュー) | 新 |
|---|---|---|
| サーバーパッケージ | `azure-ai-agentserver-agentframework` / `-langgraph`(**削除済み**) | `azure-ai-agentserver-responses` / `-invocations` |
| MAF パッケージ | `agent-framework` 単一 | `agent-framework-core` / `-openai` / `-foundry` / `-orchestrations` + `agent-framework-foundry-hosting` |
| MAF API | `AzureAIAgentClient` / `ChatAgent` / `@ai_function` | `FoundryChatClient` / `Agent` / `@tool(approval_mode=...)` |
| 起動 | `from_agent_framework(agent).run()` | `ResponsesHostServer(agent).run()` |
| ルーティング | 共有プロジェクトエンドポイント + `agent_reference` | **エージェント専用エンドポイント**(`project.get_openai_client(agent_name=...)`) |
| 実行 ID | プロジェクトのマネージド ID(共有) | **デプロイ時に専用の Entra agent identity を自動発行** |
| ライフサイクル操作 | `az cognitiveservices agent start/stop`、min/max replicas | **全廃**(自動プロビジョン / アイドル 15 分で停止) |
| Capability host | 作成が必要 | **不要**(削除) |
| プロトコルバージョン | `"v1"` | `"1.0.0"`(semver) |
| CLI | `az cognitiveservices agent` 拡張 | **削除** → `az rest` または `azd ai agent` |
| 必要ロール | Foundry Owner 等 | **Foundry Project Manager**(プロジェクトスコープ) |

**さらにコンテナプロトコル 1.0.0 自体も非推奨**で、**2026-07-31 から 1.0.0 のエージェントへのリクエストがブロックされると公表済み。**2.0.0 では `x-agent-foundry-call-id` の転送が必要になる代わりに、`x-agent-user-id` で **1 セッション内の複数ユーザー多重化**が安全に行える(1.0.0 では不可)。マルチテナントで hosted agent を使うなら 2.0.0 が前提。

**LangGraph を載せている場合の追加作業:** LangGraph 専用アダプタは削除されたため、`ResponsesAgentServerHost` + `@app.response_handler` で `context.get_history()` から履歴を LangChain のメッセージ型に自分で変換する実装が要る。モデル接続も `AzureChatOpenAI` ではなく `ChatOpenAI(base_url=f"{FOUNDRY_PROJECT_ENDPOINT}/openai/v1", use_responses_api=True)` に変える(プロジェクトスコープ権限だけで済むようになる)。Toolbox 接続には `langchain-mcp-adapters` + `mcp` が必要。

### 2.0b Agent Applications(旧 publishing モデル)→ 新オブジェクトモデル

エージェントの公開まわりも世代交代している。旧モデルは Agent(データプレーン)+ **Agent Application**(コントロールプレーンの ARM リソース)+ Deployment の 3 階層だったが、新モデルでは **Agent オブジェクトに統合**され、作成時点で安定エンドポイント・プロトコル構成・エージェント ID・agent card を持つ。「creating an agent is the only step needed」。

- **旧 Agent Application は制約が大きい:** ステートレスな `POST /responses` のみ利用可で、`/conversations`・`/files`・`/vector_stores`・`/containers` にアクセスできない。理由は「プロジェクト内の会話について、エンドユーザー間の分離をまだ強制していない」ため — **会話 ID を知られると他人の履歴にアクセスできてしまう**からで、恒久仕様ではなく修正中と明記されている。マルチユーザーのアプリを旧モデルで組んでいるなら、会話履歴はクライアント側で持つ必要がある。
- **レガシーエージェント(`agent.identity == null`)はインプレース昇格できない。**同じ定義で新規作成し直す。
- 廃止告知と EOS は「Planned / TBD」で日付未定。**日付が出る前に移行計画を立てておくべき項目。**

### 2.1 Assistants API / Agents v1 → Agents v2(Responses API)

```
  [Before]                                  [After]
  App ──> Assistants API                    App ──> Responses API
           ├ Threads      (会話)                     ├ Conversations
           ├ Messages     (発言)                     ├ Conversation Items
           ├ Runs         (実行)                     ├ Responses
           └ Assistants   (定義)                     └ Agents / Agent Versions

  クライアント 1 本                          クライアント 2 本
   (OpenAI SDK beta)                          - OpenAI クライアント(会話・実行)
                                              - プロジェクトクライアント(定義・版管理)
```

**移行の実務ポイント:**
- 公式の移行ツールはコード構造を変換するが、**過去の runs / threads / messages は移行されない**。会話履歴を業務上残す必要があるなら、旧 API から自前ストアへエクスポートする工程を別途設計する。
- 新 API では「会話・実行は OpenAI クライアント、エージェント定義・バージョン管理はプロジェクトクライアント」の 2 クライアント構成になる。DI やラッパーを 1 本の抽象に寄せていた実装ほど改修範囲が広い。
- 旧 `create_agent()` は SDK v2.0.0 で削除済み。

### 2.2 ビジュアル Workflows → コードファースト

移行先は 3 つあり、**「ビジュアルを維持したいか」「Foundry に閉じたいか」で選ぶ**。

| 移行先 | 向く場面 | 得るもの / 失うもの |
|---|---|---|
| **Microsoft Agent Framework**(公式推奨) | 今後もエージェント中心に育てる | エクスポートした YAML を宣言的ワークフローとしてほぼ持ち込める。以後 VS Code で反復。ビジュアル編集は失う(Agent Inspector で可視化は可) |
| **Azure Logic Apps** | ビジュアルデザイナーを業務部門が触る前提を維持したい | デザイナーと 1,400+ コネクタを維持。Foundry エージェントはワークフローの 1 ステップに降りる |
| **A2A エンドポイント** | 正式なワークフローは要らず、エージェント間の軽量な委譲で足りる | 疎結合。ただし v1.0 は JSONRPC・テキストのみ・ストリーミング非対応 |

エクスポートした workflow YAML は **hosted agent としてなら実行を継続できる**ため、いったん hosted agent に載せて時間を稼ぎ、その後 MAF のコードへ寄せる二段構えも取れる。

### 2.3 ハブベース(classic)→ Foundry プロジェクト

- **自動移行ツールはない。**新規プロジェクトを作り、接続を作り直す方式(公式ガイドの想定所要は 5〜10 分だが、これはリソース作成部分の話)。
- 移行対象: モデルデプロイ、データファイル、fine-tuned モデル、Assistants、vector store。
- **移行対象外:** プレビュー期の Agent の state、OSS モデルのデプロイ。
- classic に残る機能(prompt flow 等)を使っている場合は、移行ではなく**機能の代替設計**が必要。

### 2.4 Azure OpenAI 単体 → Foundry リソース

kind を `OpenAI` → `AIServices` + `allowProjectManagement: true` に変えるアップグレードが提供されており、**エンドポイント・キー・fine-tune / batch の状態を保持したまま**変換できる(非破壊、ロールバック可)。

- ポータル手順は classic ポータル + Azure ポータル側。新ポータルからの手順は記載なし。
- **CMK 利用リソースは申請フォーム経由のみ。既存 Private Endpoint 付きはポータル経由不可**(削除→再作成 or IaC)。
- Microsoft 側の自動アップグレードプログラムも走っており、`foundryAutoUpgrade` プロパティで状態確認・延期(Deferred)・ロールバックが可能。**顧客に予告なく変わるものではないが、IaC 側で意図しない差分が出る可能性があるため、Terraform/Bicep の drift 検知に入れておく。**

### 2.5 既存システムへの後付け(移行というより組込み)

既存の業務システムに AI を足す案件では、**Foundry をプラットフォームとして採用せず、モデルとツールだけ借りる**構成が現実的なことが多い。

```
  [既存業務システム]                    [Foundry]
   ┌────────────────────┐              ┌──────────────────┐
   │ 既存の認証・認可    │              │ モデルデプロイ    │
   │ 既存の監査ログ      │  Responses   │ ガードレール      │
   │ 既存の業務DB        │ ─── API ───> │ (File Search)     │
   │ ┌────────────────┐ │              │ (Code Interpreter)│
   │ │ AI オーケスト  │ │              └──────────────────┘
   │ │ レーション(自前)│ │
   │ └────────────────┘ │              会話状態・ツール認可・監査は
   └────────────────────┘              すべて既存システム側に残す
```

この構成の利点は、**既存の認可・監査・データ保持ポリシーをそのまま使える**こと。欠点は、Foundry の Tracing / Evaluations / エージェント公開といった運用機能を使えないこと(トレースは自前 OTel 計装で App Insights に寄せれば部分的に取り戻せる)。

## 3. アンチパターン集

### A1. 「ポータルで全部できます」と言ってしまう

ポータル(構成のみ)で本当に完結するのは、**単一 Prompt agent + カタログのツール + 公開**まで。分岐・ループ・リトライ・承認待ちの明示制御、ミドルウェア、ローカルテストは入らない。しかもマルチエージェントのビジュアル構成は 2026-12-01 で消える。

**対処:** 提案時に「ポータル完結の範囲」と「コードが要る範囲」を線引きした表を必ず添える。

### A2. 閉域要件を後から足す

Standard setup(BYO VNet 注入)は**後付け・変更が不可**で、再デプロイが必要。加えて、ネットワーク分離下では Traces・Memory・Work IQ・File Search・Browser Automation・Computer Use・Image Generation 等が使えない/未対応。

**対処:** ネットワーク要件はアーキテクチャ検討の最初のゲートに置く。「閉域で使える機能一覧」から設計を始める。

### A3. File Search で品質が出ないまま押し切る

File Search は埋め込みモデル(text-embedding-3-large / 256 次元)もチャンク設定(800 / オーバーラップ 400)も固定。日本語の長文契約書・表主体の技術文書では、この設定が合わないことがある。

**対処:** PoC 段階で**代表的な難しい文書 20〜30 件**で検索品質を測り、駄目なら早期に AI Search 自前索引へ切り替える。切り替えコストは後になるほど上がる。

### A4. Claude を選んだのにガードレール設計を変えない

Claude は Foundry の組み込みコンテンツフィルターが**適用されない**。Anthropic 自身の安全システムに依存する形になり、Foundry の Guardrails 画面で設定しても効かない。

**対処:** Claude 採用時は Content Safety API をアプリ側で呼ぶ設計を最初から入れる。あるいはモデル選定をやり直す。

### A5. Web search / Grounding with Bing を規制業種で使う

いずれも **DPA 対象外で、データがコンプライアンス境界の外に出る**と明記されている。

**対処:** 規制業種では原則不可として扱い、必要なら社内キュレーション済みの外部情報を AI Search に取り込む方式に置き換える。

### A6. プレビュー機能を本番の必須経路に置く

Memory、Monitoring ダッシュボード、エージェント向けガードレールの Tool call / Tool response 介入、A2A、Routines、Foundry IQ のポータル体験はいずれもプレビュー。プレビューは SLA がなく仕様変更もあり得る。

**対処:** Azure Policy の「Foundry model deployments must meet eligibility requirements」(`denyPreviewModels`)や、タグ `AZML_DISABLE_PREVIEW_FEATURE=true` でプレビューを組織的に抑止できる。本番サブスクリプションには入れておく。

### A7. クォータをアプリ設計で無視する

Foundry のクォータはデプロイ単位。複数部門・複数アプリが 1 デプロイを共有すると、1 つの暴走が全体を止める。

**対処:** 部門・アプリ別にデプロイを分けるか、APIM のトークンレート制限で切る。429 のリトライ/バックオフはアプリ側の必須実装。

### A8. 会話状態を Foundry に預けたまま法定保存要件を受ける

basic セットアップの会話は Microsoft 管理ストレージにあり、所在と保持をこちらで細かく制御できない。しかも basic → standard の切替はセットアップのやり直し。

**対処:** 保存・削除・開示の要件が見えている案件は、最初から standard(BYO Cosmos DB)か自前セッションストアを選ぶ。

### A9. `az` CLI で自動化できる前提で見積もる

**専用の `az foundry` コマンド群は存在しない。**リソース管理は `az cognitiveservices`(GA)、エージェント開発は azd 拡張(プレビュー)、それ以外の多くは「ポータル + SDK/REST のみ」でドキュメントに CLI 手順がない。

**対処:** 自動化は Bicep/Terraform(基盤)+ SDK/REST(データプレーン)前提で工数を積む。

### A10. RBAC ロール名をスクリプトに直書きする

ロール名が旧名(Azure AI User 等)から Foundry User 等へ改名ロールアウト中。ID と権限は不変。

**対処:** IaC / スクリプトではロール ID(GUID)を指定する(公式推奨)。

### A11. ドキュメントのステータス表記を 1 ページだけ見て判断する

hosted agents(GA と preview の混在表記)、Trace Replay、Toolbox、Claude のライフサイクルなど、**公式ページ間でステータスが食い違っている**箇所が複数ある。

**対処:** [Feature readiness at GA](https://learn.microsoft.com/en-us/azure/foundry/concepts/general-availability) を一次情報とし、モデルのリタイア日は [Model retirement schedule](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirement-schedule) 側を採用する。
