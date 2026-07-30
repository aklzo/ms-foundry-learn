# 09. 運用アーキテクチャ(キャパシティ・BCDR・可観測性・評価・コスト・CI/CD)

[← アーキテクチャ TOP](./README.md)

> **最終更新:** 2026-07-30(公式ドキュメントとの突合検証で訂正)

ユースケースを問わず横断で効く運用設計をまとめる。**この領域は「Foundry がやってくれない範囲」が広く、見積もりの抜けが出やすい。**

## この章の要点(先に結論)

1. **Foundry は自動フェイルオーバーも DR も提供しない。**「Foundry itself doesn't provide automatic failover or disaster recovery」と明記されている。マルチリージョンは自前設計。
2. **Agent Service の状態(会話・エージェント定義)には DR 機能がない。**「復旧はレプリカの昇格ではなく再構築で行う」。Cosmos DB の継続バックアップが唯一の救済で、**インシデント発生後には有効化できない。**
3. **エージェントの blue-green / canary は組み込み機能がない。**必要ならエージェント API の前段にルーティング層(APIM 等)を自分で置く。
4. **Azure Monitor のレガシー `Latency` メトリクスを使ってはいけない。**Azure OpenAI 用に設計されておらず誤った診断になると明記されている。
5. **リスク・安全性評価と AI Red Teaming は日本リージョンで実行できない。**評価用に別リージョンのプロジェクトを構える設計になる。
6. **capabilityHost は作成後に更新できない。**構成変更は **capability host の削除・再作成**が前提(プロジェクト削除は不要。同名+異構成での再作成は 400 になる)で、IaC の冪等更新が効かない。

---

## 1. キャパシティ設計

### 1.1 デプロイ種別の選択

デプロイ種別は「**データ処理範囲(Global / Data Zone / Regional)× 課金形態(Standard / Provisioned / Batch)**」のマトリクスで決まる。SKU 名がそのまま ARM 上の識別子になる。

| 種別 | SKU コード | データ処理 | 課金 |
|---|---|---|---|
| Global Standard | `GlobalStandard` | 任意の Azure リージョン | 従量。最大クォータ |
| Global Provisioned | `GlobalProvisionedManaged` | 任意の Azure リージョン | PTU 予約 |
| Global Batch | `GlobalBatch` | 任意の Azure リージョン | **50% 割引**・24h 目標 |
| Data Zone Standard | `DataZoneStandard` | データゾーン内(US / EU / APAC) | 従量 |
| Data Zone Provisioned | `DataZoneProvisionedManaged` | データゾーン内 | PTU 予約 |
| Standard(リージョナル) | `Standard` | 単一リージョン | 従量 |
| Regional Provisioned | `ProvisionedManaged` | 単一リージョン | PTU 予約 |
| Developer | `DeveloperTier` | 任意の Azure リージョン | 従量。**FT モデル評価専用・SLA なし・24 時間で自動削除** |
| Instant(プレビュー) | (デプロイ不要) | 任意の Azure リージョン | 従量。**West US 3 のみ** |

**Global / Data Zone の可用性トレードオフ:** 「Global Standard と Data Zone Standard では、プライマリリージョンでサービス中断が起きると、そのリージョンにルーティングされた全トラフィックが影響を受ける」と明記。

### 1.2 クォータ

- **Quota Tiers(Tier 0〜6)**に移行済み。初期割当は現使用量と Microsoft との契約関係(EA / MCA-E)で決まり、**使用量増加で自動昇格する。**オプトアウトは `Microsoft.CognitiveServices/quotaTiers` API(プレビュー)。
- **2026-05-07 以降、サブスクリプション単位のクォータプールへ順次移行中。**Global Standard は同一モデル・バージョンで**全リージョン共通の単一プール**、Data Zone Standard はデータゾーンごとのプール。ポータルの Quota ページの `Scope` 列が `Global` / `Data Zone` なら移行済み、リージョン名なら旧方式。
- **Usage tiers(レイテンシ変動の閾値):** テナント全体の月間トークンが一定量(モデルにより 250 億〜1,500 億トークン/月)を超えると、**レイテンシが 2 倍以上に振れうる**と明記されている。Batch と Provisioned には適用されない。

**アーキテクチャに効くハードリミット:**

| 項目 | 値 |
|---|---|
| Foundry リソース / リージョン / サブスクリプション | 100 |
| プロジェクト / リソース | 250(**フルスケール時の実効は約 25**) |
| モデルデプロイ / リソース | 32 |
| PTU / デプロイ 最大 | 100,000 |
| カスタム HTTP ヘッダー数 | 10(超過で **HTTP 431**)。**将来 API ではパススルー廃止予定のため依存禁止** |
| **同時エージェントセッション** | **50 / サブスクリプション / リージョン** |
| クライアントタイムアウト推奨 | 推論モデル最大 29 分 / 非ストリーミング 29 分 / **ストリーミング 60 秒** |

### 1.3 PTU サイジング

**基本性質:** PTU は**モデル非依存**(同じクォータで任意の対応モデルをデプロイ可)。ただし **Global / Data Zone / Regional は別クォータプール**で相互流用できない。そして **クォータ ≠ キャパシティ** — 「PTU クォータがあってもキャパシティが利用可能とは限らない」。削除・縮小で解放したキャパシティが戻る保証もない。

**最小デプロイ単位:** Global / Data Zone = **15 PTU(増分 5)**、Regional = **25〜50 PTU(増分 25〜50)**。

**サイジング式:**

