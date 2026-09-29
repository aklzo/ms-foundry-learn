# agentic-search-maf 実行ガイド

> **対象:** `labs/agentic-search-maf/`(自己評価型リサーチエージェント・パターン: Plan-and-Execute + Reflection ループの MAF Workflow)
> **最終確認:** 2026-09-29 オフライン(50 passed・ruff clean・依存 agent-framework-core 1.19.0 / agent-framework-openai 1.14.4 / openai 3.20.0)/ ライブ: **未実施**(初版から実 LLM でのエンドツーエンド実行はしていない。§5 は手順と期待の形のみ)
> **正は本 Markdown。** 人間用 HTML(同じディレクトリの `runbook.html`)は `python3 labs/tools/build_runbooks.py` で生成する(HTML は直接編集しない)。設計判断と移植の学びは [README](../README.md)・[architecture.md](architecture.md)・[maf-port-design.md](maf-port-design.md)。

## 1. このラボで確かめること

- 質問 1 つから、Planner → Gatherer → Evaluator ⇄(不足なら再収集)→ Reporter の**循環グラフ**が回り、出典付き Markdown レポートと自己評価(freshness / correctness / coverage)が出ること。
- 終了条件が 3 つ(充足 = `is_sufficient` かつ全軸 70 点以上 / `max_iterations` 到達 / 追加クエリも新規 finding もない)で必ず止まり、評価やレポート合成が失敗しても**集めた findings を失わない**こと。
- LLM ロールを `run()` だけのプロトコル(`SupportsRun`)に依存させておくと、MAF のグラフを**ネットワーク・モデルなしで**統合テストできること(`ScriptedAgent` パターンの原型。maf-ports のテスト方針の元になった)。

## 2. 構成

図(`architecture.png`)は本ラボには未作成。処理フローの詳細図は [architecture.md](architecture.md) の「処理フロー」。

```text
質問 ─▶ Planner ─▶ Gatherer ─▶ Evaluator ─(ReportTask)─▶ Reporter ─▶ Report(Markdown)
                      ▲            │
                      └(GatherTask)┘   ← 自己評価で不足なら追加クエリで再収集
進捗: Planner / Gatherer / Evaluator の yield_output → type="intermediate" イベント → CLI 表示と --trace JSONL
```

| コンポーネント | 役割 | 課金 |
| --- | --- | --- |
| MAF Workflow(ローカル、`workflow.py`) | 4 エグゼキュータの循環グラフ。遷移はメッセージ型で決まる決定的コード | なし |
| LLM(`llm.py`、4 ロールの `Agent`) | planner / extractor / evaluator / reporter。既定はローカル Ollama | Ollama: なし / claude・openai・azure: トークン従量 |
| 検索(`search.py`) | duckduckgo(既定・キー不要)/ searxng / serper | serper のみ API 従量 |
| 取得(`fetch/`) | SSRF ガード付き HTTP 取得 + Readability 抽出 | なし |

プロバイダーと MAF クライアントの対応(2026-09-29 以降):

| `--provider` | MAF クライアント | API | 構造化出力 |
| --- | --- | --- | --- |
| `ollama`(既定) | `OpenAIChatCompletionClient` | Chat Completions(`http://localhost:11434/v1`) | `response_format` あり |
| `claude` | `OpenAIChatCompletionClient` | Anthropic の OpenAI 互換層(Chat Completions のみ) | 無効化 → プロンプト + 寛容パース |
| `openai` | `OpenAIChatClient` | Responses API | あり |
| `azure`(別名 `foundry`) | `OpenAIChatClient` | Responses API(`<endpoint>/openai/v1/`) | あり |

## 3. 前提

