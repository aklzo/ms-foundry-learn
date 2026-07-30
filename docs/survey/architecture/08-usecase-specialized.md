# 08. ユースケース編 E — 音声・文書処理(IDP)・大量バッチ・マルチモーダル・M365 連携

[← アーキテクチャ TOP](./README.md)

> **最終更新:** 2026-07-30(公式ドキュメントとの突合検証で訂正)

チャット / RAG / 業務自動化に収まらない類型をまとめる。共通するのは、**Foundry Agent Service の外側にある Foundry Tools(旧 Azure AI Services)やモデル固有の API が主役になる**点で、エージェント中心の設計論がそのままは当てはまらない。

## パターン一覧

| # | パターン | 中核サービス | 決め手になる要件 |
|---|---|---|---|
| E1 | 音声エージェント / コンタクトセンター | Voice Live API + ACS | リアルタイム音声対話 |
| E2 | 文書処理・IDP | Document Intelligence / Content Understanding | 帳票・契約書からの構造化抽出 |
| E3 | 大量バッチ処理 | Batch デプロイ + Model router | 数万〜数百万件の分類・要約 |
| E4 | マルチモーダル生成 | 画像 / 動画モデル | 生成コンテンツの非同期処理と安全性 |
| E5 | M365 / Teams 連携 | 公開フロー + Work IQ | 業務ツール内でエージェントを使わせたい |
| E6 | ファインチューニング運用 | SFT / DPO / RFT + MLOps | 挙動・文体・タスク性能をモデル側で変えたい |

---

## E1. 音声エージェント / コンタクトセンター

### Voice Live API とは

**フルマネージドの speech-to-speech 統合 API。**STT + 生成 AI + TTS + アバターを**単一のインターフェース**で提供する。「STT → LLM → TTS」を自分でつなぐ必要がなく、公式も「**デプロイも管理も不要**」と明記している。

| 構成要素 | 選択肢 |
|---|---|
| STT | Azure speech to text(既定)/ `mai-transcribe`(プレビュー)/ `whisper-1` / `gpt-4o-transcribe` 系 |
| LLM | `gpt-realtime` 系 / `gpt-4o` 系 / `gpt-4.1` 系 / `gpt-5`〜`gpt-5.4` 系 / `phi4-*`(プレビュー)/ `azure-realtime` |
| TTS | 600+ voices・150+ locales、HD voices、`MAI-Voice-2-Flash`(プレビュー)、Custom Voice(限定アクセス) |
| アバター | standard / custom / **photo avatar**(静止画 1 枚から talking head)。viseme 出力、word 単位タイムスタンプ |
| 会話品質 | ノイズ抑制、エコーキャンセル、**日本語対応のセマンティック VAD**、フィラー除去、barge-in(割り込み)、auto-truncate |
| ツール | function calling(同期 / 非同期)、**MCP**、VoiceRAG パターン |

### ⚠ ライフサイクル: プレビュー(GA 一覧表で決着。ただし表記の不一致あり)