```
Input TPM       = Peak RPM × 平均プロンプトトークン
Output TPM      = Peak RPM × 平均応答トークン
Normalized TPM  = Input TPM × (1 - キャッシュ率) + (output:input 比 × Output TPM)
必要 PTU        = Normalized TPM ÷ (Input TPM per PTU)  → 増分単位に切り上げ
```

公式のワークショップ例(gpt-5.2、Data Zone Provisioned、1,000 RPM / プロンプト 200 トークン / 応答 20 トークン):

- キャッシュなし: 200,000 + 8×20,000 = 360,000 → 360,000 ÷ 3,400 = 105.88 → **110 PTU**
- キャッシュ率 50%: 100,000 + 160,000 = 260,000 → 76.47 → **80 PTU**(**約 27% 削減**)

**モデル選択が PTU 効率を大きく変える。**同じ 1 PTU あたりの Input TPM が、gpt-4.1 = 3,000 に対し gpt-4.1-nano = 59,400(約 20 倍)。**小型モデルで足りるタスクを大型モデルに投げると PTU コストが桁で変わる。**

**運用上の注意:** PTU デプロイは**一時停止できない(削除のみが課金停止)。**課金は分単位で即時反映されるが、「トラフィックに合わせて PTU を上下させる運用は非推奨」(コストで Reservation に劣り、スケールアップ時にキャパシティが無い可能性がある)。推奨形は **PTU でベースライン + Standard でスパイク。**

### 1.4 Spillover(PTU → Standard の溢れ処理)

**前提:** 同一 Foundry リソース内に、同一モデル・同一バージョンの Provisioned デプロイと Standard デプロイの両方が必要。

- 設定は ARM の `properties.spilloverDeploymentName`(デプロイ単位)またはヘッダー `x-ms-spillover-deployment`(リクエスト単位)。**両方設定するとデプロイプロパティが優先。**
- 発動条件は `429`(PTU 枯渇)/ `400`(長コンテキスト)/ `500` / `503`。
- **監視上の落とし穴:** 溢れた分は **PTU 側の 429 としてカウントされない**(Standard 側に `IsSpillover=True` の `200` として記録される)。**PTU の 429 件数で飽和を判断すると誤る。**
- 公式推奨は「**すべての global / data zone provisioned デプロイで spillover を有効にせよ**」。ただし PTU 優先処理のため追加レイテンシが発生しうる。
- Azure OpenAI モデルのみ。DeepSeek / Llama は非対応。

### 1.5 Prompt caching

- **条件:** プロンプト最低 **1,024 トークン**、かつ**先頭 1,024 トークンが完全一致。**以降は 128 トークン単位でヒット。**1 文字違えばヒットしない。**
- **保持ポリシー:** `in_memory`(非アクティブ 5〜10 分、最終使用から 1 時間以内に必ず消去)/ `24h`(最大 24 時間)。**gpt-5.4 以前の既定は `in_memory`、それより新しいモデルは既定 `24h` で `in_memory` 非対応。**
- **課金:** Standard はキャッシュ読取が入力単価から割引、**Provisioned は最大 100% 割引(PTU 使用率から全額控除)。**
- **⚠ gpt-5.6 以降はキャッシュ書き込みが課金対象**(それ以前は無料)。`usage` にキャッシュ書き込みは別掲されないため `cached_tokens`(読取)でしか監視できない。
- **設計への効き方:** システムプロンプト・ツール定義・共通コンテキストを**プロンプトの先頭に固定配置**し、可変部分を後ろに置く。これだけで PTU 必要量が 2〜3 割変わる。

### 1.6 Batch

- Global Standard 比 **50% 割引**、**24 時間目標。**`completion_window` は **`24h` 固定**(他の値を指定するとジョブが失敗する)。
- 24 時間を超えてもジョブは失効せず実行継続する。`expired` は「24 時間ウィンドウ内に完了できなかった」の意味。
- **クォータは「enqueued tokens」でオンライン系と完全分離。**ファイル投入時にトークン数がカウントされ終端状態まで占有する。
- 入力ファイル最大 200MB(BYO Blob なら 1GB)、1 ファイル最大 100,000 リクエスト。
- **設計への効き方:** 「夜間に全文書を分類する」「過去ログを一括要約する」といった処理を**リアルタイム経路から切り離して Batch に回すだけでモデルコストが半減する。**PoC 段階でこの切り分けを設計に入れておく。

---

## 2. 信頼性・BCDR

### 2.1 責任分界

| 層 | 責任 | 対応 |
|---|---|---|
| Agent Service コントロールプレーン / capability host | Microsoft | ゾーン冗長(Microsoft 側で担保) |
| **状態ストア(Cosmos DB / AI Search / Storage)** | **顧客** | 冗長化・バックアップ・レプリケーション設定 |
| Key Vault | Microsoft(自動フェイルオーバー) | 両リージョンで同一インスタンス使用 |
| Application Insights | 顧客 | **リージョンごとに作成** |
| Container Registry | 顧客 | geo-replication 有効化 |
| Foundry プロジェクト | 顧客 | 各リージョンで作成 |

**Basic セットアップは「人的ミスや自動化による損失に対してほぼ復旧能力を提供しない」**と明記。本番は Standard 一択。

### 2.2 マルチリージョン戦略と RTO/RPO(公式目安)

| 戦略 | 概算 RTO | 概算 RPO | 相対コスト |
|---|---|---|---|
| Hot/hot | 数分 | ほぼゼロ | 最高 |
| Hot/warm | **30 分〜2 時間** | 数分〜数時間 | 中 |
| Hot/cold | **2〜8 時間** | 数時間 | 最低 |

