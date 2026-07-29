# agentic-search-rs → MAF 移植の構成検討

作成日: 2026-07-03
対象: `agentic-search-rs`(Rust)を Microsoft Agent Framework(Python, agent-framework-core 1.10.0)で再実装するにあたっての構成判断の記録。

## 1. 結論(先に要点)

**コアのエージェント構成 —「Plan-and-Execute + ReAct 型収集 + Reflection の単一ループ」— は MAF でそのまま実現できる。** それどころか、Rust 版が自前実装していた基盤レイヤー(LLM プロバイダー抽象、構造化出力の強制、進捗イベント配信)は MAF の一級機能に置き換わり、自作コードは大きく減る。

実現**できない**・意図的に**変えた**のは以下(詳細は §4・§5):

| 項目 | 可否 | 理由の要約 |
|---|---|---|
| 計画→収集→自己評価ループ | ✅ 同等 | Workflow の循環グラフ + 条件エッジで表現 |
| LLM プロバイダー抽象(trait) | ✅ 改善 | MAF のチャットクライアント抽象がそのまま該当 |
| JSON 強制 + 寛容パース | ✅ 改善 | `response_format` でネイティブ化、寛容パースはフォールバックに |
| 進捗イベント(EventSink) | ✅ 改善 | Workflow のイベントストリームが標準装備 |
| 検索・取得・SSRF ガード | ✅ 同等(自前) | MAF に該当機能がなく、素の Python で忠実移植 |
| gpui 製 macOS GUI | ❌ 不可 | gpui は Rust ネイティブ UI。MAF は UI 層を持たない |
| Anthropic ネイティブクライアント | ⚠️ 代替 | MAF に公式クライアントなし。OpenAI 互換エンドポイントで代替 |
| 単一バイナリ配布・rustls 等 | ❌ 不可 | 言語ランタイムの差。フレームワークでは埋まらない |

## 2. 元の構成の要約

Rust 版は `docs/agentic-architecture.md` の調査に基づき「強い単一ループ+自己評価」(マルチエージェント化は MAST の知見により見送り)を採用していた:

```
質問 → Planner(分解) → [ Gatherer(検索・取得・抽出) → Evaluator(3軸採点) ]×N → Reporter
                              ↑ 不足なら followup_queries で反復 ┘
```

支える基盤: `LlmClient`/`SearchProvider`/`PageFetcher` の 3 trait、`KnowledgeStore`(重複排除・訪問管理)、`EventSink`(進捗)、SSRF ガード、指数バックオフ、寛容 JSON パース。

## 3. MAF での対応構成

### 3.1 ループ → Workflow(循環グラフ)

MAF の Workflow はエージェント/エグゼキュータを有向グラフに配置し、エッジに条件を付けられる。**グラフに循環(ループ)を張れる**ため、Rust 版の手書き `while` は次のグラフに 1:1 で写る:

```
question ──▶ Planner ──▶ Gatherer ──▶ Evaluator ──▶ Reporter ──▶ Report
                             ▲             │
                             └─(GatherTask)┘   ← 評価不足なら followup クエリでループ
```

- エッジ条件はメッセージ型で分岐: `Evaluator` が `GatherTask` を送れば Gatherer へ戻り、`ReportTask` を送れば Reporter へ抜ける(`add_edge(..., condition=lambda m: isinstance(m, ...))`)。
- 終了条件 3 つ(充足 / `max_iterations` 到達 / 進捗なし)は Evaluator エグゼキュータ内の決定的コードのまま。**LLM の自律性はノード内に閉じ、遷移はコードで統制する**という元設計の意図(=グラフオーケストレーション、agentic-architecture.md §2.3)がフレームワークの一級概念になった形。
- これは「マルチエージェント化」ではない点に注意。ノード間で会話をやり取りする協調ではなく、単一の調査ステートを共有する決定的パイプラインであり、MAST が警告する協調失敗のリスク構造は持ち込んでいない。

### 3.2 LLM ロール → `Agent` × 4 + `response_format`

