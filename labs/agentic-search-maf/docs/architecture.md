# アーキテクチャ

本ツールは「Web を検索して情報を収集し、**自分で品質を判定して足りない情報を取りに行く**」リサーチエージェントである。設計は元リポジトリ `agentic-search-rs` の「強い単一ループ+自己評価」を踏襲し、実行基盤を Microsoft Agent Framework (MAF) の Workflow に載せ替えた。移植の経緯・可否判断は [maf-port-design.md](maf-port-design.md)、MAF API の実装ナレッジは [maf-implementation-notes.md](maf-implementation-notes.md) を参照。

## 採用パターン

| パターン | 実装 |
|---|---|
| Plan-and-Execute | `PlannerExecutor` が質問をサブ質問と検索クエリに分解してから実行する |
| ReAct 型ループ | 検索 → 取得 → 抽出 → 観測を反復する `GathererExecutor` |
| Reflection / Evaluator-Optimizer | `EvaluatorExecutor` が収集結果を批評し、不足分の追加クエリを生成する |
| グラフオーケストレーション | 上記 3 つ + Reporter を MAF Workflow の循環グラフとして接続。LLM の自律性はノード内に閉じ、遷移は決定的なコード |

マルチエージェント化(エージェント間の会話協調)は元設計どおり不採用。ノードは単一の調査ステート(`KnowledgeStore`)を共有する決定的パイプラインであり、協調失敗(MAST)のリスク構造を持たない。

## 処理フロー

```
質問(str)
 │
 ▼
PlannerExecutor ──── 質問を sub_questions + 検索クエリ群に分解(LLM, 構造化出力)
 │  GatherTask(queries, iteration=1)
 ▼
GathererExecutor ─── クエリごとに:
 │                     SearchProvider.search() → 未訪問 URL を選別
 │                     PageFetcher.fetch()     → SSRF ガード + 本文抽出
 │                     extractor Agent         → 出典・日付付き finding 化
 │                     KnowledgeStore          → 正規化文字列で重複排除(新規性判定)
 │  GatherResult(new_findings)
 ▼
EvaluatorExecutor ── findings ダイジェストを LLM が3軸で採点
 │                     freshness   … 今日の日付に対して情報が新しいか
 │                     correctness … finding 間の矛盾・単一ソースの怪しさ
 │                     coverage    … 質問の全側面に答えているか
 │
 ├─ 不足 ──▶ GatherTask(followup_queries, iteration+1) ──▶ GathererExecutor(ループ)
 │
 └─ 充足 / 上限 / 進捗なし ──▶ ReportTask
                                 │
                                 ▼
                          ReporterExecutor ── 引用付き Markdown レポートを合成し、
                                              自己評価スコアと既知の限界を末尾に明記
                                 │  ctx.yield_output(Report)
                                 ▼
                              Report(markdown, evaluation, ...)
```

グラフの分岐はメッセージ型で決まる。`EvaluatorExecutor` が `GatherTask` を送れば Gatherer へ戻り、`ReportTask` を送れば Reporter へ抜ける:

```python
WorkflowBuilder(
    start_executor=planner,
    output_from=[reporter],                              # 最終成果物
    intermediate_output_from=[planner, gatherer, evaluator],  # 進捗イベント
)
.add_edge(planner, gatherer)
.add_edge(gatherer, evaluator)
.add_edge(evaluator, gatherer, condition=lambda m: isinstance(m, GatherTask))
.add_edge(evaluator, reporter, condition=lambda m: isinstance(m, ReportTask))
```

### 終了条件(暴走防止)

1. 評価が `Evaluation.sufficient()`(LLM の `is_sufficient` 判定 + 全軸 70 点以上の二重チェック)
2. `Limits.max_iterations` 到達(既定 4)
3. 追加クエリも新規 finding もない(進捗なしの早期終了)

実行済みクエリ・訪問済み URL は `KnowledgeStore` が記録し、同じ作業を繰り返さない。加えて評価呼び出しの失敗(小型モデルの JSON 崩れ等)はループを打ち切って直近の評価でレポートに進み、レポート合成の失敗は findings ダイジェストの機械整形で代替する——**長時間の収集結果をどの失敗モードでも失わない**のが不変条件。

### 収集フェーズの並列実行とリトライ

1 クエリ内の処理は 3 段(`GathererExecutor._gather_query`):

1. **選択(逐次)**: 検索ヒットから未訪問ページを `max_pages_per_query` 件選び、その場で訪問済みにする。訪問管理とページ上限を決定的に保つため逐次
2. **取得+抽出(並列)**: `asyncio.Semaphore(max_concurrent_pages)` + `asyncio.gather`(入力順を保持)。各タスクは `KnowledgeStore` に触れない純粋関数(`_extract_page`)なのでロック不要
3. **マージ(逐次)**: 重複排除は「先勝ち」なので逐次マージで再現性を保つ