**復旧できないもの:** Foundry プロジェクトのサービス側メタデータ(タグ・アセット名・説明)はリージョン障害時に復旧不可。また **Foundry プロジェクトは GRS/GZRS/RA-GRS による既定のストレージアカウントフェイルオーバーをサポートしない。**

### 2.3 モデルデプロイの冗長化パターン

**Standard デプロイ:**
1. データレジデンシが許すなら **Global Standard を第一候補**、次点 Data Zone。
2. 同一サブスクリプション内にプライマリ / セカンダリ 2 リージョンのリソースを配置。
3. 各リージョンで同一モデルのデプロイを作り、**利用可能クォータを全量 1 デプロイに割り当てる**(分割より高スループット)。
4. 前段に **APIM(ロードバランス + サーキットブレーカー)**。

**Provisioned — 「エンタープライズ PTU プール」パターン:**
- 単一の Data Zone PTU デプロイを全社共通プールとし、APIM でアプリ別のスループット制限・優先度・フェイルオーバーを制御。
- **エンタープライズ PTU プールは、プライマリの Standard デプロイとは別リージョンに配置**(同時被災回避)。
- **フェイルオーバーチェーン:** ワークロード専用 PTU → エンタープライズ PTU プール → Standard デプロイ。**PTU 間で溢れる限りレイテンシ SLA が維持される。**

### 2.4 APIM をゲートウェイに置く場合の設計ルール(公式)

- **`Retry-After` を必ず尊重する。**429 を返すエンドポイントを叩き続けず、そのモデルインスタンスのサーキットを開く。**ヘルスチェック専用エンドポイントは存在しない**ため、`429` / `500` / `503` を回路遮断シグナルとして扱う(合成トランザクションはモデル容量を消費してしまう)。
- **ラウンドロビン / フェイルオーバー先は必ず同一モデル・同一バージョン。**バージョン X と X+1 の間でロードバランスしてはならない(クライアント挙動が不定になる)。
- **全インスタンスでデプロイ名を統一**してルーティングロジックを単純化する。
- **ステートフル API はバックエンドをピン留めし、切替不能なら別インスタンスへ回さず 429 を返す**(履歴のないインスタンスへ隠蔽リダイレクトしない)。
- **データ主権:** 地政学的境界を独立したスタンプとして扱い、境界内でのみ active-active / active-passive を適用。**性能ベースルーティングはデータ主権要件と衝突する。**最も確実なのは地政学的リージョンごとに完全独立のゲートウェイを建てること。
- **ゲートウェイ冗長性:** APIM は 2 ユニット以上 × 2 ゾーン以上、カスタム実装なら最低 3 インスタンスを AZ 分散。

**APIM の主要ポリシー:** `llm-token-limit`(TPM 上限とトークンクォータ。`estimate-prompt-tokens` で**バックエンド到達前にプロンプトを弾ける**)/ `llm-emit-token-metric`(カスタムディメンション付きで App Insights へ)/ `llm-semantic-cache-store` `-lookup`(Azure Managed Redis 必須)/ `llm-content-safety` / backend pool(round-robin / weighted / **priority-based** / session-aware)/ circuit breaker(**バックエンドの `Retry-After` 値を動的トリップ期間として適用**)。

### 2.5 Agent 状態の DR(最重要のリスク開示)

> **Foundry Agent Service には組み込みの DR 機能がない。状態のレプリケーション、バックアップ、ポイントインタイム復元のいずれもできない。復旧は再構築で行う。インシデントによってエージェント・会話・ナレッジデータが恒久的に失われうる。**

**Standard セットアップが要求するリソース構成:**

| リソース | 格納内容 | 要件 |
|---|---|---|
| Cosmos DB for NoSQL | メッセージ・会話履歴・エージェントメタデータ(`enterprise_memory` DB) | **アカウント合計で最低 3,000 RU/s**。コンテナーは **3〜5 個 × 各 1,000 RU/s**(基本 3 個+Responses API 利用エージェントの初回起動で 2 個追加)。**Responses 利用時はプロジェクトあたり実質 5,000 RU/s。プロジェクト数だけ倍増が必要** |
| Azure Storage | アップロードファイル | Blob コンテナー 2 種(`azureml-blobstore` / `agents-blobstore`) |
| Azure AI Search | エージェントが作ったベクトルストア | Search Index Data Contributor + Search Service Contributor |

Cosmos DB の RU/s 不足は **capability host のプロビジョニング失敗の直接原因**になる。コンテナーは基本 3 個(`thread-message-store` 系)に加え、**Responses API を使うエージェントの初回起動で 2 個(`agent-definitions-v1` / `run-state-v1`)が追加される**(排他ではなく追加関係。 https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/use-your-own-resources )点にも注意。

**DR 補償策(公式リスト):**

