---
marp: true
theme: si-foundry
paginate: true
footer: "Microsoft Foundry SI 勉強会 — 詳細: docs/survey/ 配下(各スライド下部のリンク参照)"
---

<!-- _class: lead -->
<!-- _paginate: false -->
<!-- _footer: "" -->

# Microsoft Foundry を SI で使う

## 技術選定とアーキテクチャ判断の基準

2026-08 / 課内勉強会
本リポジトリの調査(survey)+実装検証(labs)の入口となる資料

<!-- 発表の位置づけ: 課内で Foundry を調査した人はいるが情報が未集約、プロジェクト事例がなくアーキ検討に困っている、という状況への回答。この資料は全体の入口で、詳細はすべて survey の HTML に整備済み、と最初に伝える。 -->

---

<!-- header: "§0 はじめに" -->

# 今日のゴール — 持ち帰る 3 つの判断能力

| | 判断能力 | 中身 |
|---|---|---|
| ① | **決める順序** | 後戻りコストの大きい順に 5 つのゲート(G1〜G5)で閉じる |
| ② | **当たりの付け方** | 要件の言葉 → ユースケース別パターン+選定 3 軸で構成候補を 1〜2 案に絞る |
| ③ | **見積もりの現実** | 「Foundry がやってくれないこと」と廃止期限を工数・リスクに乗せる |

- この資料は**入口(1 層目)**。各スライド下部のリンクから詳細ドキュメント(**2 層目**)に降りられる
- 全機能の暗記は不要 — 「どこを見れば載っているか」が分かれば提案は書ける

<div class="refs">2 層目の全体像: <a href="../survey/README.md">survey/README.md</a> — <span class="path">docs/survey/README.md</span></div>

<!-- ゴールは知識の網羅ではなく判断力。3 つの判断能力を最後にもう一度出すので、ここでは骨組みだけ覚えてもらえばよい。 -->

---

# この資料群の地図 — 調査と実証を分けて積んである

| 資料 | 答える問い | 更新サイクル |
|---|---|---|
| **features**(機能一覧) | その機能は**使えるのか**(GA / プレビュー、約 200 機能+出典 URL) | 月次 |
| **architecture**(設計ガイド) | **どう組むか**(公式リファレンス+ユースケース別パターン+運用・移行) | 四半期 |
| **proposal**(提案実務) | **どう提案するか**(ヒアリング・コスト手順・日本規制・公開事例) | 随時 |
| **tech-selection-guide** | 実装で**実証できたこと**だけ(labs 由来・調査と混ぜない) | 検証ごと |
| **labs/maf-ports** | 動くコード 14 本+オフラインテスト約 470 件 | — |

- **出典分離の方針**: 「公式ドキュメント調査(survey)」と「実装検証(labs)」を混ぜない。提案書では「公式ガイダンス準拠+実装検証済み」の二本立てで根拠を示せる

<div class="refs">詳細: <a href="../survey/features/html/index.html">features</a> / <a href="../survey/architecture/html/index.html">architecture</a> / <a href="../survey/proposal/html/index.html">proposal</a> / <a href="../tech-selection-guide.md">tech-selection-guide</a> — <span class="path">docs/survey/README.md</span></div>

<!-- どの資料がどの問いに答えるかだけ覚えてもらう。features は「使えるか」、architecture は「どう組むか」、proposal は「どう提案するか」。 -->

---

<!-- header: "§1 Foundry の現在地" -->

# 前提合わせ: 2025-11 Ignite の大改編で名前が全部変わった

