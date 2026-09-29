# trend-analysis — 逐次ワークフロー最小形(Port 1)

元: [`starter_ai_agents/ai_startup_trend_analysis_agent`](https://github.com/Shubhamsaboo/awesome-llm-apps/tree/main/starter_ai_agents/ai_startup_trend_analysis_agent)(Agno + Gemini 2.5 Flash + Streamlit、78行)

## 元の構成(5行)

- Streamlit のボタンハンドラ内で 3 つの Agno `Agent` を**手続き的に直列実行**(news_collector → summary_writer → trend_analyzer)
- news_collector は `DuckDuckGoTools`、summary_writer は `Newspaper4kTools`(記事本文読取)を持つ
- モデルは全役割 Gemini 2.5 Flash(API キーを UI から入力)
- 段間の受け渡しは f-string でプロンプトに前段出力を埋め込むだけ
- エラー処理は try/except 一括、観測性なし

## 移植後の構成

![architecture](./docs/architecture.png)

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

詳細な実行手順と確認観点は [docs/runbook.md](./docs/runbook.md)(人間用 HTML: `docs/runbook.html`)。

インフラ: 共有基盤のみで動作(`infra/main.bicep` は existing 参照+出力のみ)。

## 検証結果(2026-09-29 最新化チェック)

- **依存更新**(`uv lock --upgrade`): agent-framework-core 1.12.1 → **1.19.0** / agent-framework-openai 1.11.0 → **1.14.4** / openai 2.51.0 → **3.20.0** / azure-monitor-opentelemetry 1.8.9 → 1.8.10。pyproject の下限を検証版(core>=1.19・openai 連携>=1.14.4・azure-monitor>=1.8.10)に引き上げ
- オフライン **9 passed**(DeprecationWarning なし)/ ruff clean(`uv run ruff check .`。旧図スクリプトの既存指摘は図の v2 化で解消)/ `az bicep build` OK
- 構成図(`docs/architecture.png`)を v2 スタイル(日本語ラベル・処理順バッジ・処理の流れパネル・タグ付き注記)に描き直し、内容を現行実装(core 1.19 / openai 3.x・api-key・スパン名)に合わせた
- **コード改修なし**。追加確認として、実 `Agent` + `OpenAIChatClient` を `/openai/v1/responses` のモック(openai 3.x の HTTP 層 httpx2 の MockTransport)に向けて 3 段+ツール 2 種(search_news / read_article の function_call 往復)をリポジトリ外のスクラッチで完走させ、要求形(`instructions` / `tools` / `function_call_output`)とツールスキーマ推論が 1.19 でも変わらないことを確認。インメモリ OTel で `invoke_agent` ×3・`execute_tool` ×2・`executor.process` ×3・`chat gpt-5.4-mini` ×5・`workflow.run` のスパンが出ることも確認
- 変更不要と判断した点: openai 3.x は HTTP 層が httpx → httpx2 に変わったが、本ポートは OpenAI クライアントに独自 `http_client` を渡しておらず(自前ツールの httpx は別系統)影響なし / v1 エンドポイント(`<resource>.openai.azure.com/openai/v1`、api-version 不要)は現行 docs どおり / gpt-5.4-mini は 2027-09-21 まで GA / MAF 1.14→1.19 の破壊的変更(agent middleware のシーケンス化・`SecretString` の非 str 化・MCP の Cookie 既定など)は本ポートの使用 API に該当なし / Bicep の `accounts@2025-06-01` は公式 00-basic サンプルと同版(新しい GA もあるが使う機能に差がない)
- **ライブ未検証**: openai 3.x 経由の実 Foundry 呼び出しと App Insights 着信(Azure リソース削除済み)。再デプロイ時は [docs/runbook.md](./docs/runbook.md) §5〜§7 で確認する

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
