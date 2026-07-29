# MAF 実装ナレッジ(agent-framework-core 1.10.0 実測)

本ラボの実装中に **実際に踏んだ**つまづき・API の実挙動・エラー対処を記録する。すべて agent-framework-core **1.10.0**(+ agent-framework-openai)で再現確認済み。MAF は 1.0 GA(2026-04)から短期間で表面 API が動いており、Web 上のサンプルやドキュメントが古いことが多い——**実パッケージの signature を正とする**のが大原則。

## 1. パッケージ構成と依存の張り方

- 実体は分割パッケージ。本ラボが使うのは 2 つだけ:
  - `agent-framework-core` … `Agent` / Workflow / `ChatOptions` など全コア
  - `agent-framework-openai` … `OpenAIChatClient`(**Azure OpenAI もこれ**。1.10 で統合済み)
- メタパッケージ `agent-framework` は全コネクタを引き込むので、依存を絞るなら個別指定が良い。
- コネクタは **lazy import**。未インストールのクラスに触ると、必要な pip パッケージ名を教えてくれる:

  ```
  ModuleNotFoundError: The package agent-framework-openai is required to use
  `OpenAIChatClient`. Please use `pip install agent-framework-openai`, ...
  ```

  → エラーメッセージの指示どおり入れれば解決する。`agent_framework.azure` 配下も同様
  (AI Search / Cosmos / Durable Task などが個別パッケージに紐づく)。
- import 時に `ExperimentalWarning: [SKILLS] ... / [HARNESS] ...` が stderr に出る。実験的機能の予告であり無害。テストや CLI のログをフィルタする場合は文字列 `ExperimentalWarning` で除外できる。

## 2. 1.0 系ドキュメントとの API 差分(移行表)

実装開始時に 1.0 GA のドキュメント記憶で書いたコードは、1.10 では以下がすべて壊れた:

| 1.0 系サンプルの書き方 | 1.10 での書き方 |
|---|---|
| `ChatAgent(chat_client=client, instructions=..., response_format=Model)` | `Agent(client, instructions=..., name=..., default_options=ChatOptions(response_format=Model))`(client は第 1 位置引数) |
| `OpenAIChatClient(model_id=...)` | `OpenAIChatClient(model=...)` |
| `AzureOpenAIChatClient(deployment_name=...)` | `OpenAIChatClient(model=<deployment>, azure_endpoint=..., api_key=...)` に統合 |
| `WorkflowBuilder().set_start_executor(planner)` | `WorkflowBuilder(start_executor=planner)`(コンストラクタ引数化) |
| `workflow.run_stream(msg)` | `workflow.run(msg, stream=True)` |
| `from agent_framework import WorkflowOutputEvent` → `isinstance(ev, WorkflowOutputEvent)` | クラスは削除。`ev.type == "output"` で判定(`WorkflowEventType` は文字列 Literal) |
| カスタムイベント: `WorkflowEvent` を継承して `ctx.add_event(...)` | §4 の intermediate output 方式(`emit`/`add_event` の data イベントは非推奨) |

**確認手段**: ドキュメントを探すより `inspect.signature` が速い。

```python
import inspect
from agent_framework import Agent, WorkflowBuilder
print(inspect.signature(Agent.__init__))
print(inspect.signature(WorkflowBuilder.__init__))
```

## 3. Workflow の実装ナレッジ

### 3.1 エグゼキュータと型ルーティング

- `Executor` を継承し `super().__init__(id="...")`、メソッドに `@handler`。**引数の型アノテーションがメッセージルーティングの実体**なので省略不可。
- `WorkflowContext[SendT, YieldT]`: 第 1 型引数が `send_message`(グラフを流れる)、第 2 が `yield_output`(外に出る)。yield 専用なら `WorkflowContext[Never, Report]`(`typing_extensions.Never`)。
- 型引数には `X | Y` の共用体が使える(条件エッジ分岐の要)。

### 3.2 ループ(循環グラフ)と条件エッジ

- グラフに循環を張ってよい。分岐は「送るメッセージの型を変える + エッジ条件で isinstance 判定」が素直:

  ```python
  .add_edge(evaluator, gatherer, condition=lambda m: isinstance(m, GatherTask))
  .add_edge(evaluator, reporter, condition=lambda m: isinstance(m, ReportTask))
  ```

- 反復上限はアプリ側で管理する(本ラボは Evaluator が iteration を数えて打ち切る)。なお `WorkflowBuilder(max_iterations=100)` という superstep 上限が別途あり、無限ループはフレームワーク側でも止まる(`WorkflowConvergenceException`)。
- エグゼキュータのインスタンス属性はループ越しに生きるが、**ワークフローを使い回すと次の実行に漏れる**。本ラボは「1 調査 = 1 ワークフロー」のファクトリ関数(`build_research_workflow`)で回避した。

### 3.3 出力と進捗イベント

- **最終出力**: `output_from=[reporter]` をコンストラクタで明示し、reporter が `ctx.yield_output(report)`。
  - 明示しないと動きはするが DeprecationWarning:
    `WorkflowBuilder built without explicit output_from or intermediate_output_from; ... explicit designation will be required in a future version.`
