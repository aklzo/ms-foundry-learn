# mixture-of-agents — ファンアウト/ファンイン並列合議(Port 2)

元: [`starter_ai_agents/mixture_of_agents`](https://github.com/Shubhamsaboo/awesome-llm-apps/tree/main/starter_ai_agents/mixture_of_agents)(Together SDK 直書き + Streamlit、103行)

## 元の構成(5行)

- Streamlit UI で Together API キーと質問を入力し、ボタンで実行
- reference_models 4種(Qwen2-72B / Qwen1.5-72B / Mixtral-8x22B / DBRX)へ同一質問を `asyncio.gather` で**並列送信**(temperature 0.7, max_tokens 512)
- アグリゲータ(Mixtral-8x22B)が固定 system prompt で4回答を統合(**回答はカンマ結合しただけ・質問本文はアグリゲータに渡らない**)
- 個別回答は expander、統合回答はストリーミング表示
- エラー処理・観測性なし

## 移植後の構成

```
                ┌─▶ Proposer(analyst)    ─┐
question ──▶ Dispatcher ─▶ Proposer(creative)   ─┼─▶ Aggregator ──▶ MoAResult
                ├─▶ Proposer(skeptic)    ─┤      (list[ProposerReply] を合流)
                └─▶ Proposer(pragmatist) ─┘
```

- `asyncio.gather` の手続き並列を `WorkflowBuilder.add_fan_out_edges`(dispatcher → proposer 4体)+ `add_fan_in_edges`(proposer 4体 → aggregator)のグラフに昇格。fan-in は全 proposer の完了を待って `list[ProposerReply]` を1回だけ配送する(並び順はエッジ定義順=決定的)
- **既定は gpt-5.4-mini ×ペルソナ4体**(analyst / creative / skeptic / pragmatist の self-MoA)。共有基盤に他モデルがないための代替であり、`FOUNDRY_PROPOSER_MODELS=model-a,model-b,...` で「1モデル=1 proposer」の本来のモデル多様性モードに切替(要: 共有基盤への追加モデルデプロイ)。`FOUNDRY_AGGREGATOR_MODEL` で統合モデルも差し替え可
- アグリゲータの system prompt は原文をそのまま移植。ただし user message は「カンマ結合」→「proposer 名ラベル付きセクション+質問本文」に変更(下記・学び4)
- Streamlit → CLI(`uv run mixture-of-agents-maf "question" [--show-proposals] [--json]`)
- トレース: `configure_azure_monitor` + agent-framework 既定計装で App Insights へ(fan-out / fan-in のエッジ配送もスパンになる)
- テスト: オフライン 13 件(ScriptedAgent + バリア同期による並列性の証明)+ ライブスモーク(`pytest -m live`)

## 実行

```bash
uv sync --extra dev --extra live
uv run pytest                 # オフライン(ネットワーク不要)
uv run mixture-of-agents-maf "When should a team choose a monolith over microservices?"   # 要 ../../.env
FOUNDRY_PROPOSER_MODELS=gpt-5.4-mini,phi-4 uv run mixture-of-agents-maf "..."  # モデル多様性モード
uv run pytest -m live         # ライブスモーク
```

インフラ: 共有基盤のみで動作(`infra/main.bicep` は existing 参照+出力のみ)。モデル多様性モードを使う場合の追加モデルデプロイは共有基盤(`infra/shared.bicep`)側の変更。

評価: `tests/eval_dataset.jsonl` は各ケースに `single_vs_aggregate`(proposer 単体と集約後をどう比べるか: 誤情報の抑制・観点カバレッジの和集合・数値不一致の解決・集約が割に合わない対照ケース)を明記。

## 検証結果(2026-07-31)

- オフラインテスト 13 passed(fan-out 全員呼び出し / aggregator プロンプトに全回答 / 進捗イベント / 出力構造 / バリア同期での並列性証明)
- ruff clean / `az bicep build` OK
- ライブスモーク: 完走(2026-07-31)。4 ペルソナ並列(analyst 1,305 / creative 2,724 / pragmatist 1,287 / skeptic 1,630 chars)→ aggregator 統合まで成功
- トレース: App Insights に `invoke_agent` × 5(4 proposer + aggregator)着信確認。確認クエリ:

```bash
az monitor app-insights query --app appi-mafports -g rg-maf-ports \
  --analytics-query "dependencies | where timestamp > ago(30m) | summarize count() by name"
```

## 学び(MAF vs 元構成)

1. **ファンアウト/ファンインは MAF の first-class API。**`add_fan_out_edges` / `add_fan_in_edges` があり、実装(`_workflows/_edge_runner.py`)を読むと FanOutEdgeRunner は対象エッジへ `asyncio.gather` で並列配送、FanInEdgeRunner はソース毎にバッファし**全ソース到着で `list[T]` を1回だけ**ターゲットに配送する。元の `asyncio.gather` 1行と比べ行数は増えるが、「全員待ち」「並び順はエッジ定義順(到着順でない)」がフレームワーク保証になり、オフラインテストで順序を決定的にアサートできた。並列性自体もバリア同期テスト(全 proposer が互いの開始を待つ。逐次実行ならタイムアウト)で証明できる。
2. **MoA の本質はモデル多様性だが、Foundry では「モデルを増やす」= インフラ作業。**Together は1つの API キーで数十モデルを即座に混ぜられるのに対し、Foundry は各モデルを Bicep でデプロイ(capacity 割当・課金単位)してから使う。共有基盤に gpt-5.4-mini しかない制約から既定を「同一モデル×ペルソナ差」(いわゆる self-MoA)にしたが、これは原論文の主張(モデル間多様性が品質向上の源泉)からは弱い代替。SI 観点では、マルチベンダーモデル合議の PoC は Foundry 単体だと立ち上げコストが高く、モデルカタログの serverless デプロイ併用や「そもそも合議が要るか」の見極めが先に来る。
3. **「温度で多様性」はモデル世代で消えた技法。**元アプリは temperature 0.7 に頼るが、gpt-5 系 reasoning モデルは temperature 指定を受け付けない(既定値固定)。そのため多様性の軸を temperature ではなくペルソナ(instructions)差に置き換えた。移植とは API の対応付けだけでなく「多様性の作り方」のような設計技法自体の翻訳が要る、という例。
4. **移植で元コードのバグ級の癖を発見: アグリゲータに質問が渡っていない。**元の user message はカンマ結合した4回答のみで、質問本文は system prompt 内の "the latest user query" という言及だけ。回答同士の境界もカンマで曖昧。移植では「proposer 名ラベル付きセクション+質問本文」に直し、忠実性より正しさを優先した差分として記録した。グラフ化に伴い型付きメッセージ(`ProposerReply`)を定義したことで、この種の「何をアグリゲータに渡すか」が暗黙でなく設計判断として可視化された。
5. **fan-out のソースは単一 executor である必要があり、入口正規化の dispatcher が1ノード増える。**str 入力 → `ProposalRequest` への持ち上げだけの executor だが、グラフモデルではこの「入口の正規化」がトレース上も1ノードとして見える。元コードの暗黙の `main()` より観測しやすい一方、「たった1行の変換に executor 1つ」というオーバーヘッドの感覚は SI での工数見積りに直結する。
