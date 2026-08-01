# 11. エージェント構成の判断フレームワーク — 「複数試作して比較するしかないか」への回答

[← アーキテクチャ TOP](./README.md)

> **最終更新:** 2026-08-01(初版)
> **経緯:** SI 文脈の問い「ユースケース・要件からアーキテクチャ / エージェント構成を選ぶ指標は事前に構築できるか。それともプロジェクトの中で複数試作して比較するしかないか」への回答として、公式・業界の判断フレームワークを調査した(Web 調査 2026-08-01)。
> **位置づけ:** [03. 選定ガイド](./03-decision-guide.md)が「Foundry を使うと決めた後」の構成判断(5 ゲート)を扱うのに対し、本章はその**手前と外側** — ①どのプラットフォームで作るか(Copilot Studio / Foundry / 自前)、②単一エージェントか複数か、③どのオーケストレーションパターンか — と、提案の根拠として引用できる公式フレームワークを扱う。実装検証由来の知見は [tech-selection-guide](../../tech-selection-guide.md) にあり、本章は公式ドキュメント・公開ガイダンスのみを出典とする。

## 結論 — 机上で当たりをつけられる。比較試作が必要な範囲は限定される

2025-12 以降、Microsoft 自身が SI が欲しい形の判断フレームワークを公式ドキュメントとして整備した。しかも CAF は判断表の中で「**基準が明確なケースは試作を省略してよい(Skip prototyping: Yes)。比較プロトタイプが必要なのはアーキテクチャ判断が不明確な場合だけ**」と明言している。

| 判断 | 公式フレームワーク | 決まり方 |
|---|---|---|
| ①どのプラットフォームで作るか | CAF デシジョンツリー(§2) | **机上で決まる。**決め手は機能でなく「誰が作り・誰が保守し・どこまで制御が要るか」 |
| ②単一エージェントか複数か | CAF 単一 vs マルチ判断(§3) | 3 条件に該当すればマルチ確定、非該当なら**単一で開始**。比較試作は判断が割れるときのみ |
| ③どのオーケストレーションパターンか | AAC パターンカタログ(§4) | 要件シグナルから机上で選べる。フレームワーク非依存 |
| ④品質・コスト・レイテンシの実額 | (フレームワークなし) | **ここだけ実測。**ただし「複数アーキ並行構築」でなく「単一試作+評価ハーネス」で潰す(§7) |

残る不確実性は「アーキテクチャの選択」ではなく「顧客データ・プロンプト・モデル挙動に依存する品質と実コスト」に局所化されており、そこは評価基盤(L13)で回帰可能にするのが公式・業界共通の推奨である。

## 1. 公式ガイダンスの全体地図

