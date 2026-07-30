# trend-analysis — 逐次ワークフロー最小形(Port 1)

元: [`starter_ai_agents/ai_startup_trend_analysis_agent`](https://github.com/Shubhamsaboo/awesome-llm-apps/tree/main/starter_ai_agents/ai_startup_trend_analysis_agent)(Agno + Gemini 2.5 Flash + Streamlit、78行)

## 元の構成(5行)

- Streamlit のボタンハンドラ内で 3 つの Agno `Agent` を**手続き的に直列実行**(news_collector → summary_writer → trend_analyzer)
- news_collector は `DuckDuckGoTools`、summary_writer は `Newspaper4kTools`(記事本文読取)を持つ
- モデルは全役割 Gemini 2.5 Flash(API キーを UI から入力)
- 段間の受け渡しは f-string でプロンプトに前段出力を埋め込むだけ
- エラー処理は try/except 一括、観測性なし

## 移植後の構成

```
topic ──▶ CollectorExecutor ──▶ SummarizerExecutor ──▶ AnalyzerExecutor ──▶ TrendReport
          (search_news tool)     (read_article tool)     (ツールなし)
```

- 3 役割を MAF `Agent`(gpt-5.4-mini on Foundry)にし、直列実行を `WorkflowBuilder` のグラフに昇格
- `DuckDuckGoTools` → 自前 `search_news`(キーレス DDG HTML、agentic-search-maf から移植)/ `Newspaper4kTools` → 自前 `read_article`(httpx + BS4)
- Streamlit → CLI(`uv run trend-analysis-maf "topic" [--json]`)
- トレース: `configure_azure_monitor` + agent-framework 既定計装で App Insights へ(エージェント実行・ツール呼び出しがスパンになる)
- テスト: オフライン 9 件(ScriptedAgent + httpx.MockTransport)+ ライブスモーク(`pytest -m live`)

## 実行

```bash
uv sync --extra dev --extra live
uv run pytest                 # オフライン(ネットワーク不要)
uv run trend-analysis-maf "AI coding agents for enterprises"   # 要 ../../.env
uv run pytest -m live         # ライブスモーク
```

インフラ: 共有基盤のみで動作(`infra/main.bicep` は existing 参照+出力のみ)。

## 検証結果(2026-07-31)

- オフラインテスト 9 passed / ライブスモーク完走(collect 2,407 → summarize 2,329 → analysis 4,398 chars)
- トレース: App Insights に dependencies として着信を確認(確認クエリは下記)

```bash
az monitor app-insights query --app appi-mafports -g rg-maf-ports \
  --analytics-query "dependencies | where timestamp > ago(30m) | summarize count() by name"
```

## 学び(MAF vs 元構成)

1. **手続き直列 → グラフ化のコストはほぼゼロ、得るものは観測性と進捗イベント。**元の 3 行の `run()` 呼び出しは Executor 3 つ+エッジ 2 本になり行数は増えるが、`stream=True` の intermediate イベントで進捗が構造化され、トレースもノード単位で切れる。この規模だと「グラフにする価値は観測性のため」と言い切れる。
2. **Agno のツール同梱文化 vs MAF の「ツールは素の callable」。**`DuckDuckGoTools()` の1行に相当するものが MAF にはなく自前実装(約60行)が要る。ただしクロージャで httpx を束縛すれば `MockTransport` でテスト可能になり、**テスト容易性は自前ツールの方が上**。Foundry の Web search ツール(Agent Service 組み込み)は DPA 対象外・別課金のため既定にしなかった — SI では「検索をどの層で持つか」が契約論点になることを実感できる。
3. **`from __future__ import annotations` とツールスキーマ推論の相性に注意。**アノテーションが文字列化されるため、スキーマ推論やテストは `get_type_hints` 前提で書く必要がある(MAF 1.10 は対応済みだが、テストで `__annotations__` を直接見ると罠)。
4. **トレース配線は2行**(`configure_azure_monitor` + 既定計装)。元アプリに観測性を足す場合の Agno + Langfuse 等の構成より明確に楽で、「Foundry に載せる動機として観測性が最初に効く」という docs/survey の仮説と一致した。
5. **モデル差し替えは設定のみ**(Gemini → gpt-5.4-mini)。プロンプトは原文をほぼ流用して動作。マルチモデル比較は Port 2(mixture_of_agents)で扱う。