1. **Cosmos DB: 継続バックアップ(7 日 or 30 日)を事前に有効化。インシデント発生後には有効化できない。**PITR 復元は同一アカウント・同一 DB へ。復元後は Foundry プロジェクトの Connected resources でエンドポイントを更新。**組織固有のユニークなアカウント名を使う**(PITR は元名の新アカウントを作るため名前衝突で復元失敗する)。
2. **AI Search: 組み込みのリストアがない。**データ損失時は Microsoft サポート依頼のみで **RTO に重大な影響。****AI Search を一次データストアとして扱わず、元データからの再構築パイプラインを常備する。**
3. **Storage: GZRS + customer-managed failover。**ZRS のみだとサポート依頼が必要で RTO が伸びる。
4. **スレッドに添付されたユーザーアップロードファイルは原則復旧不可。**「一時的(transient)なもの」であることをステークホルダーに合意させる。
5. **エージェント定義をコードとして管理する**(定義・接続・システムプロンプト・パラメータをソース管理へ。**ポータル経由の未追跡変更を避ける**)。
6. プロジェクトには**ユーザー割当マネージド ID** を使う(誤削除時に既存のロール割当を再利用できる)。
7. Foundry アカウント / Cosmos DB / AI Search / Storage に**削除ロック。**ただしコンテナー内データ・個別エージェント・スレッドは保護されない。
8. **単一責務原則:** Cosmos DB / AI Search / Storage はこのワークロード専用にする(爆発半径の限定)。

### 2.6 可用性ゾーンと SLA

- Microsoft 管理の Agent Service コンポーネントはゾーン冗長。**顧客管理の依存(Cosmos DB / AI Search / Storage)は自分でゾーン冗長設定が必要。**
- **Foundry ポータル・データプレーン API・Agent Service はゾーン冗長の直接制御を提供しない。**
- **Standard モデルデプロイは単一リージョンで AZ 非対応。**マルチデータセンター可用性を得るには Global または Data Zone デプロイが必須。
- **Foundry はモデルデプロイに対するラウンドロビンやサーキットブレーカーを提供しない。**リージョン内の粒度細かい冗長性が要るなら APIM 等の自前ゲートウェイが必要。
- AI Search は Standard ティア以上 + AZ 対応リージョン + レプリカ 3 以上でゾーン分散。
- SLA: Azure OpenAI は可用性 **99.9%**、Provisioned-Managed デプロイには**トークン生成の 99% レイテンシ SLA** が付く。
- **`learn.microsoft.com/azure/reliability/reliability-foundry` は存在しない**(404)。Foundry 専用の Azure Reliability ハブページは未整備。

### 2.7 早期検知の運用設定

1. 全 Foundry ワークロードの Azure サービスに **Service Health アラート**
2. Cosmos DB / Azure OpenAI / Storage に **Resource Health アラート**
3. App Insights の**可用性テスト**(複数地点からエージェントエンドポイントを常時プローブ)
4. アクショングループ(メール / SMS / インシデント管理)でフェイルオーバー判断を迅速化
5. **委任サブネットの IP 使用率は Azure portal に露出していない。**枯渇の先行指標は「data proxy の HTTP 5xx」「hosted agent のセッション作成失敗」「新規プロジェクトのプロビジョニング失敗」の 3 つのみで、**プラットフォームからの事前警告はない。**定期的にエージェントセッションを作る合成監視で補う。

---

## 3. 可観測性

### 3.1 トレーシング

- **ステータス:** prompt / hosted エージェントは **GA**、**workflow と外部エージェントはプレビュー。Tracing の VNet 対応もプレビュー。**
- **サーバーサイドトレースが出発点:** Foundry プロジェクトに Application Insights を接続するだけで**コード変更なしに**数分でトレースが出る。**ポータルでは直近 90 日分**を検索・フィルタできる。
- **キャプチャ内容:** ユーザー入力とエージェント出力、ツール呼び出しと結果、**トークン消費**、所要時間・レイテンシ、リトライ、コスト。
- **Conversation ビュー(トレースリプレイ相当):** Response ID / Trace ID から Conversation ID を辿り、会話履歴・順序付きアクション・ツール呼び出し・入出力を再生できる。
- **保存先は App Insights。**保持期間・サンプリング・課金は App Insights / Log Analytics の設定に従う(**Foundry 側の上乗せ課金はない**)。
- **必要ロール:** ログ参照に **Log Analytics Reader**。対象テーブルが Protected なら Privileged Monitoring Data Reader も必要。
- **セキュリティ:** トレースはプロンプト・出力・ツール引数などの機微情報を含みうる。**テレメトリ到達前にマスクする**のが公式ベストプラクティス。

### 3.2 OpenTelemetry GenAI セマンティック規約のステータス(設計に効く)

Foundry は OpenTelemetry のセマンティック規約に従ってトレースを保存するが、**規約側の成熟度は「Development(非安定)」**である。`gen_ai.provider.name` / `gen_ai.operation.name` / `gen_ai.usage.input_tokens` / `gen_ai.conversation.id` / `gen_ai.agent.name` などはすべて Development バッジで、**`gen_ai.system` は既に非推奨(`gen_ai.provider.name` に置換)。**2026 年に GenAI 規約は専用リポジトリへ分離され、コア規約とは別リリースサイクルになった。

> **設計上の含意:** KQL クエリ・Grafana ダッシュボード・アラートを `gen_ai.*` 属性名に直接ハードコードすると、SDK / 規約の更新で壊れる。**属性名を 1 箇所に抽象化する**か、Foundry ポータル側の抽象化に寄せる。

### 3.3 Azure Monitor メトリクス

**⚠ 最重要の落とし穴:** `Cognitive Services - HTTP Requests` カテゴリの**レガシー `Latency` / `BlockedCalls` / `TotalCalls` は Azure OpenAI 用に設計されておらず、使うと誤った診断になる**と明記されている。

**使うべきメトリクス:**

