# 08. ユースケース編 E — 音声・文書処理(IDP)・大量バッチ・マルチモーダル・M365 連携

[← アーキテクチャ TOP](./README.md)

> **最終更新:** 2026-07-29
>
> ⚠ **本ページの信頼度について:** この領域を担当した調査エージェントが完了しなかったため、本ページは [features/07-foundry-tools](../features/07-foundry-tools.md)・[features/02-models](../features/02-models.md)・[features/03-agent-service](../features/03-agent-service.md) の記載と、他エージェントが副次的に確認した情報に基づく。**他ページより一次情報の裏取りが薄い。**特に音声とマルチモーダル生成は、実案件で使う前に公式ページの再確認が必要。次回更新時の重点項目。

チャット / RAG / 業務自動化に収まらない類型をまとめる。共通するのは、**Foundry Agent Service の外側にある Foundry Tools(旧 Azure AI Services)やモデル固有の API が主役になる**点で、エージェント中心の設計論がそのままは当てはまらない。

## パターン一覧

| # | パターン | 中核サービス | 決め手になる要件 |
|---|---|---|---|
| E1 | 音声エージェント / コンタクトセンター | Voice Live API | リアルタイム音声対話 |
| E2 | 文書処理・IDP | Document Intelligence / Content Understanding | 帳票・契約書からの構造化抽出 |
| E3 | 大量バッチ処理 | Batch デプロイ + Model router | 数万〜数百万件の分類・要約 |
| E4 | マルチモーダル生成 | 画像 / 動画モデル | 生成コンテンツの非同期処理と安全性 |
| E5 | M365 / Teams 連携 | 公開フロー + Work IQ | 業務ツール内でエージェントを使わせたい |

---

## E1. 音声エージェント / コンタクトセンター

### Voice Live API

**フルマネージドの speech-to-speech 統合 API。**STT + 生成 AI + TTS + アバターを**単一の WebSocket インターフェース**で提供する。従来のように「STT → LLM → TTS」を自分でつなぐ必要がない。

| 項目 | 内容 |
|---|---|
| ステータス | **GA 相当・要確認**(安定版 API `2025-10-01` / `2026-04-10` が存在し `-preview` が付かないが、「generally available」の明文は未確認。最新プレビューは `2026-06-01-preview`) |
| リソース | **Foundry リソースに最適化。**Speech リソースでは **Foundry Agent Service 統合と BYOM が使えない**と明記 |
| モデル | GPT-Realtime / GPT-5 系 / Phi 等をマネージド提供。**BYOM はプレビュー** |
| SDK | Python / C# は安定版、**Java / JS はプレビュー** |
| エージェント統合 | MCP は Foundry(新)のエージェントで対応 |
| **制約** | **SIP 非対応** |

**SIP 非対応が意味すること:** 既存の PBX / IP 電話網に直接つなぐことができない。電話系のコンタクトセンター案件では、**Azure Communication Services など別のテレフォニー層を挟む構成**が必要になる(※この具体的な接続パターンは本調査で一次情報を確認できていない — **要確認**)。

### 関連する音声モデルの状況

`gpt-realtime`(GA)/ `gpt-realtime-1.5`(GA)/ `gpt-realtime-2` `2.1`(プレビュー)/ `gpt-audio`(GA)/ `gpt-4o-transcribe` 系(プレビュー)。**`whisper` / `tts` / `tts-hd` は 2026-12-15 リタイア予定。**`gpt-realtime-translate` / `-whisper` は時間課金。

**Fast transcription**(録音済み音声をリアルタイム超の速度で同期文字起こし、GA)は**新ポータルのみ対応で classic は非対応。****LLM speech**(LLM 強化の transcribe / translate)はプレビュー。

### ⚠ 音声とガードレールの重大な非対称

**ガードレールは音声モデル(Whisper 等)が処理するプロンプト・完了には適用されない**と明記されている。**音声エージェントでは、Foundry の統一ガードレールに頼れない。**テキスト化した後の経路で Content Safety を自分で噛ませる設計になる。

### 設計上の論点

