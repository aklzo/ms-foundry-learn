# 01. 要件シナリオ別プレイブック — 「この要件が来たら何を決め、どこで詰まるか」

[← ケースブック TOP](./README.md)

> **最終更新:** 2026-09-04(初版)
> SI で頻出する 12 の要件セットについて、**ゲート判定 → 推奨構成 → 却下した案と理由 → 詰まりどころ → 見積もり・契約で効く点**を 1 シナリオ 1 節で書く。[architecture 03 の 5 ゲート](../architecture/03-decision-guide.md)と [11 の判断フレームワーク](../architecture/11-decision-frameworks.md)を「要件の言葉」から逆に引けるようにしたもの。詰まりどころは [02 索引](./02-pitfalls-index.md)の P-ID で参照する。
> **前提:** 構成の詳細(図・数値・上限)は architecture 各章に置き、本ページは判断と根拠だけを書く。「本ドキュメントの判断」と明記した箇所は公式に書かれていない SI 側の判断。

## シナリオ一覧

| ID | 要件の言葉(顧客が言うこと) | 主構成 | 後戻りコストが最大の決定 |
| --- | --- | --- | --- |
| [S-01](#s-01-社内ナレッジ検索チャット-sharepoint-が主データ) | 「社内文書を検索して答えるチャットが欲しい。データは SharePoint」 | A1 → A2 / A4 | 「部署によって見える文書が違うか」 |
| [S-02](#s-02-社内ヘルプデスク-itsm-servicenow-連携) | 「問い合わせを AI が一次回答し、チケットに書き戻す」 | B1 + A2(ハイブリッド) | 書き込み・状態遷移を誰が決定的に実行するか |
| [S-03](#s-03-承認付き業務自動化-hitl) | 「AI が案を作り、担当者が承認してから実行」 | B2 / B3 | 承認待ちの長さ(分か、日か) |
| [S-04](#s-04-閉域必須の規制業種-金融・公共) | 「インターネットに出ない構成で」 | D1 | VNet 注入の要否(作成時のみ) |
| [S-05](#s-05-顧客向け公開チャット) | 「Web / LINE で一般顧客に公開したい」 | C1 | 会話の認可(BOLA)とコスト上限 |
| [S-06](#s-06-マルチテナント-saas) | 「複数のお客様に SaaS として提供」 | C2 | テナント分離の単位とメータリング |
| [S-07](#s-07-既存システムへの-ai-機能追加-既存-aoai-資産の活用) | 「今の業務システムに AI を足したい」「AOAI は既に使っている」 | L2 = S(Responses API のみ)| Foundry の運用機能を捨てる合意 |
| [S-08](#s-08-copilot-studio-で始めた業務部門から-限界-と言われた) | 「Copilot Studio で作ったが精度・制御が足りない」 | Copilot Studio + Foundry hosted agent の二層 | 移行ではなく分業にできるか |
| [S-09](#s-09-文書・動画処理-idp) | 「帳票・契約書・研修動画を構造化して検索したい」 | E2(DI / CU + AI Search) | DI(決定論)か CU(LLM)か |
| [S-10](#s-10-音声エージェント-コンタクトセンター) | 「電話・音声で対話させたい」 | E1(Voice Live) | 国内処理要件との両立可否 |
| [S-11](#s-11-廃止期限駆動の移行案件) | 「Assistants / prompt flow / On Your Data / 旧 hosted agent で作ったものがある」 | 10 章の移行パターン | 期限までの猶予と状態データの扱い |
| [S-12](#s-12-顧客閉域環境への納品-ci-cd・構築・搬入・プロンプト運用) | 「弊社の閉鎖環境に構築して引き渡してほしい」 | S-04 + 納品プロセス | 「閉鎖」の Lv 定義(Lv3 か Lv4 か) |

複数に跨る案件は、**後戻りコストが最大の決定を持つシナリオを主**にする(例: 「SharePoint RAG だが閉域必須」なら S-04 が主、S-01 が従)。

---

## S-01. 社内ナレッジ検索チャット(SharePoint が主データ)

**要件の言葉:** 「社内規程・マニュアルを検索して答えてほしい」「データは SharePoint にある」「まず PoC で効果を見たい」「運用は情シスが兼務」

**ゲート判定:**

| ゲート | 判定 | 根拠 |
| --- | --- | --- |
| G1 データ | 社外秘だが個人情報は少ない → Regional / Data Zone 可 | 国内処理必須なら Regional Standard(P-M03) |
| G2 ネットワーク | パブリック + Entra 認証で足りることが多い | 閉域なら S-04 へ |
| G3 制御 | 「検索して答える」のみ → Prompt agent(M) | 分岐・承認なし |
| G4 統合 | 新規 AI アプリが主役 → フル統合 | Teams 公開が出口なら P-X 系を確認 |
| G5 ライフサイクル | 1〜2 年・内製運用 → GA 機能のみ、IaC 必須 | プレビュー(SharePoint ツール・Work IQ)は代替可能な範囲に |

**推奨構成:** **A1(File Search)で PoC → 品質が出なければ A2(AI Search 自前索引)**。「部署によって見える文書が違う」なら**最初から A2**(GA 要件を満たす唯一の方式)。SharePoint ツール(A4)は「全員が M365 Copilot ライセンスを持つ」「ユーザー委任(OBO)で動く対話型のみ」のときだけ。

**決め手と却下案:**

- **File Search を本番に押し切らない。**チャンク 800 / 400・埋め込み固定で日本語長文・表主体の文書に合わないことがある(P-R01)。素の検索 API がないため引用順位の制御や RRF 統合もできない(P-R02)。PoC は代表的な難しい文書 20〜30 件で測る
- **SharePoint ツールは「ライセンス+OBO+テキストのみ」の三重制約**(P-R09)。実行時に `User does not have valid license` で落ちるため、接続テストが通っても安心しない。ライセンスがない顧客には AI Search の SharePoint インデクサ案を並記
- **権限別表示は AI Search ツールでは実現できない**(P-R07)。「全員同じ」かどうかをヒアリングで必ず確認し、違うなら A2 で自前セキュリティフィルタ(architecture 04 の 4 方式)
- Foundry IQ(A5)は「複数エージェント / アプリでナレッジを共有」「ACL 同期」が要件のときに価値が出る。単一アプリなら過剰。Partial GA(P-R08)

**詰まりどころ:** P-R01・R02・R05・R07・R09・R13(日本語アナライザー)・P-I05(API キーで始めてナレッジを足すと Entra 必須)・P-X12(Teams 公開でナレッジ付きだけ失敗)

**見積もり・契約で効く点:** AI Search のティア(Basic 以上、閉域なら PE 対応 SKU)/ M365 Copilot ライセンスの有無 / モデル更改(リタイア 12〜18 か月、P-M07)の運用を契約に含めるか / 評価ハーネス(20〜30 件の正解セット)を PoC の成果物に

**実証状況:** [port 4(corrective-rag)](../../../labs/maf-ports/ports/corrective-rag/README.md)・[port 10(Foundry IQ)](../../../labs/maf-ports/ports/db-routing-iq/README.md)・[probe 03(File Search)](../../../labs/foundry-probes/probes/03-file-search/NOTES.md)・[外部案件 §4](./03-case-helpdesk.md)(File Search の限界)

---

## S-02. 社内ヘルプデスク × ITSM(ServiceNow)連携

**要件の言葉:** 「問い合わせを AI が聞き返して一次回答」「チケットに要約を書き戻す」「解決 / 引き継ぎの判定」「データの正は ITSM 側」「添付は保存したくない」

**ゲート判定:**

| ゲート | 判定 | 根拠 |
| --- | --- | --- |
| G1 データ | 添付・原本の不保存が要件 → File Search / Conversations に原本を置かない | 会話テキストは自前 SoR でも保持することになる(→ 弁別にならない。[03 §2](./03-case-helpdesk.md#2-判断の変遷-タイムライン)) |
| G2 ネットワーク | 閉域 Lv2〜3 が多い → S-04 の判定を併用 | hosted agent なら VNet 注入(P-H01) |
| G3 制御 | **ITSM 書き込み・状態遷移は決定的に**。検索・回答生成は LLM | H(ハイブリッド) |
| G4 統合 | ITSM が主、AI は従 → 決定的シェルは自前 | Foundry は LLM コア+会話面 |
| G5 | 顧客デプロイ・長期保守 → プレビュー不使用 | GA 証跡を機能ごとに記録 |

**推奨構成(本ドキュメントの判断):** **決定的シェル(ACA / Functions: 聞き返し・ITSM 書き込み・状態機械)+ LLM コア(hosted agent または自前 function calling)+ AI Search 自前索引**のハイブリッド。会話状態は自前 Cosmos を SoR にし、Foundry Conversations は使うなら standard setup(BYO)で「作業記憶」として二重保持。

**決め手と却下案:**

- **「全部 Foundry」は ITSM 書き込みの決定性が保証できない**(prompt agent のツール呼び出しはリトライ・重複呼び出しがありうる。architecture 05「更新系を入れるときの必須事項」)。**「全部自前」は版管理・観測・スケールゼロを自前で持つ**(v3 の運用グルー)。ハイブリッドが両方の利点を取る
- 撤退理由は機能単位で書く。「Foundry はデータがサービス側に残る」は standard setup(BYO)で反証された。成立するのは「添付原本の不保存」と「書き込みの決定性」
- hosted agent を使うなら cold start +数秒で keep-warm 不要(P-H13)。ACA の scale-to-zero(44.8 秒)とは別物
- OpenAPI ツールで ITSM を直接叩く場合、Basic 認証・SAS URL は非対応(P-X18)。MI か API キー(ヘッダー)

**詰まりどころ:** P-H01・H02・H03・H04・H20(プレリリース lib)・P-A04(Conversations に TTL なし)・P-I02(伝播 15〜45 分)・P-R02・P-M02(gpt-5-mini の遅さ)・P-O04(評価 SDK)・P-C09(プロンプト正本)・P-X18

**見積もり・契約で効く点:** 二重保持の削除ジョブ・照合の工数 / BYO Cosmos(5 × autoscale 1,000 RU/s、P-M14)/ 評価ハーネス(自前 4 指標+groundedness)を「載せ替え判断の道具」として先に作る / 閉域なら S-12 の納品プロセス

**実証状況:** **[03 案件事例](./03-case-helpdesk.md)そのもの**(v2 → v3 → v4、2026-08-30 実測)

---

## S-03. 承認付き業務自動化(HITL)

**要件の言葉:** 「AI が調査して実行案を提示」「担当者が承認してから実行」「誰が何を承認したか監査に残す」「失敗したステップだけ再開したい」

**ゲート判定:**

| ゲート | 判定 | 根拠 |
| --- | --- | --- |
| G3 制御 | **承認・分岐・再開 → コードファースト確定**(Prompt agent では足りない) | architecture 03 G3 |
| G2 | 基幹連携が社内網なら BYO VNet | ツールは MCP / OpenAPI(VNet サブネット経由) |
| G5 | 監査要件 → 業務監査ログはアプリ側に別途 | Foundry Tracing は 90 日・機微情報を含みうる(P-O08) |

**推奨構成:** **B2(MAF Workflow を hosted agent で実行、`RequestInfoExecutor` で HITL)**。承認待ちが数時間〜数日なら **B3(MAF + Durable Extension、Functions + DTS にホスト)**。ツールは Toolbox(MCP)経由で基幹 API へ。

**決め手と却下案:**

- **ポータルのビジュアル Workflows は 2026-12-01 廃止**なので選ばない。Logic Apps は「業務部門がデザイナーを触る」前提を維持したいときの B5
- **handoff パターンを one-shot 承認フローに使わない**(P-F02)。制御をコードで決められるなら決定的ルーティング(構造化出力 + switch-case)。順序・終了が確率的になる
- **チェックポイントはインメモリ既定**(P-F06)。水平スケールや数日の承認待ちには外部ストアか Durable Extension。hosted agent の中から DTS を使う公式パターンは未確認 → Durable なら Functions か自前コンピュートにホスト
- 更新系ツールには冪等キー・金額 / 権限 / 件数の上限チェックをツール側に置く(プロンプトで「10 万円以上は承認を取れ」は統制ではない)
- エージェントにガードレールを割り当てるとモデル側を完全上書きする(P-G05)。Tool call / Tool response の介入点を置き忘れると未スキャン

**詰まりどころ:** P-H05(publish で identity 変更)・H07(プロトコル選定)・H17・H18(長時間 workflow のチェックポイント)・P-I07(audience)・P-F02・F04・F06・P-G05・P-X19(Functions ツールは standard のみ)・P-X20(MCP OAuth)

**見積もり・契約で効く点:** hosted agent の compute(セッション × サイズ、P-H14)/ Durable Task Scheduler / 業務監査ログのストア / 「承認 UI」はスコープに入るか(Teams なら P-X 系)

**実証状況:** [port 3(handoff → switch-case)](../../../labs/maf-ports/ports/research-handoff/README.md)・[port 7(リング)](../../../labs/maf-ports/ports/game-design-team/README.md)・[port 14(middleware ガバナンス)](../../../labs/maf-ports/ports/governed-agent/README.md)。**Durable Extension・HITL の数日待ちは未実証**

---

## S-04. 閉域必須の規制業種(金融・公共)

**要件の言葉:** 「インターネットに出ない」「プライベートエンドポイントで」「監査で通信経路を説明できること」「データは国内」

**ゲート判定:**

| ゲート | 判定 | 根拠 |
| --- | --- | --- |
| G1 | 国内処理 → Regional Standard(Japan East)。使えるモデル世代が落ちる(P-M03) | Data Zone APAC は国外含む |
| G2 | **閉域は最初のゲート。作成時に確定・後付け不可** | inbound(PE)と outbound(VNet 注入)は別物(P-N01) |
| G3 | 閉域で使えない機能から逆算 | File Search / Tracing VNet / Memory / Work IQ / Logic Apps / Browser 系 |
| G5 | 長期・顧客保守 → GA のみ、IaC 必須 | capabilityHost の API は preview 版のみ(P-C06)— サービス面と分けて判断 |

**推奨構成:** **D1(standard setup + BYO VNet 注入 + PE)**。RAG は AI Search 自前索引一択、記憶は自前、観測主系は自前 OTel + App Insights(AMPLS)。hosted agent を使うなら**作成時に注入**。

**決め手と却下案(閉域で「動くはず」が壊れる断面):**

- **hosted agent を注入なしで作ると「デプロイ成功・実行失敗」**(P-H01)。公式ツール表の「PE 経由で対応」は注入前提。Lv3(インバウンド遮断のみ)要件でも注入つきで作る
- **PE を貼っただけでは outbound は閉じていない**(P-N01)。顧客の「閉域」を inbound / outbound / ツール別経路に分解して合意(Bing / Web / SharePoint Grounding はパブリック経路、P-N06)
- **File Search は閉域で提案しない**(P-N13)。公式は 2026-08-14 更新で「対応」になったが、閉域作成アカウントで vector store 作成が 500 の実測
- **Tracing VNet は Preview**(P-N14)。監査主系を Foundry トレースに置かない
- 「ポータルは見えるのに Playground が死ぬ」は DNS(6 ゾーン)が定番(P-N02)。踏み台(Bastion)をコストに積む
- 委任サブネットは /27 最小・/24 推奨。IP 枯渇はポータルに出ない(P-N05)
- 評価・レッドチーミングは日本リージョンで完結しない(P-O07)。評価データが国外に出る点を所在方針に明記
- FW の TLS 検査がエージェント通信を壊す。Agent Service の固定 IP はない(P-N07)

**詰まりどころ:** P-H01・H09(private ACR は 2026-06-25 以降のプロジェクト)・P-N01〜N19 のほぼ全部・P-I06(カスタムサブドメイン)・P-C06・C10・C11・P-O06(評価はストレージ公開必須)・P-M03

**見積もり・契約で効く点:** 固定費(Bastion / Firewall / Premium SKU / PE 群、P-N16)/ CapHost 作成 30 分超・purge 20 分のデプロイ時間(P-N15)/ セルフホストランナー(P-N11)/ Regional Standard のクォータが桁違いに小さい(P-M03)/ 「Lv3 でも外に出る通信」(ARM・Entra・App Insights)を顧客了承事項に

**実証状況:** [外部案件 §4-2(閉域 Lv3 ラウンド)](./03-case-helpdesk.md#4-2-閉域-lv3-ラウンド-2-本トラック最大の発見)。**VNet 注入つき hosted agent の構築は未実証**(公開記事も対応後のものは見当たらない)

---

## S-05. 顧客向け公開チャット

**要件の言葉:** 「Web サイト / LINE で一般顧客に」「不特定多数」「炎上しない」「月額上限を守りたい」

**ゲート判定:**

| ゲート | 判定 | 根拠 |
| --- | --- | --- |
| G1 | 顧客個人情報 → PII マスキング(保存境界で)、会話ログの所在 | basic か standard か |
| G2 | 公開 + WAF + APIM | 閉域ではない |
| G3 | FAQ 中心なら Prompt agent、複雑なら hosted | — |
| G5 | SLA → プレビュー排除 | Guardrails for agents はプレビュー |

**推奨構成:** **C1(App Gateway / WAF + APIM + Prompt / hosted agent + Guardrails)**。認証は外部 IdP → フロントで変換。

**決め手と却下案:**

- **BOLA を自前で潰す**(P-A05)。conversation ID を渡せば誰の会話でも読める。所有権検証をリクエストごとに
- **コストのハードリミットは Foundry にない**。APIM の `llm-token-limit` + 予算アラート + 自作の自動停止。429 / 403 の両方をハンドリング(P-X16)。直接キーを禁止しないとゲートウェイを迂回される
- **コンテンツフィルターはフェイルオープン**(P-G03)。`content_filter_results` の検証を必須実装に。Prompt Shields の誤検知はドメイン別に計測(P-G02)。日本語は `ensure_ascii` の罠(P-G01)
- ストリーミングは既定フィルタ(非同期フィルタは表示済み内容の取り消しが要る、P-G04)
- Claude を選ぶならフィルタを APIM / アプリ側で(P-M05)

**詰まりどころ:** P-A05・P-G01〜G04・P-X15〜X17・P-M05・M06(model router が Grok へ)・P-M12(PTU 誤設定の請求事故)

**見積もり・契約で効く点:** WAF チューニング工数 / APIM のティア / PTU か Standard か(スパイクは spillover)/ 評価と継続評価(judge のクォータ、P-O06)

**実証状況:** [probe 07(ガードレール)](../../../labs/foundry-probes/probes/07-guardrails/NOTES.md)・[probe 05(model router)](../../../labs/foundry-probes/probes/05-model-router/NOTES.md)。**WAF / APIM を含む公開構成の E2E は未実証**

---

## S-06. マルチテナント SaaS

**要件の言葉:** 「複数のお客様に同じエージェントを提供」「テナントごとに課金」「テナント間でデータが混ざらない証明」

**ゲート判定:** S-05 に加えて **G4 = テナント分離の単位**(プロジェクト / デプロイ / 索引 / 会話)と **L11 = APIM が事実上必須**(テナント別メータリング)。

**推奨構成:** **C2(hosted agent + コンテナプロトコル 2.0.0 + テナント別索引 + APIM)**。会話は standard setup(BYO Cosmos)か自前セッションストア。

**決め手と却下案:**

- **hosted agent は 1 セッション内の複数ユーザー多重化がプロトコル 2.0.0 前提**(1.0.0 は 2026-07-31 からブロック)。`x-agent-user-id` で分離
- **同一アカウント内の全プロジェクトがモデルデプロイを共有**(P-N15)。プロジェクト単位のモデル分離が要件ならアカウントを分ける(クォータ分割・PE 追加)
- Responses API はテナント分離が難しいと公式に書かれている(architecture 06)。会話・ファイル・vector store の名前空間を自前で
- 実行時のツール上書き(`vector_store_ids` 等)でテナント別ナレッジを切り替えられる(バージョンを増やさない)。ただし File Search の attributes フィルタは効かない報告(P-R01)
- チャージバックは「次元設計 → 単価 → 自動化」の順(P-X17)。高カーディナリティで監視コストが跳ねる

**詰まりどころ:** P-A05・P-N05(セッション = IP)・P-N15・P-X15〜X17・P-H06(カナリア不可)・P-H14(セッション × サイズ課金)

**見積もり・契約で効く点:** 委任サブネット /24(閉域なら)/ テナント数 × プロジェクト数の Cosmos RU / APIM Premium / 同時セッション上限(既定 50、申請で拡大)

**実証状況:** **未実証**(labs は単一テナント)。公式の 4 方式比較(architecture 06)と C2 図まで

---

## S-07. 既存システムへの AI 機能追加 / 既存 AOAI 資産の活用

**要件の言葉:** 「今の業務システムにチャットを足したい」「認証・監査は既存のまま」「Azure OpenAI は既に使っている」「他クラウドも使うのでロックインは避けたい」

**ゲート判定:** **G4 = 既存システムが主**。Foundry はモデル + プラットフォームツールの供給元(L2 = S)。

**推奨構成:** **既存アプリ内オーケストレーション + Responses API のみ利用**(architecture 10 §2.5)。既存 AOAI リソースは Foundry リソースへ非破壊アップグレード(§2.4)。

**決め手と却下案:**

- **Foundry の運用機能(Tracing / Evaluations / エージェント公開)を捨てることになる**点を提案時に明示(P-O01)。トレースだけは自前 OTel で部分的に取り戻せる
- 「後で Foundry に載せ替える」は無料ではない。ツール定義は移るがオーケストレーションは書き直し。**載せ替え判断は評価ハーネスがあれば 1 日で答えが出る**([03](./03-case-helpdesk.md)の v3 → v4 比較)
- AOAI アップグレードは CMK 利用リソースは申請フォーム、既存 PE 付きはポータル不可(architecture 10 §2.4)。`foundryAutoUpgrade` の drift を IaC で検知
- gpt-5 系へのモデル更改でパラメータが壊れる(P-M01)。ライブラリが勝手に付与する `temperature` / `max_tokens` を grep で見つけられない
- API キー運用のまま OBO ツール(AI Search 等)を足すと Entra 必須(P-I05)

**詰まりどころ:** P-O01・P-M01・M02・M07・P-I05・I06・P-A01(v1 / v2 混在)・P-A03(Assistants 廃止)

**見積もり・契約で効く点:** 自前オーケストレーションの保守工数 / モデル更改の運用(契約論点)/ 評価基盤を最初に作るか

**実証状況:** [外部案件 v3](./03-case-helpdesk.md)(AOAI chat completions + 自前 function calling on ACA)・[tech-selection-guide §1-3](../../tech-selection-guide.md#1-3-フレームワーク書き換えコストの実測感全ポート)(フレームワーク書き換えの実測感)

---

## S-08. Copilot Studio で始めた業務部門から「限界」と言われた

**要件の言葉:** 「Copilot Studio で作ったが回答精度が上がらない」「ツールが増えて誤選択する」「基幹 API を叩きたい」「業務部門が引き続き触りたい」

**ゲート判定:** architecture 11 §2 の乗り換えシグナル 3 つ — **30〜40 アクション超 / 多段のエージェント階層 / 決定的ワークフローが業務クリティカル** — に当たるものだけがプロコード側。

**推奨構成:** **二層構成**: Copilot Studio = 体験層(対話の入口・M365 チャネル・業務部門の保守)、Foundry hosted agent = 業務固有の複雑な処理。接続は connected agent(プレビュー)か **Responses エンドポイント直叩き(HTTP ツール)**。

**決め手と却下案:**

- **「移行」ではなく「分業」にする。**開発者不在のまま Foundry へ「機能アップグレード」として移行するのが最頻の失敗(P-X06)。コスト所有(Azure)・サポート窓口・CI/CD・監視が変わる
- **connected agent は本番で壊れやすい**: テストパネルでは動くのに Teams / M365 Copilot チャネルで定型エラー(P-X02)。Activity プロトコルの有効化は REST / SDK のみでポータルに出ない(P-X01)。本番は Responses エンドポイント直叩きを第一候補に
- Foundry 側の出力は「プレーンテキスト・短文」に制約する出力契約を仕様化(Markdown 表・引用・ストリーミングは Teams で描画失敗)
- Copilot Studio 側の課金: 125% 超で全エージェント停止、推論モデルは 100 倍クレジット(P-X05)
- 単一 vs マルチは CAF の 3 条件(architecture 11 §3)。「役割分担があるからマルチ」は理由にならない

**詰まりどころ:** P-X01〜X06・P-X10(Teams SSO は Foundry にない)・P-X11(Teams から OBO で MCP は不可)・P-I12(Agent ID 無効化の挙動差)

**見積もり・契約で効く点:** 受託範囲を「connected agent として呼ばれる Foundry hosted agent」に切る / Copilot Studio 側のクレジット試算(1 対話あたり)/ 接続がプレビューである点の明示(G5)

**実証状況:** **未実証**(labs に Copilot Studio 接続なし)。公式ドキュメント + Q&A の失敗事例のみ

---

## S-09. 文書・動画処理(IDP)

**要件の言葉:** 「請求書・契約書を読み取って構造化」「研修動画を検索できるように」「紙をスキャンした PDF」

**ゲート判定:** 定型帳票(信頼度スコア重視)は **Document Intelligence(決定論)**、非定型・可変レイアウト・マルチモーダルは **Content Understanding(LLM)**。CU は新ポータル未対応(classic)・BYO モデル接続必須・リージョン限定。

**推奨構成:** **E2(非同期パイプライン: CU / DI → 正規化 → AI Search 索引 → エージェント)**。大量処理は Batch(50% 割引)。

**決め手と却下案:**

- **CU の罠 13 点**(P-D01): セグメントが先頭・末尾を覆わないと発話が消える、重複セグメント、アナライザーは実質イミュータブル(PUT 上書きが黙って無視)、defaults は再デプロイで再登録、ソフト削除 → パージ → 同名再作成で内部モデル解決が壊れる
- **請求が 2 か所に分かれる**(P-D02): LLM / 埋め込みトークンは Foundry モデルデプロイ側。代表ファイルで `usage` を実測してから見積もる(動画 1 時間 ≈ $2.7〜2.9 の実測)
- CU 動画は 1 FPS・512×512(P-D03)。「画面上の細かい文字の転記」「高速動作の検知」は単体では満たせないと明示
- 評価設計の落とし穴: 回答値の動画間衝突、「動画を問わない」ans@k(cu-video-rag §1-11)。正解セットの一意化を先に
- 日本語アナライザー未指定は事故(P-R13)

**詰まりどころ:** P-D01〜D04・P-R13・P-M03(CU のリージョン)

**見積もり・契約で効く点:** CU の contextualization トークン別建て / advanced レート(agentic・ラベル付き)/ ページ・サイズ上限 / 前処理(画像入り PDF・文字エスケープ正規化)の工数

**実証状況:** **[cu-video-rag](../../../labs/cu-video-rag/README.md)**(104 本・111 クエリ・ragas、CER 0.44%、ans@3 0.67、コスト $12)

---

## S-10. 音声エージェント(コンタクトセンター)

**要件の言葉:** 「電話で受け付けたい」「リアルタイムで対話」「日本語」「通話録音は国内に」

**ゲート判定:** **G1 国内処理 × リアルタイム音声は現時点で両立しない**(P-M08: 音声モデルは Japan East に遅い。Japan East は Voice Live 対応だがネイティブ音声モデル非提供)。SIP 非対応(ACS か既存 PBX が別途)。

**推奨構成:** **E1(Voice Live API、3 層分離: 音声非依存コア / テキスト / 音声)+ ACS**。UI / オーケストレーションは日本、音声処理だけ Global の分離案を最初から提示。

**決め手と却下案:**

- **Voice Live はプレビュー**(GA 一覧表)。ガードレールは組込みで変更・無効化不可(P-G06)。修正が要件なら BYO model 経路
- 日本語の誤認識・言語自動検出・EOU の早発はロケール固定・フレーズリスト・EOU 設定で(P-D05)
- ACS 連携は 24 kHz / 16 kHz のリサンプリング・再接続・監視を初期スコープに(P-D06)
- gpt-realtime はピーク時間帯に ResponseFailed、WebSocket 1006(P-D07)。単一リージョン前提にしない。OpenAI 直のサンプルをそのまま移植しない
- 音声非依存コアを分離すると移植とテストの両方に効く(port 12)

**詰まりどころ:** P-D05〜D07・P-M08・P-G06

**見積もり・契約で効く点:** Voice Live のセッション上限・クォータ(architecture 08 E1)/ ACS の通話料 / マイク・電話の実機検証環境 / プレビュー依存の明示

**実証状況:** [port 12(claim-voice-live)](../../../labs/maf-ports/ports/claim-voice-live/README.md)(WebSocket 接続 + ツールループまで。**実機音声・電話は未実証**)

---

## S-11. 廃止期限駆動の移行案件

**要件の言葉:** 「Assistants API で作ったものがある」「prompt flow で組んだ」「ハブベースのプロジェクト」「Azure OpenAI On Your Data で RAG」「去年の hosted agent プレビューで作った」

**ゲート判定:** 期限(architecture 10 §1)と **状態データの扱い**が全て。

| 資産 | 期限 | 状態データ | 移行先 |
| --- | --- | --- | --- |
| Assistants API / Agents v1 | 2026-08-26 / 2027-03-31 | **移行されない**(自前エクスポート) | Responses API(P-A03) |
| hosted agent 旧基盤 | 2026-08-20(EOS 済み) | 再デプロイ | 新基盤(P-H15) |
| ビジュアル Workflows | 2026-12-01 | YAML は hosted agent でなら実行継続 | MAF(推奨)/ Logic Apps / A2A |
| On Your Data | 2026-10-14 | チャンク / 厳密度の挙動差 | Agent Service + Foundry IQ(P-R12) |
| prompt flow | 2027-04-20 | — | MAF |
| ハブベース(classic) | 未発表(投資停止) | プレビュー期の Agent state は対象外 | Foundry プロジェクト(自動ツールなし) |

**決め手と却下案:**

- **棚卸しから始める。**Assistants の利用箇所を一括発見する単一ツールはない(P-A03 の 4 手法)。エンドポイント形式(`openai.azure.com/openai/assistants` vs `services.ai.azure.com/api/projects/...`)で世代判定
- **SDK の世代混在**(P-A01・A02): `azure-ai-projects` 1.x と 2.x は非互換。上位フレームワーク(SK / MAF / LangChain)経由でも明示 pin
- **SK / AutoGen → MAF は「再実装 + 回帰評価」として見積もる**(P-F07)。import 置換でテストは通るのに挙動が違う。ゴールデン会話 20 本以上、旧経路を 1 リリース残す
- 旧 hosted agent 記事は読み替えが必要(P-H15)。`agent.yaml` → `azure.yaml`、LangGraph アダプタは廃止(P-F10)
- classic の Managed VNet はエージェント outbound を守らない(P-N17)。閉域化しようとせず新プロジェクトへ

**詰まりどころ:** P-A01〜A03・A10・P-H15・P-F01(MAF のマイナー破壊的変更)・F07・F10・P-R12・P-N17

**見積もり・契約で効く点:** 会話履歴の移行(なし前提)/ 2 クライアント構成への改修範囲 / 評価基盤(移行の合否判定)/ 期限内に PoC → 本番が収まるか(7-3)

**実証状況:** [tech-selection-guide §1-3](../../tech-selection-guide.md#1-3-フレームワーク書き換えコストの実測感全ポート)(13 パターンの書き換え実測)・[port 11](../../../labs/maf-ports/ports/hn-briefing-hosted/README.md)(新基盤 hosted agent)

---

## S-12. 顧客閉域環境への納品(CI/CD・構築・搬入・プロンプト運用)

**要件の言葉:** 「弊社の閉鎖環境に構築して引き渡してほしい」「ソースコードも弊社環境に」「外部 SaaS(GitHub)は使えない」「運用後にプロンプトを直したい」

**ゲート判定:** **「閉鎖」の Lv 定義を先に合意する。**Lv3(インバウンド遮断のみ。ARM 管理プレーンは公開)か Lv4(egress 統制・外部レジストリ・PyPI・GitHub 禁止)かで、CI/CD・搬入・監視の設計と見積もりが別物になる([03 §5](./03-case-helpdesk.md#5-顧客閉域環境への納品で問題になった点-v2-期の洗い出し-2026-08-07))。

**推奨構成(本ドキュメントの判断):**

| 論点 | Lv3 | Lv4 |
| --- | --- | --- |
| CI/CD | 自社 GitHub のまま、成果物(イメージ・Bicep)だけ届ける。`az acr build`(クラウド側ビルド)で成立 | Azure DevOps + VNet 内セルフホストエージェント + Azure Artifacts(PyPI upstream)+ ベースイメージの ACR ミラー |
| イメージ搬入 | ACR(Basic 可) | ACR Premium + PE + 「自社でビルド → `az acr import` / tar 持ち込み」の搬入手順書 |
| データプレーン配布(エージェント定義・ナレッジ投入) | 一時開放 → 配布 → 再遮断(暫定)| VNet 内ランナーから(P-N11) |
| プロンプト運用 | Git 一方向(P-C09)。ポータル編集は評価ゲート付きのみ | 同左 + 変更 = イメージ再ビルドなら搬入経路を通る |
| 監視 | App Insights(出方向 NAT 許容) | AMPLS で PE 化 |
| ポータル操作 | Bastion / VPN(P-N18) | 同左(閉域内ブラウザの Entra ログイン経路も設計) |

**決め手と却下案:**

- **「Lv3 なら Azure DevOps は必須ではない」**が、顧客ポリシーが Lv4 相当なら Azure DevOps + セルフホストが必要で設計・手順が別途。完全な閉鎖(dev.azure.com すら不可)なら Azure DevOps Server(オンプレ)の世界
- **プロンプトの二重化(ポータル / 管理画面 ↔ Git)は退行事故の元**(P-C09)。正本は Git、Foundry へは一方向デプロイ
- 初期セットアップの非冪等な手作業(ARM PUT)は戻し忘れの温床。capabilityHost の再 PUT は冪等(P-C06)なので stack 化する
- Lv3 でも外に出る通信(ARM・Entra・App Insights・Container Apps 委任)を顧客了承事項(T-xx)として明文化(P-N07 の FQDN 一覧)
- VS Code 拡張・`az cognitiveservices agent` はデプロイ経路にしない(P-C01・C08)。azd か SDK

**詰まりどころ:** P-N11・N16・N18・P-C01〜C11・P-H16(azd の断続失敗)・P-I02(伝播待ち)

**見積もり・契約で効く点:** Lv 判定のヒアリング項目(C-01 相当)を提案前に / セルフホストランナー・ACR Premium・AMPLS の固定費 / 搬入手順書・runbook を納品物に / 「プロンプト修正」の運用メニュー(評価ゲート込み)

**実証状況:** [外部案件 §5](./03-case-helpdesk.md#5-顧客閉域環境への納品で問題になった点-v2-期の洗い出し-2026-08-07)(v2 期の洗い出し)+ §4-2(一時開放運用)。**Lv4 の搬入・Azure DevOps 構成は未実証**

---

## シナリオ横断で毎回効くもの

- **評価ハーネスを先に作る。**S-01 / S-02 / S-07 / S-11 の「載せ替え・移行の合否」は同一データセット比較があれば 1 日で決まる。「選定は指標で、検証は評価で」(architecture 11 §7)
- **RBAC 伝播(P-I02)と「読めるのに実行できない」(P-I01)** は全シナリオの初期障害の定番。CI/CD に伝播待ちを入れる
- **記事の日付を見る。**hosted agent は 2026-04 以前の記事が旧基盤前提(P-H15)。features / architecture の「最終更新」と突き合わせる
- **プレビュー不使用ポリシーは「サービス面」と「IaC の API version」を分ける**(P-C06)。一律禁止だと GA 機能が使えなくなる
- **撤退理由は機能単位で書く**([03 §6](./03-case-helpdesk.md#6-提案への含意-一般化))。「Foundry はデータが残る」は反証されうる。「書き込みの決定性」は今も成立