| 目的 | メトリクス |
|---|---|
| リクエスト数・エラー | `AzureOpenAIRequests`(ディメンション: `StatusCode`、**`IsSpillover`**、`ServiceTierRequest/Response`、`StreamType`) |
| 可用性 | `AzureOpenAIAvailabilityRate` |
| 総応答時間 | `AzureOpenAITTLTInMS` |
| 初回トークン応答性 | `AzureOpenAITimeToResponse` |
| トークン生成速度 | `AzureOpenAINormalizedTBTInMS` |
| **PTU 使用率** | **`AzureOpenAIProvisionedManagedUtilizationV2`**(V1 は非推奨) |
| キャッシュヒット率 | `AzureOpenAIContextTokensCacheMatchRate` |
| トークン数 | `ProcessedPromptTokens` / `GeneratedTokens` / `TokenTransaction` |
| ガードレール | `RAIHarmfulRequests`(`Category` / `Severity` で split)/ `RAIRejectedRequests` |

新しい `Models -*` カテゴリ(`ModelRequests` / `InputTokens` / `ProvisionedUtilization` 等)は Azure OpenAI 以外のモデルも含み、ポータルはこちらへの切替を推奨している。

**診断ログ:** `Audit Logs`(無料)/ `Request and Response Logs`(無料)/ `Trace Logs`(無料)/ `Azure OpenAI Request Usage`(課金)/ `Managed Network Events`(課金)。出力先は `AzureDiagnostics` テーブル。**Basic log plan と ingestion-time transformation はいずれも非対応。**Metrics Explorer では Resource types を「**Foundry Tools**」に設定する。

### 3.4 自前オーケストレーション時の可観測性ギャップ

> アプリケーション内でオーケストレーションするコードを App Service 上で動かす場合、**エージェントのメトリクスは Azure AI Foundry には表示されない。Foundry は完全マネージドの Foundry エージェントしか見えないからである。**

OpenTelemetry の GenAI セマンティック規約に沿って計装すれば、Application Insights 側と App Service の Agents タブでは集計される。**「Foundry のダッシュボードを見せる」ことが要件に入っていないかを事前に確認する。**

### 3.5 Agent Monitoring Dashboard(プレビュー)

Foundry ポータル → Build → エージェント → Monitor タブ。データソースは接続済み App Insights。

**公式が示す運用閾値:**
- **Latency: 10 秒超**ならモデルのスロットリング、複雑なツール呼び出し、ネットワーク問題の兆候
- **Run success rate: 95% 未満**なら失敗した run を調査すべき
- Token usage が多すぎる = 冗長なプロンプト / 応答の兆候

設定パネルの内訳: Continuous evaluation(公式にステータス明示なし。他項目と異なり preview 表記が無いのみで、ダッシュボード自体は View agent metrics (preview))/ Scheduled evaluations(プレビュー)/ Red team scans(プレビュー)/ Alerts(プレビュー)。**継続的評価の `max_hourly_runs` 既定は 100/時**で、到達すると評価 run がスキップされる。**プロジェクトのマネージド ID に Foundry User ロールが必要**(未付与だとルール作成が失敗する)。

**Foundry 外のエージェントも監視できる:** Foundry Control Plane に AI Gateway 経由で登録し、同一 App Insights に OTel GenAI 規約準拠のテレメトリを送れば、継続的評価とエラーレート追跡が使える。

---

## 4. 評価と LLMOps

### 4.1 評価器の選び方(公式の組み合わせ推奨)

- **RAG アプリ:** Retrieval + Groundedness + Relevance + Content Safety
- **エージェントアプリ:** Tool Call Accuracy + Task Adherence + Intent Resolution + Rubric + Content Safety
- 全アプリ共通でリスク・安全性評価器(Hate / Sexual / Violence / Self-Harm)を追加

**評価レベル:** `turn`(既定)と `conversation` がある。**レベルの異なる評価器を同一 run に混在させられない。**

**RAG 評価器の精度側と再現側:** Groundedness は**精度**(応答がコンテキストに沿っているか)、Response Completeness は**再現**(正解データを網羅しているか)を測る。検索パラメータのスイープに使えるのは **Document Retrieval**(正解ラベル必要、LLM 不要で NDCG / XDCG / fidelity を数値計算)。

### 4.2 ⚠ ツールによって使えない評価器がある

公式に明記:

> `tool_call_accuracy`、`tool input accuracy`、`tool_output_utilization`、`tool_call_success`、`groundedness` の各評価器は、**エージェントの会話に Azure AI Search / Bing Grounding / Bing Custom Search / SharePoint Grounding / Code Interpreter / Fabric Data Agent / Web Search への呼び出しが含まれる場合は使うな。**

完全サポートは **File Search / Function Tool / MCP / Knowledge-based MCP。**

> **設計への含意:** 「Foundry Agent + Azure AI Search ツール」構成は、**エージェント評価のストーリーが File Search / MCP(= Foundry IQ)構成より弱い。**評価自動化が要件に入っているなら、この非対称性が RAG 方式の選定に効いてくる。

### 4.3 クラウド評価の実行

- **`azure-ai-projects>=2.2.0` + OpenAI 互換 evals API**(`client.evals.create`、評価器は `builtin.*` 名で指定)。**Entra ID 認証必須(キー不可)。**
- 上限: **1 行あたり最大 2MB / バッチ評価あたり最大 100,000 行。**評価 run 作成はテナント / サブスクリプション / プロジェクトの各レベルでレート制限され、超過時は `retry-after` 付きで返る(**指数バックオフ必須**)。
- 6 シナリオ: データセット評価(GA)/ モデルターゲット評価(GA)/ エージェントターゲット評価(GA)/ エージェント応答評価(GA)/ **トレース評価(プレビュー)** / **会話レベル評価(プレビュー)**。現行ドキュメントではさらに **Synthetic data evaluation / Conversation simulation(いずれもプレビュー)** が追加されている。
- **`azure-ai-evaluation` はローカル評価専用。**クラウド / バッチ評価は `azure-ai-projects` を使う。

