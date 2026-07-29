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

## 元リポジトリとの対応

| Rust (agentic-search-rs) | Python (本ラボ) | 置き換え |
|---|---|---|
| `agent/mod.rs` の手書き while ループ | `workflow.py` | MAF Workflow(循環グラフ + 条件エッジ) |
| `llm/` の `LlmClient` trait + 自作 HTTP クライアント×3 | `llm.py` | MAF `OpenAIChatClient` 1 クラス + `Agent`×4 ロール |
| `llm/json.rs` の寛容 JSON 抽出 | `json_utils.py` + `response_format` | 構造化出力をネイティブ利用、寛容パースはフォールバックに降格 |
| `events.rs` の `EventSink` コールバック | `events.py` + `yield_output` | Workflow の intermediate output イベント |
| `search/`・`fetch/`(SSRF ガード含む) | `search.py`・`fetch/` | MAF に該当機能なし → 素の Python で忠実移植 |
| `agent/knowledge.rs`・`prompts.rs`・`config.rs`・`retry.rs` | 同名モジュール | ほぼ 1:1 移植 |
| `crates/cli` | `cli.py` | argparse |
| `crates/gui`(gpui / macOS) | **なし** | 移植不可(docs 参照)。代替は DevUI / trace JSONL |

## 必要環境

- Python 3.10+(開発時は 3.13 / agent-framework-core **1.10.0** で検証)
- 既定プロバイダーはローカル [Ollama](https://ollama.com/)(API コストゼロ)。`--provider` で claude / openai / azure に切替可能

## セットアップと実行

```sh
cd labs/agentic-search-maf
uv venv && uv pip install -e ".[dev]"

# ローカル LLM(既定・無料)
ollama serve
ollama pull llama3.2:3b

# 実行
.venv/bin/agentic-search-maf "調査したい質問" --output report.md --trace report.trace.jsonl

# Azure OpenAI / Microsoft Foundry Models を使う場合
export AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com
export AZURE_OPENAI_API_KEY=...
.venv/bin/agentic-search-maf "質問" --provider azure --model <deployment-name>
```

環境変数は Rust 版と同名(`AGS_LLM_PROVIDER` / `AGS_LLM_MODEL` / `AGS_SEARCH_PROVIDER` / `AGS_REPORT_LANGUAGE` / `AGS_MAX_CONCURRENT_PAGES` / `AGS_MAX_RETRIES` など)。検索プロバイダーは duckduckgo(既定・キー不要)/ searxng / serper。

## テスト

ネットワーク・LLM 不要で完走する(Rust 版と同じ方針。LLM ロールはスクリプト化したフェイクに差し替え)。

```sh
.venv/bin/python -m pytest -q -W error::DeprecationWarning   # 非推奨 API の混入も検知
.venv/bin/ruff check src/ tests/ && .venv/bin/ruff format --check src/ tests/
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
