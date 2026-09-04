# 03. 案件事例: 社内ヘルプデスク × ServiceNow — 設計判断が 3 回変わった経緯と実測

[← ケースブック TOP](./README.md)

> **最終更新:** 2026-09-04(初版)
> **出典:** 外部案件リポジトリ `foundry-servicenow-helpdesk`(非公開)の docs/v2〜v4(ADR・検証計画・実測記録)。本リポジトリの [tech-selection-guide §5](../../tech-selection-guide.md#5-外部案件検証からの追記foundry-servicenow-helpdesk、2026-08-05) に載せた v2/v3 期の実測に、**v4(2026-08-30、hosted agent + standard setup、公開+閉域の 2 ラウンド)の実測**を加えて、判断の変遷ごと記録する。顧客名・固有情報は含まない。

## この事例から持ち帰るもの(先に結論)

1. **「Foundry を使うか」は 1 回で決まらない。**同じ案件で「フル活用(v2)→ 意図的撤退(v3)→ hosted agent で再挑戦(v4)」と 3 回判断が変わった。変わった理由は技術の不足ではなく、**顧客制約(データ所在・プレビュー不使用・閉域)の解像度が上がったこと**と、**公式側の対応(standard setup の BYO、hosted agents GA)が追いついたこと**の 2 つ
2. **撤退の根拠は後から弁別にならないことがある。**v3 は「会話・ファイルがサービス側に保存されるから」を撤退理由にしたが、v3 自身も会話を自前 Cosmos に 1 年保持しており、**会話については弁別になっていなかった**。本当に効いていたのは「添付原本を保存しない」「ServiceNow 書き込み・状態遷移をアプリ層で決定的に実行する」の 2 点。**撤退理由は「何が Foundry だと満たせないか」を機能単位で書く**
3. **閉域 × hosted agent は「デプロイ成功・実行だけ失敗」という気づきにくい断面で壊れる。**アウトバウンド VNet 注入(作成時のみ設定可)なしの閉域では、hosted agent は自プロジェクト(モデル・Conversations)にも BYO AI Search にも戻れない。公式の閉域ツール表「PE 経由で対応」は**注入構成が前提**
4. **hosted agent は cold start +数秒で keep-warm 不要**(実測 cold 12.4 秒 / warm 8.1 秒)。ACA の scale-to-zero(44.8 秒)とは別物で、「常時起動なしで応答性を両立」できる点が ACA に対する優位。ただし運用モデル(デプロイ経路・資格情報・観測)が 2 種類になるのがコスト
5. **v3 脳 → v4 脳の同一データセット比較で品質劣化なし。**「Foundry に載せ替えると精度が変わるか」は評価ハーネスがあれば 1 日で答えが出る。**載せ替え判断の前に評価ゲートを作る**のが正しい順序

## 1. 案件の骨格

| 項目 | 内容 |
| --- | --- |
| 業務 | 社内ヘルプデスクの問い合わせ AI。利用者は ServiceNow(SN)のフォームから起票 → AI が聞き返し・FAQ / 過去チケット / マニュアルを検索して一次回答 → 解決 or 担当者へ引き継ぎ。**SN が業務の正(データの正は SN)** |
| 顧客制約 | ①「Azure 保存は最終手段」(添付原本は保存しない)②プレビュー機能・プレリリースライブラリ不使用(顧客環境にデプロイして納品するため)③閉域 Lv2〜3(インバウンド遮断+PE。アウトバウンドは NAT 許容。Lv4 = egress 統制は当初スコープ外) |
| ガードレール方針 | SN への書き込み・処理ステータス遷移・解決 / 引き継ぎの発火は**ツールにせずアプリ層が決定的に実行**(誤発火防止・監査の確定)。これは v2〜v4 で不変 |
| 評価 | 自前 4 指標(retrieval hit@3 / unanswerable / category / hearing)のゲート+groundedness。同一データセットで版間比較 |

architecture の型で言えば **B1(単一エージェント+基幹 API)+ A2(AI Search 自前索引)+ D1(閉域)** の複合。ヒアリングシート([proposal 01](../proposal/01-hearing-sheet.md))なら Phase 2-3(機密区分)・4-1(閉域は要件か希望か)・7-2(プレビュー許容)が全部「厳しい側」に倒れた案件。

## 2. 判断の変遷(タイムライン)

| 版 | 時期 | 構成 | 決め手 | 後から見てどうだったか |
| --- | --- | --- | --- | --- |
| **v2** | 〜2026-08 上旬 | **Foundry フル活用**: Prompt agent + Conversations(basic)+ evals API + Foundry トレーシング。Azure 実環境 6 ラウンド(閉域 2 回)、groundedness 4.46、同時 10 負荷試験 | 「可能な限り Foundry 活用」の基本方針 | 技術的には成立。**顧客閉域環境への納品**を考えると、プロンプトのポータル編集と Git の乖離・イメージ搬入経路未設計・閉域 CI/CD 未設計が露出(§5) |
| **v3** | 2026-08-15 決定 | **意図的撤退**: AOAI chat completions + AI Search + **自前 Python オーケストレータ(function calling)on Container Apps**。モデル実行基盤としての Foundry(AIServices アカウント+デプロイ)は使用継続 | ①会話・ファイルがサービス側保存 → 「Azure 保存は最終手段」と衝突 ②SN 書き込み・状態遷移をアプリ層で決定的に | ①は**会話については弁別になっていなかった**(v3 も Cosmos に保持)。②は正しい。**Standard setup(BYO)・hosted agent を対案として検討した記録がなかった**のが反省点 |
| 顧客質疑 | 2026-08-18 | 「なぜ Foundry(エージェント機能)を使わないのか」 | — | 文書で回答したが、**「技術的には移行可能、方針として V3R-37 を優先」**という説明は顧客の基本方針(Foundry 活用)と緊張。→ v4 で「動く対案+実測」を作る判断 |
| **v4** | 2026-08-30 構築・実測 | **ハイブリッド**: 決定的シェル(聞き返し・SN 書き込み・状態機械)は ACA のまま、**RAG 回答コアだけ hosted agent + Conversations(standard setup / BYO)** に載せる。`AGENT_MODE=hosted` で v3 と切替可能、src 共有 | GA かつ閉域対応(一次情報で確認)。standard setup が「全エージェントデータが自社テナント内」を公式に明文化 → V3R-37 への正式回答になった | 公開環境では成立・品質劣化なし。**閉域(Lv3・注入なし)では実行だけ失敗**(§4)。v3 は現行本流のまま維持し、v4 は「対案の実証」として並走 |

**変遷の読み方:** 判断が変わるたびに「顧客制約の言語化」が進んだ。v2 は「Foundry 活用」、v3 は「データ所在」、v4 は「GA・閉域対応・全データ自社テナント内」。**提案時にここまで制約を言語化できていれば v3 の撤退は「部分撤退」で済んだ可能性が高い**(→ [01 S-02](./01-scenario-playbook.md#s-02-社内ヘルプデスク-itsm-servicenow-連携))。

## 3. v4 の設計判断(ADR 12 本の要約)

| 判断 | 決定 | 却下した案と理由 |
| --- | --- | --- |
| 実行基盤 | 会話脳 = **hosted agent**(GA・japaneast)。API/UI/Jobs = ACA 継続 | ACA 継続のみ(v3): サーバー・監視配線・版管理のグルーが自前。hosted は App Insights 自動注入・不変バージョン・スケールゼロがマネージドで付く |
| コンテナ内サーバー | **FastAPI で Responses protocol 2.0.0 を自前実装**。デプロイは `azure-ai-projects`(GA)の `create_version_from_code`(zip + REMOTE_BUILD、ACR 不要) | `agent-framework-foundry-hosting`: **プレリリース版のみ**で「プレリリース不使用」制約と衝突。MAF ごと採用も同 lib 依存で不可。→ プロトコル改訂への追随義務を負う代わりに契約テストで検知 |
| 責務分割 | ヒアリング・カテゴリ修正 = 決定的シェル(ACA)/ 検索 3 種 = hosted agent 内の LLM ツール選択 | 全部 hosted: SN 書き込みの決定性が失われる |
| 会話ストア | **自前 Cosmos(SoR: 状態機械・所有権・ETag)+ Conversations(BYO)の二重保持**。自前 Cosmos が削除台帳を兼ねる | (a) 自前のみ = Foundry の会話面を検証できない (b) Conversations basic = Microsoft 管理ストレージで方針と衝突 |
| standard setup | **使い捨て RG の新規アカウントで作成時に有効化**(後付け不可)。BYO Cosmos はエージェント用と自前 SoR で**別アカウント**(誤操作防止) | 既存環境への in-place 追加は不可能なので設計しない。長命環境なら第 2 アカウント並設(TPM クォータ分割・PE 追加が必要) |
| API version | capabilityHosts / connections の ARM API は **2025-04-01-preview のみ**(2026-08-30 時点) → 「コントロールプレーン IaC の版」と「顧客が触るサービス面の GA」を区別し、例外として採用・記録 | — |
| 検索方式 | faq / ticket = AI Search 継続、manual も **AiSearchTool を恒久採用**(File Search は不成立、§4) | File Search: 素の検索 API がなく決定的ヒット列に写像できない |
| 保持期間 | Conversations に TTL なし → **終端フック(best-effort)+ 日次スイープ**の 2 段削除。順序は Foundry 先・台帳後 | — |
| プレビュー不使用 | 採用機能ごとに **GA 証跡(URL・確認日)** を記録してから採用。除外: Memory / Routines / Workflows / Foundry IQ(ポータル面 Preview)/ model router(既定で非 OpenAI へ)/ Bing・Web・SharePoint(公開経路+DPA 外)/ **Tracing VNet(Preview)** | — |
| プロンプト正本 | **Git 一方向**(Foundry へはデプロイのみ)。v2 の「ポータル編集が Git と乖離して退行」の教訓 | ポータル編集開放: 評価ゲートを通らない変更が本番に入る |
| 評価 | 自前 4 指標ゲート(ブロッキング)+ evals API groundedness(レポート指標)。**azure-ai-evaluation SDK は不使用**(gpt-5 系ジャッジで 400) | — |
| 監視 | **主系 = 自前 OTel + App Insights**、Foundry トレーシングは開発時の付加系 | Tracing VNet が Preview のため閉域運用の前提に置けない |

## 4. 実測(2026-08-30・japaneast・2 ラウンド)

### 4-1. 公開環境(ラウンド 1)

| # | 実測 | 設計への含意 |
| --- | --- | --- |
| 1 | **エージェント面エンドポイント(`/agents/{name}/endpoint/protocols/openai/responses`)は `?api-version=v1` クエリ必須**(欠くと 400)。プロジェクトの `/openai/v1` 面は逆にクエリを拒否 — 非対称 | Routines REST([tech-selection-guide 罠 10](../../tech-selection-guide.md#2-実装ナレッジ集ハマりどころ))と同型。SDK の `default_query` で固定 |
| 2 | **agent identity の既定アクセスに Conversations の読み取りは含まれない**。履歴フェッチが失敗しコンテナ内 500。**Azure AI User + Cognitive Services OpenAI User** を 2 段目テンプレートで明示付与 | 公式の「モデル推論・セッションストレージへ既定アクセス」を「Conversations も読める」と読まない |
| 3 | **RBAC 伝播は 15〜45 分規模・MI ごとに不均一**(API / ジョブ / agent identity)。デプロイ直後の E2E は伝播窓に入り失敗 | CI/CD に伝播待ち(ポーリング)を入れる。伝播中の失敗は「バグ」と誤診しない |
| 4 | hosted agent provisioning **初回 125.9 秒 / 2 回目 45.9 秒**(zip 55 ファイル・REMOTE_BUILD) | デプロイ工程に 2〜3 分のポーリングを見込む |
| 5 | **cold start 12.4 秒(17 分アイドル後)/ warm 8.1 秒**(E2E = API シェル+エージェント面+LLM ツールループ込み)。サンドボックス復帰ペナルティは +数秒 | ACA scale-to-zero 44.8 秒(v2 実測)と違い **keep-warm 不要**。対話 UX でも許容範囲 |
| 6 | **File Search に素の検索 API はない**(`vector_stores.search` = 全面 404)。モデル内ツール専用(`file_search_call.queries` で書き換えクエリは取得可)。**.xlsx / .jpg / .png は `unsupported_file` で投入不可** | 「決定的ヒット列を返す検索ツール」としては使えない。RRF 統合・引用順位制御が要るなら AI Search |
| 7 | BYO Cosmos に **`enterprise_memory` DB + 5 コンテナ**(agent-entity-store / thread-message-store / run-state-v1 / system-thread-message-store / agent-definitions-v1)。**5 コンテナ × autoscale 最大 1,000 RU/s**(課金下限 100)。アイドル月 6〜7 千円規模 | v2 期の記録「最低 3,000〜5,000 RU/s 固定」より大幅に軽い。**standard setup のコスト障壁は当時より小さい**([proposal 02](../proposal/02-cost-estimation.md) の BYO 行は要更新) |
| 8 | **project → App Insights 接続(`connections/appinsights`)がないと hosted agent へ接続文字列が注入されず、コンテナ内部ログがどこにも届かない** | 障害切り分けで最初に確認する項目。Bicep に接続を含める |
| 9 | v3 脳 vs v4 脳(同一データセット・実インデックス): retrieval hit@3 0.708 → 0.667(誤差域)、unanswerable 0.000 → 0.200(改善: LLM ツール選択が無関係な質問で検索を抑制)、category / hearing 1.000 → 1.000 | **載せ替えによる品質劣化なし**。比較ゲートが RRF 重み付けの実装差を実検出した(回帰検出として機能) |
| 10 | 破棄: standard setup ではエージェント・会話・ファイルの実体が全て自社 RG 内 → **RG 削除で破棄が閉じる**(basic では Microsoft 管理側の消滅を自分で確認できない) | 「消したことを証明できる」のは BYO の運用上の利点 |
| 11 | `openai` SDK 3.x は `httpx2`(改名フォーク)を使い `respx` でモック不能 → `openai<3` にピン | テスト戦略が SDK メジャーに依存する |

### 4-2. 閉域 Lv3(ラウンド 2)— 本トラック最大の発見

公網遮断(PNA Disabled + PE + internal ingress)後、API / UI / Foundry project / AI Search の 4 面すべて遮断を確認し、ジャンプボックスからは PE 経由で受付・聞き返しまで到達。しかし**回答ターンだけが縮退応答**になった。切り分け(Search のみ開放 → 変化なし / Foundry PNA も開放 → 即座に実回答)で確定:

> **アウトバウンド VNet 注入なしの閉域(Lv3 = インバウンド遮断のみ)では hosted agent は成立しない。**hosted agent コンテナは顧客 VNet 外の Foundry 管理コンピュートで動くため、PNA Disabled にした**自プロジェクト(モデル・Conversations)にも BYO AI Search にも到達できない**。閉域ツール表の「AI Search = PE 経由」「File Search = PE 経由」は**アウトバウンド VNet 注入構成([公式 15-private-network-standard-agent-setup](https://github.com/microsoft-foundry/foundry-samples/tree/main/infrastructure/infrastructure-setup-bicep/15-private-network-standard-agent-setup))が前提**で、注入は**作成時のみ設定可**。

| # | 実測 | 設計への含意 |
| --- | --- | --- |
| 12 | 上記。インフラ(standard setup・PE・エージェント配布)は注入なしでも立つため **「デプロイは成功するが実行だけが通らない」** | **閉域で hosted agent を使うなら Lv3 要件でも最初から VNet 注入つきで作る。**代替は「会話脳を ACA に留める(v3 構成)」か「Foundry を選択ネットワーク+信頼サービスで部分開放」 |
| 13 | PNA Disabled ではデータプレーン配布(`create_version_from_code`・ナレッジ投入)も公網から届かない → 「一時開放 → 配布 → 再遮断」で運用(スクリプト化) | 恒久運用では閉域内の配布経路(セルフホストランナー等)が必要。[architecture 07 §3](../architecture/07-usecase-regulated-edge.md#その他の運用上の制約) の「VNet 化後は `azd up` 不可」と同じ問題 |
| 14 | 閉域作成アカウントでは(一時開放中でも)**vector store 作成自体が 500** で継続失敗(公開作成アカウントでは成功)。原因未特定 | File Search 不採用の追加補強。閉域で File Search を提案しない |
| 15 | 閉域の Key Vault シークレット参照は PE / DNS 完成後でないと解決に失敗(`dependsOn` 必須) | Bicep の依存順序 |
| 16 | capabilityHost の再 PUT(同一構成)は**冪等**。Foundry アカウントの `networkAcls` は未設定だとプロパティ自体が存在しない(PNA のみで切替) | stack 再デプロイは安全 |
| 17 | テレメトリの閉域到達は**未確認のまま環境破棄**(理論上は NAT 経由で届くはず) | 次回閉域検証の持ち越し |

## 5. 顧客閉域環境への納品で問題になった点(v2 期の洗い出し、2026-08-07)

Foundry の機能可否とは別に、**「顧客の閉鎖環境に構築して引き渡す」SI 固有の問題**が v2 期に洗い出された。Foundry 案件に限らない普遍的な地雷なので、[01 S-12](./01-scenario-playbook.md#s-12-顧客閉域環境への納品-ci-cd・構築・搬入・プロンプト運用) の根拠として残す。

| # | 論点 | 深刻度 | 何が起きるか |
| --- | --- | --- | --- |
| 1 | コンテナイメージのビルド・搬入経路が閉域未設計(ベースイメージは ghcr.io、`uv sync` で PyPI 直、ACR Basic = PE 非対応) | 致命 | Lv3(インバウンド遮断のみ)なら `az acr build`(クラウド側ビルド)で成立するが、**Lv4(外部レジストリ・PyPI 禁止)では ACR Premium + PE + 「自社でビルド → `az acr import` / tar 持ち込み」の搬入手順が必要**で、その手順書が存在しなかった |
| 2 | 管理画面のプロンプト編集がコンテナ内で揮発し Git と乖離 | 致命 | 評価ゲートを通らない変更が本番に入る / 再デプロイで消える。→ v4 で「プロンプト正本は Git 一方向」に |
| 3 | 閉域向け CI/CD が事実上未設計(GitHub ホストランナー + PyPI + OIDC 前提) | 高 | **Lv3 か Lv4 かで答えが変わる。**Lv3 なら Azure DevOps 不要(成果物だけ届ける)。Lv4 なら Azure DevOps + VNet 内セルフホストエージェント + Azure Artifacts(PyPI upstream)+ ベースイメージの ACR ミラー。**「どちらか」をヒアリングで確定しないと見積もれない** |
| 4 | 1 本以外のプロンプト・評価データがイメージ同梱で、変更 = イメージ再ビルド | 高 | 運用で「プロンプトを直す」たびに搬入経路(#1)を通る |
| 5 | 初期セットアップが ARM PUT の非冪等な手作業 | 高 | 戻し忘れリスク。→ v4 では capabilityHost 再 PUT 冪等を実証し stack 化 |
| 6 | Lv3 でも外に出る通信 6 種(ARM 管理プレーン・Entra・App Insights 等) | 中〜高 | 顧客の「閉鎖」の定義次第でスコープ外になる。**T-xx(顧客了承事項)として明文化** |
| 7 | 閉域内ブラウザ → 管理画面の Entra ログイン経路が未設計 | 中〜高 | Bastion / jump box / VPN のどれかを顧客側と合意 |
| 8 | 監視の閉域化(AMPLS)未実装 | 中 | Lv4 では App Insights も PE 化が必要 |

## 6. 提案への含意(一般化)

1. **撤退理由は機能単位で書く。**「Foundry はデータがサービス側に残る」ではなく「添付原本の不保存は File Search / Conversations では満たせない(理由: …)」「SN 書き込みの決定性は prompt agent のツール呼び出しでは保証できない」まで書く。前者は standard setup の登場で反証されたが、後者は今も成立している
2. **ハイブリッド(決定的シェル + LLM コア)が SI の現実解。**「全部 Foundry」「全部自前」の二択にしない。決定性が要る部分(書き込み・状態遷移・監査)を自前シェルに、LLM に任せる部分(検索・回答生成)を hosted agent に置くと、Foundry の運用機能(版管理・観測・スケールゼロ)を使いつつガードレールを保てる
3. **閉域 hosted agent は「作成時に注入」を提案書に書く。**後付け不可なので、Lv3 要件でも注入前提で VNet・委任サブネット(/27 以上)・PE を最初から積む。注入なしで作ると「デプロイは通るのに実行が失敗」で PoC が破綻する
4. **評価ハーネスを先に作る。**v3 → v4 の載せ替え判断は、同一データセット比較があったから 1 日で「劣化なし」と言えた。技術選定の A/B は評価基盤がないと感想戦になる
5. **顧客の「閉鎖環境」は Lv 定義を先に合意する。**Lv3(インバウンド遮断)と Lv4(egress 統制・外部 SaaS 禁止)で CI/CD・搬入・監視の設計と見積もりが別物になる
6. **プレビュー不使用ポリシーは「サービス面」と「IaC の API version」を分けて運用する。**standard setup は GA 機能だが Bicep の API は preview 版しかない(2026-08-30 時点)。一律「preview 禁止」だと GA 機能が使えなくなる

## 参照

- 本リポジトリ側の関連: [tech-selection-guide §5・§6](../../tech-selection-guide.md) / [architecture 05 B1・B2](../architecture/05-usecase-agent-automation.md) / [architecture 07 §2〜3](../architecture/07-usecase-regulated-edge.md) / [02 詰まりどころ索引](./02-pitfalls-index.md)(P-H・P-I・P-N 系)
- 公式一次情報(v4 GA 証跡で使用): [Feature readiness at GA](https://learn.microsoft.com/en-us/azure/foundry/concepts/general-availability)(ms.date 2026-08-14)/ [Configure network isolation](https://learn.microsoft.com/en-us/azure/foundry/how-to/configure-private-link)(2026-08-14)/ [Hosted agents](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents)(2026-08-19)