### 4.4 リージョン制約(日本の案件で必ず効く)

| 機能 | 対応リージョン |
|---|---|
| バッチ評価 | 広範(**Japan East / Japan West を含む**) |
| **リスク・安全性評価器** | **East US 2 / North Central US / France Central / Sweden Central / Switzerland West / Australia East のみ** |
| Groundedness Pro | East US 2 / Sweden Central のみ |
| Protected material | **East US 2 のみ** |
| **AI Red Teaming** | **公式2ページ間で記載が揺れる**(evaluation-regions-limits-virtual-network は East US 2 / North Central US の 2 リージョン、ai-red-teaming-agent は +France Central / Sweden Central / Switzerland West の 5 リージョン)。**いずれにせよ日本・APAC 非対応** |
| Agent playground 評価 | 米国 8 + 欧州 7 リージョン(**APAC なし**) |

> **設計への含意:** 本番推論は Japan East、**安全性評価と Red Teaming は別リージョンの評価専用プロジェクト**という分離構成になる。**プロンプト・応答が評価のために国外に渡る**ため、法務確認が必須。評価だけなら Agent 用のフル構成(Cosmos DB / AI Search / capability host)は不要で、評価専用の Bicep テンプレートが用意されている。

### 4.5 AI Red Teaming Agent

PyRIT ベース。**Attack Success Rate = 成功攻撃数 ÷ 総攻撃数**を算出する。

- **エージェント固有リスク(クラウドのみ):** Prohibited actions(禁止 / 高リスク / 不可逆アクション)、Sensitive data leakage、Task adherence。
- **XPIA(間接プロンプトインジェクション):** メールや文書などツール経由の外部データに悪意ある指示を埋め込み、エージェントが不正実行するかを検証。攻撃戦略に `Indirect Jailbreak` がある。
- **サポート対象:** hosted prompt agent / hosted container agent は対応。**workflow エージェント・非 Foundry エージェント・Function tool 呼び出し・Browser automation・Connected Agent・Computer Use は非対応。**
- **既知の限界:** 合成データのため実データ分布を代表しない、**生成モデルで ASR を判定するため非決定的で偽陽性がありうる(対処前に必ずレビュー)。**
- **「purple environment」(本番相当リソースの非本番環境)での実行を推奨。**

---

## 5. コストアーキテクチャ

### 5.1 何に課金されるか

| 要素 | 課金 |
|---|---|
| モデルトークン | 入力 / 出力 / キャッシュ読取(**gpt-5.6 以降はキャッシュ書込も**) |
| **Foundry Agent Service 本体** | **プロンプトとワークフローを使う Foundry ネイティブエージェントの作成・実行に追加課金はない** |
| **Hosted agents** | **vCPU 時間 + メモリ GiB 時間** |
| File Search ストレージ | **ベクトルストレージ GB/日** |
| Code Interpreter | **セッション単位** |
| Web Search / Custom Search | **1,000 トランザクション単位** |
| Logic Apps コネクタ / Fabric data agent / SharePoint / Bing grounding / Foundry IQ | いずれも別課金 |
| Cosmos DB / Storage / AI Search | 各サービスの通常課金 |
| Application Insights / Log Analytics | 取込データ量と保持設定。**Foundry 側の上乗せなし** |
| **Foundry Observability** | **課金対象は safety / red teaming / playground 評価のみ。**品質評価と継続的評価は自分のモデルデプロイのトークン課金のみ。**モニタリングとトレーシングは無料** |
| ファインチューニング | Training + **Hosting(デプロイ中は未使用でも時間課金)** + Inference |

**⚠ 見落としがちな課金:**
- **ファインチューニング済みモデルのホスティング料は未使用でも発生する。**
- **Agents playground の評価は全 Foundry プロジェクトで既定 ON。**停止するには playground の metrics から全評価器を選択解除する必要がある。
- **PTU は削除するまで課金が止まらない**(一時停止不可)。

**⚠ 実単価が公開されていない:** Foundry Agent Service / Foundry Observability の公開料金ページは**メーター名と単位のみで金額が `$-` プレースホルダ。**見積時は Azure 料金計算ツールにサインインするか営業経由で取得する必要がある。**Foundry は料金計算ツールに専用ページを持たない**(複数のオプションサービスの組合せのため)。

### 5.2 FinOps レバー

| レバー | 効果 |
|---|---|
| **Batch API** | Global Standard 比 **50% 割引** |
| **Prompt caching** | Provisioned は最大 100% 割引。**サイジング例で必要 PTU 110 → 80(-27%)** |
| **Model router** | Balanced モードで品質 1〜2% 以内、Cost モードで 5〜6% 帯の最安モデルを選択 |
| **PTU Reservations** | 1 か月 / 1 年コミットで時間課金より割引(**割引率は公開ドキュメントに記載なし**) |
| **Spillover** | PTU 使用率を最大化(バースト分だけ Standard へ) |
| **小型モデル** | gpt-4.1-nano は PTU 効率が gpt-4.1 の約 20 倍 |
| **APIM セマンティックキャッシュ** | 近傍プロンプトの応答再利用で**バックエンド呼び出し自体を削減** |
| **APIM `llm-token-limit`** | `estimate-prompt-tokens=true` で**上限超過プロンプトをバックエンド到達前に遮断** |

