# Microsoft Foundry キャッチアップ計画書

作成日: 2026-07-03(改訂: 技術選定判断力の獲得を主目的に再構成)

## 1. 目的

SI 案件における **AI エージェント関連の技術選定判断ができるようになる**こと。具体的には、顧客要件に対して以下を根拠を持って判断できる状態を目指す:

1. **Foundry ポータル(ノーコード / 構成のみ)で足りる**要件はどこまでか
2. **コード実装(MAF など)が必要になる**のはどんな構成か
3. **MAF でも困難で、LangGraph や他フレームワークを選ぶべき**なのはどんな場合か
4. そもそも **Foundry に乗せるべきか、乗せないべきか**(既存システム組み込み、マルチクラウド、ベンダーロックイン回避など)

学習は座学ではなく**同一シナリオを複数方式で実装して境界を体感する検証実験**を中心に進め、最終成果物として `docs/tech-selection-guide.md`(技術選定ガイド)を作る。

> 注: AI-103 資格は本計画ではいったんスコープ外。ただし本計画のハンズオンは試験ドメイン 1・2(計 55〜65%)とほぼ重なるため、後日受験する場合は Phase 3(Vision / Language 系)の追加学習のみで対応できる。

## 2. 技術選定の全体像(2026 年 7 月時点)

調査の結果、選定は「ポータル vs MAF vs 他フレームワーク」という一列の比較ではなく、**3 つの独立した軸**で考えるべきと判明した。

### 軸 A: エージェントの定義方法 — 構成のみ(Prompt Agent)か、コード(Hosted Agent)か

Foundry Agent Service には 2 種類のエージェントタイプがある:

| | Prompt Agent | Hosted Agent |
|---|---|---|
| 定義方法 | 構成のみ(指示文 + モデル + ツール)。ポータル / SDK / REST | 自前のエージェントコードをコンテナ or zip でデプロイ |
| ランタイムコード | 不要(Foundry がフルマネージドで実行) | 自分で保守(ホスティング・スケール・ID は Foundry 管理) |
| コスト | 推論 + ツール利用のみ | 上記 + コンテナコンピュート |
| 向く場面 | 高速立ち上げ、カスタムオーケストレーション不要な本番エージェント | カスタムコード呼び出し、独自オーケストレーション、マルチエージェント、独自プロトコル(webhook / voice / AG-UI) |

### 軸 B: コードを書く場合のフレームワーク — MAF は選択肢の一つ

**重要な発見**: Hosted Agent は MAF 専用ではない。**MAF / LangGraph / OpenAI Agents SDK / Anthropic Agent SDK / GitHub Copilot SDK / 完全自前コード**が公式にサポートされる。つまり「Foundry を使うか」と「MAF を使うか」は独立した判断。LangGraph 製エージェントを Foundry にホストする構成も正規ルート。

### 軸 C: Foundry との統合度 — 全部乗せる / モデルとツールだけ借りる / 使わない

- **フル統合**: Prompt / Hosted Agent として Foundry 上で実行(ID・スケール・観測・公開まで Foundry)
- **Responses API のみ利用**: 既存アプリ内で動くエージェントコードから Foundry のモデル + プラットフォームツール(file search, code interpreter, web search, MCP, memory)だけを呼ぶ。**既存システム組み込み型の SI 案件で重要なパターン**
- **Foundry 非依存**: AOAI 直、他クラウド、セルフホスト

## 3. 能力境界の初期仮説(ハンズオンで検証する)

以下は調査ベースの仮説。**各項目を labs/ の実験で確認し、検証結果を境界レポートに反映する**のが本計画の中身。

### 3.1 ポータル(構成のみ)でできること

