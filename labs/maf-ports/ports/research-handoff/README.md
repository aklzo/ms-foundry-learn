# research-handoff — handoff/トリアージ型(Port 3)

元: [`starter_ai_agents/openai_research_agent`](https://github.com/Shubhamsaboo/awesome-llm-apps/tree/main/starter_ai_agents/openai_research_agent)(OpenAI Agents SDK + Streamlit、331行)

## 元の構成(5行)

- triage_agent(`output_type=ResearchPlan` + `handoffs=[handoff(research), handoff(editor)]`)が計画を立て、**SDK が自動生成する handoff ツール呼び出しで LLM 自身が委譲先を選ぶ**
- research_agent は `WebSearchTool`(OpenAI ホスト実行)+ `save_important_fact`(Streamlit session_state へ保存)で検索・要約(300語以内)
- editor_agent(`output_type=ResearchReport`)は `Runner.run(editor, triage_result.to_input_list())` と**手続きで**呼ばれ、会話履歴全体から長文レポートを生成 — つまり 2 段目の「handoff」は宣言だけで実際は手動実行
- `output_type` と `handoffs` の競合対策として `hasattr(final_output, 'topic')` の fallback あり(handoff 発火時は final_output が ResearchPlan でなくなる)
- UI は Streamlit(進捗・ファクト・レポートのタブ表示)、`trace()` で OpenAI 側トレーシング

## MAF の handoff サポート調査(本ポートの核心)

installed package(agent-framework-core 1.10 / 1.12)を調査した結論:

- **core の `_workflows/` に handoff の first-class API はない**。`grep -ri handoff` でヒットするのはイベント種別 `"handoff_sent"` の定義など参照のみ
- `agent_framework.orchestrations` 名前空間に `HandoffBuilder` / `HandoffAgentExecutor` 等があるが、これは**別パッケージ `agent-framework-orchestrations`(PyPI、調査時点 1.0.1)への lazy re-export** で、未インストールなら ModuleNotFoundError になる
- `HandoffBuilder`(1.0.1 の `_handoff.py`)の実装: 参加者の `Agent` を clone して **合成ツール `handoff_to_<target_id>` を注入**し、`_AutoHandoffMiddleware` がその呼び出しを **short-circuit(実行せず合成結果を返す)** してルーティング信号にする。グラフは全結線(メッシュ)で、アクティブなエージェントが応答を全員に broadcast。**既定は human-in-loop**(handoff しない応答のたびに `request_info` でユーザー入力を要求)で、`with_autonomous_mode` で自律継続に切替。OpenAI Agents SDK の `handoff()` と同じ「LLM がツール呼び出しで委譲先を選ぶ」思想

本ポートで HandoffBuilder を**採用しなかった**理由:

1. 参加者は実 `Agent` インスタンス限定(clone・ツール注入・middleware が前提。protocol 実装の scripted fake は participants にできない)→ **PORTING.md §4 のオフラインテスト必須要件と両立しない**
2. 会話型(human-in-loop / 自律ループ)の semantics が、元アプリの**一発完結パイプライン**(topic → 計画 → 検索 → レポート)には過剰で合わない — 元アプリ自身、2 段目の handoff を手動 `Runner.run` で代替していた
3. core 外の追加依存(1.0.x)になる

代わりに**トリアージの構造化出力(`TriageDecision.handoff_to`)+ core の `add_switch_case_edge_group`(Case / Default)**で表現した。表現力の差は「学び 1」参照。

## 移植後の構成

```
                  ┌─[handoff_to == "research"]─▶ Research ──▶ Editor ─▶ ResearchHandoffResult
topic ─▶ Triage ──┤   (search_web +                (要約+facts を
         (構造化出力)  save_important_fact)          プロンプトで受領)
                  └─[Default("editor" 直行)]──────▶ Editor
```

- 3 役割を MAF `Agent`(gpt-5.4-mini on Foundry)にし、handoff は `TriageDecision`(plan + handoff_to + reason)の構造化出力+ switch-case エッジに置換。editor 直行分岐は元の `handoffs=[research, editor]` の editor 宣言に対応
- 元の `output_type=` は `ChatOptions(response_format=...)` で再現(`ResearchPlan` / `ResearchReport` は元の Pydantic モデルをそのまま移植)。パースは `.value` 優先+lenient JSON 抽出フォールバック(agentic-search-maf から移植)
- `WebSearchTool` → 自前 `search_web`(キーレス DDG。trend-analysis の search.py/tools.py をコピー)/ `save_important_fact` → クロージャ束縛の `FactStore`(session_state という暗黙の共有メモリを型付きストアに置換)
- 元アプリのフォールバック 2 種を踏襲: トリアージのパース失敗 → 既定計画で research 続行 / レポートのパース失敗 → 生テキストをそのまま本文に
- Streamlit → CLI(`uv run research-handoff-maf "topic" [--show-facts] [--json]`)
- トレース: `configure_azure_monitor` + agent-framework 既定計装で App Insights へ(委譲判断は `HandoffDecided` の intermediate イベントにも出す)
- テスト: オフライン 31 件(トリアージ両分岐・handoff 先が受け取るコンテキスト・構造化出力 3 経路・fallback 2 種・ツール・実 Agent 配線)+ ライブスモーク(`pytest -m live`)

## 実行

```bash
uv sync --extra dev --extra live
uv run pytest                 # オフライン(ネットワーク不要)
uv run research-handoff-maf "best affordable espresso machines for a French press upgrader"   # 要 ../../.env
uv run research-handoff-maf --show-facts --json "..." # ファクト含む全出力
uv run pytest -m live         # ライブスモーク
```

インフラ: 共有基盤のみで動作(`infra/main.bicep` は existing 参照+出力のみ)。

評価: `tests/eval_dataset.jsonl` は各ケースに `expected_route`(research / editor)を明記。鮮度依存トピック(価格・規制動向)は research、教科書的知識(TCP/UDP、TPS)は editor が期待値。editor 直行なら幻覚価格が出る「分岐ミスの実害」ケースと、どちらでも書ける境界ケースを含む。

## 検証結果(2026-07-31)

- オフラインテスト 31 passed / ruff clean / `az bicep build` OK(生成 json は削除)
- ライブスモークとトレース到達確認は未実施(呼び出し元で実施)。確認クエリ:

```bash
az monitor app-insights query --app appi-mafports -g rg-maf-ports \
  --analytics-query "dependencies | where timestamp > ago(30m) | summarize count() by name"
```


**ライブスモーク(2026-07-31):** triage→research handoff(理由付き)→ editor 構造化レポート 1,684 語で完走。トレース: `invoke_agent`×3、`execute_tool search_web`×8、`save_important_fact`×5 を App Insights で確認。

## 学び(MAF vs 元構成)

1. **handoff の表現力差 — 「LLM の自由裁量によるツール呼び出し」vs「型付きルーティングデータ+エッジ条件」。**OpenAI Agents SDK の handoff は `handoffs=[handoff(agent)]` の 1 行で、会話履歴の引き継ぎも SDK が暗黙に行う。MAF core で同じことをすると、(a) 委譲判断を構造化出力のフィールドに落とす、(b) エッジ条件で分岐する、(c) handoff 先に渡すコンテキストをプロンプトとして自分で組み立てる、の 3 点が**全部明示的な設計判断になる**。行数は増えるが、「トリアージがなぜそう判断したか(reason)」「handoff 先が何を受け取るか」がデータとして残り、オフラインテストで両分岐・受け渡し内容・fallback を決定的にアサートできた。元 SDK の handoff はこのどれもテストしづらい(LLM の裁量なので)。一方で「会話の途中で任意のタイミングで委譲」のような動的パターンは、条件付きエッジでは事前に列挙した分岐しか書けず、HandoffBuilder(または元 SDK)が本質的に有利。**SI の技術選定では「委譲先が事前に列挙できる業務フローか、列挙できない会話か」が分水嶺**になる。
2. **MAF の first-class handoff は core でなく別パッケージ、しかも「会話型」に振っている。**`agent-framework-orchestrations` の HandoffBuilder は合成ツール+middleware short-circuit という元 SDK と同じ機構だが、既定 human-in-loop・全結線 broadcast・checkpoint 対応と、カスタマーサポート的な**長寿命会話**を主眼に設計されている。元アプリのような一発パイプラインに被せると「request_info で止まる/autonomous mode の turn 制御」など余計な面が付いてくる。「handoff」という同じ語が SDK ごとに別のワークロードを指している好例で、機能名の一致だけで移植先を決めると事故る。
3. **`output_type` と handoff の競合という元アプリのバグ級の癖が、グラフ化で構造的に消えた。**元コードの `hasattr(final_output, 'topic')` fallback は「triage が handoff すると final_output が ResearchPlan でなくなる」ことへの対症療法。移植では計画と委譲判断を 1 つの構造化出力(TriageDecision)に同居させたので競合自体が存在しない。そもそも元アプリの editor 段は宣言上 handoff・実際は手動 `Runner.run` であり、**移植とは「宣言と実挙動のズレを洗い出して本当の制御フローを決め直す作業**だと実感した。
4. **response_format(ネイティブ構造化出力)は Foundry 経由でそのまま効くが、lenient フォールバックは保険として残す価値がある。**`ChatOptions(response_format=PydanticModel)` で `.value` に検証済みインスタンスが入る(agentic-search-maf で実証済みのパターン)。ただしプロバイダ差・散文包み・Literal 逸脱(handoff_to に未知値)があり得るため、`.value` 優先+抽出フォールバック+既定計画 fallback の 3 段構えにし、全経路をオフラインテストで固定した。
5. **Streamlit session_state という「UI がエージェントの記憶を持つ」構造は、そのままでは移植できない。**`save_important_fact` は st.session_state に書き込み、UI がポーリング表示していた。CLI 化では FactStore(クロージャ束縛)+型付きメッセージ(ResearchFindings.facts)+最終結果への同梱に分解した。ツールの副作用が UI 状態に依存するアプリは、見た目の行数以上に移植コストがかかる — SI の見積り観点では「ツールがどこに書き込んでいるか」を最初に確認すべき。
