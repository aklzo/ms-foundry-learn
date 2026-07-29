# 06. 安全性・ガードレール(Trustworthy AI)

[← 機能一覧 TOP](./README.md)

> **最終更新:** 2026-07-29(learn.microsoft.com 現行ページ確認)

## 概要(Ignite 2025 以降の再編)

旧「コンテンツフィルター」は「**Guardrails and controls**」枠組みに再編された。新ドキュメントは https://learn.microsoft.com/en-us/azure/foundry/guardrails/ 配下。ガードレール=コントロールの名前付きコレクションで、各コントロールは「リスク × 介入ポイント × アクション」で定義される。

- **介入ポイントは4つ**: User input / Tool call(プレビュー・エージェントのみ)/ Tool response(プレビュー・エージェントのみ)/ Output
- **アクションは2つ**: Annotate(モデルのみ)/ Annotate and block
- 分類器は引き続き **Azure AI Content Safety** のモデルを利用
- 既定ガードレールは **Microsoft.DefaultV2**(編集不可。テキストは Medium 閾値、画像は Low 閾値)
- **モデル向けガードレールは Azure が販売する全 Foundry Models に適用(音声モデル除く)。エージェント向けガードレールはプレビュー**で、Foundry Agent Service のエージェントのみ対象
- エージェントに割り当てたガードレールは、基盤モデルのガードレールを**完全に上書き**する
- REST API 上の実体は従来どおり **RAI policy**(ARM リソース)で、デプロイの `raiPolicyName` で割当て。リクエスト単位の上書きは `x-policy-id` ヘッダー

## 機能一覧