- Prompt Agent の作成・プレイグラウンドでのテスト・公開(Teams / M365 Copilot / Entra Agent Registry への配布まで)
- ツール接続: web search、file search、code interpreter、memory、MCP サーバー(カタログから追加、認証はキー / Entra / OAuth OBO)
- **Connected Agents**: プライマリエージェントからタスク特化エージェントへの委任による、外部オーケストレーター不要のマルチエージェント
- **Multi-Agent Workflows(プレビュー)**: ビジュアルデザイナーでエージェント・ツール・データフローを接続
- トレーシング、評価、バージョニング、コンテンツフィルター等の運用機能

> ⚠️ **選定上の重大な注意**: 廃止されるのは「ワークフロー機能」のみ(ビジュアルデザイナー + ポータル内ワークフロー実行が **2026-12-01 にリタイア**)。**ポータルでのエージェント作成・プレイグラウンド・公開・Connected Agents は廃止対象外**。公式移行パスは 3 つ:
> 1. **MAF(推奨)**: エクスポートした YAML を MAF の宣言的ワークフローにほぼそのまま持ち込み、Hosted Agent としてデプロイ。以後は VS Code(Agent Inspector で可視化・実行可)で反復
> 2. **Azure Logic Apps**: ビジュアルデザイナーを維持したい場合。Foundry エージェントをワークフローのステップとして呼び出せる
> 3. **A2A エンドポイント**: 正式なワークフローが不要な軽量のエージェント間連携
>
> Microsoft 自身がコードファースト(= MAF)へ誘導しており、ポータル完結のワークフロー構成を長期運用前提で提案するのはリスク。なお **Foundry IQ はワークフローの移行先ではない**(§3.4 参照)。

### 3.2 コード(MAF 等)が必要になる(はずの)構成

- 条件分岐・ループ・エラーリカバリを含む複雑なオーケストレーションロジック
- 独自のビジネスロジック・社内 API との密結合(カスタム関数の域を超えるもの)
- 承認フロー(human-in-the-loop)の細かい制御、チェックポイントからの再開
- ミドルウェア(ロギング・認可・入出力加工)をエージェント実行パイプラインに挟む構成
- 独自プロトコル対応(webhook 起点、音声、AG-UI)
- ローカル / CI での単体テスト・再現性が求められる開発プロセス

### 3.3 MAF で困難・他フレームワークが有利な(可能性のある)領域

- **LangGraph**: 型付き共有ステートが流れる明示的なグラフモデル、チェックポイント + タイムトラベルデバッグ、成熟した HITL(interrupt)、LangSmith による観測、圧倒的なコミュニティ資産。複雑なステートフルワークフローの制御性は現時点で最有力との評価が多い
- **MAF の弱点(仮説)**: GA から 3 か月の若いエコシステム。コミュニティのパターン蓄積・サードパーティ統合・ドキュメントの厚みは LangChain 系に劣る。高度なステート操作の表現力は要検証
- **MAF の強み**: .NET + Python 同一 API、Foundry / Azure(Entra ID、ガードレール、観測)とのネイティブ統合、A2A プロトコル、AutoGen + SK の後継としての Microsoft サポート
- その他の考慮: マルチクラウド要件・ロックイン回避が強い案件ではフレームワーク中立性自体が選定基準になる

### 3.4 Foundry IQ の位置づけ(オーケストレーションとは別レイヤー)

Foundry IQ は**ナレッジ / グラウンディング層**であり、ワークフロー(オーケストレーション)の後継ではない:

- Azure AI Search を基盤とするフルマネージドのナレッジシステム。トピック単位で再利用可能な**ナレッジベース**を定義し、複数のエージェント / アプリが同じ知識でグラウンディングできる(エージェントごとに RAG 配線を作らなくてよい)
- **Agentic Retrieval**: クエリ計画 → 検索 → 統合を自己反省的に行う検索エンジン。初回検索が不十分なら検索戦略を自動で改善。「retrieval reasoning effort」を設定可能
- **IQ ファミリー**の一角: Work IQ(M365 の働き方シグナル)、Fabric IQ(データのビジネスセマンティクス)、Foundry IQ(エージェントへの統一ナレッジ供給)という 3 層構成。Foundry IQ が Work IQ / Fabric IQ への統一アクセスを仲介する
- 選定上の意味: **RAG 基盤の内製(AI Search 直組み) vs Foundry IQ 採用**という新しい選定分岐が生まれている。Phase 1–2 の RAG 実装時に両方式を比較する