並列度の既定はプロバイダー別(ローカル Ollama=1 / API=4)。クエリ間は逐次のまま(検索 API のレート制限・DuckDuckGo の 429 回避)。取得・LLM 呼び出しは一時障害(タイムアウト・接続断・5xx・429)に対し指数バックオフで `max_retries` 回まで再試行する(`retry.py`)。4xx・SSRF 拒否・パース失敗は再試行しない。

## モジュール構成

```
src/agentic_search_maf/
  workflow.py    エージェント本体(4 エグゼキュータ + グラフ組み立て)。1 回の調査 = 1 ワークフロー
  llm.py         チャットクライアント工場 + 4 ロールの Agent 生成(ChatOptions/response_format)
  schemas.py     構造化出力スキーマ(Plan / Extraction / Evaluation)と寛容パース
  prompts.py     全プロンプトを集約(挙動調整はここだけ触る)
  knowledge.py   KnowledgeStore(重複排除・訪問/クエリ管理・文字数予算付きダイジェスト)
  events.py      進捗イベントのペイロード(Pydantic 判別共用体)+ trace JSONL の読み書き
  search.py      SearchProvider プロトコル + duckduckgo / searxng / serper
  fetch/
    __init__.py  HttpFetcher(手動リダイレクト・サイズ上限・Content-Type 検査)
    guard.py     SSRF ガード(スキーム/ホスト検査 + DNS 解決先の公開性チェック)
    extract.py   HTML→テキスト(Readability + 全 DOM フォールバック)
  config.py      AGS_* 環境変数(Rust 版と同名)。SecretKey は repr でマスク
  errors.py      例外階層 / retry.py 指数バックオフ / json_utils.py 寛容 JSON 抽出
  cli.py         CLI フロントエンド(イベントストリーム消費・trace 出力)
```

### 依存の向き

`workflow.py` は具象プロバイダーを知らず、コンストラクタ注入された `ResearchAgents` / `SearchProvider` / `PageFetcher` / `KnowledgeStore` だけに依存する。逆に `llm.py` / `search.py` / `fetch/` は `workflow.py` を知らない。配線は `cli.py`(フロントエンド)が行う——Rust 版の「core の公開 API(Config → ファクトリ → ResearchAgent)だけを使う」構図と同じ。

`agent_framework` への import は `workflow.py` / `llm.py` / `cli.py` に限定し、knowledge / search / fetch / config / events / schemas はフレームワーク非依存に保っている(最小環境でも import・テスト可能)。

## フロントエンドとの接続

進捗は MAF のイベントストリームで受け取る:

```python
async for event in workflow.run(question, stream=True):
    if event.type == "intermediate":   # PlanReady / QueryStarted / PageProcessed / ...
        ...
    elif event.type == "output":       # Report
        ...
```

ペイロード(`events.py`)は serde 互換の判別共用体で、CLI は `--trace` で JSON Lines として永続化する(Rust 版 GUI の監査トレースと同形式)。「どのクエリを実行し、何を取得し、なぜ追加調査を行ったか」を実行後に追跡できる。

## 拡張ポイント

- **LLM プロバイダー追加**: OpenAI 互換なら `config.py` の `LlmProviderKind` と `llm.build_chat_client` に 1 分岐追加。非互換 API は MAF の `BaseChatClient` を継承
- **検索エンジン追加**: `search.SearchProvider` プロトコルを満たすクラスを実装し `build_provider` に追加
- **取得方法の差し替え**(ヘッドレスブラウザ等): `fetch.PageFetcher` プロトコルを実装
- **フロントエンド追加**: `build_research_workflow` を組み立ててイベントストリームを消費するだけ(CLI が参照実装)

テストではこの 3 つの注入点をすべてフェイクに差し替えている(`tests/test_workflow.py`)。

## 技術選定の補足

| 選定 | 理由 |
|---|---|
| ループを Workflow グラフで表現(素の while でも書けた) | 本ラボの目的が MAF 学習であることに加え、checkpoint(中断再開)・`WorkflowViz`・DevUI 等のグラフ前提機能への足場になる |
| 4 ロールを `Agent` に分離(1 クライアント直叩きでも書けた) | instructions と response_format をロールに固定でき、プロンプトとロジックの分離(prompts.py 集約)が保てる |
| `OpenAIChatClient` 単一クラスで 4 プロバイダー | 1.10 で Azure OpenAI が統合済み。Ollama / Anthropic は OpenAI 互換エンドポイントに乗せ、自作 HTTP クライアントをゼロにする |
| httpx + 手動リダイレクト | httpx にはリダイレクトポリシーのフックがなく、SSRF ガードの「全ホップ再検証」を保つには手動ループが必要 |
| readability-lxml + BeautifulSoup | Rust 版 dom_smoothie(Readability 系)+ scraper と同じ二段構え(本文抽出 → 全 DOM フォールバック) |
| 構造化出力 + 寛容パースの二重化 | プロバイダーが response_format を無視/失敗しても Rust 版と同じプロンプト経路で動く |