Rust 版の planner/extractor/evaluator/reporter は「システムプロンプト固定の単発補完」だった。MAF ではそれぞれをステートレスな `Agent`(instructions 固定、スレッド持ち回りなし)にし、Plan/Extraction/Evaluation を Pydantic モデルとして `ChatOptions(response_format=...)` に渡す。

- 対応プロバイダーでは JSON スキーマがサーバー側で強制され、Rust 版 `llm/json.rs` の「プロンプトで JSON を頼み、寛容にパースする」戦略は不要になる。
- ただし **`response.value` はパース失敗時に例外を投げる**(1.10 実測)ため、また `response_format` を無視するプロバイダーもあるため、寛容パース(`json_utils.py`)はフォールバックとして残した。小型ローカルモデル対策という元の設計意図はそのまま。

### 3.3 プロバイダー抽象 → チャットクライアント 1 クラス

Rust 版は trait + 自作 HTTP クライアント 3 実装(約 500 行)。MAF 1.10 では `OpenAIChatClient` が OpenAI / Azure OpenAI(v1 API, `azure_endpoint`)を単一クラスで扱い、Ollama と Anthropic は各社の OpenAI 互換エンドポイントで同じクラスに乗る。結果、`llm.py` は設定→コンストラクタ引数の写像だけになった。

### 3.4 イベント → Workflow の intermediate output

Rust 版の `EventSink`(コールバック型)は、core にイベント基盤がないための自作だった。MAF では:

- 進捗を出すエグゼキュータを `intermediate_output_from=[planner, gatherer, evaluator]` に指定し、`ctx.yield_output(payload)` で発行(1.10 で `WorkflowEvent.emit` / `add_event` 系は非推奨化済み)。
- フロントエンドは `workflow.run(question, stream=True)` のイベントストリームから `type == "intermediate"` を拾う。
- ペイロード(`PlanReady` / `QueryStarted` / `PageProcessed` / `IterationDone` / `EvaluationDone`)と trace JSONL の形式は Rust 版と互換に保った(監査ログの思想を維持)。

### 3.5 MAF が持たないもの → 素の Python で忠実移植

検索プロバイダー、ページ取得、SSRF ガード、Readability 抽出、リトライ、KnowledgeStore は MAF の守備範囲外(ツール/MCP として持ち込む前提)なので、Rust 実装をほぼ逐語移植した。設計上の判断:

- **SSRF ガードのリダイレクト再検証**: `reqwest` はリダイレクトポリシーにフックを差せるが、httpx に相当機能がない。`follow_redirects=False` + 手動ループで各ホップを再検証し、同じセキュリティ特性(公開 URL からプライベートアドレスへのバウンス防止)を保った。
- **並列取得の順序保証**: `futures::buffered`(入力順保持・並列度制限)は `asyncio.Semaphore` + `asyncio.gather`(順序保持)で同等。逐次マージによる「先勝ち」重複排除の再現性も維持。
- **IP 判定**: Rust 版が手で列挙していた非公開レンジ(loopback / private / link-local / CGN 100.64/10 / ULA など)は Python `ipaddress` の `is_global` が同じ集合をカバーする(IPv4-mapped IPv6 のみ手動アンラップ)。

## 4. 実現できないもの・その理由

### 4.1 gpui 製 macOS GUI(`crates/gui`)— 移植不可

- **理由**: gpui は Zed 由来の Rust ネイティブ UI フレームワークで、Python バインディングは存在しない。また MAF は UI 層を提供しない(SDK + ランタイムであって、フロントエンドは守備範囲外)。
- **代替**:
  - MAF の **DevUI**(ローカル開発用 UI)でエージェント/ワークフローの実行・可視化は可能。ただし Rust 版 GUI の「履歴保存・レポート閲覧」に相当する製品機能ではない。
  - 進捗のリアルタイム表示と監査トレースは、本移植では CLI の stderr 出力 + `--trace` の JSONL で代替済み(GUI が担っていた trace 永続化を CLI に昇格)。
  - 本格的な GUI が必要なら Web フロント(FastAPI + SSE でイベントストリームを中継)が自然だが、本ラボの範囲外とした。