| 機能名 | 説明 | ステータス | ポータル | CLI | Python SDK | 出典 | 備考 |
|---|---|---|---|---|---|---|---|
| Guardrails and controls(枠組み) | リスク検出・介入ポイント・アクションを定義するコントロールの集合をモデル/エージェントに割当てる新枠組み | モデル向け: GA相当(プレビュー表記なし・既定適用)/ エージェント向け: パブリックプレビュー | 新ポータル: Build > Guardrails(作成・割当・Playground テスト) | 記載なし | 記載なし(注釈読取は OpenAI SDK 経由のみ例示) | https://learn.microsoft.com/en-us/azure/foundry/guardrails/guardrails-overview | REST: RAI Policies Create Or Update(ARM)。`x-policy-id` でリクエスト単位上書き可(画像入力チャットでは不可) |
| Content filters(既定フィルター/カスタム構成) | Hate・Sexual・Violence・Self-harm を Safe/Low/Medium/High の4段階重大度で検出 | GA相当(プレビュー表記なし) | 新: Build > Guardrails / classic: Guardrails & controls | 記載なし | 注釈取得は OpenAI SDK(Python/JS)例あり | https://learn.microsoft.com/en-us/azure/foundry/guardrails/how-to-create-guardrails ・ https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/default-safety-policies | 「Off」は Modified Guardrails 承認顧客のみ(申請フォーム制)。4カテゴリの user input / output コントロールは削除不可・上書きのみ可 |
| Asynchronous Filter(非同期フィルター) | バッファリングなしのトークン単位ストリーミング。フィルター信号は最大約 1,000 文字遅延 | GA(比較表に「Status: GA」明記・全顧客対象) | classic のコンテンツフィルター構成画面の「Streaming」セクション | 記載なし | OpenAI Python SDK v1.0+ / API 2024-02-01 以降 | https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/content-streaming | テキスト・全 GPT モデル対象。遅延フラグ分は Customer Copyright Commitment 対象外の可能性と明記 |
| Prompt Shields(直接/間接攻撃検出) | ジェイルブレイク(直接)とドキュメント埋込み(間接)の攻撃検出。間接攻撃は tool response 介入ポイントにも適用可 | GA相当(プレビュー表記なし)。モデル・エージェント両対応 | 新: Guardrails のリスクとして構成 | 記載なし | 記載なし | https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/content-filter-prompt-shields | 既定ポリシーで jailbreak はプロンプト側で有効。間接攻撃注釈は API 2024-04-01-preview 以降 |
| Spotlighting | 間接攻撃対策の追加層。ドキュメントを base64 変換して信頼度を下げるようタグ付け | パブリックプレビュー。**モデルのみ(エージェント非対応)** | Guardrails のドキュメント攻撃コントロール内トグル | 記載なし | 記載なし | https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/content-filter-prompt-shields | 既定オフ。Chat Completions API のみ。トークン増によるコスト増・応答内にエンコード言及の副作用あり |
| Groundedness detection | RAG 出力がソース文書に接地しているかを検出(Non-Reasoning / Reasoning モード) | パブリックプレビュー。**モデルのみ(エージェント非対応)** | Guardrails のリスクとして構成可 | 記載なし | 記載なし | https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/content-filter-groundedness | フィルター統合時は API 2025-01-01-preview 以降・ストリーミングのみ。英語のみ。文書デリミタ書式必須 |
| Groundedness correction | 非接地箇所をソースに基づき自動修正 | パブリックプレビュー | 記載なし(API 機能) | 記載なし | 記載なし | https://learn.microsoft.com/en-us/azure/ai-services/content-safety/overview | Content Safety API の correction オプションとして提供 |
| Protected material detection(テキスト) | 歌詞・記事・レシピ等の既知著作物と一致する出力を検出 | GA相当(プレビュー表記なし)。既定で completion 側有効 | Guardrails で構成 | 記載なし | 記載なし | https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/content-filter-protected-material | 英語のみ。歌詞 11 語超・ニュース 200 字超などの閾値 |
| Protected material detection(コード) | 既知 GitHub リポジトリのコードとの一致を検出、引用・ライセンス注釈を返す | GA相当(プレビュー表記なし)。既定で completion 側有効 | Guardrails で構成 | 記載なし | 記載なし | 同上 | インデックスは 2023-04-06 までのコードのみ。引用表示が CCC 適用条件になり得る |
| Custom categories(standard / rapid) | 独自カテゴリの学習・定義によるカスタム検出 | パブリックプレビュー(両方) | classic: Content Safety の Try it out 相当 | 記載なし | 記載なし | https://learn.microsoft.com/en-us/azure/ai-services/content-safety/overview | **新 Foundry ガードレールのリスク一覧には未統合**(スタンドアロン API のみ)。standard は英語のみ・リージョン限定 |
| PII 検出/リダクション | LLM 出力内の個人情報(メール・電話・政府 ID・Azure キー等)を検出・フラグ/ブロック | パブリックプレビュー。モデル・エージェント両対応 | Guardrails のリスクとして構成 | 記載なし | 記載なし | https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/content-filter-personal-information | Annotate / Annotate and Block の2モード(カテゴリ別設定可)。注釈に `redacted` フラグあり。API 2025-01-01-preview 以降 |
| Task adherence | エージェントのツール呼び出しがユーザー意図と整合するかを検出、HITL エスカレーション用シグナルを返す | パブリックプレビュー(タイトルに明記)。モデル・エージェント両対応 | classic: Guardrails + controls > Try it out / 新: Guardrails リスクとして構成 | 記載なし | 記載なし(REST + ポータル) | https://learn.microsoft.com/en-us/azure/foundry/guardrails/task-adherence | REST: `contentsafety/agent:analyzeTaskAdherence`(2024-12-15-preview)。最大 10 万字。**データが指定 Geo 外(US/EU)で処理される可能性の明記あり** |
| ブロックリスト | 用語の完全一致/正規表現によるカスタムフィルター。プロンプト側/補完側に適用可 | GA相当(プレビュー表記なし)。ただし **Azure OpenAI モデル限定**と明記 | 新: Build > Guardrails > Blocklists タブ(CSV アップロード可) | `az account get-access-token` のみ使用(専用コマンドなし) | 記載なし | https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/use-blocklists | ARM REST(`raiBlocklists`、api-version 2024-10-01)。1リスト最大1万語・反映まで約5分。Microsoft 内蔵 profanity リストあり |
| Azure AI Content Safety(サービス本体) | 有害コンテンツ検出のスタンドアロン API 群(テキスト/画像/マルチモーダル) | GA(サービス。個別 API にプレビュー混在)。docs 上のブランドは「Foundry Tools」配下に再配置 | Content Safety Studio + classic ポータルの Guardrails + controls | 記載なし | 対応(Quickstart あり) | https://learn.microsoft.com/en-us/azure/ai-services/content-safety/overview | ガードレールの分類器として Foundry に統合。API バージョンの 90 日非推奨ポリシーを明記 |
| Risks & safety モニタリング | デプロイ単位のブロック率・カテゴリ別統計と「潜在的悪用ユーザー検出」ダッシュボード | 要確認(ページに GA/preview 表記なし)。**classic ポータル専用**(「新ポータルでは利用不可」と明記) | classic のみ: Models + endpoints > デプロイ > Monitoring | 記載なし | 記載なし | https://learn.microsoft.com/en-us/azure/foundry-classic/openai/how-to/risks-safety-monitor | 対応リージョン: East US / Switzerland North / France Central / Sweden Central / Canada East。悪用ユーザー検出は user GUID 送信 + Azure Data Explorer(BYO ストレージ)必須 |
| Abuse monitoring(サービス側悪用監視) | Microsoft 側でのコンテンツ分類+使用パターンによる悪用検出 | 稼働中(Models sold by Azure 対象) | ポータル操作なし(サービス側) | — | — | https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/abuse-monitoring | Risks & safety ダッシュボードとは別の、Code of Conduct 執行のための仕組み |