## 4. 検証実験ベースの学習フェーズ

### 共通検証シナリオ

境界を比較可能にするため、**同一のリファレンスシナリオを各方式で実装する**:

> 「社内ドキュメント検索(RAG)+ 外部 API 実行を行うマルチエージェント。処理は トリアージ → 調査 → 実行案の提示 → **人間の承認** → 実行 の流れで、失敗時のリトライと監査ログを持つ」

SI で頻出する要素(RAG、ツール実行、マルチエージェント、HITL、エラー処理、監査)を一通り含み、方式ごとの得手不得手が露出する設計。

### Phase 0: 環境準備(Week 1)

- [ ] Azure サブスクリプション、Foundry リソース + プロジェクト作成
- [ ] Python 環境、Azure CLI、各 SDK セットアップ
- [ ] リポジトリ構成整備(§5)
- 成果物: `notes/00-setup.md`

### Phase 1: ポータルの限界を探る(Week 2–3)

- [ ] Prompt Agent 作成 → ツール接続(file search / MCP / カスタム関数)→ プレイグラウンド → 公開まで一巡
- [ ] Connected Agents でシナリオのマルチエージェント部分を構成
- [ ] Multi-Agent Workflows(ビジュアルデザイナー)でシナリオ全体を構成し、**どこで詰まるかを記録**(HITL の制御粒度、エラーリカバリ、監査ログの限界を重点確認)
- [ ] Prompt Agent を SDK / REST から定義する code-first パスも確認(CI/CD 適合性の評価)
- 成果物: `labs/01-portal-agents/`、`notes/01-portal-boundary.md`(ポータルで出来たこと / 出来なかったことの一覧)

### Phase 2: MAF で同一シナリオを実装(Week 4–6)

- [ ] MAF(Python)基礎: ChatAgent、ツール、MCP 統合、ミドルウェア
- [ ] MAF Workflows でシナリオをグラフとして実装(HITL、チェックポイント、リトライ)
- [ ] Hosted Agent として Foundry にデプロイ(コンテナ化、Entra ID、セッションステート、トレーシング)
- [ ] Responses API 単体利用パターンの検証(既存アプリ組み込みを想定し、Foundry のツールだけ借りる)
- [ ] Phase 1 で詰まった箇所が MAF で解決するかを個別に確認
- 成果物: `labs/02-maf/`、`notes/02-maf-boundary.md`(ポータル比での解禁事項 + MAF 自体の制約メモ)

### Phase 3: LangGraph で同一シナリオを実装・比較(Week 7–8)

- [ ] LangGraph 基礎: StateGraph、条件エッジ、チェックポインター、interrupt(HITL)
- [ ] 同一シナリオを LangGraph で実装し、MAF 実装と**コード量・表現力・デバッグ体験・観測性**を比較
- [ ] LangGraph 製エージェントを Foundry Hosted Agent としてデプロイ(「LangGraph on Foundry」構成の実用性確認)
- [ ] タイムトラベルデバッグ・複雑なステート操作など「MAF で困難」仮説の検証
- 成果物: `labs/03-langgraph/`、`notes/03-framework-comparison.md`

### Phase 4: 技術選定ガイドの作成(Week 9–10)

- [ ] 全検証結果を統合し、**`docs/tech-selection-guide.md`** を作成:
  - 要件 → 方式のディシジョンツリー(構成のみで足りるか / コードが要るか / どのフレームワークか / Foundry に乗せるか)
  - 比較マトリクス(開発速度、制御性、運用負荷、コスト構造、ロックイン、成熟度)
  - 各方式の「地雷」リスト(例: ビジュアルデザイナーの 2026-12 サポート終了、Assistants API の 2026-08-26 廃止)