### 4.2 Anthropic ネイティブ対応 — 部分的

- **理由**: MAF に Anthropic 公式チャットクライアントがない。
- **代替**: Anthropic の OpenAI SDK 互換エンドポイント(`https://api.anthropic.com/v1/`)を `OpenAIChatClient` で叩く。ただし互換レイヤーは `response_format` を保証しないため、claude プロバイダー選択時は構造化出力を無効化し、プロンプト + 寛容パース(= Rust 版と同じ経路)に自動フォールバックする(`supports_structured_output`)。
- **別案(不採用)**: `BaseChatClient` を継承して Anthropic Messages API クライアントを自作すれば trait 実装追加という Rust 版の拡張ポイントを忠実に再現できるが、学習目的に対しコストが見合わないため見送り。拡張ポイントが存在すること自体は確認済み。

### 4.3 言語・ランタイム由来の非機能特性 — 埋まらない差

フレームワークの構成論とは別軸だが、元ツールの価値の一部だったもの:

- 単一バイナリ配布(`cargo build --release` で完結、rustls により OpenSSL 不要)→ Python は venv + 依存群が必要。
- 型システムによる静的保証(enum の網羅的 match、trait 境界)→ Python では実行時検証 + テストで代替。
- GIL のないネイティブ並行性 → 本ワークロードは I/O バウンドなので asyncio で実用上同等。

## 5. 意図的に変えた点(できるが変えた)

| 変更 | 理由 |
|---|---|
| ループを while からグラフに変換 | MAF の流儀に合わせるのが本ラボの目的。副産物として checkpoint(中断再開)や視覚化(`WorkflowViz`)への足場ができた |
| `azure` プロバイダーを追加 | Foundry 学習リポジトリとして Azure OpenAI / Foundry Models を一級対応にするため |
| trace 出力を CLI に搭載 | Rust 版では GUI のみが trace を書いていた。GUI を落とす代わりに CLI へ移した |
| Claude 既定モデルを claude-sonnet-5 に更新 | 移植時点の現行世代に合わせた(Rust 版は claude-sonnet-4-6) |
| SHA-256 ハッシュによる重複排除を正規化文字列 set に簡略化 | Python では文字列 set が自然で、挙動は同一。ハッシュはメモリ最適化であり意味論ではない |

## 6. 検証状況

- `pytest` 44 件(ネットワーク・LLM 不要)。Rust 版のテストを移植: KnowledgeStore、SSRF ガード、寛容 JSON、DDG パース、本文抽出、trace JSONL 往復、評価充足判定。
- ワークフロー統合テスト 2 件は **実際の MAF グラフ**上でフェイク LLM を走らせ、(a) 不足→追加検索→充足で 2 反復して終了、(b) 評価者が壊れた JSON を返しても収集済み findings がレポートに残る、を検証。進捗イベント(intermediate output)の個数も確認。
- 実 LLM でのエンドツーエンド実行は未実施(Ollama / API キーが必要)。実行手順は README 参照。

## 7. 学び(SI 的な技術選定視点)

- **MAF Workflow は「LangGraph 相当」の位置**。決定的グラフ + 条件エッジ + 循環 + checkpoint という道具立てはほぼ同型で、既に自己評価ループを持つ設計なら移植は素直。フレームワーク選定はループ表現力よりも周辺(ホスティング=Foundry Agent Service、可観測性、组織の Azure 依存度)で決まる。
- **フレームワークが吸収するのは「LLM に触る部分」だけ**。検索・取得・SSRF 対策・重複排除といったドメイン基盤は結局自前であり、移植工数の大半はここだった。エージェントフレームワーク移行の見積もりでは「ハーネス部分は書き直し不要、ツール層は持ち越し」と考えるのが正確。
- **API の変化速度に注意**。学習プラン記載の 1.0 GA(2026-04)から 3 か月で 1.10 になり、`ChatAgent`→`Agent`、`WorkflowBuilder` のコンストラクタ引数化、イベント API の非推奨化など表面が動いた。ドキュメント例より実パッケージの signature を正とする運用が必要。