| 観点 | 旧 | 現行 |
|---|---|---|
| ブランド | Azure AI Studio / Azure AI Foundry | **Microsoft Foundry** |
| ブランド | Azure AI Services | **Foundry Tools** |
| エージェント API | Assistants API(Threads / Runs) | **Responses API(Agents v2)** |
| 用語 | Threads / Messages / Runs / Assistants | **Conversations / Items / Responses / Agent Versions** |
| リソースモデル | Hub + Azure OpenAI + AI Services | **Foundry リソース**(単一) |
| SDK | `azure-ai-inference` 等 複数 | **`azure-ai-projects` 2.x + `openai`** |
| ドキュメント | /azure/ai-foundry/ | **/azure/foundry/**(新)+ /azure/foundry-classic/(旧) |

- **検索で出てくる情報の大半は旧名義**。この対応表を頭に入れて読まないと、廃止済み API の記事で設計してしまう

<div class="refs">詳細: <a href="../survey/features/html/index.html">features/index(前提知識の節)</a> — <span class="path">docs/survey/features/README.md</span></div>

<!-- 調査情報が未集約になる一因がこの改称。メンバーが過去に調べた内容も旧名義の可能性があるので、まずここを揃える。 -->

---

# Foundry の構成要素マップ(features の 8 カテゴリ)

| # | カテゴリ | 主な中身 |
|---|---|---|
| 01 | プラットフォーム基盤 | Foundry リソース / プロジェクト / RBAC / ネットワーク / CMK / IaC |
| 02 | モデル | カタログ(OpenAI / Claude / Grok 等)/ デプロイタイプ / Model router / Foundry Local |
| 03 | Agent Service | Agents v2(Responses API)/ prompt・hosted エージェント / Memory / Routines / A2A |
| 04 | ツール・ナレッジ | File Search / AI Search / Web search / MCP / Toolbox / **Foundry IQ** |
| 05 | 観測・評価 | トレーシング / 評価器 / クラウド評価 / AI Red Teaming / モニタリング |
| 06 | ガードレール | コンテンツフィルター / Prompt Shields / Groundedness / PII |
| 07 | Foundry Tools | Speech(Voice Live)/ Document Intelligence / Content Understanding |
| 08 | 開発者サーフェス | v1 API / SDK / CLI / Bicep / **Microsoft Agent Framework** / LangGraph 統合 |

- 機能ごとの GA / プレビュー+サーフェス別対応(ポータル / CLI / SDK / REST)を全行出典つきで整理済み

<div class="refs">詳細: <a href="../survey/features/html/index.html">features/index</a> — <span class="path">docs/survey/features/01〜08-*.md</span></div>

<!-- 個々の機能はこの場で覚えなくてよい。「この 8 分類のどこかに載っている」と分かればよい。 -->

---

# 「GA だが足元が動いている」を読む(SI 選定観点の要点)

- **新ポータルは GA、ただし機能単位で GA / プレビューが混在。** 体系的な一覧は公式の [Feature readiness at GA](https://learn.microsoft.com/en-us/azure/foundry/concepts/general-availability) が唯一 — 提案前に必ず引く
- **Agent Service はサービスとして GA。** しかし hosted agents は 2026-08-20 に初期プレビュー基盤終了(再デプロイ必須)、ビジュアル Workflows は 2026-12-01 廃止 — 「GA だが足元が動いている」状態
- **CLI は一級市民ではない。** 専用の `az foundry` は存在しない。多くの機能が「ポータル + SDK / REST のみ」 — 自動化の見積もりに直接効く
- **Claude(Anthropic)が本格参入(GA)。** ただし Anthropic SDK + Marketplace 課金 + **Foundry 組み込みコンテンツフィルター非適用**という独自制約つき

<div class="refs">詳細: <a href="../survey/features/html/index.html">features/index(ハイライトの節)</a> — <span class="path">docs/survey/features/README.md</span></div>

<!-- この 4 点は提案の失敗パターンに直結する。特にフィルター非適用の Claude とビジュアル Workflows 廃止は後のスライドでも繰り返し出てくる。 -->

---

# 公式リファレンスアーキテクチャは 3 本しかない

![bg right:44% fit](../survey/architecture/images/baseline-chat.png)

| | 名称 | 位置づけ |
|---|---|---|
| 公式-A | Basic Chat | PoC 専用。**記事自身が本番非推奨と明言** |
| 公式-B | **Baseline Chat** | **本番の出発点。** WAF が「AI ワークロードの推奨アーキテクチャ」と名指し(図 →) |
| 公式-C | Baseline in ALZ | hub-spoke 版。実装コードは記事から削除済み(AI Landing Zones は Preview) |

- それ以外の公式ページは「ガイド」「ソリューションアイデア」で**検証レベルが下がる** — 顧客提案での引用時は区別する

<div class="refs">詳細: <a href="../survey/architecture/html/01-official-baselines.html">architecture/01-official-baselines</a> — <span class="path">docs/survey/architecture/01-official-baselines.md</span></div>

<!-- 「公式の推奨構成はどれか」と聞かれたら Baseline 一択。事例記事やソリューションアイデアをリファレンスとして引用しない、という区別が提案の信頼性を作る。 -->

---

<!-- header: "§2 判断①: 決める順序" -->

# 判断① 決定は「後戻りコストの大きい順」に閉じる

| ゲート | 問い | これで決まるもの |
|---|---|---|
| **G1 データ・規制** | そのデータを、どこで、誰に処理させてよいか | モデル・デプロイタイプ・外部ツール可否 |
| **G2 ネットワーク** | 閉域か、パブリックか | 使える Foundry 機能の一覧(**後付け不可**) |
| **G3 制御** | 明示的な状態遷移・承認・再開が要るか | ポータル完結か、コードファーストか |
| **G4 統合** | 既存システムとの主従はどちらか | プラットフォームとして使うか、部品として使うか |
| **G5 ライフサイクル** | いつまで、誰が保守するか | プレビュー可否・IaC の作り込み度 |

- 機能比較表から入ると G1 / G2 の手戻りで壊れる。**上から順に閉じる**のがこのガイドの背骨

<div class="refs">詳細: <a href="../survey/architecture/html/03-decision-guide.html">architecture/03-decision-guide</a> — <span class="path">docs/survey/architecture/03-decision-guide.md</span></div>

<!-- 「何から決めればいいか分からない」への回答がこの 5 ゲート。以降のスライドは全部この順序の上に載っている。 -->

---

# G1 / G2 は後付けできない — 最初のヒアリングで確定させる

- **BYO VNet 注入(閉域構成)は作成後の変更不可。** 後から閉域要件が出ると作り直し — アンチパターンの代表格
- 閉域では **File Search / Traces / Memory / Work IQ / Browser Automation / Image Generation 等が使えない**。「閉域で使えない機能の一覧」から設計を始める
- **「日本国内でデータ処理を完結」= Regional Standard(Japan East)のみ。** APAC Data Zone は日豪韓星印で処理されうるため**不可**
- **Web search / Grounding with Bing は DPA 対象外・別課金**(データがコンプライアンス境界の外に出ると明記)— 規制業種では原則不可として扱う

<div class="refs">詳細: <a href="../survey/architecture/html/07-usecase-regulated-edge.html">architecture/07-usecase-regulated-edge</a> — <span class="path">docs/survey/architecture/07-usecase-regulated-edge.md</span></div>

<!-- ヒアリングの地雷質問「閉域は要件か希望か」「データを国外に出せるか」はここに直結する。曖昧なまま構成を書かない。 -->

---

# G3〜G5 と、11 章の結論「机上で当たりをつけられる」

- **G3 制御**: 分岐・ループ・承認・再開の明示制御が要るなら**コードファースト**。CAF も「クリティカルな業務ロジックには決定的ワークフローを強制せよ(Foundry / MAF)」と名指し
- **G4 統合**: 既存システムが主なら「**モデルとツールだけ借りる**」構成(Responses API のみ)。ただし Foundry の Tracing / Evaluations 等の運用機能は使えなくなる
- **G5 ライフサイクル**: 顧客内製・非開発者運用ならポータル中心。プレビュー許容度もここで確定
- **「複数試作して比較するしかない」は誤り**(CAF が Skip prototyping: Yes と明言)。プラットフォーム・単一 vs マルチ・パターンは**机上で決まる**。実測が要るのは品質・コスト実額だけ — そこは評価ハーネスで回帰可能にする

<div class="refs">詳細: <a href="../survey/architecture/html/11-decision-frameworks.html">architecture/11-decision-frameworks</a> — <span class="path">docs/survey/architecture/11-decision-frameworks.md</span></div>

<!-- 「事例がないからアーキを決められない」への直接の回答がこのスライド。公式フレームワーク(CAF / AAC)が 2025-12 以降に整備され、机上で決められる範囲が大きく広がった。 -->

---

<!-- header: "§3 判断②: 要件 → パターンの当たり付け" -->
<!-- _class: xdense -->

# 判断② ユースケース別パターン全体マップ(A1〜E6)

詳細: <a href="../survey/architecture/html/index.html">architecture/index</a> — <span class="path">docs/survey/architecture/README.md</span>(完全版は付録 A1)

| ID | パターン | 主な決め手 |
|---|---|---|
| A1 | 部門内 FAQ チャット | File Search 最小構成。速度優先・権限制御なし |
| A2 | 全社ナレッジ検索(本番) | **ユーザーごとに見える文書が違う**(本番の標準形) |
| A3 | 既存 AI Search 資産の活用 | 索引設計を自分で持ち続けたい |
| A4 | M365 / SharePoint 主データ源 | 権限透過。M365 Copilot ライセンス前提 |
| A5 | 複数ソース横断・高精度 | Foundry IQ(agentic retrieval) |
| B1 | 単一エージェント+基幹 API | 参照系中心 |
| B2 | **承認付き業務自動化(HITL)** | 「担当者が承認してから実行」(MAF hosted agent) |
| B3 | 長時間・確実な再開 | 数時間〜数日停止して再開(Durable + DTS) |
| B4 | マルチエージェント(専門分化) | 領域ごとに権限を分けたい |
| B5 | 業務フローエンジン主導 | 業務部門がビジュアルで保守(Logic Apps / Copilot Studio) |
| C1 | 一般顧客向けチャット | 不特定多数(WAF + APIM) |
| C2 | マルチテナント SaaS | 複数顧客に販売(APIM 事実上必須) |
| C3 | 大規模・複数部門への払い出し | 部門別按分・キャパシティ |
| D1 | 規制業種・閉域 | BYO VNet。閉域・監査・データ主権 |
| D2 | ソブリン(Azure Government) | hosted agent・MCP・A2A 非対応に注意 |
| D3 | エッジ・オンプレ | Foundry Local / Azure Local 版 / 切断コンテナ |
| E1 | 音声エージェント | Voice Live(SIP 非対応) |
| E2 | 文書処理・IDP | DI(定型)/ Content Understanding(非定型) |
| E3 | 大量バッチ処理 | **Batch で 50% 割引** |
| E4 | マルチモーダル生成 | 画像・動画。閉域不可 |
| E5 | M365 / Teams 連携 | 業務ツール内で使わせる |
| E6 | ファインチューニング運用 | 挙動・文体はモデル側、知識追加は RAG |

<!-- 全部は説明しない。「要件を聞いたらこの表のどれかに落とす」という使い方だけ伝え、A・B・D を代表として次のスライドから深掘りする。 -->

---

# A: 社内ナレッジ検索・RAG — 本線は A1 → A2

![bg right:46% fit](../survey/architecture/images/a2-knowledge-search.png)

- **A1(File Search 最小構成)で PoC → 品質が出なければ A2** が定石
- 「部署によって見える文書が違う」→ **A2 一択**(GA 要件を満たす唯一の方式)
- File Search は**埋め込み・チャンク設定が固定** — 日本語の長文・表主体文書で品質が出ないことがある
- PoC 段階で**難しい文書 20〜30 件**の検索品質を測ってから方式を確定する

<div class="refs">詳細: <a href="../survey/architecture/html/04-usecase-chat-rag.html">architecture/04-usecase-chat-rag</a> — <span class="path">docs/survey/architecture/04-usecase-chat-rag.md</span></div>

<!-- 図は A2(本番標準形)の構成。SI 案件で一番多い類型なので、A1 で始めて A2 に上げる、という段取りごと覚えてもらう。 -->

---

# RAG の 5 分岐 — どこにナレッジを持たせるか

| パターン | 選ぶとき | 注意 |
|---|---|---|
| A1 File Search | 手軽・小規模・静的データ | 設定固定・権限制御なし |
| A2 AI Search 自前索引 | **本番の標準形。** セキュリティトリミング必須のとき | 索引設計・運用は自前 |
| A3 AI Search ツール直結 | 既存の索引資産を活かす | 索引設計を持ち続ける覚悟 |
| A4 SharePoint ツール | M365 が主データ源・権限透過 | プレビュー+Copilot ライセンス or 従量課金 |
| A5 Foundry IQ | 複数ソース・複数エージェントで共有 | 一部 GA・ポータル体験はプレビュー |

- **Azure OpenAI On Your Data は 2026-10-14 廃止。** 「モデルが直接データを読む」構成の既存提案書は要更新(移行先: Agent Service + Foundry IQ)

<div class="refs">詳細: <a href="../survey/architecture/html/04-usecase-chat-rag.html">architecture/04-usecase-chat-rag</a> — <span class="path">docs/survey/architecture/04-usecase-chat-rag.md</span></div>

<!-- RAG は「どれが優れているか」ではなく「データの場所・権限・運用体制でどれに落ちるか」。On Your Data 廃止は過去の提案書を持っているメンバーに一番効く情報。 -->

---

# B: 業務自動化・マルチエージェント

![bg right:46% fit](../survey/architecture/images/b2-hitl-automation.png)

- B1(参照系: prompt agent+ツール)→ **B2 承認付き業務自動化**(HITL)が本線。「担当者が承認してから実行」は **MAF hosted agent**(図 →)
- 承認待ちが数時間〜数日なら **B3**(Durable Extension + DTS)で確実な再開を設計
- **ビジュアル Workflows は 2026-12-01 廃止** — ポータルでマルチエージェントを組む提案はしない。移行先は MAF(推奨)/ Logic Apps / A2A
- 業務部門がビジュアルで保守し続けたいなら **B5**(Logic Apps / Copilot Studio 主導)に倒す

<div class="refs">詳細: <a href="../survey/architecture/html/05-usecase-agent-automation.html">architecture/05-usecase-agent-automation</a> — <span class="path">docs/survey/architecture/05-usecase-agent-automation.md</span></div>

<!-- 廃止されるのはビジュアル Workflows だけで、ポータルのエージェント作成・公開・Connected Agents は残る。この線引きを混同しない。 -->

---

# C: 顧客向け公開・マルチテナント — 境界防御はアプリ側の責務

- **C1 一般公開**: WAF のチューニングと **BOLA 対策**を工数に入れる — **会話 ID のユーザー単位認可を Foundry はやってくれない**(ID を知られると他人の会話を読める)
- **C2 マルチテナント SaaS**: **APIM が事実上必須**。テナント別のトークン計測・課金按分は APIM の `llm-emit-token-metric` で自前実装
- **C3 大規模・複数部門**: クォータは**デプロイ単位** — 1 デプロイ共有だと 1 つの暴走が全体を止める。部門別デプロイ分割か APIM のレート制限で切る
- 429 のリトライ / バックオフはアプリ側の必須実装

<div class="refs">詳細: <a href="../survey/architecture/html/06-usecase-customer-facing.html">architecture/06-usecase-customer-facing</a> — <span class="path">docs/survey/architecture/06-usecase-customer-facing.md</span></div>

<!-- 公開系は「Foundry の機能」より「Foundry がやらない境界防御」が主戦場。BOLA と按分は次の§5(やってくれないこと)にも再登場する。 -->

---

# D: 規制業種・閉域・エッジ

![bg right:46% fit](../survey/architecture/images/d1-closed-network.png)

- **D1 閉域**(図 →): BYO VNet + standard setup(BYO 3 点)+ PE 群
- 設計の出発点は「**閉域で使えない機能の一覧**」(File Search / Traces / Memory / 画像生成…)
- **固定費(Firewall / PE / APIM)が月額の下限を決める** — 小規模の閉域案件はトークン代より固定費
- **D2 Gov**: hosted agents・MCP・A2A 非対応
- **D3 エッジ 3 形態**: Foundry Local(端末・GA)/ Azure Local 版(申請制)/ 切断コンテナ

<div class="refs">詳細: <a href="../survey/architecture/html/07-usecase-regulated-edge.html">architecture/07-usecase-regulated-edge</a> — <span class="path">docs/survey/architecture/07-usecase-regulated-edge.md</span></div>

<!-- 金融・公共の案件はまずこの章。G2 ゲート(後付け不可)の実体がここにある。 -->

---

# E: チャット以外の類型 — 音声・文書処理・バッチ・M365

| ID | 類型 | 使うもの | 落とし穴 |
|---|---|---|---|
| E1 | 音声エージェント | Voice Live API | **SIP 非対応**・ガードレール非適用。Japan East はネイティブ音声モデル非提供 |
| E2 | 文書処理・IDP | DI(定型帳票)/ Content Understanding(非定型) | CU は BYO モデル接続必須・ページ課金 |
| E3 | 大量バッチ | Batch デプロイ | **50% 引き**だが 24h ターゲット・SLA なし |
| E4 | 画像・動画生成 | 非同期ジョブ | **閉域不可** |
| E5 | M365 / Teams 公開 | 公開フロー(GA) | Bot Service が別途必要 |
| E6 | ファインチューニング | MLOps パイプライン | **挙動・文体は FT、知識追加は RAG**。デプロイは作り直し前提 |

<div class="refs">詳細: <a href="../survey/architecture/html/08-usecase-specialized.html">architecture/08-usecase-specialized</a> — <span class="path">docs/survey/architecture/08-usecase-specialized.md</span></div>

<!-- 「チャット以外」の引き合いが来たときの索引。E6 の「知識は RAG、挙動は FT」は顧客への説明でそのまま使える一行。 -->

---

<!-- header: "§4 判断②: ポータルか、コードか、どの FW か" -->

# 選定は一列比較ではなく「3 つの独立した軸」

- **軸 A: エージェントの定義方法** — 構成のみ(**Prompt agent**: ポータル / SDK で定義、フルマネージド実行)か、コード(**Hosted agent**: 自前コードをデプロイ、独自オーケストレーション可)か
- **軸 B: コードを書く場合のフレームワーク** — Hosted agent は **MAF 専用ではない**。MAF / LangGraph / OpenAI Agents SDK / 自前コードが公式サポート。「Foundry を使うか」と「MAF を使うか」は**独立した判断**(LangGraph 製エージェントを Foundry にホストする構成も正規ルート)
- **軸 C: Foundry との統合度** — フル統合 / **Responses API のみ利用**(モデルとプラットフォームツールだけ借りる。既存システム組み込み型の SI 案件で重要)/ Foundry 非依存

<div class="refs">詳細: <span class="path">docs/learning-plan.md §2(技術選定の全体像)</span> — <a href="../learning-plan.md">learning-plan.md</a></div>

<!-- 「ポータル vs MAF vs LangGraph」と一列に並べた瞬間に議論が壊れる。3 軸が独立していることだけ持ち帰ってもらえれば、このセクションは成功。 -->

---

<!-- _class: dense -->

# 16 レイヤー × M / H / S — 「Foundry 機能を使う vs 自前実装」

| # | レイヤー | M(フルマネージド) | H(ハイブリッド) | S(自前) | 迷ったら |
|---|---|---|---|---|---|
| L1 | モデル提供 | Foundry モデルデプロイ | + APIM ゲートウェイ | 他クラウド / セルフホスト | M |
| L2 | オーケストレーション | Prompt agent | Hosted agent(MAF・LangGraph) | 自アプリ + Responses API | H |
| L3 | 会話状態 | Conversations | BYO Cosmos DB | 自前 DB | M→S |
| L4 | 長期記憶 | Foundry Memory(プレビュー) | Memory + 自前フィルタ | 自前サマライズ + ベクトル検索 | S(本番) |
| L5 | ナレッジ / RAG | File Search / Foundry IQ | AI Search + 自前索引 | 自前パイプライン | H |
| L6 | ツール実行 | ツールカタログ / MCP | Toolbox + 自前 MCP | アプリ内 function calling | H |
| L7 | コード実行 | Code Interpreter | Custom CI | ACA dynamic sessions 直 | M |
| L8 | ガードレール | Guardrails 既定 | カスタム | Content Safety API 自前呼び | M+S 併用 |
| L9 | ID・認可 | Foundry RBAC + Entra | OBO / Agent identity | 自前認可基盤 | M |
| L10 | ネットワーク | パブリック + Private Link | BYO VNet 注入 | 自前 VNet | 要件次第 |
| L11 | ゲートウェイ | クォータのみ | **APIM AI ゲートウェイ** | 自前プロキシ | H |
| L12 | 可観測性 | Foundry Tracing | OTel 自前計装 → App Insights | 自前ログ基盤 | M+H |
| L13 | 評価 | Foundry Evaluations | evals API を CI から | 自前ハーネス | H |
| L14 | UI・チャネル | Teams / M365 公開 | 自作 Web + Responses API | 既存システム組込み | 要件次第 |
| L15 | 実行基盤 | Hosted agents | Container Apps 等 | AKS / オンプレ | H |
| L16 | IaC・CI/CD | ポータル手動 | Bicep / Terraform + azd | 既存 IaC に統合 | S |

<div class="refs">詳細(各レイヤーの全選択肢と根拠): <a href="../survey/architecture/html/02-building-blocks.html">architecture/02-building-blocks</a> — <span class="path">docs/survey/architecture/02-building-blocks.md</span></div>

<!-- 個別レイヤーの議論になったらこの表に戻る。「迷ったら」列は既定値であって正解ではない。根拠は 02 章に全部書いてある。 -->

---

# マルチエージェント協調の分水嶺 — 2 軸 3 値(実装で実証済み)

**制御を誰が決めるか(コード / LLM)× 制御が戻るか(戻る / 移る)**

| 型 | 制御 | 応答 | MAF での器 | 例 |
|---|---|---|---|---|
| **グラフ** | コード | — | Workflow(core) | 直列・並列・分岐・ループ |
| **相談型(agent-as-tool)** | LLM が選ぶ | **戻る** | Agent + 動的ツール生成 | 通信制約下の協調 |
| **担当交代(handoff)** | LLM が選ぶ | **移る** | HandoffBuilder(別パッケージ・会話型) | サポートのエスカレーション |

- そもそも**単一エージェントで始める**(CAF: 最初からマルチにしてよいのは境界・組織・確定拡張の 3 条件のみ。Anthropic: マルチはトークン 3〜10 倍)
- 実証: 元アプリの「handoff」の多くは**固定シーケンス** — グラフ化で失うものはなく、型・テスト・可視化を得る。one-shot パイプラインに handoff を使うと順序・終了が確率的になる(Port 7 で比較実装)

<div class="refs">詳細: <span class="path">docs/tech-selection-guide.md §1-1</span> / <a href="../survey/architecture/html/11-decision-frameworks.html">architecture/11(AAC 5 パターンとの対照)</a></div>

<!-- AAC の 5 パターン・LangChain の 4 型とこの 2 軸 3 値は同型。労力をかけて覚えるのはこの 1 枚でよい。 -->

---

# フレームワーク書き換えコストの実測感(14 移植からの抜粋)

| 元 → MAF | 書き換えの実態 |
|---|---|
| LangGraph(StateGraph) | ノード→Executor、条件エッジ→switch-case。**無型共有 dict → 型付きメッセージ**の規律が強制される |
| OpenAI Agents SDK(handoff) | 構造化出力+switch-case で明示化。1 行 → 数十行だが**テスト可能に** |
| AG2 旧 Swarm | 長寿命エージェントの「必要悪」がステートレス Agent.run では純関数に縮退 |
| LangChain ルーター(3 DB 振り分け) | 三段カスケード約 150 行が **Foundry IQ の宣言+プロンプトに消滅**。ただし可観測性・単体テスト可能性を失う |
| ADK + FastAPI(常時稼働) | hosted agent 化で変わるのは周辺 3 点のみ。Routines で cron 配管が不要に |

- 共通パターン: **書き換えで元コードの欠陥が見つかる** — 型付きグラフへの移植自体がコードレビューとして機能する

<div class="refs">詳細(全 14 行+検証元ポート): <span class="path">docs/tech-selection-guide.md §1-3</span> — <a href="../tech-selection-guide.md">tech-selection-guide.md</a></div>

<!-- 「他 FW からの乗り換えは怖い」への実測回答。移行コストは思ったより一様に低いが、失うもの(LangChain ルーター行の可観測性など)も正直に書いてある。 -->

---

# 作りたいもの → 実証済みコードの対応表(labs/maf-ports)

| 作りたいもの | 実証済みの型 | ポート |
|---|---|---|
| 直列パイプライン | Executor+エッジ、進捗イベント | trend-analysis |
| 並列実行+合流 | fan-out / fan-in エッジ | mixture-of-agents |
| ルーティング / トリアージ | 構造化出力+switch-case | research-handoff |
| 自己補正 RAG | 採点→分岐→書換のグラフ+AI Search | corrective-rag |
| 評価駆動の品質ループ | サイクリックグラフ+クラウド評価 | critique-loop |
| 常時稼働+スケジュール | hosted agent+Routines | hn-briefing-hosted |
| 音声エージェント | Voice Live(3 層分離) | claim-voice-live |
| ガバナンス / 監査 | middleware 3 種+ハッシュ連鎖監査 | governed-agent |

- 14 ポート合計**約 470 テストをネットワークなしで実行** — 「エージェントはテストできない」は設計の問題
- **Foundry に載せる最初の動機は観測性** — トレース配線は実質 2 行、ノード・ツール単位のスパンが自動計測

<div class="refs">詳細: <span class="path">labs/maf-ports/README.md(進捗表)/ docs/tech-selection-guide.md §3</span></div>

<!-- 「事例がない」への課内の回答がこの表。顧客事例ではないが、動くコード+テスト+Bicep 一式が型ごとにあるので、提案の実現可否確認と工数見積もりの根拠に使える。 -->

---

<!-- header: "§5 判断③: 見積もりに乗せる現実" -->

# Foundry が「やってくれないこと」— 頻出トップ 5

| # | やってくれないこと | 誰が埋めるか |
|---|---|---|
| 1 | リージョン間の自動フェイルオーバー・DR(**復旧は再構築**) | アプリ層ルーティング+Cosmos 継続バックアップ+再構築パイプライン |
| 2 | 会話へのユーザー単位認可(**BOLA**) | アプリ側で所有権をリクエストごとに検証 |
| 3 | エージェントの blue-green / canary | APIM 等のルーティング層 |
| 4 | 部門・テナント別のトークン計測・課金按分 | APIM `llm-emit-token-metric` |
| 5 | コストのハードリミット(公式明記: 機能がない) | 予算アラート+自作の自動化 |

- さらにコンテンツフィルターは**フェイルオープン**する(フィルター利用不能時はフィルタリングなしで HTTP 200)— 規制業種では `finish_reason` と `content_filter_results` の検証を必須実装にする
- 全 12 項目は付録 A2。**提案時に顧客と合意しておく項目**として使う

<div class="refs">詳細: <a href="../survey/architecture/html/index.html">architecture/index(全案件共通の前提の節)</a> — <span class="path">docs/survey/architecture/README.md</span></div>

<!-- 「Foundry でできます」と言った後に効いてくるのがこのリスト。提案の除外事項・前提条件欄にそのまま転記できる形にしてある。 -->

---

<!-- _class: dense -->

# 重要期限 2026–2027 — 提案書の賞味期限

| 期限 | 対象 | 設計への効き方 |
|---|---|---|
| **2026-08-20** | Hosted agents 初期プレビュー基盤 | **自動移行されない。** パッケージ・API・ID がまとめて変わる |
| **2026-08-26** | Assistants API / `azure-ai-inference` SDK | Threads / Runs 前提のアプリは全面改修。**状態データは移行されない** |
| **2026-10-14** | **Azure OpenAI On Your Data** | 「モデルが直接データを読む」構成が終わる。**RAG の既存提案書は要更新** |
| **2026-12-01** | ビジュアル Workflows | **ポータルでマルチエージェントを組む構成が消える。** 長期案件で提案不可 |
| 2026-10 前後 | gpt-4o / o1 / o3 / o4-mini 等 | モデル固定でチューニングしたプロンプトの再検証 |
| 2027-03-31 | Agents (classic)(v1) | classic プロジェクト上のエージェント資産 |
| **2027-04-20** | prompt flow | **新規開発に非推奨**(セキュリティ更新も停止済み)。MAF へ移行 |
| 2027-10 前後 | FT 済みモデルの deployment | 学習停止の約 6 か月後に推論も停止。**FT は作り直し前提** |
| 2028-09-25 | Azure AI Vision Image Analysis | 画像解析パイプラインの作り替え |
| 日付未公表 | Agent Applications / ハブベース(classic) | 廃止予告済み。**新規案件で classic を選ぶ理由はほぼない** |

- PoC → 本番のスケジュールと期限の衝突チェックを提案フローに組み込む(期間内に廃止が到来するなら最初から後継 API で作る)

<div class="refs">詳細: <a href="../survey/architecture/html/10-migration-antipatterns.html">architecture/10-migration-antipatterns</a> / <a href="../survey/features/html/index.html">features/index(期限表)</a></div>

<!-- 「GA だから安心」ではなく「いつ消えるか」で見る。太字 4 つ(08-20 / 08-26 / 10-14 / 12-01)は直近数か月なので暗記推奨。 -->

---

# 提案・レビューで踏みやすいアンチパターン(11 個から 3 つ)

- **「ポータルで全部できます」と言ってしまう** — ポータル完結は「単一 Prompt agent+カタログツール+公開」まで。分岐・ループ・承認の明示制御、ローカルテストは入らない。**対処: ポータル完結の範囲とコードが要る範囲の線引き表を提案に添える**
- **File Search で品質が出ないまま押し切る** — 埋め込み・チャンク設定は固定で、日本語長文・表主体の文書に合わないことがある。**対処: PoC で難しい文書 20〜30 件を測り、駄目なら早期に AI Search へ**(切替コストは後になるほど上がる)
- **`az` CLI で自動化できる前提で見積もる** — 専用の `az foundry` は存在せず、多くの機能はポータル+SDK / REST のみ。**対処: 自動化は Bicep / Terraform(基盤)+SDK / REST(データプレーン)前提で工数を積む**

<div class="refs">詳細(全 11 個): <a href="../survey/architecture/html/10-migration-antipatterns.html">architecture/10-migration-antipatterns</a> — <span class="path">docs/survey/architecture/10-migration-antipatterns.md</span></div>

<!-- 残り 8 個(閉域後付け・Claude のガードレール・プレビュー本番投入など)は既に他のスライドで触れたものも多い。設計レビュー前に 10 章を通読するのが実用的な使い方。 -->

---

# 実装のハマりどころ(labs での実測から 3 点)

- **RBAC 伝播は 5〜15 分・ノード間で不均一。** さらに Bicep 作成の Foundry プロジェクトは MI にモデルのデータプレーン権限が自動付与されない(ポータル作成は付く)— 401 の原因切り分けで半日溶ける
- **データプレーンは Bicep の外。** AI Search のインデックス、Memory のストアは ARM で作れず「**Bicep → セットアップスクリプトの 2 段デプロイ**」が定型。**IaC 完結を前提にした見積もりは崩れる**
- **Foundry Memory は同期 add ではなく LRO+debounce(既定 300 秒)。** 「書いた直後に読む」は成立しない前提で UX とテストを設計する

<div class="refs">詳細(全 13 点+検証元ポート): <span class="path">docs/tech-selection-guide.md §2(実装ナレッジ集)</span> — <a href="../tech-selection-guide.md">tech-selection-guide.md</a></div>

<!-- 「運が悪いと半日〜1 日溶ける系」を 13 点まとめてある。実装フェーズに入るメンバーは §2 を最初に読むと元が取れる。 -->

---

<!-- header: "§6 提案実務への接続" -->

# 提案フロー 5 ステップと資料の対応

| ステップ | やること | 使う資料 |
|---|---|---|
| 1. ヒアリング | 質問リストで要件採取 → 構成候補を 1〜2 案に絞る | proposal/01(ヒアリングシート) |
| 2. 実現可否チェック | 候補構成の機能を GA / プレビュー確認 → リスク一覧化 | features(機能一覧) |
| 3. 概算 | 月額レンジを試算 | proposal/02(コスト手順) |
| 4. リスク・規制説明 | 顧客説明の論点を準備 | proposal/03(日本規制) |
| 5. 体制 | チームの知識ギャップを確認 | proposal/04(Azure 知識マップ) |

- ヒアリング後のアウトプット: 構成候補 1〜2 案 / **プレビュー依存リスト** / **廃止日程との衝突チェック** / 概算月額レンジ / 規制・契約の論点リスト

<div class="refs">詳細: <a href="../survey/proposal/html/index.html">proposal/index</a> — <span class="path">docs/survey/proposal/README.md</span></div>

<!-- 提案の型は既に 5 ステップに分解して資料化済み。「明日から案件で使える」状態であることを伝えるのがこのセクション。 -->

---

# ヒアリングとコスト概算の「型」

<div class="cols">
<div>

**ヒアリングシート(proposal/01)**

- Phase 0〜7・約 30 問。**太字は地雷質問**(聞き漏らすと提案後に手戻り)
- 例: 閉域は**要件か希望か** / データを**国外に出せるか** / **ユーザーごとに見えるデータが違うか** / 引き渡し後**誰が運用するか**
- 回答 → 構成クイックマップで architecture の型に落ちる

</div>
<div>

**コスト見積もり手順(proposal/02)**

- Step 1 トークン推計(日本語 ≒ 1 文字 1 トークン。**エージェントは内部呼び出しで 2〜5 倍**)
- Step 2 構成要素チェックリスト(**モデル以外が過半になる構成は珍しくない**)
- Step 3 単価取得先(**単価はドキュメントに書かない主義** = 陳腐化対策)
- Step 4 PTU 判断 / Step 5 削減レバー(Batch 50% 引き等)

</div>
</div>

- 閉域構成の経験則: **固定費(Firewall / PE / APIM)だけで月額の下限が決まる** — 先に固定費を積んでから変動費を載せる

<div class="refs">詳細: <a href="../survey/proposal/html/01-hearing-sheet.html">proposal/01-hearing-sheet</a> / <a href="../survey/proposal/html/02-cost-estimation.html">proposal/02-cost-estimation</a></div>

<!-- ヒアリングシートは 60〜90 分の初回ヒアリングでそのまま使える。コスト手順は試算例 A / B / C(社内 RAG・顧客向け・文書処理バッチ)つき。 -->

---

# 日本の規制対応 — 顧客定番質問に答えられる状態にしてある

- **ISMAP**(政府・自治体): 対象サービスの**登録状況の確認が先決** — 案件ごとに最新を確認する設計(登録リストは変動するため文書に固定値を書かない)
- **FISC**(金融): 安全対策基準との対応整理+閉域構成(D1)が前提になりやすい
- **個人情報保護法**: 委託構成の整理+**abuse monitoring(人手レビュー)の説明**を準備 — オプトアウト申請の要否を含む
- **3 省 2 ガイドライン**(医療): 該当時の論点を整理済み
- 位置づけ: **G1(データ・規制)/ G2(ネットワーク)ゲートの日本ローカル具体化**。顧客からの定番質問への回答型を用意してある

<div class="refs">詳細: <a href="../survey/proposal/html/03-japan-compliance.html">proposal/03-japan-compliance</a> — <span class="path">docs/survey/proposal/03-japan-compliance.md</span></div>

<!-- 規制の細部を暗記する必要はない。「定番質問の回答型がある」「登録状況は案件ごとに最新確認」の 2 点だけ覚えてもらう。 -->

---

# 提案書で引用できる公開事例(Microsoft 公式出典のみ)

- **Foundry / Agent Service 名指しの日本事例**: **富士通**(営業支援エージェント、**生産性 67% 向上**)/ **NTT データ**(Fabric + Foundry Agent Service、**市場投入 50% 短縮**)/ **Sky**(Fabric + Foundry でデジタルワーカー推進)
- **エージェント型(Azure OpenAI 名義)**: 大和証券(AI オペレーター)/ トヨタ(O-Beya)/ ソフトバンク / JR 西日本 など 5 件
- **グローバル**: Air India(**1 日 4 万件**処理)/ Accenture(**4 か月で 17 ユースケース**)/ Atomicwork(問い合わせ 65% 自動化)
- 使い方の注意: 事例は「**同業種・同類型で公開実績がある**」ことの証明に使い、**アーキテクチャ選定の根拠には使わない**(その役割は公式リファレンス)。「Foundry 事例が少なく見える」のは主に名義変遷の問題

<div class="refs">詳細(効果数値の正確な表現+出典 URL): <a href="../survey/proposal/html/05-case-studies.html">proposal/05-case-studies</a> — <span class="path">docs/survey/proposal/05-case-studies.md</span></div>

<!-- 効果数値は必ず出典の表現のまま引用する(「約」「目標」を落とさない)。二次記事は収録していないので、そのまま提案書に載せられる。 -->

---

<!-- header: "§7 クロージング" -->
<!-- _class: dense -->

# 迷ったらここから — 要件の言葉の逆引き

| 要件の言葉 | 当たりをつけるパターン |
|---|---|
| 「社内文書を検索して答える」 | **A1** で PoC → 品質が出なければ **A2** |
| 「部署によって見える文書が違う」 | **A2**(GA 要件を満たす唯一の方式) |
| 「担当者の承認を経て実行」 | **B2**(MAF hosted agent)。承認待ちが数日なら **B3** |
| 「複数のエージェントが協調する」 | **B4**。ビジュアル Workflows は選ばない(2026-12-01 廃止) |
| 「顧客向けに公開する」 | **C1**。WAF チューニングと BOLA 対策を工数に |
| 「複数のお客様に SaaS として提供」 | **C2**。APIM が事実上必須 |
| 「閉域で運用する」 | **D1**。「閉域で使えない機能一覧」から設計 |
| 「日本国内でデータ処理を完結」 | Regional Standard(Japan East)。APAC Data Zone は不可 |
| 「音声で対話したい」 | **E1**(Voice Live)。SIP 非対応に注意 |
| 「請求書を読み取って」 | **E2**。定型は DI、非定型は Content Understanding |
| 「月間 N 万件を処理」 | **E3**(Batch 50% 引き)+ PTU サイジング |
| 「既存システムに組み込む」 | オーケストレーションは自前(L2 の S)。Foundry の運用機能は使えなくなる |
| 「ロックイン回避」 | Foundry はモデル供給元として使い、抽象レイヤーを自前で持つ |

<div class="refs">詳細: <a href="../survey/architecture/html/index.html">architecture/index(選定早見表)</a> — <span class="path">docs/survey/architecture/README.md</span></div>

<!-- このスライドは後日参照用。顧客の言葉を聞いた瞬間に引ける形にしてある。ブックマーク推奨は architecture の index。 -->

---

# この情報は腐る — 鮮度の保ち方

- 更新サイクル: **features は月次**(What's new が月次更新のため)/ **architecture は四半期** / proposal は随時。**Ignite(11 月)・Build(5 月)直後は必ず更新**
- 一次情報のウォッチリスト(上から順に):
  - [What's new in Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/whats-new-foundry) — 月次の新機能・ステータス変更
  - [Feature readiness at GA](https://learn.microsoft.com/en-us/azure/foundry/concepts/general-availability) — GA / プレビューの最重要ページ
  - [Model retirement schedule](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirement-schedule) — モデルのリタイア日
- **公式ページ間でステータス表記が食い違う**ことがある(hosted agents / Trace Replay 等)— Feature readiness を正とする
- このスライド自体も survey の大型更新(Ignite / Build 後)に合わせて改訂する

<div class="refs">詳細(更新手順): <a href="../survey/features/html/index.html">features/index(更新運用ガイドの節)</a> — <span class="path">docs/survey/features/README.md</span></div>

<!-- 資料の信頼性は更新運用で決まる。誰でも更新できるよう手順は features README に明文化してあり、生成 AI に更新作業を依頼する手順まで書いてある。 -->

---

# まとめ — 3 つの判断能力と、次の案件で最初にやること

| | 判断能力 | 使う道具 |
|---|---|---|
| ① | 決める順序 | **G1〜G5** を後戻りコストの大きい順に閉じる |
| ② | 当たりの付け方 | 要件の言葉 → **A1〜E6 パターン**+**3 軸**(定義方法 / FW / 統合度) |
| ③ | 見積もりの現実 | 「**やってくれないこと 12**」+**廃止期限**+実測ハマりどころ |

**次の案件で最初にやること(3 手):**

1. **proposal/01 のヒアリングシート**で要件を採取(太字の地雷質問だけでも)
2. **G1 → G5** の順にゲートを閉じ、構成候補を A1〜E6 の 1〜2 パターンに絞る
3. 候補構成の機能を **features で GA / プレビュー確認**+**期限表と衝突チェック**

<!-- 3 手のうち 1 つでも次の案件で実行されたら、この勉強会は成功。質疑では「いま抱えている案件をこの型に当てるとどうなるか」を歓迎する。 -->

---

# 2 層目への入口(リンク集)/ Q&A

| 資料 | 何に使う | 場所 |
|---|---|---|
| 機能一覧(features) | その機能は使えるのか | <span class="path">docs/survey/features/html/index.html</span> |
| 設計ガイド(architecture) | どう組むか・パターン・運用 | <span class="path">docs/survey/architecture/html/index.html</span> |
| 提案実務(proposal) | ヒアリング・コスト・規制・事例 | <span class="path">docs/survey/proposal/html/index.html</span> |
| 技術選定ガイド | 実装で実証した判断基準 | <span class="path">docs/tech-selection-guide.md</span> |
| 学習計画(3 軸の原典) | 選定の全体像 | <span class="path">docs/learning-plan.md</span> |
| 移植ラボ(実装例 14 本) | 動くコード・テスト・Bicep | <span class="path">labs/maf-ports/README.md</span> |

- HTML はリポジトリを clone してブラウザで開くだけ(ビルド済みでコミットされている)
- 以降は付録(パターン完全版 / やってくれないこと全 12 項 / 期限全体表 / Copilot Studio 境界)

<div class="refs"><a href="../survey/features/html/index.html">features</a> / <a href="../survey/architecture/html/index.html">architecture</a> / <a href="../survey/proposal/html/index.html">proposal</a> / <a href="../tech-selection-guide.md">tech-selection-guide</a> / <a href="../learning-plan.md">learning-plan</a> / <a href="../../labs/maf-ports/README.md">labs/maf-ports</a></div>

<!-- 資料はここで終わり。以降は発表では飛ばす付録で、後日参照用の完全版テーブルを収録している。 -->

---

<!-- header: "付録" -->
<!-- _class: xdense -->

# 付録 A1: ユースケース別パターン完全版(A1〜E6)

詳細: <a href="../survey/architecture/html/index.html">architecture/index</a> — <span class="path">docs/survey/architecture/README.md</span>

| ID | パターン | オーケストレーション | RAG / ナレッジ | 主な決め手 |
|---|---|---|---|---|
| A1 | 部門内 FAQ チャット | Prompt agent | File Search | 速度優先。権限制御なし |
| A2 | 全社ナレッジ検索(本番) | Prompt / Hosted agent | **AI Search 自前索引** | ユーザーごとに見える文書が違う |
| A3 | 既存 AI Search 資産の活用 | Prompt agent | AI Search ツール直結 | 索引設計を自分で持ち続けたい |
| A4 | M365 / SharePoint 主データ源 | Prompt agent | SharePoint ツール(OBO) | 権限透過。M365 Copilot ライセンス前提 |
| A5 | 複数ソース横断・高精度 | 任意(MCP 経由) | **Foundry IQ** | 複数エージェントでナレッジ共有 |
| B1 | 単一エージェント+基幹 API | Prompt agent + Toolbox | 補助的 | 参照系中心 |
| B2 | 承認付き業務自動化(HITL) | **MAF hosted agent** | 調査工程で使用 | 「担当者が承認してから実行」 |
| B3 | 長時間・確実な再開 | MAF + Durable Extension + DTS | 任意 | 数時間〜数日停止して再開 |
| B4 | マルチエージェント(専門分化) | MAF workflows / A2A | 領域別 | 領域ごとに権限を分けたい |
| B5 | 業務フローエンジン主導 | Logic Apps / Copilot Studio | 任意 | 業務部門がビジュアルで保守 |
| C1 | 一般顧客向けチャット | 任意 | 任意 | 不特定多数(公開 + WAF + APIM) |
| C2 | マルチテナント SaaS | Hosted agent(プロトコル 2.0.0) | テナント別索引 | 複数顧客に販売(APIM 必須) |
| C3 | 大規模・複数部門への払い出し | 任意 | 任意 | 部門別按分・キャパシティ(APIM 必須) |
| D1 | 規制業種・閉域 | Hosted agent or 自前 | AI Search 自前索引一択 | BYO VNet。閉域・監査・データ主権 |
| D2 | ソブリン(Azure Government) | Prompt agent 対応 | File Search / AI Search | hosted agent・MCP・A2A 非対応 |
| D3 | エッジ・オンプレ | Foundry 非依存 | 自前 | Foundry Local / Azure Local 版 / 切断コンテナ |
| E1 | 音声エージェント | Voice Live API | 任意 | リアルタイム音声対話(SIP 非対応) |
| E2 | 文書処理・IDP | 非同期パイプライン | DI / Content Understanding | 帳票・契約書の構造化抽出 |
| E3 | 大量バッチ処理 | ジョブ実行基盤 | 不要 | Batch で 50% 割引 |
| E4 | マルチモーダル生成 | 非同期ジョブ | 不要 | 画像・動画生成(閉域不可) |
| E5 | M365 / Teams 連携 | Prompt / Hosted agent | Work IQ 等 | 業務ツール内で使わせる |
| E6 | ファインチューニング運用 | MLOps パイプライン | 併用推奨 | 挙動・文体をモデル側で変える |

---

<!-- _class: dense -->

# 付録 A2: Foundry がやってくれないこと(全 12 項)

| # | やってくれないこと | 誰が埋めるか |
|---|---|---|
| 1 | リージョン間の自動フェイルオーバー・DR(復旧は再構築) | アプリ層ルーティング + Cosmos 継続バックアップ + 再構築パイプライン |
| 2 | 会話へのユーザー単位の認可(BOLA) | アプリ側で所有権をリクエストごとに検証 |
| 3 | エージェントの blue-green / canary | APIM 等のルーティング層 |
| 4 | モデルデプロイのラウンドロビン・サーキットブレーカー | APIM のバックエンドプール + circuit breaker |
| 5 | 部門・テナント別のトークン計測と課金按分 | APIM `llm-emit-token-metric` |
| 6 | コストのハードリミット | 予算アラート + 自作の自動化 |
| 7 | プロジェクト内のエージェント単位のアクセス制御 | アプリの認証認可層 / hosted agent の Entra Agent ID |
| 8 | `max_output_tokens` / `truncation` によるトークン制御 | 自前オーケストレーション |
| 9 | 閉域での Traces / Memory / File Search / Work IQ / 画像生成 等 | 自前実装または機能除外 |
| 10 | Claude モデルへのコンテンツフィルター | APIM `llm-content-safety` かアプリ層で Content Safety |
| 11 | 音声モデルへのガードレール | テキスト化後の経路で Content Safety |
| 12 | capabilityHost の更新(変更は削除・再作成) | IaC を「作り直し前提」で設計 |

- 加えて**コンテンツフィルターはフェイルオープン** — 規制業種は `finish_reason` / `content_filter_results` の検証を必須実装に

<div class="refs">詳細: <a href="../survey/architecture/html/index.html">architecture/index(全案件共通の前提の節)</a> — <span class="path">docs/survey/architecture/README.md</span></div>

---

<!-- _class: xdense -->

# 付録 A3: 重要期限の全体表(features 側)

詳細: <a href="../survey/features/html/index.html">features/index</a> — <span class="path">docs/survey/features/README.md</span>

| 期限 | 対象 | 影響・移行先 |
|---|---|---|
| 2026-08-20 | Hosted agents 初期プレビュー基盤 | サポート終了。新基盤へ再デプロイ必須 |
| 2026-08-26 | Assistants API(Azure OpenAI) | 廃止。Responses API(Agents v2)へ |
| 2026-08-26 | `azure-ai-inference` SDK | 廃止(beta のまま GA せず終了)。OpenAI SDK + v1 API へ |
| **2026-08-31** | NTT Data `tsuzumi-7b`(Legacy) | 廃止。後継 `tsuzumi2` へ。**日本語特化モデル案件で効く** |
| 2026-10-01 前後 | gpt-4o / o1 / o3 / o4-mini 等の旧モデル群 | リタイア |
| **2026-10-14** | `gpt-4.1-nano` | リタイア(gpt-4.1 / mini より約半年早い。混同しない) |
| 2026-10-14 | Azure OpenAI On Your Data | 廃止。Foundry Agent Service + Foundry IQ へ |
| 2026-12-01 | ビジュアル Workflows | 廃止。MAF / Logic Apps / A2A へ |
| 2027-03-31 | Agents (classic)(v1、Threads / Runs) | 廃止。Agents v2 へ(状態データは自動移行されない) |
| 2027-04-20 | prompt flow | 廃止。新規開発に非推奨。MAF へ |
| 2028-09-25 | Azure AI Vision Image Analysis 4.0 / 3.2 | 廃止。DI / Content Understanding / Foundry Models へ |
| 日付未公表 | Agent Applications / コンテナプロトコル 1.0.0 | 廃止予告済み(1.0.0 は 2026-07-31 からブロック開始と公表) |
| 予告 15 日のみ | Fireworks 系モデル(`FW-*`) | 標準 60 日でなく **15 日前通知**。本番の必須経路に置かない |

---

# 付録 A4: Copilot Studio との境界線(一次情報で引ける)

- **Copilot Studio → Foundry(プロコード)への乗り換えシグナル 3 つ**(公式ドキュメントで裏づけ):
  - **30〜40 アクション超**でオーケストレーターのツール選択精度が落ちる(公式明記)
  - **多段のエージェント階層が組めない**(connected agents を持つエージェントは他の connected agent になれない)
  - **決定的ワークフローが業務クリティカル** — CAF が「Foundry / MAF の workflows を使え」と実装先を名指し
- 選定の決め手は機能でなく「**誰が作り・誰が保守し・どこまで制御が要るか**」(CAF デシジョンツリー)
- **両者は排他ではない** — 入口・M365 チャネル・業務部門の保守は Copilot Studio、複雑な処理は Foundry hosted agent(connected agent として呼ぶ)が公式推奨の分業構成。**SI の受託範囲を「Copilot Studio で簡単に作れないエージェントの開発」とする契約の切り方が公式構成と一致**(ただし接続はプレビュー)

<div class="refs">詳細: <a href="../survey/architecture/html/11-decision-frameworks.html">architecture/11-decision-frameworks</a> — <span class="path">docs/survey/architecture/11-decision-frameworks.md</span></div>