### 5.3 ショーバック / チャージバック

- **プロジェクト単位の配賦(プレビュー):** 全 Foundry プロジェクトの使用量に**自動的に `project` タグが付く**(手動タグ付け不要)。Cost analysis で Tag フィルタを使う。**⚠ Models sold by Azure のみ対応で、Azure Marketplace 経由のモデルは未対応。**
- **メーターの見え方の罠:** Cost Analysis のサービスフィルタに「Azure OpenAI」は無い(Cognitive Services 分類の下の Service tier で絞る)。**パートナー / コミュニティモデルのメーターは Foundry リソースではなくリソースグループ配下に出る**ため、**Cost Analysis はリソースグループスコープにする。**
- **概算値と実請求はズレる:** ポータルの Estimated cost は**割引や契約価格を反映せず、Provisioned(PTU)も含まない。**課金イベントが Cost Analysis に現れるまで**取り込みタイミングにより遅延がある**(公式は具体的な時間を明示していない。分単位の比較ではなくトレンドで照合する)。財務照合には Cost Management と請求書を使う。**さらに prompt agent と非 Foundry エージェントのコストは Overview の概算に含まれない。**
- **⚠ ハードリミットが無い:** 「OpenAI にはハードリミットがあるが、**Azure OpenAI には現状その機能がない**」。予算超過での自動停止が要件なら、予算アラートのアクショングループから起動する**自動化を自作する必要がある。**
- **消費者別の粒度が要るなら APIM。**`llm-emit-token-metric` のディメンション(既定8種: API ID / Operation ID / Product ID / User ID / Subscription ID / Location / Gateway ID / Backend ID。テナント ID 等はカスタムディメンション〈最大5個〉で追加)を付ければ、Foundry が提供しない粒度でチャージバックできる。

### 5.4 PTU Reservations の注意点

- **デプロイ種別ごとに別購入**(Global / Data Zone / Regional は相互流用不可)。**Global 予約はリージョン非依存**で、複数リージョンの Global PTU デプロイを 1 つの予約でカバーできる。
- マッチング条件は「**デプロイ種別 × リージョン × スコープ**」の 3 つで、**モデルやデプロイ ID では一致させない**(モデル非依存なので新モデル追加時も自動的にカバーされる)。
- **予約はキャパシティを保証しない。必ずデプロイを先に作ってから予約を買う。**
- **余剰予約は失効し翌期に繰り越されない**(24×7 稼働前提の価格)。
- **デプロイを削除しても予約は自動解約されない。**
- **⚠ ドキュメント間の食い違い:** デプロイ種別間の交換について、Reservations 側は可能と読め、provisioned-throughput-billing 側は不可と明記している。**実行前にサポート確認を推奨。**

---

## 6. プラットフォーム自体の CI/CD

### 6.1 環境分離

**公式指針:** 「実験・テスト・本番の環境を計画するとき、**依存リソースを含めて Foundry リソースを明確に分離せよ。**」つまりプロジェクト分割ではなく**リソースごと分離**する。

**プロジェクトは共有 / 分離の単位:** 「同一プロジェクト内の全エージェントは同じファイルストレージ・スレッドストレージ・検索インデックスにアクセスする。データはプロジェクト間で分離される。**プロジェクトが現時点での共有と分離の単位である。**」

**⚠ プロジェクト RBAC の限界:** 「Foundry プロジェクトに **Foundry User** ロールを持つプリンシパルは、**そのプロジェクト内のすべてのエージェントと対話できる。**」どのユーザーがどのエージェント / 会話にアクセスできるかを制御するのは Foundry の RBAC ではなく**自社アプリの認証認可層。**

### 6.2 移植できるもの / できないもの

| 移植できる | 移植できない / 手動 |
|---|---|
| エージェント定義・接続・システムプロンプト・パラメータ(**as code で管理していれば**) | **capabilityHost(更新不可)** |
| モデルデプロイ(IaC で再作成) | Foundry プロジェクトのサービス側メタデータ(タグ・アセット名・説明) |
| Bicep 化した接続、共有 Key Vault | 会話スレッドと添付ファイル |
| geo-replication 済み ACR イメージ | AI Search インデックス(再構築のみ) |
| リージョンを跨いで参照可能な Storage 接続 | Application Insights(リージョンごとに作成) |

> **⚠ capabilityHost は作成後に更新できない**(`400 BadRequest`)。構成変更は **capability host の削除・再作成**で行う(プロジェクト削除は不要。同名+異構成での再作成は 400 になる。 https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/capability-hosts )。**IaC の冪等更新が効かない最大のポイント**で、パイプラインは「capability host の作り直し」を前提に設計する。

### 6.3 エージェントのバージョニングとリリース

- **Foundry はイミュータブルなエージェントバージョンをネイティブサポートする。**定義を変更するたびにバージョンスナップショットが作られ、監査証跡とロールバック先になる。hosted agent のロールバックは**エンドポイントのバージョンセレクタを過去バージョンに向け直すだけ**(リビルド不要)。
- **Structured inputs** でエージェント定義をパラメータ化でき、1 バージョンでユーザー別 / 文脈別の構成を再デプロイなしに提供できる。**⚠ ただし instruction テキストに限定すべき。**MCP サーバー URL などツールエンドポイントをテンプレート化すると、呼び出し側が実行時に任意の外部サービスへエージェントをリダイレクトでき、静的ガバナンスが崩れる。
- **⚠ カナリア / ブルーグリーンは組み込み機能がない:**
  > Foundry はエージェントの blue-green / canary デプロイの組み込みサポートを提供しない。これらのデプロイパターンや、ユーザーのエージェントバージョン間の制御された移行が必要なら、**エージェント API の前段に API ゲートウェイやカスタムルーターのようなルーティング層を実装せよ。**
  - なお prompt agent は `FixedRatio` によるトラフィック % 指定ができるが、**hosted agent は 1 エンドポイント = 1 バージョンで分割できない。**