| 区分 | 必要なもの | 備考 |
| --- | --- | --- |
| ツール | uv(Python は 3.10 以上。開発・検証は 3.13) | オフライン実行はこれだけ |
| ローカル LLM(既定) | [Ollama](https://ollama.com/) + `ollama pull llama3.2:3b` | 無料。小型モデルは JSON 崩れが起きやすい(寛容パースが吸収) |
| Azure(任意) | Azure OpenAI / Foundry リソースとモデルデプロイ(例: gpt-5.4-mini)。本ラボに Bicep はない。maf-ports の共有基盤([shared.bicep](../../maf-ports/infra/shared.bicep))のデプロイを流用できる | トークン従量 |
| 権限(Azure をキーなしで使う場合) | 署名ユーザーに Cognitive Services OpenAI User 相当(リソース)+ `az login` + `uv sync --extra azure` | RBAC 伝播に 5〜15 分 |

環境変数(シェルで export。`.env` は読まない。名前は Rust 版と同じ):

| 変数 | 用途 | 既定 / 取得元 |
| --- | --- | --- |
| `AGS_LLM_PROVIDER` | LLM プロバイダー(`--provider` が優先) | `ollama` |
| `AGS_LLM_MODEL` | モデル名(azure はデプロイ名。`--model` が優先) | ollama: `llama3.2:3b` / claude: `claude-sonnet-5` / openai: `gpt-4o-mini` / azure: なし(必須) |
| `AGS_LLM_BASE_URL` | OpenAI 互換エンドポイントの上書き | ollama: `http://localhost:11434/v1` / claude: `https://api.anthropic.com/v1/` |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | claude / openai 用の API キー | 各社コンソール |
| `AZURE_OPENAI_ENDPOINT` | azure 用。**リソースのルート**(`https://<foundry>.openai.azure.com`)。`/openai/v1` は付けない | shared.bicep 出力 `openaiV1Endpoint` から `/openai/v1` を除いた部分 |
| `AZURE_OPENAI_API_KEY` | azure 用キー。未設定なら Entra ID(`DefaultAzureCredential`) | ポータルの「キーとエンドポイント」 |
| `AGS_SEARCH_PROVIDER` / `AGS_SEARXNG_URL` / `SERPER_API_KEY` | 検索プロバイダー切替 | `duckduckgo` / `http://localhost:8080` / なし |
| `AGS_REPORT_LANGUAGE` | レポートの言語 | `日本語` |
| `AGS_MAX_CONCURRENT_PAGES` / `AGS_MAX_RETRIES` | 1 クエリ内のページ並列度 / 一時障害の再試行回数 | ollama: 1、それ以外: 4 / 2 |

## 4. オフライン実行(Azure 不要・無料)

```bash
cd labs/agentic-search-maf
uv sync --extra dev
uv run pytest -q -W error::DeprecationWarning   # 期待: 50 passed(ネットワーク・LLM 不要。非推奨 API の混入も検知)
uv run ruff check . && uv run ruff format --check src/ tests/   # 期待: All checks passed! / already formatted
```

オフラインテストが固定している主な挙動:

- [ ] 1 回目の評価が不足 → 追加クエリで 2 周目 → 充足で終了し、同一 finding は重複排除される(`test_loop_runs_followup_iteration_then_stops_when_sufficient`。PlanReady 1 回・QueryStarted 2 回・EvaluationDone 2 回)
- [ ] 評価者が壊れた JSON を返してもレポートは出る(`test_evaluator_failure_still_produces_a_report`)
- [ ] 充足判定は `is_sufficient` と全軸 70 点以上の二重チェック(`test_sufficiency_requires_flag_and_scores`)
- [ ] SSRF ガードがループバック・プライベート・メタデータ IP・内部ホスト名・資格情報付き URL を拒否する(`tests/test_guard.py`)
- [ ] 寛容パースがコードフェンス・前後の地の文・壊れた要素混じりの出力から finding を救出する(`tests/test_json_utils.py`・`tests/test_schemas.py`)
- [ ] プロバイダー → クライアントの対応(ollama/claude は Chat Completions、openai/azure は Responses、azure は `/openai/v1/`)(`tests/test_llm.py`)

## 5. ライブ実行(ローカル LLM は無料 / クラウド LLM は課金あり)

### 5.1 準備

```bash
# ローカル LLM(既定)
ollama serve &
ollama pull llama3.2:3b

# Azure を使う場合(本ラボに Bicep はない。既存のモデルデプロイを使う)
export AZURE_OPENAI_ENDPOINT=https://<foundry>.openai.azure.com
export AZURE_OPENAI_API_KEY=...        # 省略時は Entra ID → uv sync --extra dev --extra azure && az login
```

### 5.2 実行

```bash
cd labs/agentic-search-maf
uv run agentic-search-maf "Microsoft Agent Framework の最新リリースで何が変わったか" \
  --output report.md --trace report.trace.jsonl -v

# Azure(Foundry Models)で
uv run agentic-search-maf "質問" --provider azure --model gpt-5.4-mini --max-iterations 2 \
  --output report.md --trace report.trace.jsonl
```

期待される出力の例(stderr。CLI の書式から作った**形の例**で、実測値ではない):

```text
plan ready: 4 queries: MAF release notes, agent-framework-core changelog, ...
searching: MAF release notes
  page https://example.com/... (+3)
iteration 1 done: +9 findings (total 9)
evaluation 1: freshness 80, correctness 75, coverage 55, sufficient=False
searching: <評価者の追加クエリ>
iteration 2 done: +4 findings (total 13)
evaluation 2: freshness 85, correctness 80, coverage 75, sufficient=True
report written to report.md
trace written to report.trace.jsonl
done: 13 findings from 6 sources in 2 iteration(s) | scores: freshness 85, correctness 80, coverage 75
```

`report.md` の末尾には `## Self-assessment`(3 軸のスコア表と Known limitations)が付く。

## 6. 確認観点

| 確認 | # | 観点 | 確認方法 | 期待結果 |
| --- | --- | --- | --- | --- |
| [ ] | 1 | 正常系: レポート生成 | §5.2 を実行し `report.md` を開く | 本文に出典 URL 付きの記述、末尾に `## Self-assessment` の表。stderr 最終行が `done: ... findings from ... sources` |
| [ ] | 2 | 自己評価ループ | stderr の `evaluation N:` 行と `searching:` 行 | `sufficient=False` の後に評価者由来の追加クエリで次の iteration が始まる。`sufficient=True` か `--max-iterations` 到達で止まる |
| [ ] | 3 | 早期終了(進捗なし) | ニッチすぎる質問や `AGS_SEARCH_PROVIDER` の結果が空になる条件で実行し `-v` のログを見る | `no follow-up queries and no new findings; stopping early` が出て、上限前にレポートへ進む |
| [ ] | 4 | 異常系: 小型モデルの JSON 崩れ | `llama3.2:3b` で実行し `-v` ログを確認 | `evaluation failed; writing report with the last successful evaluation` が出てもレポートは出る(`report synthesis failed` 時は「調査結果(自動整形)」の findings 羅列) |
| [ ] | 5 | SSRF ガード | `uv run pytest tests/test_guard.py -q` | 全件 pass(ライブでは内部 URL が検索結果に出ても `skipping page ...` で飛ばされる) |
| [ ] | 6 | プロバイダー切替 | `--provider claude`(要 `ANTHROPIC_API_KEY`)/ `--provider azure` で同じ質問 | claude は構造化出力なし(寛容パース経路)でも完走。azure は `/openai/v1/responses` に届く(401/404 なら §9) |
| [ ] | 7 | 観測: trace JSONL | `head report.trace.jsonl` | 1 行 1 イベント。`plan_ready` → `query_started` → `page_processed` → `iteration_done` → `evaluation_done` の順に並ぶ |
| [ ] | 8 | コスト | クラウド LLM 使用時は `--max-iterations 2` と `AGS_MAX_CONCURRENT_PAGES` を小さくして試す | 1 調査あたりの呼び出し数 ≒ 1(planner)+ ページ数(extractor)+ iteration 数(evaluator)+ 1(reporter) |

## 7. トレース・評価の確認

OpenTelemetry / Application Insights には送っていない(本ラボはローカル CLI で、観測は `--trace` の JSON Lines に一本化)。trace は Rust 版 GUI の監査トレースと同形式。

```bash
# イベント種別ごとの件数
python3 -c "import json,collections,sys; print(collections.Counter(json.loads(l)['type'] for l in open('report.trace.jsonl') if l.strip()))"
```

- 期待: `plan_ready` 1 件、`evaluation_done` = iteration 数、`page_processed` = 処理したページ数。
- 1 行の形: `{"timestamp": "2026-...+09:00", "type": "plan_ready", "queries": [...]}`(時刻 + イベントのフィールドを平坦化)。
- 自己評価の中身は `evaluation_done` 行の `evaluation`(3 軸の score / issues と `followup_queries`)で追える。

## 8. 片付け

- ローカル実行のみなら不要(Ollama を止めるだけ)。
- Azure のモデルデプロイを本ラボ用に作った場合は、使い終わったらリソースグループごと削除する(`az group delete -n <rg> --yes --no-wait`)。maf-ports の共有基盤を流用した場合はそちらの手順に従う。

## 9. トラブルシューティング

| 症状 | 原因 | 対処 |
| --- | --- | --- |
| `ConfigError: provider azure requires AZURE_OPENAI_ENDPOINT` | エンドポイント未設定 | `AZURE_OPENAI_ENDPOINT=https://<foundry>.openai.azure.com` を export |
| azure で 404(URL が `/openai/v1/openai/v1/`) | エンドポイントに `/openai/v1` まで含めた | MAF が `/openai/v1/` を付けるので、リソースのルートだけを渡す |
| `ConfigError: provider azure without AZURE_OPENAI_API_KEY uses Entra ID ...` | キーなし運用で `azure-identity` 未導入 | `uv sync --extra dev --extra azure` と `az login`(または API キーを設定) |
| azure で 401 / PermissionDenied | Entra ID の RBAC 未付与・伝播待ち、またはリソースでキー認証が無効 | ロールを付与して 5〜15 分待つ / キーレスに切り替える |
| `SettingNotFoundError: ... requires a model` | azure でデプロイ名未指定 | `--model <deployment>` か `AGS_LLM_MODEL` |
| claude / ollama で 404 `/v1/responses` | 2026-09-29 より前のコード(Responses クライアントで互換エンドポイントを叩いていた) | 最新の `llm.py`(`OpenAIChatCompletionClient`)を使う |
| Ollama 実行が非常に遅い / タイムアウト | ローカル推論は prefill 律速(タイムアウトは ollama のみ 900 秒) | 小さいモデル・`--max-iterations` を下げる。並列度は 1 のままが速い |
| `query '...' failed: duckduckgo returned HTTP 202`(や 429) | DuckDuckGo のレート制限・ボット判定 | 時間をおく / `AGS_SEARCH_PROVIDER=searxng`(ローカル SearXNG)か `serper` |
| stderr に `ExperimentalWarning: [SKILLS]/[HARNESS]` | MAF の実験的機能の予告 | 無害 |

## 10. 関連・更新履歴

- 設計判断と学び: [README](../README.md) / [architecture.md](architecture.md) / [maf-port-design.md](maf-port-design.md) / [maf-implementation-notes.md](maf-implementation-notes.md)
- 開発者サーフェス(SDK・MAF)の位置づけ: [features/08 開発者サーフェス](../../../docs/survey/features/08-developer-experience.md)
- エージェント自動化ユースケースのアーキ: [architecture/05](../../../docs/survey/architecture/05-usecase-agent-automation.md)

| 日付 | 内容 |
| --- | --- |
| 2026-09-29 | 初版(agent-framework-core 1.10→1.19 / openai 2.x→3.20 に更新、`uv.lock` 新設。ollama/claude を Chat Completions クライアントへ、azure のキーなし時に Entra ID を明示) |