**[GA 一覧表](https://learn.microsoft.com/en-us/azure/foundry/concepts/general-availability)に「Build > Agents — Voice Live = Preview」と明記されている**(2026-07-30 確認)。**提案では Preview として扱う。**

一方で Voice Live 自身のページには preview バナーも GA 宣言も無く、安定版 API(`2025-10-01` / `2026-04-10`)が存在し、課金は 2025-07-01 に開始されている — **ドキュメント間で表記が一致していない。**SLA を論点にする案件では Microsoft への個別確認が必要。

個別機能で明示的にプレビューなのは:

- **WebRTC 接続**(SLA なし・本番非推奨の標準免責文つき)
- `phi4-mm-realtime` / `phi4-mini`、`mai-transcribe`、`MAI-Voice-2-Flash`、BYOM の Anthropic プロファイル、auto-truncation、評価機能

> 本番設計では **WebRTC を外し WebSocket に寄せる**のが安全。

### 接続モデル

| 方式 | 位置づけ |
|---|---|
| **WebSocket(既定・本番向け)** | 「サーバー間統合が容易」と公式に位置づけられている。**フロントから直接ではなく、自社ミドル層を挟む前提** |
| WebRTC(**プレビュー**) | WS 制御チャネルで SDP 交換。Global standard デプロイのみで最寄りリージョンへ自動ルーティング |
| アバター映像 | WebSocket セッション内で SDP 交換し、音声とは別に WebRTC/ICE で映像配信 |

WebRTC 利用時は **3 チャネル構成**(WS 制御 / WebRTC データチャネル / RTP メディア)になり、アバター設定は side-band 制御では未サポート。

認証は Microsoft Entra ID(推奨)または API キー。**ただしエージェント連携モードは Entra ID 必須。**

### セッション上限とクォータ(サイジングの起点)

| 項目 | 値(Speech リソース Standard S0) |
|---|---|
| 新規接続 / 分(NCPM) | **30** |
| **最大セッション長** | **60 分** |
| トークン / 分(TPM) | **120,000** |
| 換算式 | **TPM = NCPM × 4,000**(NCPM を上げると TPM も自動追随) |
| アバター併用時 | 別途 **2 接続/分**、発話中最大 30 分、アイドル 5 分 |

**⚠ ドキュメント間の不整合:** FAQ は「100,000 tokens per minute」、クォータページは 120,000。**設計時にサポート確認する。**

**コンタクトセンター規模(同時数百コール)では必ず増枠申請が必要。**増枠は専用フォームから「Voice Live API tokens per minute」を選ぶ。**429 はクォータ超過だけでなくオートスケール追随中にも発生する**ため、指数バックオフは必須。公式の推奨負荷パターンは「20 接続から 90〜120 秒ごとに +20、失敗時は 1-2-4-4 分間隔でリトライ」。

### レイテンシ

**Voice Live 固有の SLO / 目標値は公式に見つからなかった。**参照できる数値は以下:

- Azure OpenAI Realtime API の接続方式比較: **WebRTC 約 100ms / WebSocket 約 200ms**(SIP は可変)
- **ガードレール処理は介入点あたり約 50〜100ms 加算**
- エコーキャンセルの前提: 「再生が **2 秒以上**遅延するとエコーキャンセル品質が落ちる」
- つなぎ発話機能(`interim_response`)は `latency_threshold_ms` を超えたら発話を挿入する(サンプル値 100)

### テレフォニー統合(SIP 非対応の回避)

**Voice Live は SIP を直接サポートしない**と FAQ に明記。Architecture Center も「Voice Live API は SIP をサポートしないが、**外部の SIP トランキングソリューションとは連携する**」としている。

**公式に文書化されている接続方法は 3 系統:**

```
 [PSTN / SIP トランク / PBX]
        │  ACS 提供番号 または Direct Routing(SIP)
        ▼
 [Azure Communication Services  Call Automation]
        │  双方向オーディオストリーミング(WebSocket)
        │  16-bit PCM mono 16kHz または 24kHz / 20ms パケット(50fps)
        │  mixed(全参加者ミックス) or unmixed(参加者別・最大 4ch)
        ▼
 [自社ミドル層(サーバー)]
        │  WebSocket
        ▼
 [Voice Live API]  ← STT + LLM + TTS
        │
        └──> 生成音声を ACS へ書き戻して通話へ
```

1. **ACS Call Automation(第一推奨)** — ACS の提供番号を使うか、既存の PSTN キャリア / PBX と **Direct Routing(SIP)** でつなぐ。リファレンス実装として **Call Center Voice Agent Accelerator** が公開されている。
2. **サードパーティ音声コネクタ** — **Twilio Media Streams / Infobip Calls / Genesys AudioHook** が公式に列挙されている。既存コンタクトセンター資産がある場合の現実解。
3. **Voice Live を使わず Azure OpenAI GPT Realtime API の SIP を直接使う** — こちらは **SIP をネイティブサポート**する。着信は Webhook イベントで受け、REST で accept / reject / refer / hangup を制御する。**ただし SIP 対応リージョンは `swedencentral` と `eastus2` のみ。**

> **日本案件での判断:** 国内 PSTN 接続なら ACS Direct Routing か Twilio / Genesys 経由が現実的。**AOAI Realtime の SIP は対応リージョンが北欧・米国のみ**で、音声往復レイテンシとデータ所在の両面で不利になる。Voice Live + ACS なら Voice Live 側を Japan East に置ける(ただし次項のモデル制約あり)。

### ⚠ 日本リージョンの制約が構成を決める

| 機能 | Japan East | Japan West |
|---|---|---|
| `gpt-realtime` 系ネイティブ speech-to-speech | **✗(提供なし)** | ✗ |
| `gpt-4.1` / `gpt-5` 系(テキスト LLM) | Global standard | Global standard |
| HD voices | **✗** | ✗ |
| リアルタイムアバター | **✗** | ✗ |
| **Foundry エージェント連携** | **✅** | **✗** |

> **Japan East ではネイティブ speech-to-speech が使えない。**日本リージョン内で完結させるなら「**非マルチモーダルモデル(`gpt-4.1` / `gpt-5` 等)+ Azure STT/TTS**」構成になり、レイテンシ特性が変わる(モデル内で音声を直接扱う構成に比べて往復が増える)。
>
> さらに **Global standard はデータが任意の Azure リージョンで処理される**ため、データ所在要件がある案件では Japan East の Standard デプロイか Data Zone の検討が必要。なお Speech サービス自体は「リソースのリージョン外でデータを保存・処理しない」と明記されている。

### Foundry エージェントとの連携

| 方式 | 指定方法 |
|---|---|
| Foundry agents(new) | SDK の `AgentSessionConfig`(`agent_name` / `project_name` / `agent_version` / `conversation_id` / リソース上書き / 認証 ID) |
| Foundry agents(classic) | WebSocket のクエリで `agent_id` + `project_id` |
| Hosted agents | 同じく `AgentSessionConfig`(Responses プロトコル)/ Invocations プロトコル |

**制約(設計に効くもの):**

- **カスタムエージェント使用時は `instructions` を渡せない。**プロンプトはエージェント側のメタデータに持たせる。
- **エージェントモードは Entra ID 認証のみ**(API キー不可)。
- **Azure Speech リソース(非 Foundry リソース)では、Agent Service 連携も BYOM も使えない。**リソース種別の選択が機能を決める。
- **MCP は「モデルモード(phi 系を除く)」と「Foundry(new)エージェント」で使えるが、classic エージェントでは使えない。**API バージョン `2026-04-10` 以降が必須。承認フロー(`require_approval`)は音声で許諾を取る形になる。
- Hosted agent を音声対応にするには、Invocations プロトコルで音声トランスクリプトの入出力を実装し、マニフェストに `voiceLiveCompatible: "true"` を付ける必要がある。

### ⚠ ガードレール — 調整も無効化もできない

FAQ に明記されている:

> **コンテンツフィルタリングは含まれる。**ただし **Voice Live API のコンテンツフィルタリングを変更または無効化することはできない。**カスタムのコンテンツフィルタリングが必要なら **bring-your-own-model 機能を使う。**

カテゴリ・しきい値・音声そのものに適用されるのか(テキスト化後なのか)・注釈が返るのかは、**公式ドキュメントで確認できなかった。**

加えて、Foundry Models 側のコンテンツフィルタ記事には **「Whisper のような音声モデルが処理するプロンプトと完了にはコンテンツフィルタリングシステムが適用されない」**と Important として明記されている。

**→ 金融・医療など独自ポリシーが必要な案件は BYOM が前提**(= Foundry リソース必須。Azure Speech リソースでは不可)。BYOM は 3 プロファイル(Azure OpenAI realtime / Azure OpenAI chat completion / Anthropic messages〈プレビュー〉)があり、公式のユースケースとして「**自分の LLM にカスタマイズしたコンテンツセーフティ構成を適用する**」「PTU を使う」「ファインチューン済みモデルを使う」が挙げられている。**BYOM ページは「レイテンシ削減のためフィルタを非同期モードにせよ」と推奨している。**

### E1 のチェックリスト

- [ ] Voice Live を**プレビュー前提**で扱っているか(GA 一覧表の表記。SLA を論点にするなら表記不一致について Microsoft に確認)
- [ ] WebRTC(プレビュー)を本番設計から外したか
- [ ] **Japan East でネイティブ speech-to-speech が使えない**前提で構成を組んだか
- [ ] 同時コール数から必要 NCPM を逆算し(TPM = NCPM × 4,000)、増枠申請の要否を判断したか
- [ ] **最大セッション 60 分**を超える通話の扱いを決めたか
- [ ] テレフォニー接続方式(ACS / サードパーティ / AOAI SIP)を選び、リージョンとデータ所在を確認したか
- [ ] コンテンツフィルタの調整が必要なら **BYOM 前提**の構成にしたか
- [ ] 429 に対する指数バックオフと段階的な負荷投入を実装したか

---

## E2. 文書処理・IDP(Intelligent Document Processing)

### まず Document Intelligence と Content Understanding の使い分けを決める

**公式は「新しいスキルセットには Content Understanding を使え」と方向を示しつつ、Document Intelligence は廃止ではない**と明記している。

> 既に Document Intelligence を本番で動かしているなら、API・エンドポイント・SDK・課金は変わらない。**移行は不要。**

**公式の選択マトリクス:**

| シナリオ | 推奨 | 理由(公式表現) |
|---|---|---|
| OCR / レイアウト抽出のみ | **CU `prebuilt-read` / `prebuilt-layout`** | 「より低コストでリッチなレイアウト抽出」 |
| **マルチモーダル / RAG 前処理** | **CU プリビルト or カスタム** | 「検索の取り込み、根拠付き要約」 |
| **定型帳票(請求書・領収書・ID・税)** | **DI プリビルトモデル** | 「一般的で構造化された文書テンプレートに対する高精度」 |
| 非構造化(契約・法務) | CU `prebuilt-contract` | 推論 + 推定フィールド |
| ラベルなしカスタム抽出 | CU カスタム(ゼロショット) | 「フィールドを平易な言葉で記述するだけ」 |
| ラベルありカスタム抽出 | DI カスタムモデル | 「わずか 5 件のラベル付きサンプルで」 |
| **オンプレ / 閉域(エアギャップ)** | **DI コンテナ**(構造化抽出)/ **Vision Read OCR コンテナ**(単純 OCR) | **Content Understanding にはコンテナが存在しない** → マルチモーダル文書処理はオンプレ不可。詳細は [07 章 9.3](./07-usecase-regulated-edge.md#9-3-切断コンテナ-エアギャップでの-foundry-tools) |

### 上限値の比較(サイジングに直結)

| 項目 | Document Intelligence (S0) | Content Understanding (S0) |
|---|---|---|
| 最大文書サイズ | **500 MB** | 200 MB(PDF/TIFF/画像) |
| **最大ページ数** | **2,000** | **300** |
| Office ファイル | 800 万文字 | 100 万文字 |
| TXT/HTML/MD 等 | — | **1 MB** |
| 音声 | — | 300MB 推奨(最大 1GB)、2 時間推奨(最大 4 時間) |
| 動画 | — | `analyzeBinary` で 200MB / 30 分、URL 指定で 4GB / 2 時間 |
| スループット | 15 TPS(申請で調整可) | 1,000 ページ・画像/分 |

> **⚠ ページ上限の逆転:** **Content Understanding は 300 ページ、Document Intelligence Layout は 2,000 ページ。**超長尺 PDF は上流で分割するか DI Layout を選ぶ。Content Understanding スキルのトラブルシュートでも「インデックス前にソース文書を小さいファイルに分割せよ」と推奨されている。

**ページ単位課金の換算(DI):** PDF = 1 ページ、**DOCX / HTML = 3,000 文字で 1 ページ単位**、XLSX = 1 ワークシート、PPTX = 1 スライド。

### Content Understanding の GA での破壊的変更(見落とすと詰まる)

API `2025-11-01` で GA(2025 年 11 月)。プレビュー版 API は 2026-07-15 までに廃止済み。

- **Pro モード(クロスファイル推論)と Face API はプレビュー限りで GA に持ち越されなかった。**
- **プレビュー期のマネージド生成モデルキャパシティが廃止された** → **自分の Foundry の LLM デプロイと埋め込みデプロイを持ち込む必要がある**(モデル不要の例外は **`prebuilt-read` / `prebuilt-layout` の 2 つのみ**〈公式 whats-new に明記〉)。
- 専用分類 API が廃止され、アナライザ API の `contentCategories` に統合(カテゴリ上限 50 → 200)。

**課金モデル:** (1) content extraction(文書は 1,000 ページ単位、音声 / 動画は分単位、**画像は無料**)、(2) contextualization(固定: 1,000 トークン/ページ、10 万トークン/時間の音声、100 万トークン/時間の動画)、(3) **LLM / 埋め込みトークンは自分の Foundry デプロイに課金。**コスト倍率は source grounding + confidence で約 2 倍、extractive モードで約 1.5 倍、segmentation で約 2 倍。**ミニモデルで LLM コストを最大 80% 削減できる**と明記されている。

### 取り込みパイプラインのアーキテクチャ

```
 [文書投入: Blob / SharePoint / メール / スキャナ]
        │
        ▼
 [キュー(Service Bus / Storage Queue)]  ← バックプレッシャーとリトライの受け皿
        │
        ▼
 [処理ワーカー]
   選択肢: Durable Functions / Container Apps jobs / Logic Apps / AI Search インデクサ
        │
        ├─> [Document Intelligence Layout or Content Understanding]  構造抽出
        ├─> [チャンク分割 + 埋め込み]  ← 埋め込みは Batch デプロイに回すとコスト半減
        └─> [Azure AI Search インデックス] / [Cosmos DB]
        │
        ▼
 [Foundry エージェント]  ← 検索・質問応答
```

**公式リファレンスが 2 つある:**
- **Durable Functions 版**(文書分類):Web アプリ → Blob + Service Bus → Durable Functions(analyze / metadata store / embedding)→ AI Search。注目点は「**Agent Framework にはテキスト分割プリミティブがないため Semantic Kernel の `TextChunker` を使う**」ことと、**埋め込み工程を Batch デプロイ(`GlobalBatch`、24 時間ターンアラウンド)に回してコスト削減する**推奨。
- **Container Apps 版**(マルチモーダル):Container Apps + Queue Storage + Content Understanding + Azure OpenAI + Cosmos DB。**confidence score による人手レビュー分岐**を持つ点が実務的で、公式に「ワークフローが単純 / ビジュアル設計を好む / ローコード寄りチームなら **Logic Apps か Azure Functions に置き換えよ**」と代替案も示されている。

**AI Search のスキルとして組み込む場合の比較:**

| | Document Layout skill | **Content Understanding skill** |
|---|---|---|
| ステータス | 既存パイプライン向け | **GA(2026-04-01)。**セマンティックチャンキングはプレビュー |
| 表・図の出力 | **プレーンテキスト(情報欠落)** | **Markdown** |
| ページ跨ぎの表 | 分断される | **単一単位で抽出** |
| チャンクのページ跨ぎ | 不可 | 可 |
| 無料枠 | インデクサあたり 20 文書/日 | **なし(全文書課金)** |

**両スキル共通の罠:** **レイアウト処理に 5 分以上かかる文書はタイムアウトし、しかも課金される。**

**Markdown 出力の挙動変更(DI v4.0 GA):** **表は HTML テーブルとして出力される**(パイプ表ではない。結合セル・複数行ヘッダー対応のため)。選択マークは Unicode `☒` / `☐`(旧 `:selected:`)。**後段のパーサを書くときにここを間違えやすい。**

### Vision の世代交代に注意

**Azure AI Vision Image Analysis 4.0/3.2 は 2028-09-25 廃止**で、「2026-09-25 までに移行計画を」と記載されている。公式の移行先は OCR → Document Intelligence、顔 → Face API、埋め込み → Cohere Embed、汎用 → GPT 系 Foundry Models / Content Understanding。**既存の画像解析パイプラインを持つ顧客には、この期限を提示する。**

---

## E3. 大量バッチ処理

**「リアルタイムでなくてよい処理」を切り出すだけでモデルコストが半減する。**PoC 段階でこの切り分けを設計に入れる。

| レバー | 効果 | 注意 |
|---|---|---|
| **Batch デプロイ** | **Global Standard 比 50% 割引**、24 時間目標 | `completion_window` は **`24h` 固定**(他の値を指定するとジョブ失敗)。**enqueued tokens クォータはオンライン系と完全分離** |
| **Model router(Cost モード)** | 品質 5〜6% 帯で最安モデルを選択 | **有効コンテキストウィンドウが最小の下位モデルに制限される。**大きなコンテキストなら model subset で絞る |
| **小型モデル** | gpt-4.1-nano は PTU 効率が gpt-4.1 の約 20 倍 | 品質検証が前提 |
| **Prompt caching** | 共通プレフィックスの再利用 | **先頭 1,024 トークンが完全一致**する設計にする |

**Batch の制限:** 入力ファイル最大 200MB(BYO Blob なら 1GB)、**1 ファイル最大 100,000 リクエスト**、有効期限未設定なら入力ファイル 500 個 / リソース(`expires_after` を設定すると 10,000 個)。24 時間を超えてもジョブは失効せず実行を継続する。

**運用推奨:** **Dynamic quota を ON** にして余剰容量を機会的に利用する。一部リージョンでは `token_limit_exceeded` を即時返す **fail-fast + 指数バックオフ**でジョブをキューイングできる。

**アーキテクチャの骨格:**

```
 [投入: Blob / DB / イベント]
        │
        ▼
 [ジョブ生成(JSONL 作成)] ← Functions / Container Apps jobs
        │
        ▼
 [Batch デプロイに投入] ──> 24h 以内に完了 ──> [結果 JSONL]
        │                                            │
        │ fail-fast + 指数バックオフでリトライ           ▼
        └────────────────────────────────>  [結果取り込み・後処理]
```

**リアルタイム経路との共存:** Batch とオンラインでクォータプールが分離されているため、**バッチが暴走してもリアルタイム側のクォータを食わない。**これは設計上の大きな利点で、「日中はチャット、夜間は一括処理」を同一リソースで安全に同居させられる。

---

## E4. マルチモーダル生成(画像・動画)

### モデルのライフサイクル

| モデル | ステータス |
|---|---|
| **`gpt-image-2`** | **GA。申請不要** |
| `gpt-image-1.5` / `gpt-image-1` / `gpt-image-1-mini` | **限定アクセス(要申請)。**ライフサイクルは **`gpt-image-1` のみ Preview**(2026-10-23 リタイア)。`gpt-image-1.5`(2026-12-16 リタイア)と `gpt-image-1-mini` は **GA** |
| `dall-e-3` | **2026-03-04 に廃止済み** |
| `FLUX.2-pro` / `FLUX.2-flex`(Black Forest Labs) | **GA**(model-retirement-schedule の Black Forest Labs 表で Lifecycle = GA)。multi-reference は API のみ(Playground 不可) |
| `MAI-Image-2.5` 系(Microsoft) | プレビュー |
| **`sora` / `sora-2`(動画)** | **プレビュー** |

### 画像生成 — API は同期。制約はレート制限

**画像生成は同期 API**(`/images/generations`、`/images/edits`)で、非同期ジョブではない。FLUX は Image API に加えてプロバイダ固有 API(`seed` / `safety_tolerance` 等が使える)も利用できる。

| 項目 | `gpt-image-2` | `gpt-image-1.5` / `-1` / `-1-mini` |
|---|---|---|
| サイズ | **任意解像度。**両辺が 16px の倍数、長辺 ≤3,840px(4K)、アスペクト比 ≤3:1、総ピクセル 655,360〜8,294,400 | `1024x1024` / `1024x1536` / `1536x1024` のみ |
| 品質 | `low` / `medium` / `high` | 同左 |
| 出力 | `png`(既定)/ `jpeg`。**GPT-image 系は常に base64 を返す**(`response_format` 非対応) | 同左 |
| 枚数 | `n` は 1〜10。`partial_images` でストリーミング可 | 同左 |
| 編集 | inpainting(マスクは同寸法 PNG、alpha=0 が編集対象)/ variations。入力は PNG/JPG **50MB 未満** | 同左 |
| プロンプト長 | (4,000 文字は dall-e-3 世代の制限。gpt-image 系の上限は現行リファレンスで要確認) | 同左 |

**⚠ 設計上の最大の制約はレート制限。**既定は **9 RPM 前後**しかない。

| モデル / デプロイ種別 | Tier 1 | Tier 3 | Tier 6 |
|---|---|---|---|
| `gpt-image-2` GlobalStandard | 6 | 18 | 36 |
| `gpt-image-2` **DataZoneStandard** | **2** | **6** | **12** |
| `gpt-image-1.5` GlobalStandard | 9 | 30 | 90 |
| `gpt-image-1-mini` GlobalStandard | 12 | 54 | 180 |

**TPM は設定されず RPM のみ。**しかも **Data Zone デプロイは Global の 1/3 程度**まで落ちる。**データ所在要件と画像生成スループットは正面から衝突する。**

### 動画生成(Sora / Sora 2)— 非同期ジョブ + 24 時間の失効

**API は 2 系統が併記されている**(Azure 独自の jobs API と、OpenAI v1 互換の videos API)。いずれも「ジョブ作成 → ポーリング → コンテンツ取得」の流れ。

```
 POST  .../video/generations/jobs        → {"id":"task_...","status":"queued"}
 GET   .../video/generations/jobs/{id}   → queued → preprocessing → running
                                            → processing → succeeded | failed | cancelled
 GET   .../video/generations/{gid}/content/video → MP4 バイナリ
```

OpenAI 互換側は Create / Get Status / Download / **List** / **Delete** の 5 エンドポイントに加え、`remix` で構図・モーションを再利用できる。生成時間は **1〜5 分。**

**アーキテクチャを支配する制約:**

| 項目 | 値 |
|---|---|
| **同時実行** | **2 ジョブまで**(1 つ終わるまで新規不可) |
| **ジョブ保持** | **作成後 24 時間で失効** |
| **クォータ** | `sora` は 60 RPM、**`sora-2` は 2 job RPM**(動画ジョブ要求のみカウント) |
| 入力 | 画像最大 2 枚(間を補間)、動画 1 本・最大 5 秒 |

**⚠ ドキュメント内に不整合がある。**解像度と尺について「Limitations 節」「API パラメータ表」「トラブルシュート表」の 3 箇所で記述が食い違っている(尺は 1〜20 秒 vs 4/8/12 秒、解像度も列挙が異なる)。**実装前に対象リージョン・デプロイで実測確認する。**

**ストレージ:** 出力は Azure OpenAI 側に保持され、Download で取得、Delete で個別削除する。**BYO Storage(自社 Blob への直接出力)の記載は見つからなかった。ジョブが 24 時間で失効する以上、成功後すぐに自社 Blob へ退避する設計が必須。**

### ⚠ 安全性とプロベナンス — 動画は文書化されていない

**画像には Content Credentials(C2PA)が自動付与される。**

> Azure OpenAI が生成したすべての AI 生成画像には **Content Credentials** が含まれる。これは C2PA のオープン仕様に基づく、改ざん検知可能なコンテンツの来歴開示手段である。

マニフェストには `description: "AI Generated Image"`、`softwareAgent`(`Azure OpenAI DALL-E` または `Azure OpenAI ImageGen`)、生成タイムスタンプが入り、Azure OpenAI に遡る証明書で署名される。追加設定は不要で、検証は contentcredentials.org などで行える。

**ただし重大な留保が 3 つある:**

1. この記事は **「Foundry (classic) ポータル専用。新 Foundry ポータル向けには提供されない」**と明記されており、**新 Foundry ドキュメントに対応記事が存在しない**(該当 URL は 404)。
2. **`gpt-image-2` が明示的に列挙されていない**(記載は「DALL·E and GPT-image-1 series」)。同系統として付与される可能性は高いが**確認できず。**
3. **動画(Sora / Sora 2)への C2PA・電子透かし・プロベナンス付与の記載は一切見つからなかった。**生成動画の来歴表示が要件なら、**自前で C2PA を付与する検討が必要。**

**コンテンツフィルタリングは入力プロンプトと出力画像の両方に適用される。**「全モデルで入出力フィルタリング」「**未成年のフォトリアリスティック画像を既定でブロック**」と明記され、ブロック時は `error.code: "contentFilter"` が返る。解除は限定アクセス申請経由。

**⚠ 画像入力シナリオではリクエスト単位のガードレール指定が効かない。**「画像入力(chat with images)のシナリオではリクエスト時のガードレール指定が利用できず、既定のガードレールが使われる」と明記されている。

**Sora 2 の RAI 制限は商用ユースケースの大半を排除しうる。**公式に列挙されているのは:

- **IP(知的財産)およびフォトリアリスティックなコンテンツをすべてブロック**
- **18 歳未満の視聴に適した内容のみ**(将来この制限を回避する設定を提供予定)
- **著作権キャラクター・著作権音楽は拒否**
- **実在人物(著名人を含む)は生成不可**
- **人間の顔が写った入力画像は現在拒否**

> **企画段階で先に潰すべき制約。**「自社タレントを起用した動画を生成する」「実写風の製品映像を作る」といった用途は現時点で成立しない。

### アーキテクチャガイダンスは存在しない

**「キュー + ワーカー + Blob + セーフティレビュー」型のメディア*生成*パイプラインを扱う Azure Architecture Center の公式記事・サンプルは見つからなかった。**最も構造が近いのは「Extract and Map Information from Unstructured Content」(Container Apps + Queue Storage + Blob + Cosmos DB + confidence score による人手レビュー分岐)だが、これは**処理・抽出であって生成ではない。**

**画像 6〜36 RPM / Sora 2 が 2 RPM + 同時 2 ジョブ**という制約下では、汎用パターンである **Queue-Based Load Leveling / Competing Consumers / Background jobs** の適用が実質必須になる。本ドキュメントの構成案:

```
 [API]  ← ユーザー要求を受けて即座にジョブ ID を返す(同期で待たない)
   │
   ▼
 [Service Bus / Queue Storage]  ← Queue-Based Load Leveling
   │
   ▼
 [Container Apps ワーカー]  ← RPM 上限に合わせてレート制限。429 は指数バックオフ
   ├─ 画像: 同期 images/generations
   └─ 動画: jobs API を作成 → 状態を Cosmos DB に永続化 → 外部からポーリング
   │
   ▼  成功時は 24 時間以内に必ず退避
 [Blob Storage]  ← 長期保管
   │
   ▼
 [Content Safety / 人手レビュー] ──> [公開ストレージへ昇格]
```

**Sora 2 の「同時 2 ジョブ・24 時間失効」がスループット設計の支配要因**になる。

---

## E5. M365 / Teams 連携

### エージェントを Teams / M365 Copilot に公開する

**公開フロー自体は GA。**安定エンドポイントを Teams アプリマニフェスト化して M365 / Teams のエージェントストアへ公開する。

| 項目 | 内容 |
|---|---|
| 必要リソース | **Bot Service リソース**(`Microsoft.BotService`) |
| 承認 | 組織公開は **M365 管理者承認** |
| **閉域での制約** | **パブリックネットワーク無効プロジェクトはポータルからの公開が不可・REST のみ** |
| Azure Government | **非対応** |
| 旧形式 | 旧 Agent Applications 形式は新規公開不可(フォーマット移行が必要) |

**プロトコル:** Teams / M365 チャネル配信には **Activity プロトコル**が使われ、Responses プロトコルから自動ブリッジされる。

**認証は 2 モード:** OAuth 2.0 の **OBO**(ユーザートークンあり)と、**エージェント自身の ID**(自律 / バックグラウンド)。

**課金は publisher-pays**(発行者がインフラ費用を負担し、エンドユーザーは既定で課金されない)。**社内展開のコスト設計で見落としやすい。**

### Copilot Studio との棲み分け

- **Copilot Studio から Foundry エージェントへの接続はプレビュー**(新 Foundry ポータルで作成されたエージェントのみ)。
- 逆方向(**Foundry → M365 Copilot / Teams の publish)は GA。**
- CAF は SaaS(Copilot Studio)vs PaaS(Foundry)として整理し、ハイブリッド運用も推奨している。ただし「**Low-code SaaS 開発は重いカスタマイズで限界に達し、マネージドプラットフォームへの移行が必要になる**」とも明記。
- **Copilot Studio / Foundry のエージェントセキュリティ機能は Microsoft Agent 365 へ移行中。**

### Work IQ(M365 のコラボレーション文脈を使う)

**成立条件が厳しいので先に確認する:**

- **M365 Copilot ライセンスが必須**(開発者・エンドユーザー双方)
- **Entra Global Administrator による `WorkIQAgent.Ask` のテナント同意が必須**
- **BYO Entra アプリ(OBO)のみ**サポート
- **VNet 統合非対応**
- データレジデンシは Foundry プロジェクトのリージョンではなく **M365 テナントの構成に従う**
- 接続は A2A プロトコル。Java SDK 非対応

M365 の権限・秘密度ラベル・情報バリアを自動適用し、顧客コンテンツはモデル学習に使われない。

### M365 Agents SDK という選択肢

M365 Copilot / Teams / パートナープラットフォーム / 独自アプリ / Web にまたがるフルスタック・マルチチャネル向け。**Semantic Kernel や MAF をオーケストレータとして内部で使える。**公式の使い分けは「**AI モデルやオーケストレーションを完全に制御したいなら、M365 Agents SDK か Agents Toolkit 経由の Foundry によるプロコード方式を選べ。**」

---

## E6. ファインチューニング / モデルカスタマイズの運用

### まず「本当に必要か」を潰す

**公式の立場は「多くのユースケースでファインチューニングは不要」である。**マルチテナンシー記事に最も明快な形で書かれている。

> **ただしファインチューニングはほとんどのユースケースで必要ない。**通常は Azure OpenAI on your data 機能や別の RAG アプローチでモデルをグラウンディングできる。

一方で「FT は知識を追加できないから知識は RAG で」という定式化は**公式ドキュメントには存在しない。**公式のフレーミングは**相補的**で、むしろ「**FT と検索の組合せ**」を推している。

> **ファインチューニングと検索手法を組み合わせると、モデルが外部知識を統合する能力が向上する。**ファインチューニングは、**取得したデータを効果的に使い、無関係な情報を除外するようモデルを訓練する。**

**FT が有利になる条件(公式の 7 カテゴリ):**

1. **プロンプトエンジニアリングのオーバーヘッド削減** — few-shot を積み上げてプロンプトが長大化しトークン数とレイテンシが増えるケース。「**エッジケースが多数あるシナリオで価値がある**」
2. スタイル・トーンの変更
3. 特定フォーマット / スキーマでの出力生成
4. **ツール利用の強化** — 「多数のツールを列挙するとトークン使用量が増え誤情報につながる。ツールの例で FT すると、**完全なツール定義が無くても**精度と一貫性が上がる」
5. **検索ベース性能の強化**(上記の RAG 併用)
6. 効率最適化(大→小モデルへの知識移転)
7. 蒸留

**前提条件:** 「**数百〜数千件のタスク固有のプロンプト・応答ペア**という、小規模で高品質なデータセットがある場合に適する」。データ量の目安は初期テストで 50〜100 件、本番は 500 件以上。

**⚠ 公式が明記している FT の運用負債:**

> **データが更新されたとき、または更新されたベースモデルがリリースされたときに、ファインチューニングをやり直す必要があるかもしれない。**これには定期的な監視と更新が伴う。

さらにモデルライフサイクル記事にも「**ファインチューン済みモデルから新しいモデルリビジョンへ移るときは、使う前に新バージョンを再度ファインチューニングする必要がある**」と明記されている。**ベースモデルが 18 か月でリタイアする以上、FT は「作って終わり」にならない。**

### 手法の使い分け

| 手法 | 適用条件(公式の表現) |
|---|---|
| **SFT**(教師ありファインチューニング) | 「**問題の解き方が有限**で、特定タスクを教えて精度と簡潔さを高めたい場合に最適」 |
| **RFT**(強化ファインチューニング) | 「**問題の解き方が多数ある場合に最適。**grader がモデルに段階的に報酬を与え推論品質を高める」。例として金融のリスク評価、医療のデータ分析・仮説生成 |
| **DPO**(直接選好最適化) | 報酬モデル不要でバイナリ選好から学習。「計算負荷が軽く高速……アラインメントに同等に効果的でより効率的」。**選好する応答と選好しない応答の両方**を学習データに含める |
| **蒸留** | 独立した手法ではなく **SFT の用途の 1 つ**として記述されている。大きいモデルの出力で小さいモデルを FT する |

**公式のスタッキング推奨:** 「まず **SFT** でユースケースに最適化したモデルを作り、**次に DPO** で応答を自分の選好にアラインさせる。SFT の段階ではデータ品質とタスクの代表性に集中し、DPO の段階で具体的な比較によって応答を調整する。」

**対応モデル(抜粋):** GPT-4.1 系 / GPT-4o は SFT + DPO(4.1 と 4o は**ビジョンも対応**)、GPT-4o-mini は SFT のみ、**o4-mini は RFT のみ。**Phi 4 / Ministral 3B / Mistral 系は SFT。NTT の tsuzumi-7b も SFT 対応として列挙されているが、**Legacy 扱いで 2026-08-31 にリタイア予定**(後継は tsuzumi2)のため、**新規案件で選ぶべきではない。**なお `gpt-5` の RFT はゲート制・招待制。

**Serverless か Managed compute か:** Serverless は Microsoft 側キャパシティで従量課金、GPU クォータ不要、**OpenAI モデルへの独占的アクセス**。Managed compute はモデル種別が広く高度なカスタマイズが可能だが、**学習・ホスティング両方に自前 VM が必要で、多くの顧客が持っていない高いクォータを要求し、OpenAI モデルを含まない。**公式の結論は「**大半の顧客には serverless が最良のバランス**」。

### ⚠ コスト構造 — 使わなくても課金され、放置すると消える

**2 つのルールが同時に効くので、両方を運用設計に入れる。**

> デプロイした各カスタマイズ済み(ファインチューン済み)モデルは、**chat completions や response API の呼び出しがあるかどうかに関わらず、時間単位のホスティングコストが発生する。**

> **カスタマイズ済みモデルをデプロイした後、デプロイが 15 日を超えて非アクティブのままだと、そのデプロイは削除される。**……**非アクティブなデプロイの削除は、基盤となるカスタマイズ済みモデル自体を削除したり影響を与えたりしない。カスタマイズ済みモデルはいつでも再デプロイできる。**

**含意は 2 つ。**(1) 見積もりでは「**デプロイ数 × 稼働時間**」が固定費になる。学習済みモデルの**保管自体は無料**なので、使わないデプロイは消す。(2) **低頻度利用の本番エンドポイントが 15 日で黙って消える。**キープアライブの定期呼び出しか、明示的な再デプロイ手順を運用に入れる(この対策自体は公式に記載がない)。

**デプロイ種別の使い分け:**

| 種別 | コスト特性 | ステータス |
|---|---|---|
| **Standard** | トークン従量 + 時間ホスティング。**データレジデンシはデプロイリージョン内に限定** | GA |
| **Global Standard** | コスト削減。ただし「**カスタムモデルの重みがリソースの地理的範囲外に一時的に保存される可能性がある**」 | プレビュー |
| **Developer Tier** | **時間ホスティング料が無い。**ただし可用性 SLA なしで「**モデル候補の評価用であり本番用ではない**」。評価用デプロイは **24 時間で自動削除**される(deployment-types に明記。前述の「非アクティブ 15 日で削除」〈未使用 FT デプロイの一般ルール〉とは別) | — |
| **Provisioned Throughput** | レイテンシ重視のエージェント向け。**ベースモデルと同じリージョナル PTU キャパシティを使う**ため既存 PTU クォータを流用できる | プレビュー |

**→ 評価・PoC は Developer Tier(時間課金なし)、本番は Standard / Global Standard / PTU** という切り分けが公式の意図。**Global Standard を選ぶとカスタムモデルの重みが地理的範囲外に出る可能性がある**点は、規制案件では致命的になりうる。

**クロスリージョン / クロスサブスクリプション / クロステナントのデプロイに対応している**(学習したリージョンと別のリージョンへデプロイ可能)。ただし**ポータルはクロスリージョン非対応で SDK / REST が必要。**

### ⚠ 2 段階リタイアと、API のステータス表記のズレ

> **ファインチューン済みモデルは 2 段階でリタイアする: training と deployment。**明示的な記載がない限り、**training のリタイアはベースモデルのリタイア日より早くはならない。**training がリタイアするとファインチューニングには使えなくなるが、**それ以前に学習済みのモデルはデプロイ可能なまま残る。****deployment のリタイア時点で、推論とデプロイはエラーを返す。**

主要モデルの日程は「training は 2027-04 前後(既存顧客のみ延長)、**deployment は約 6 か月後の 2027-10**」という形で並んでいる。**学習停止から推論停止まで約半年のバッファ**がある設計。

**⚠ 自動化を書くときの落とし穴:** Models API のフィールド値がドキュメント / ポータルの用語とズレている。

| ドキュメント上の段階 | API の `lifecycleStatus` |
|---|---|
| Deprecated(**まだ動く**) | **`Deprecating`** |
| Retired(**410 Gone**) | **`Deprecated`** |

さらに **FT 可否の判定には `deprecation.fineTune` フィールドを使う**(推論用の `deprecation.inference` とは別)。ここを取り違えると「まだ使えるモデルを廃止扱いする / 廃止済みを使える扱いする」逆転バグになる。

**リタイア日の延長申請はできない**と明記されている(「Retirement dates aren't extendable.」)。

### パイプラインは「既存の MLOps を使え」が公式回答

**ファインチューニング専用の E2E 参照アーキテクチャは Azure Architecture Center に存在しない。**公式の答えは明快で:

> **基盤モデルのファインチューニングは、データ準備・モデル学習・評価・デプロイといった、従来型の機械学習モデルの学習と論理的に similar なプロセスに従う。これらのプロセスは、スケーラビリティ・再現性・ガバナンスを確保するために、既存の MLOps 投資を使うべきである。**

つまり **MLOps v2 のパイプライン設計 + GenAIOps の評価**をそのまま当てる。ステージごとの公式ガイダンスは:

| ステージ | 要点 |
|---|---|
| DataOps | **再現性とデータバージョニング**により、異なる特徴量データで実験し、モデル性能を比較し、結果を再現できるようにする |
| 実験 | **Azure ML パイプライン**でデータ前処理から学習・評価までのファインチューニングプロセス全体を管理する |
| 評価 | Evaluate Model コンポーネント、または Foundry を使うなら**評価 SDK** に拡張する |
| デプロイ | 学習・検証データは **JSONL** で用意。**ゲートウェイ経由で段階的にロールアウト**し、問題があれば以前のバージョンへロールバックする |
| 監視 | 逸脱・エラー率・処理時間に加え、**レイテンシ・トークン使用量・429 エラー**を追う。**クォータ使用量の監視**も明記 |

**ガバナンス面の公式推奨:** 「自動化コードに**データリネージを組み込んで監査可能性を支える**」「**モデルカタログを維持し、新モデルの発見とカタログ更新を自動化する**」「**モデルは、それを学習させた生データと同程度の機密性で扱う**」。加えてモデルライフサイクル記事は「**本番モデルをテストの機会なく自動的に新バージョンへアップグレードするプラットフォーム機能の使用を避けよ。Azure OpenAI ではデプロイを No Auto Upgrade に設定せよ**」と明記している。

**学習データ取り込みの落とし穴:** Azure Blob Storage から学習データを取り込むには**ストレージアカウントのパブリックネットワークアクセスを有効にする必要がある。**閉域環境ではローカルファイルアップロードか SDK 経由を使う。

**その他の数値制約:** 学習ファイルは 512MB 未満、**JSONL のみ**、UTF-8 with BOM、suffix は 18 文字まで、batch size 最大 256、epochs は `-1` で自動決定。

---

## この章で「公式に確認できなかった」もの

推測で埋めず、確認できなかったことを明示する。

| 項目 | 状況 |
|---|---|
| ~~Voice Live の GA 明文~~ **解決(2026-07-30)** | GA 一覧表に「Agents — Voice Live = **Preview**」と明記。ただし Voice Live 自身のページには preview バナーが無く、表記の不一致は残る |
| **Voice Live 固有のレイテンシ SLO** | 数値目標の記載なし。AOAI Realtime の接続方式比較(WebRTC 約 100ms / WebSocket 約 200ms)が唯一の参考値 |
| **Voice Live のコンテンツフィルタの詳細** | 「含まれる」「変更・無効化不可」は明記。**カテゴリ・しきい値・音声への適用範囲・注釈の返却有無は不明** |
| **Voice Live の TPM** | FAQ が 100,000、クォータページが 120,000 で不一致 |
| **Sora 2 の解像度・尺** | 同一ページ内の 3 箇所で記述が食い違う。実測確認が必要 |
| **`gpt-image-2` への C2PA 付与** | 明示的な列挙がない。同系統として付与される可能性は高いが未確認 |
| **動画のプロベナンス** | C2PA・透かし・来歴メタデータの記載が一切ない |
| **新 Foundry での Content Credentials** | 記事が classic 専用で、新ポータル向けページが存在しない(404) |
| **メディア生成パイプラインの公式アーキテクチャ** | 存在しない。処理・抽出側の記事が最も近いだけ |
| **ファインチューニング専用の E2E 参照アーキテクチャ** | 存在しない。公式の答えは「**既存の MLOps 投資をそのまま使え**」 |
| ~~リソースあたりの FT デプロイ数上限~~ **解決(2026-07-30)** | **10 デプロイ/リソース**([quotas-limits](https://learn.microsoft.com/en-us/azure/foundry/openai/quotas-limits) に明記)。training jobs は 100/リソース、同時実行 3(Developer tier は 5) |
| 新ポータルの fine-tuning 総覧ページ | `/azure/foundry/concepts/fine-tuning-overview` は **404**。総覧は classic 配下にのみ存在し、新ポータル側は複数ページに分散している |