- **進捗イベント**: `intermediate_output_from=[planner, gatherer, evaluator]` を指定し、各エグゼキュータが `ctx.yield_output(進捗ペイロード)`。ストリームには `type="intermediate"` で流れる。
  - 旧方式 `WorkflowEvent.emit(id, data)` / `ctx.add_event`(`type="data"`)は 1.10 で非推奨:
    `DeprecationWarning: WorkflowEvent.emit() / type='data' are deprecated; use ctx.yield_output() from an intermediate-designated executor.`
- 消費側:

  ```python
  async for ev in workflow.run(question, stream=True):
      if ev.type == "intermediate": ...   # 進捗ペイロード(自前の Pydantic モデル)
      elif ev.type == "output": ...       # 最終成果物
  ```

  非ストリーミングは `result = await workflow.run(question)` → `result.get_outputs()` / `result.get_intermediate_outputs()`。
- 進捗ペイロード自体は任意の型でよい。本ラボは `type` フィールド付き Pydantic 判別共用体にして trace JSONL(監査ログ)と共用している。

## 4. Agent / 構造化出力の実装ナレッジ

- `ChatOptions` は **dict のサブクラス**。属性アクセス(`opts.response_format`)は `AttributeError: 'dict' object has no attribute ...` になる。読みたければ `opts["response_format"]`。
- `AgentResponse` の構造化出力は `.value` プロパティだが、**遅延パースで、失敗すると例外を投げる**(pydantic `ValidationError`、非 JSON なら `ValueError`)。「値がなければ None」ではない:

  ```python
  try:
      value = response.value
  except Exception:
      value = None            # → response.text から寛容パースにフォールバック
  ```

  小型ローカルモデルや response_format を無視するプロバイダー(Anthropic の OpenAI 互換層など)を混ぜるなら、このフォールバックは必須(本ラボの `schemas.parse_structured`)。
- `Agent` はスレッド(会話履歴)を渡さなければ **呼び出しごとにステートレス**。単発補完ロール(planner/評価など)には素のまま使ってよく、同一インスタンスへの並行 `run()` も問題なかった(extractor をページ並列で共有)。
- Ollama / Anthropic 用の `OpenAIChatClient` には `api_key` が必須(SDK 側の要求)。Ollama はダミー文字列で通る。

## 5. エラー対処クックブック

| 症状 | 原因 | 対処 |
|---|---|---|
| `ImportError: cannot import name 'WorkflowOutputEvent'` | 1.10 でクラス削除 | `ev.type == "output"` で判定に書き換え |
| `ModuleNotFoundError: No module named 'agent_framework_openai'` | コネクタ未インストール | メッセージ記載の `pip install agent-framework-openai` |
| `TypeError: ... unexpected keyword argument 'chat_client'`(等) | 1.0 系の呼び出し方 | §2 の移行表 / `inspect.signature` で現行引数を確認 |
| `AttributeError: 'dict' object has no attribute 'response_format'` | `ChatOptions` は dict | 添字アクセスにする |
| `.value` 参照で `ValidationError` / `ValueError` | 構造化出力の遅延パース失敗 | try/except + テキストからのフォールバックパース |
| `DeprecationWarning`(output_from / WorkflowEvent.emit) | 旧 API 使用 | §3.3 の新方式へ。回帰防止に `pytest -W error::DeprecationWarning` |
| stderr に `ExperimentalWarning: [SKILLS]/[HARNESS]` | 実験的機能の予告 | 無害。必要ならログフィルタ |
| ハンドラが呼ばれない / メッセージが流れない | `@handler` 引数の型アノテーション欠落・不一致 | 送信側の型と受信ハンドラの型を一致させる(共用体可) |

## 6. テスト戦略(オフラインで MAF グラフを検証する)

- LLM ロールは `.text` / `.value` を持つオブジェクトを返す `run()` さえあれば差し替え可能(本ラボの `ScriptedAgent`)。`Agent` を直接モックする必要はない——**エグゼキュータをプロトコル(`SupportsRun`)に依存させておく**のが肝。
- ワークフロー統合テストは実グラフを `run(stream=True)` で回し、`intermediate` イベントの個数・`output` の内容まで検証できる(`tests/test_workflow.py`)。ネットワーク・モデル不要で 1 秒未満。
- `pytest.importorskip("agent_framework")` でフレームワーク非依存テストと分離しておくと、最小環境でも大半のテストが走る。
- 回帰防止の実行方法: `pytest -q -W error::DeprecationWarning`(非推奨 API の混入を CI で落とせる)。

## 7. 未検証・今後確認したいこと

- 実 LLM(Ollama / Azure OpenAI)でのエンドツーエンド実行と、Ollama の `response_format`(json_schema)実挙動
- checkpoint(`checkpoint_storage`)による中断再開 — 循環グラフとの組み合わせ
- `WorkflowViz` / DevUI によるグラフ可視化
- Foundry Agent Service(Hosted Agents)へのデプロイ経路(`agent-framework-azure-ai` 系)