## 補足ノート

**1. エージェント/デプロイ単位の適用と継承ルール**
1つのガードレールを複数のモデルデプロイ・複数のエージェントに割当て可能。エージェントに明示割当てがない場合は基盤モデルデプロイのガードレールを継承し、明示割当てがあればモデル側設定を**完全に上書き**(Tool call / Tool response にコントロールがなければその経路は未スキャンになる点に注意)。Spotlighting と Groundedness はエージェント未対応で、割当てても無効化される。ガードレール処理のレイテンシは介入ポイントあたり約 50〜100ms と明記。エージェント向けのガイド付きセットアップ: https://learn.microsoft.com/en-us/azure/foundry/guardrails/guided-set-up

**2. サードパーティモデルへの適用(SI 判断上の重要点)**
- ガードレールが自動適用されるのは「**Foundry Models sold by Azure**」(Azure OpenAI、DeepSeek、Grok 等の Azure 直販モデル。Whisper 等音声モデル除く)。
- serverless API のパートナーモデルは Content Safety の既定フィルター(テキスト Medium)が適用され、デプロイ単位でオン/オフ可・Content Safety 料金が別課金( https://learn.microsoft.com/en-us/azure/foundry-classic/concepts/model-catalog-content-safety )。
- **Claude は例外**: Claude モデルのページに「**Foundry doesn't provide built-in content filtering for Claude models at deployment time**」と明記(推論時に AI Content Safety を自分で構成する)。Claude は Anthropic 自身の安全システムに依存( https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/claude-models )。

**3. サーフェスの全体傾向**
構成サーフェスは「新 Foundry ポータル(Build > Guardrails)」と「REST(ARM の RAI policy / raiBlocklists)」の2本柱。**Azure CLI・Python SDK 専用の管理コマンド/クラスは現行ドキュメントに記載なし**(Python は注釈の読取・Content Safety データプレーン呼出しの例のみ)。Risks & safety モニタリングだけは classic ポータル専用のまま新ポータル未移植という非対称がある。

**4. ステータス表記の注意**
「モデル向けガードレール枠組み」自体はプレビュー表記がなく既定で全顧客に適用されているため実質 GA 扱いだが、ページに「GA」の文言があるわけではない。Risks & safety モニタリングも現行ページにライフサイクル表記がなく「要確認」とした。