- **レイテンシが主要な非機能要件になる。**ガードレール処理は介入点あたり約 50〜100ms 加算される。PTU の検討が早い段階で必要。
- **会話の永続化と監査。**音声の場合、文字起こしテキストを監査ログに残すのか、音声そのものを残すのかで、ストレージとプライバシーの設計が変わる。
- **Language サービスの位置づけ変化に注意。**CLU(会話言語理解)・要約・感情分析・QA は「**legacy capabilities**」に降格し、コア機能は PII 検出・言語検出・NER・Text analytics for health のみになった。**従来型のインテント分類ベースの IVR 設計は、エージェント時代の推奨経路ではない。**代わりに **Language MCP server(プレビュー)** と **Intent Routing agent / Exact Question Answering agent(いずれもプレビュー)** が Foundry Tool Catalog に登場している。

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
| **オンプレ / 閉域(エアギャップ)** | **DI コンテナ** | **「現時点で唯一の選択肢」** |

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
- **プレビュー期のマネージド生成モデルキャパシティが廃止された** → **自分の Foundry の LLM デプロイと埋め込みデプロイを持ち込む必要がある**(`prebuilt-read` / `prebuilt-layout` / `prebuilt-layoutWithFigures` のみモデル不要)。
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
- **Container Apps 版**(マルチモーダル):Container Apps + Queue Storage + Content Understanding + Azure OpenAI + Cosmos DB。公式に「ワークフローが単純 / ビジュアル設計を好む / ローコード寄りチームなら **Logic Apps か Azure Functions に置き換えよ**」と代替案が示されている。

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

> ⚠ この節は特に一次情報の裏取りが薄い。実案件では公式ページの再確認が必要。

**モデルの現況:**

| 種別 | 状況 |
|---|---|
| 画像生成 | `gpt-image-2` は GA(2026-04-21)。`gpt-image-1` のみプレビュー。**`gpt-image-1` は 2026-10-23、`gpt-image-1.5` は 2026-12-16 リタイア予定** |
| 画像生成(パートナー) | BFL FLUX.2-pro / flex 等が GA(マルチ参照画像はプレビュー扱い) |
| 動画生成 | **Sora / Sora 2 はパブリックプレビュー。**非同期ジョブ API。API は `api-version=preview` |
| 画像生成ツール(エージェント) | **プレビュー。**`gpt-image-1` + LLM オーケストレータが同一プロジェクトに必要 |

**アーキテクチャ上の含意:**

- **非同期ジョブとして設計する。**特に動画生成はジョブ投入 → ポーリング → 成果物取得の流れになるため、**同期 API の裏に隠すとタイムアウトする。**キュー + ワーカー + 成果物ストレージ(Blob)が基本形。
- **Image Generation ツールは閉域で使えない**(ネットワーク分離下で「Not supported / 開発中」)。
- **リタイア日が近いモデルが多い。**特に画像生成系は 2026 年後半に複数のリタイアが予定されており、**モデル固定でプロンプトを作り込むと更改コストが読めなくなる。**
- 生成物の安全性・権利関係(protected material 検出、content credentials 等)については、本調査で十分な一次情報を確認できていない。**要確認。**

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

## この章の未確認事項(次回更新時の重点)

本ページは一次情報の裏取りが他ページより薄い。以下は**特に再確認が必要:**

1. **Voice Live の GA 明文表記**(安定版 API の存在から実質 GA と判断できるが「generally available」の文言自体は未確認)
2. **音声エージェントとテレフォニー(ACS / SIP 相当)の公式な接続パターン**
3. **リアルタイム音声のセッション上限・レイテンシ目標値**
4. **マルチモーダル生成の安全性まわり**(content credentials、透かし、protected material 検出の適用範囲)
5. **Foundry Local のライフサイクル表記**(現行ページに preview / GA の明記なし)
6. **Foundry Local on Azure Local の具体的な構成要件**
7. **マルチテナント SaaS 向けの Azure Architecture Center 公式ガイダンス**(`secure-multitenant-rag` の存在は確認済みだが内容は未取得)
8. **ファインチューニング / 蒸留の運用アーキテクチャ**(FT モデルのホスティング課金が発生することは確認済み。RFT・蒸留のパイプライン設計は未確認)
