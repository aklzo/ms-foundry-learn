# agentic-search-maf

`agentic-search-rs`(`~/devs/agentic-search-rs` にある Rust 製の自己評価型リサーチエージェント)を **Microsoft Agent Framework (MAF)** で書き直した学習ラボ。

元ツールと同じく、質問を与えるとエージェントが検索クエリを計画し、Web ページを収集・抽出したうえで、**鮮度・正確性・網羅性**を自己評価し、不足があれば追加検索を自律的に行う。最終成果物は出典付きの Markdown レポート。

**「同じ構成を MAF で実現できるか」の検討結果は [docs/maf-port-design.md](docs/maf-port-design.md) を参照。** 結論だけ言うと: コアのエージェントループは MAF の Workflow(循環グラフ)でそのまま実現でき、むしろ Rust 版で手書きしていた基盤(LLM 抽象・イベント配信・構造化出力)の多くがフレームワーク機能に置き換わる。再現できないのは gpui 製 macOS GUI と Rust 固有の非機能特性。

## ドキュメント

| ドキュメント | 内容 |
|---|---|
| [docs/architecture.md](docs/architecture.md) | **アーキテクチャ**(処理フロー・モジュール構成・終了条件・並列実行・拡張ポイント・技術選定) |
| [docs/maf-port-design.md](docs/maf-port-design.md) | Rust 版からの**移植の構成検討**(実現可否マトリクス・できないものと理由・意図的な変更) |
| [docs/maf-implementation-notes.md](docs/maf-implementation-notes.md) | **MAF 実装ナレッジ**(1.10 実測。API 差分の移行表・エラー対処クックブック・テスト戦略) |
| [docs/runbook.md](docs/runbook.md) | **実行ガイド**(オフライン/ローカル LLM/Azure の実行手順と確認観点。人間用 HTML: `docs/runbook.html`) |

## 元リポジトリとの対応

| Rust (agentic-search-rs) | Python (本ラボ) | 置き換え |
|---|---|---|
| `agent/mod.rs` の手書き while ループ | `workflow.py` | MAF Workflow(循環グラフ + 条件エッジ) |
| `llm/` の `LlmClient` trait + 自作 HTTP クライアント×3 | `llm.py` | MAF `OpenAIChatClient`(Responses: openai/azure)/ `OpenAIChatCompletionClient`(Chat Completions: ollama/claude)+ `Agent`×4 ロール |
| `llm/json.rs` の寛容 JSON 抽出 | `json_utils.py` + `response_format` | 構造化出力をネイティブ利用、寛容パースはフォールバックに降格 |
| `events.rs` の `EventSink` コールバック | `events.py` + `yield_output` | Workflow の intermediate output イベント |
| `search/`・`fetch/`(SSRF ガード含む) | `search.py`・`fetch/` | MAF に該当機能なし → 素の Python で忠実移植 |
| `agent/knowledge.rs`・`prompts.rs`・`config.rs`・`retry.rs` | 同名モジュール | ほぼ 1:1 移植 |
| `crates/cli` | `cli.py` | argparse |
| `crates/gui`(gpui / macOS) | **なし** | 移植不可(docs 参照)。代替は DevUI / trace JSONL |

## 必要環境