| ドキュメント | 内容 | ms.date |
|---|---|---|
| [CAF: AI agent adoption(build-secure-process)](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ai-agents/build-secure-process) | 採用プロセス全体(Plan → Govern/Secure → Build → Manage)。Build の 5 領域(Orchestration / Models / Knowledge & Tools / Observability / Security)を **Foundry / MAF / Copilot Studio 別の実装先つき**で規定 | 2025-12-01(更新 2026-06) |
| [CAF: Single-Agent vs Multi-Agent](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ai-agents/single-agent-multiple-agents) | 単一 / マルチの判断基準・デシジョンツリー・判断表 | 2025-12-01(更新 2026-02) |
| [AAC: AI Agent Orchestration Patterns](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns) | 複雑度の階段+ 5 パターン(when to use / avoid / 比較表 / アンチパターン / コスト) | 2026-02-12(更新 2026-05) |
| [Copilot Studio: Multi-agent orchestration patterns](https://learn.microsoft.com/en-us/microsoft-copilot-studio/guidance/multi-agent-patterns) | ローコード側のマルチエージェント設計基準(child / connected の使い分け・分割判断) | 2026-05-21 |
| [Copilot Studio: Add other agents](https://learn.microsoft.com/en-us/microsoft-copilot-studio/authoring-add-other-agents) | connected agents の構成方法と既知の制限(多段連鎖不可など) | 2026-05-15 |

[01 章](./01-official-baselines.md)の公式-A/B/C が「**インフラの形**」のリファレンスなのに対し、これらは「**エージェントの形**」の判断基準であり相補的。なお AAC には MAF によるマルチエージェント実装例 [Multiple-agent workflow automation](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/idea/multiple-agent-workflow-automation) もあるが、こちらは**ソリューションアイデア級**(検証レベルは公式-A/B/C より下)。

## 2. 層① プラットフォーム選定 — Copilot Studio / Foundry / 自前

### CAF のデシジョンツリー

```
 潜在的なエージェントユースケース
        │
        ▼ そもそも生成 AI エージェントが要るか？
        │   No → コード / 非生成 AI モデル(Fabric・ML 等)
        │        (静的 Q&A、推論を伴わないコンテンツ生成もエージェント不要側)
        ▼ SaaS エージェントで機能要件を満たせるか？
        │   Yes → M365 Copilot エージェント / GitHub Copilot / Fabric data agents /
        │         Dynamics 365 / Security Copilot 等をそのまま使う
        ▼ 作る(Build)
        ├── Copilot Studio(SaaS・ノー/ローコード)
        ├── Microsoft Foundry(PaaS・プロコード)
        └── GPUs & Containers(IaaS)
```

**選定の決め手は「エージェントの機能」ではなく「誰が作り、誰が保守し、どこまで制御が要るか」**(builder persona / 運用モデル / 統制要件)。これは 03 章 G4「業務部門がノーコードで育てたいか」・G5「いつまで誰が保守するか」と同じ軸であり、機能比較表で決めようとするのが誤りだという点で公式・実務側の見解が一致している。実務側の経験則(二次情報: [PnP ブログ](https://pnp.github.io/blog/post/copilot-studio-vs-agent-builder-vs-foundry/))は「**Copilot Studio をデフォルトにし、コネクタとローコード制御で足りないときだけ Foundry**」で、判断基準は①作り手は誰か ②ユーザー接点はどこか ③ロジックの複雑さ ④Go-Live 後に誰が面倒を見るか、の 4 軸。

### Copilot Studio の上限ライン(一次情報で確認できたもの)

「Copilot Studio で簡単に作れない業務」の境界を、公式ドキュメントの記載で引く:

| 制約 | 内容 | 出典 |
|---|---|---|
| **アクション数の精度劣化** | **30〜40 個のアクション**(ツール・トピック・エージェント)を超えるとオーケストレーターのツール選択精度が落ちる目安、と公式が明記 | [Add other agents](https://learn.microsoft.com/en-us/microsoft-copilot-studio/authoring-add-other-agents) |
| instructions | 8,000 文字まで | [Quotas and limits](https://learn.microsoft.com/en-us/microsoft-copilot-studio/requirements-quotas) |
| ナレッジ / トピック | ナレッジソース 500 / トピック 1,000 / スキル 100(いずれもエージェントあたり) | 同上 |
| **マルチエージェントの多段連鎖不可** | connected agents を持つエージェントは、**他のエージェントの connected agent にはなれない**(多段のエージェント階層は組めない) | [Add other agents – Known limitations](https://learn.microsoft.com/en-us/microsoft-copilot-studio/authoring-add-other-agents) |
| 外部エージェント接続はプレビュー | **Foundry エージェント / A2A / Fabric data agents / M365 Agents SDK への接続はいずれも public preview**(本番非推奨の注記つき) | 同上 |
| 決定的制御の上限 | エージェントフロー・トピックによる決定的制御はあるが、CAF は「**クリティカルな業務ロジックには決定的ワークフローを強制せよ。Foundry / MAF の workflows を使え**」と実装先を名指し | [CAF build-secure-process](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ai-agents/build-secure-process) |
| モデル制御 | モデル選択は可([primary model 選択](https://learn.microsoft.com/en-us/microsoft-copilot-studio/authoring-select-agent-model)・Foundry からの BYO model)だが、推論パラメータの細かい調整やオーケストレーションループ自体の差し替えは不可 | — |

**本ドキュメントの判断:** 03 章 G3 の「明示的な状態遷移が要るか」に加えて、**「30〜40 アクション超」「多段のエージェント階層」「決定的ワークフローが業務クリティカル」の 3 つが Copilot Studio → Foundry(プロコード)への乗り換えシグナル**として一次情報で裏づけられる。

### 両者は排他ではない — 分業構成が公式の推奨形

Copilot Studio の connected agents は **Foundry で作ったエージェントを部品として呼べる**(プレビュー)。「対話の入口・M365 チャネル・業務部門の保守は Copilot Studio、業務固有の複雑な処理は Foundry hosted agent」という分業は、公式ブログ([Choosing the Right Starting Point](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/choosing-the-right-starting-point-for-enterprise-ai-agents-with-copilot-studio-a/4535024))でも推奨される構成であり、03 章 G4 の「業務フローエンジン主導(B5)」の現代版にあたる。**SI の受託範囲が「Copilot Studio で簡単に作れないエージェントの開発」なら、納品物は connected agent として Copilot Studio 側から呼ばれる Foundry hosted agent、という契約の切り方が公式構成と一致する。**ただし接続がプレビューである点は提案時に明示する(G5)。

## 3. 層② 単一エージェントか複数か — CAF の判断基準

### 最初からマルチエージェントにしてよいのは 3 条件のみ

1. **セキュリティ・コンプライアンス境界をまたぐ** — 規制・ポリシーがデータ分離を強制する場合(例: 金融の取引作成と検証の職務分離)。least-privilege をアーキテクチャで強制する
2. **複数チームが別ドメインを保有** — チームごとに独立した開発サイクル・ナレッジ・デプロイが要る場合。組織構造への整合
3. **成長がロードマップ上確定** — 機能・データソース・事業部門の拡張が確定している場合。**3〜5 機能を超える**ソリューションが目安

### それ以外は単一エージェントで試作してから

CAF は「マルチエージェントは**検証されていない複雑さ・性能の思い込み**で選ばれがち」と明記し、以下を単一で始める根拠に挙げる:

| 状況 | CAF の指示 |
|---|---|
| planner / reviewer など**役割分担がある** | **役割分担だけではマルチの理由にならない。**ペルソナ切替・条件付きプロンプト・ツール権限制御で足りるかをまず単一で検証 |
| 市場投入速度・低コスト優先 | 単一で開始(マルチは調整ロジックと通信プロトコルで初期開発が遅くなる) |
| 大量データ処理 | スケール問題の多くは**アーキテクチャでなく検索設計**(チャンク・索引・リランク)。それらを尽くしてなお劣化するときだけマルチ |
| 高スループット | 並列化が実測で効果を出すときのみマルチ。調整オーバーヘッドが並列の利得を食い潰すことが多い |
| マルチモーダル | まずマルチモーダルモデル 1 体で。特定モダリティに専用最適化が要るときだけ分割 |

### 判断表(CAF Decision framework) — 「試すしかないのか」への公式回答

| アプローチ | 使う場面 | 試作の要否 |
|---|---|---|
| **単一エージェント** | ドメインが狭い・統一コンテキスト・速度/コスト優先 | **省略可**(スコープが単純なら直行) |
| **比較プロトタイプ** | アーキテクチャ判断が不明確で、コンテキスト処理・役割分離・性能の証拠が要る | 定義した成功指標に対する対照テストを実施 |
| **マルチエージェント** | セキュリティ・コンプラ・組織の**ハードな境界**がある、マルチドメイン拡張が確定 | **省略可**(要件が分離を強制するなら直行) |

つまり公式の回答は「**全部試す」ではなく「基準に該当すれば直行、割れたときだけ比較試作**」。

### ローコード側にも同型の基準がある(Copilot Studio)

[Multi-agent patterns](https://learn.microsoft.com/en-us/microsoft-copilot-studio/guidance/multi-agent-patterns) の分割基準はスケールこそ違うが同じ構造をしている: 分割するのは「別ドメインのツール・ナレッジ一式を持つ」「別のガバナンス・アクセス制御が要る」「複数の親から再利用される」場合のみで、**該当しなければ child agent(トピック相当の軽量サブルーチン)で済ませ、「まず 1 エージェントで作り、明確な必要が見えたときだけ分割せよ」**と明記。これは CAF の 3 条件のローコード版であり、プラットフォームを問わず同じ判断構造が使えることを示す。

### マルチエージェントのコスト(トレードオフの定量感)

CAF は「エージェント間のプロトコル設計・エラー処理・状態同期」「エージェントごとのプロンプト・監視・デバッグ」「冗長なコンテキスト処理による費用増」「ハンドオフごとのレイテンシ蓄積」を列挙する。定量の参考値は Anthropic(§5)の「**マルチは単一の 3〜10 倍のトークンを消費**」。

## 4. 層③ オーケストレーションパターン — AAC のカタログ

### 複雑度の階段 — 「要件を満たす最低の複雑度を選べ」

| レベル | 使う場面 | 備考 |
|---|---|---|
| 直接モデル呼び出し | 分類・要約・翻訳など 1 パスで済むタスク | プロンプトで解けるならエージェント不要 |
| **単一エージェント+ツール** | 単一ドメイン内の多様な要求(注文照会・DB 検索等) | **「エンタープライズユースケースの正しい既定値であることが多い」**と公式が明記 |
| マルチエージェント | ドメイン横断、エージェントごとのセキュリティ境界、並列専門化 | プロンプト複雑性・ツール過多・セキュリティ要件で単一が破綻するときだけ正当化される |

### 5 パターンの比較(AAC "Choose a pattern" 表の要約)

| パターン | 調整方法 | ルーティング | 向く場面 | 注意点 |
|---|---|---|---|---|
| **Sequential** | 直列パイプライン。前段の出力を処理 | **決定的**(順序は事前定義) | 段階依存が明確な逐次精錬(draft→review→polish) | 前段の失敗が伝播。並列性なし |
| **Concurrent** | 並列。同一入力に独立に取り組む | 決定的 or 動的選択 | 独立視点の並列分析、レイテンシ重視 | 結果矛盾の解決戦略が必須。リソース集中 |
| **Group chat** | 共有スレッドで議論。チャットマネージャーが発言順を制御 | マネージャー制御 | 合意形成・ブレスト・maker-checker 検証 | ループしやすい。**3 体以下推奨**と明記 |
| **Handoff** | 動的委譲。アクティブなのは常に 1 体 | **エージェントが委譲先を決める** | 処理中に適任者が判明するタスク | 無限ハンドオフ・経路の予測不能性 |
| **Magentic** | マネージャーがタスク台帳を構築・適応 | マネージャーが動的に割当 | 解法が事前に決められないオープンエンド問題 | 収束が遅い。コスト最不安定 |

**Handoff の「使うな」条件が重要:** 「初期入力から適切なエージェント(列)が特定できるなら、**決定的ルーティングか単純なディスパッチャを使え**」「ルーティングが規則ベースで決まるなら handoff にするな」。逆に maker-checker(evaluator-optimizer / critic loop)は Group chat の特殊形として定義され、**チェッカーの合否基準と反復上限・上限到達時のフォールバック(人へのエスカレーション等)をセットで設計せよ**とされる。

### アンチパターン(公式列挙から設計レビューで使うもの)

- 単純な sequential / concurrent で足りるのに複雑なパターンを使う
- **意味のある専門化を持たないエージェントを追加する**
- **決定的なワークフローに非決定的パターンを使う(およびその逆)**
- 並列エージェント間で可変状態を共有する(トランザクション不整合)
- マルチホップ通信のレイテンシ・コンテキスト肥大によるモデル消費を見落とす

### コスト・実装上の含意

- パターン選択が直接コストに効く: sequential / handoff は逐次で積み上がり、concurrent はスパイクし、**magentic は最も変動が大きく総額を予測しにくい**
- エージェントごとにタスク複雑度に見合うモデルを割り当てる(分類・抽出・整形は小型モデルで品質が落ちないことが多い)
- **パターンはフレームワーク非依存**と公式が明言: MAF workflows に 5 パターンすべての 1:1 実装があり、LangChain / CrewAI / OpenAI Agents SDK でも適用可
- ただし **Foundry Agent Service の connected agents(ポータルのマネージドなエージェント連鎖)は「主として非決定的」でパターン実装範囲に制限がある**、と AAC 自身が注記。決定的パターンが要るならコードファースト(03 章 G3 と同結論)

## 5. 業界の収斂 — Microsoft 外の指標(参考)

Microsoft 固有の話ではなく、主要ベンダーの基準が同方向に収斂している。ベンダー非依存の指標として提案書に使える。

**Anthropic**([When to use multi-agent systems](https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them)): マルチが単一に勝つのは 3 条件のみ — ①**コンテキスト汚染**(サブタスクが 1,000+ トークンの出力を生むが後工程に不要)②**並列化**(独立サブタスク)③**専門化**(ツール 15〜20+ で選択精度が劣化、ドメイン混線)。コストは **3〜10 倍**。失敗モードは「伝言ゲーム」(問題種別で分割するとハンドオフごとに情報が落ちる)で、**分割はコンテキスト境界で行い、共有コンテキストが要る作業は同一エージェントに残す**。原則は「動く最小構成から始め、証拠があるときだけ複雑化」。

**LangChain**([Choosing the Right Multi-Agent Architecture](https://www.langchain.com/blog/choosing-the-right-multi-agent-architecture)): 4 アーキテクチャ(subagents = 監督者がサブエージェントをツールとして呼び結果が戻る / skills = 単一エージェントが専門プロンプトを動的ロード / handoffs = 会話状態に応じて制御ごと移す / router = 分類→並列ディスパッチ→合成)を「分散開発・並列性・多段推論・ユーザーとの直接対話」の 4 軸で選ぶ。原則は「**エージェントを増やす前にツールを増やせ。明確な限界に当たったときだけマルチへ**」。

**対応関係(本ドキュメントの判断):** Copilot Studio の「30〜40 アクションで分割検討」と Anthropic の「15〜20+ ツールで専門化検討」は同じ現象(オーケストレーターのツール選択精度劣化)に対する閾値であり、プラットフォームが変わっても**「ツール選択精度の劣化」が単一→マルチの主要シグナル**という点で一致する。

## 6. 本リポジトリの既存指標との対照

| 本リポジトリ側 | 公式・業界側 | 関係 |
|---|---|---|
| 03 章の 5 ゲート(後戻りコスト順) | CAF デシジョンツリー | 同じ思想。**「後戻りコスト順に閉じる」という順序づけは本リポジトリ側の付加価値**(CAF は順序に言及しない) |
| G3「明示的な状態遷移が要るか」 | CAF「クリティカル業務ロジックに決定的ワークフローを強制」 | 一致。公式引用で補強可能 |
| 03 章 Q「マルチエージェントは本当に必要か」 | CAF の 3 条件+単一先行原則 | 一致。「権限を分けたい/並列調査」は CAF 条件 1・Anthropic 条件②③に対応 |
| tech-selection-guide の 2 軸 3 値(制御=コード/LLM × 戻る/移る) | AAC の Routing 列(deterministic / agents decide)+ LangChain の subagents(戻る)vs handoffs(移る) | **同型。**グラフ= Sequential・Concurrent(決定的ルーティング)、相談型 agent-as-tool = LangChain subagents、担当交代= AAC Handoff |
| Port 7 実証「one-shot パイプラインに handoff を使うと決定性が確率的になる」 | AAC アンチパターン「決定的ワークフローに非決定的パターン」+ Handoff の「使うな」条件 | 実装検証と公式が独立に同じ結論 |
| (未カバー) | AAC の Group chat / Magentic | **labs 未検証。**maker-checker は critique-loop(Port 9)が近いが、会話スレッド型合意形成と magentic 型動的計画は未移植 |

**ギャップの解消状況(本章調査による):**

- tech-selection-guide §4 の未検証領域「ポータル(prompt agents)だけの限界線」に隣接する「**Copilot Studio 側の限界線**」は、§2 の一次情報(30〜40 アクション・多段連鎖不可・決定的制御の上限)で机上でもかなり埋まった
- 「LangGraph との同一シナリオ実装比較」は優先度を下げてよい(**本ドキュメントの判断**)。理由: ①AAC がパターンのフレームワーク非依存を明言 ②選定は「パターン → フレームワーク」の順で決まり、フレームワーク差は移植コスト実測(tech-selection-guide §1-3)で既にカバーされている ③Hosted agent はどちらも受けられる(03 章)

## 7. SI 実務への落とし込み — 提案時の判断手順

```
 1. プラットフォーム確定(CAF ツリー+§2)          … 机上
    「誰が作り・誰が保守し・どこまで制御が要るか」
    Copilot Studio 上限ライン(30〜40 アクション/多段連鎖/決定的制御)に
    当たるものだけが Foundry プロコード側 = SI の受託範囲
        ▼
 2. Foundry 内の構成確定(03 章 G1〜G5)             … 机上
        ▼
 3. 単一かマルチか(CAF 3 条件)                     … 机上
    該当なし → 単一エージェント+ツールで開始(公式推奨の既定値)
        ▼
 4. パターン選択(AAC 5 パターン ≒ 2 軸 3 値)       … 机上
    「制御をコードで決められるか」を最初に問う(決定的に倒せるなら倒す)
        ▼
 5. 品質・コスト・レイテンシの検証                   … ここだけ実測
    単一エージェントの薄い試作+評価ハーネス(L13、CI 統合)
    限界が実測で出た軸だけ複雑化(マルチ化・パターン変更)
```

- 「複数アーキテクチャを作って比較」は CAF の**比較プロトタイプ該当時のみ**。かつ比較対象は手順 1〜4 で絞った 2 案であり、ゼロベースの N 案比較ではない
- 評価ハーネスは選定指標とセットで標準化する(継続的評価・CI 統合は [09 章](./09-operations.md)・03 章チェックリスト参照)。**「選定は指標で、検証は評価で」が提案の型**
- 提案書では「公式ガイダンス(CAF / AAC)準拠+実装検証済み(tech-selection-guide)」の二本立てで根拠を示せる

## 出典

**一次情報(Microsoft Learn):**

- CAF: [Process to build agents(build-secure-process)](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ai-agents/build-secure-process) / [Single-Agent vs Multi-Agent](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ai-agents/single-agent-multiple-agents)
- AAC: [AI Agent Orchestration Patterns](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns) / [Multiple-agent workflow automation(ソリューションアイデア級)](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/idea/multiple-agent-workflow-automation)
- Copilot Studio: [Multi-agent orchestration patterns](https://learn.microsoft.com/en-us/microsoft-copilot-studio/guidance/multi-agent-patterns) / [Add other agents](https://learn.microsoft.com/en-us/microsoft-copilot-studio/authoring-add-other-agents) / [Quotas and limits](https://learn.microsoft.com/en-us/microsoft-copilot-studio/requirements-quotas)

**公式ブログ(準一次):**

- [Choosing the Right Starting Point for Enterprise AI Agents(Foundry blog)](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/choosing-the-right-starting-point-for-enterprise-ai-agents-with-copilot-studio-a/4535024)

**他社・実務者(参考・二次):**

- Anthropic: [When to use multi-agent systems](https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them)
- LangChain: [Choosing the Right Multi-Agent Architecture](https://www.langchain.com/blog/choosing-the-right-multi-agent-architecture)
- PnP: [Agent Builder vs Copilot Studio vs Foundry: How We Decide for Every Client](https://pnp.github.io/blog/post/copilot-studio-vs-agent-builder-vs-foundry/)

## 更新運用(本章のウォッチリスト)

| # | ソース | 見るもの |
|---|---|---|
| 1 | [CAF ai-agents セクション](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ai-agents/build-secure-process) | 判断基準の改訂(`ms.date`)。新設セクションのため構成変更が起きやすい |
| 2 | [AAC ai-agent-design-patterns](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns) | パターンの追加・「Choose a pattern」表の変更 |
| 3 | [Copilot Studio: Add other agents](https://learn.microsoft.com/en-us/microsoft-copilot-studio/authoring-add-other-agents) | **Foundry / A2A 接続の GA 昇格**(現在プレビュー。GA すると §2 の分業構成が本番提案可能になる) |