- **モデルデプロイの version upgrade を自動アップグレードにしない**(テストスイート検証前に応答が変わるのを防ぐ)。
- **非決定性への対処:** 「Foundry Agent Service で定義したエージェントは非決定的に振る舞うため、望ましい品質水準をどう測り維持するかを決めなければならない。**現実的なユーザーの質問とシナリオに対する理想的な応答をチェックするテストスイートを作って実行せよ。**」→ §4 のクラウド評価を CI のゲートに組み込む形になる。

### 6.4 IaC

- **Bicep テンプレート集:** `microsoft-foundry/foundry-samples` の `infrastructure/infrastructure-setup-bicep/` に番号付きシナリオ(private network basic / standard agent setup / APIM 併用 / managed VNet / 評価専用など)。既存リソースの ARM Resource ID を渡して再利用できる。
- 主要リソース種別: `Microsoft.CognitiveServices/accounts`(kind `AIServices`)/ `accounts/projects` / `accounts/deployments`(`sku.name` でデプロイ種別、`properties.spilloverDeploymentName` で spillover)/ `capabilityHosts`(アカウントスコープとプロジェクトスコープの 2 階層)。
- **推奨プラクティス:** ARM/Bicep で両リージョンへ同一デプロイし、**CI/CD パイプラインを両リージョンにデプロイしてドリフトを防ぐ。**ロール割当・VNet / Private Endpoint / DNS も両方に用意する。
- **閉域環境では公開端末から `azd up` / `azd deploy` ができない。**VNet 内のセルフホスト GitHub Actions runner / Azure DevOps agent が公式の推奨パターンで、**CI/CD 基盤の追加コストとして見積もりに入れる。**

---

## 7. 運用設計チェックリスト

**キャパシティ**
- [ ] データレジデンシ要件を確認(「日本国内処理」なら APAC Data Zone は不可)
- [ ] Quota Tier を確認し、自動昇格をオプトアウトするか判断
- [ ] PTU サイジングを式で算出し、**キャッシュ率を織り込む**
- [ ] PTU 購入前に**必ずデプロイを先に作成**してキャパシティ確認 → その後 Reservation 購入
- [ ] Batch に回せる処理を切り分けた(50% 割引)

**信頼性**
- [ ] PTU デプロイ全てに **spillover を有効化**
- [ ] APIM: backend pool(priority-based)+ circuit breaker(`Retry-After` 尊重)、2 ユニット × 2 AZ 以上
- [ ] **Cosmos DB の継続バックアップをインシデント前に有効化**、ゾーン冗長、ユニークなアカウント名
- [ ] Cosmos DB RU/s = 1,000 × コンテナー数 × プロジェクト数(最低 3,000 RU/s)
- [ ] Storage は GZRS、AI Search は Standard 以上 + レプリカ 3
- [ ] Foundry アカウント / Cosmos DB / AI Search / Storage に削除ロック
- [ ] **スレッド添付ファイルは復旧不可**であることをステークホルダーと合意

**可観測性**
- [ ] App Insights を接続、Log Analytics Reader を配布
- [ ] **レガシー `Latency` を使わず** `AzureOpenAITimeToResponse` / `TTLTInMS` / `NormalizedTBTInMS` を使用
- [ ] PTU は `ProvisionedManagedUtilizationV2`(V1 は非推奨)
- [ ] **spillover は 429 として計上されない**点をダッシュボードに明記
- [ ] トレースの PII / シークレット redaction をテレメトリ到達前に実装
- [ ] `gen_ai.*` 属性名への直接依存を 1 箇所に抽象化
- [ ] 委任サブネットの IP 枯渇に対する合成監視

**評価**
- [ ] 評価器の組み合わせを決定(RAG / エージェントで別)
- [ ] **使用ツールが評価器の限定サポートリストに入っていないか確認**
- [ ] **安全性評価と Red Teaming 用に別リージョンのプロジェクトを設計**し、越境の法務確認
- [ ] 継続的評価の `max_hourly_runs` をトラフィックに合わせて調整
- [ ] Agents playground の既定 ON 評価をコスト観点で棚卸し

**コスト**
- [ ] `project` タグでプロジェクト別チャージバック(**Marketplace モデルは対象外**)
- [ ] Cost Analysis は**リソースグループスコープ**
- [ ] FT モデルのホスティング料、PTU の削除忘れ、playground 評価を定期棚卸し
- [ ] 予算アラート + 自動化(**ハードリミットは存在しない**)

**CI/CD**
- [ ] dev/stg/prod は **Foundry リソースごと分離**
- [ ] **capabilityHost 更新不可**を前提にパイプライン設計(capability host の削除・再作成前提。プロジェクト削除は不要)
- [ ] エージェント定義を as-code 化(ポータルでの未追跡変更を禁止)
- [ ] モデルデプロイの自動アップグレードを OFF
- [ ] カナリア / ブルーグリーンが要るなら**ルーティング層を自前で用意**