- Python 3.10+(開発時は 3.13。agent-framework-core **1.10.0** で実装、2026-09-29 に **1.19.0** / agent-framework-openai 1.14.4 / openai 3.20.0 で再検証)
- 既定プロバイダーはローカル [Ollama](https://ollama.com/)(API コストゼロ)。`--provider` で claude / openai / azure に切替可能

## セットアップと実行

```sh
cd labs/agentic-search-maf
uv sync --extra dev          # uv.lock どおりに .venv を作る(Azure をキーなしで使うなら --extra azure も)

# ローカル LLM(既定・無料)
ollama serve
ollama pull llama3.2:3b

# 実行
.venv/bin/agentic-search-maf "調査したい質問" --output report.md --trace report.trace.jsonl

# Azure OpenAI / Microsoft Foundry Models を使う場合
export AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com
export AZURE_OPENAI_API_KEY=...   # 省略すると Entra ID(DefaultAzureCredential。要 --extra azure と az login)
.venv/bin/agentic-search-maf "質問" --provider azure --model <deployment-name>
```

詳細な実行手順と確認観点は [docs/runbook.md](./docs/runbook.md)(人間用 HTML: `docs/runbook.html`)。

環境変数は Rust 版と同名(`AGS_LLM_PROVIDER` / `AGS_LLM_MODEL` / `AGS_SEARCH_PROVIDER` / `AGS_REPORT_LANGUAGE` / `AGS_MAX_CONCURRENT_PAGES` / `AGS_MAX_RETRIES` など)。検索プロバイダーは duckduckgo(既定・キー不要)/ searxng / serper。

## テスト

ネットワーク・LLM 不要で完走する(Rust 版と同じ方針。LLM ロールはスクリプト化したフェイクに差し替え)。

```sh
uv run pytest -q -W error::DeprecationWarning   # 非推奨 API の混入も検知
uv run ruff check . && uv run ruff format --check src/ tests/
```

ワークフローの統合テスト(`tests/test_workflow.py`)は Rust 版 `agent/mod.rs` のテストを移植したもので、「不足→追加検索→充足で終了」のループと「評価者が壊れてもレポートは失われない」フォールバックを実 MAF グラフ上で検証する。

## 構成

```
src/agentic_search_maf/
  workflow.py    エージェント本体: Planner → Gatherer → Evaluator ⇄(ループ)→ Reporter
  llm.py         チャットクライアント工場 + 4 ロールの Agent 生成
  schemas.py     構造化出力スキーマ(Plan / Extraction / Evaluation)+ 寛容パース
  prompts.py     全プロンプト(Rust 版から逐語移植)
  knowledge.py   KnowledgeStore(重複排除・訪問管理・ダイジェスト)
  events.py      進捗イベントのペイロード + trace JSONL(Rust 版と互換)
  search.py      SearchProvider(duckduckgo / searxng / serper)
  fetch/         SSRF ガード・リダイレクト再検証・Readability 抽出
  config.py      AGS_* 環境変数(Rust 版と同名)
  retry.py       指数バックオフ(一時障害のみ再試行)
  cli.py         CLI フロントエンド
```

## 検証結果(2026-09-29 最新化チェック)

オフライン(ネットワーク・LLM 不要)のみ。実 LLM でのエンドツーエンド実行は初版から未実施(ライブ未検証)。

- **依存更新**: agent-framework-core 1.10.0 → **1.19.0**、agent-framework-openai 1.10.0 → **1.14.4**、openai 2.44.0 → **3.20.0**、readability-lxml 0.8.4.1 → 0.9、pytest 9.1.1 / pytest-asyncio 1.4.0 / ruff 0.16.9。`uv.lock` を新規作成(以前は `uv pip install -e` 運用でロックなし)。pyproject の下限を検証版に引き上げ。
- **テスト**: `uv run pytest -W error::DeprecationWarning` → **50 passed**(既存 44 + 新規 `tests/test_llm.py` 6)。ruff check / format clean。MAF 1.10→1.19 の破壊的変更・非推奨警告は本ラボの使用 API(`Agent`・`ChatOptions`・`WorkflowBuilder(start_executor=, output_from=, intermediate_output_from=)`・`run(stream=True)`・`ev.type`)には無し → Workflow 側は**変更不要**。
- **改修 1(不具合修正)**: ollama / claude プロバイダーを `OpenAIChatClient` → `OpenAIChatCompletionClient` に変更。`OpenAIChatClient` は 1.10 の時点から **Responses API** のクライアントで、Anthropic の OpenAI 互換層は Chat Completions しか持たない(`/v1/responses` なし。出典: https://platform.claude.com/docs/en/api/openai-sdk )。初版は実 LLM 未実行だったため潜在していた。Ollama も `response_format` の実績がある Chat Completions 側に寄せた。openai / azure は Responses のまま。
- **改修 2(不具合修正)**: azure プロバイダーで `AZURE_OPENAI_API_KEY` 未設定時に Entra ID(`DefaultAzureCredential`)を明示的に渡すようにした。旧コメントは「MAF が Entra ID を解決する」としていたが、agent-framework-openai はキーも credential もないと `SettingNotFoundError` を投げる(1.14.4 の `_shared.py` で確認)。`azure-identity` は optional extra `azure` に分離。
- **変更不要**: Azure 経路は `<endpoint>/openai/v1/` の Responses API(v1 API は GA、api-version 不要)で現行どおり。既定モデル名は Azure ではデプロイ名を指定する方式のため影響なし。
- **今後の選択肢**: `agent-framework-anthropic` / `agent-framework-ollama`(いずれも 2026-09 時点でベータ)が GA したら、互換エンドポイント経由をネイティブクライアントに置き換えられる(構造化出力の無効化フォールバックが不要になる可能性)。