- [ ] 想定 SI 案件 2〜3 パターン(例: 社内ヘルプデスク、既存業務システムへのエージェント組み込み、規制業界向け)に対する模擬選定を書いて妥当性を自己検証
- 成果物: `docs/tech-selection-guide.md`(最終成果物)

## 5. リポジトリ構成

```
ms-foundry-learn/
├── docs/
│   ├── learning-plan.md          # 本計画書
│   └── tech-selection-guide.md   # 最終成果物: 技術選定ガイド
├── notes/                        # 境界レポート・学習ノート
├── labs/
│   ├── 01-portal-agents/         # ポータル検証(スクショ・エクスポートした構成・YAML)
│   ├── 02-maf/                   # MAF 実装
│   └── 03-langgraph/             # LangGraph 実装
└── README.md                     # 概要と進捗トラッカー
```

各 lab には README.md を置き、「検証したかった仮説 → 結果 → 選定への示唆」を必ず記録する。

## 6. 学習方針

1. **仮説駆動**: §3 の各仮説に番号を振り、labs で潰していく。「できた / できなかった」だけでなく「どれだけ苦労したか(工数感)」も記録する — SI の見積もり感覚に直結するため
2. **一次情報優先**: Foundry は変化が速い。[Foundry Blog](https://devblogs.microsoft.com/foundry/) / [Agent Framework Blog](https://devblogs.microsoft.com/agent-framework/) を週次確認し、廃止予定日(§3.1 ⚠️ 等)の変更を追う
3. Semantic Kernel / AutoGen ベースの記事は陳腐化している前提で読む(両者はメンテナンスモード)
4. 比較は公平に: MAF 贔屓・LangGraph 贔屓のブログが多いので、必ず自分の手で確認した結果を正とする

## 7. 主要リソース

- [Foundry Agent Service 概要(Prompt vs Hosted Agent の公式整理)](https://learn.microsoft.com/en-us/azure/foundry/agents/overview)
- [Foundry Workflows(ビジュアルデザイナーと 2026-12-01 サポート終了の告知)](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/workflow)
- [Multi-Agent Workflows 発表記事](https://devblogs.microsoft.com/foundry/introducing-multi-agent-workflows-in-foundry-agent-service/)
- [Build 2026: Build and run agents at scale](https://devblogs.microsoft.com/foundry/agent-service-build2026/)
- [Microsoft Agent Framework Overview](https://learn.microsoft.com/en-us/agent-framework/overview/)
- [MAF at Build 2026(Agent Harness / Hosted Agents / CodeAct)](https://devblogs.microsoft.com/agent-framework/microsoft-agent-framework-at-build-2026-announce/)
- [What is Foundry IQ?(公式)](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/what-is-foundry-iq) / [Foundry IQ 発表記事](https://devblogs.microsoft.com/foundry/build-smarter-agents-faster-with-foundry-iq/)
- [LangGraph ドキュメント](https://langchain-ai.github.io/langgraph/)
- [LangGraph vs MAF 比較(HackerNoon)](https://hackernoon.com/langgraph-vs-microsoft-agent-framework-the-real-difference-is-state)

## 8. マイルストーン

| 時期 | マイルストーン |
|---|---|
| Week 1 末 | 環境構築完了 |
| Week 3 末 | ポータル境界レポート完成(ポータルで出来ること一覧) |
| Week 6 末 | MAF 版シナリオ実装 + Hosted Agent デプロイ完了 |
| Week 8 末 | LangGraph 版実装 + フレームワーク比較レポート完成 |
| Week 10 末 | **技術選定ガイド完成** — 模擬案件で選定判断を書けている状態 |
