# game-design-team — AG2 Swarm リング型(Port 7)

元: [`agent_teams/ai_game_design_agent_team`](https://github.com/Shubhamsaboo/awesome-llm-apps/tree/main/advanced_ai_agents/multi_agent_apps/agent_teams/ai_game_design_agent_team)(AutoGen/AG2 旧 Swarm API + Streamlit、291 行)

## 元の構成(5行)

- Streamlit フォームで 15 項目(世界観・ジャンル・対象層・予算・メカニクス等)を集めてタスク文を組み、`initiate_swarm_chat(initial_agent=story, agents=[story, gameplay, visuals, tech], max_rounds=13)` で 4 役割の `SwarmAgent` を回す
- ハンドオフは **AfterWork リング**: `register_hand_off(AFTER_WORK(next))` ×4(story→gameplay→visuals→tech→story)。加えて各エージェントの `update_*_overview` 関数が `SwarmResult(agent="次", context_variables=...)` を返して**関数呼び出しの戻り値でも制御移譲**する
- 共有状態は **context_variables**(全員が読める dict)。1 周目は各役割が update 関数(**tool_choice で呼び出しを強制**)で 2-3 文の要約を書き込む
- **UPDATE_SYSTEM_MESSAGE** の動的プロンプト: 毎ターン「自分のキーが未記入なら要約指示+関数強制 / 記入済みなら『## X Design』詳細指示+tools 削除+会話履歴を先頭 task 1 件に切り詰め」+記入済み要約一覧を system prompt に差し込む
- 2 周目(詳細)を書き終えた `chat_history[-4:]` を Streamlit 側が story/gameplay/visuals/tech として拾い、expander 表示(**max_rounds=13 はこの添字が成立するよう暗黙に調整された値**: 1 task + 4×(関数呼び出し+関数結果) + 4 詳細 = 13)

なお、コード中で定義される `context_variables = {"story": None, ...}` は `initiate_swarm_chat` に**渡されていない**(dead code)。swarm は空 context で開始し、`.get()` が missing key に None を返すため偶然同じ挙動になる — Port 3 学び 3・Port 4 学び 3 と同じ「宣言と実挙動のズレ」がここにもあった。

## AG2 Swarm → MAF 対応表(本ポートの核心)

| 元(AG2 旧 Swarm API) | 移植後(MAF core) | 備考 |
| --- | --- | --- |
| `initiate_swarm_chat(initial_agent=story, max_rounds=13)` | `WorkflowBuilder(start_executor=story)` + `workflow.run(GameDesignContext(task))` | 開始点は同じ「story から」。停止は回数でなくデータ条件(下記) |
| `register_hand_off(AFTER_WORK(next))` ×4 のリング | `add_edge` ×3 + tech→story の**ループエッジ**(switch-case の Default) | 応答後の無条件遷移 → グラフの明示エッジ |
| `SwarmResult(agent="gameplay_agent", context_variables=...)`(update 関数の戻り値でルーティング) | Executor が `ctx.send_message(updated_context)`(行き先はエッジが決める) | **委譲先は元コードでも全部ハードコード** — LLM は選んでいない(学び 1) |
| `context_variables`(全員が読める可変 dict) | `GameDesignContext.summaries`(型付き dataclass をメッセージとして運ぶ) | LLM の関数呼び出しによる書き込み → Executor の決定的書き込み |
| `update_*_overview` 関数 + `tool_choice` 強制 | 要約フェーズの応答テキストをそのまま回収 | 強制付き関数呼び出しは実質「構造化出力」。MAF では強制装置ごと不要(学び 2) |
| `UPDATE_SYSTEM_MESSAGE(update_system_message_func)` | `prompts.build_summary_prompt / build_section_prompt`(毎 run 組み立て) | system prompt 差し替え機構 → ステートレス実行では只の文字列組み立て(学び 2) |
| フェーズ判定(`agent._context_variables.get(role) is None`) | `RoleExecutor` の同じ判定(`context.summaries[role] is None`) | 判定ロジック自体は 1:1 で移植 |
| 詳細フェーズの履歴切り詰め(`_oai_messages[k][:1]`) | 不要(Agent.run が毎回ステートレス) | 「task+全要約だけ渡す」が既定の動作になる |
| `max_rounds=13`(回数による停止) | switch-case エッジ `Case(all_sections_done → deliver)` | 回数の暗黙調整 → 状態から決まる終了(学び 4) |
| `chat_history[-4:]` の添字拾い(Streamlit 側) | `DeliverExecutor` → `GameDesignDocument.sections`(型付き) | 添字とターン数の暗黙結合が消える(学び 4) |
| `st.sidebar.success('Story overview: ...')` | intermediate イベント `RoleSummaryDone / RoleSectionDone` | CLI が stderr に表示 |
| Streamlit フォーム 15 項目 | `GameSpec`(既定値=ウィジェット初期値)+ CLI フラグ | タスク文の f-string は原文踏襲 |

## 移植後の構成

```
GameDesignContext(task, summaries={}, sections={})
      │
      ▼        1周目: 要約(2-3文)を summaries に書き足す
   story ─▶ gameplay ─▶ visuals ─▶ tech ─┐
      ▲                                   │ switch-case
      └──[Default: サマリー周回中]────────┤
               2周目: '## X Design' を     └─[全セクション完成]─▶ deliver
               sections に書き足す                                  │
                                                                    ▼
                                                          GameDesignDocument
                                                          (4 セクションの企画書)
```

- 4 役割 = 4 `RoleExecutor`(id: story/gameplay/visuals/tech)+ `DeliverExecutor`。リングを 2 周し、1 周目は要約、2 周目は詳細セクションを `GameDesignContext` に書き足して次へ渡す(計 8 エージェントターン。元の max_rounds=13 と同じ実質仕事量)
- 役割ペルソナ(元 system_messages 原文)は `Agent` の静的 instructions、フェーズ指示+要約一覧+タスク文は `prompts.py` が**実行のたびに**組み立てて `Agent.run` に渡す(research-handoff の「handoff 先が受け取るコンテキストをプロンプトで明示する」方式の拡張)。文言は原文踏襲(「You task is write ...」の typo 含む)
- Streamlit → CLI(`uv run game-design-team-maf [--vibe ... --game-type ... --json]`)。既定値は元ウィジェットの初期値
- トレース: `configure_azure_monitor` + agent-framework 既定計装で App Insights へ
- テスト: オフライン 30 件(リング順序・context 蓄積・動的プロンプト・最終成果物・HandoffBuilder 変種の構築)+ ライブスモーク(`pytest -m live`)

## HandoffBuilder 比較(agent-framework-orchestrations)

Port 3 では調査のみで不採用にした `HandoffBuilder` を、今回は**実際に同じ 4 役割で組んだ**(`src/game_design_team_maf/handoff_variant.py` + live 専用の `examples/handoff_builder_variant.py`。`uv sync --extra orchestrations` で導入する core 外の別パッケージ、検証時 1.0.2)。

| 元アプリの機構 | HandoffBuilder での再現 | 主実装(MAF core)での再現 |
| --- | --- | --- |
| AfterWork リング | `add_handoff` ×4 で明示リング(既定は全結線メッシュ)。ただし発火は **LLM が `handoff_to_*` ツールを呼んだときだけ** → 「返答の最後に必ず呼べ」とプロンプトに書く | グラフのエッジ(決定的) |
| context_variables | なし。共有状態は「全結線 broadcast される会話履歴」そのもの | 型付きメッセージ(決定的) |
| UPDATE_SYSTEM_MESSAGE | なし。participants は build 時に clone される静的 Agent。フェーズは「1 回目は要約 / 2 回目は詳細」と instructions に書き **LLM に会話履歴から数えさせる** | Executor が状態から判定(決定的) |
| max_rounds=13 | `with_termination_condition`(会話全文の述語: '## Tech Design' が現れたら終了)+ `with_autonomous_mode()`(既定の human-in-loop を解除) | switch-case のデータ条件(決定的) |

判明した制約(構築テスト `tests/test_handoff_variant.py` で固定):

1. participants は実 `Agent` 限定(clone・ツール注入・middleware 前提)。scripted fake は `TypeError` で弾かれる → **実行のオフラインテストは構造的に不可能**(構築の検証のみ可能)。PORTING.md §4 と両立しないという Port 3 の不採用理由を実物で確認
2. 全参加者に `require_per_service_call_history_persistence=True` が必須(handoff ツールを middleware が short-circuit するため、履歴整合の要件。無いと `build()` が `ValueError`)— ドキュメントより先にエラーメッセージで知るタイプの制約
3. one-shot パイプラインに載せるには「human-in-loop 既定の解除(autonomous mode)」「終了述語の自作」「リング・フェーズ・終了をプロンプトに書き下す」の 3 点が必要で、**主実装ではグラフと Executor が決定的に保証していた性質が全部確率的になる**(LLM がツールを呼び忘れたら autonomous mode の nudge 頼み、フェーズを数え違えたら要約と詳細が崩れる)

## 実行

```bash
uv sync --extra dev --extra live
uv run pytest                 # オフライン(ネットワーク不要・30 件)
uv run game-design-team-maf   # 既定値(Epic fantasy with dragons / RPG / ...)で実行(要 ../../.env)
uv run game-design-team-maf --vibe "Cozy island life" --game-type Simulation \
    --mechanics "Crafting,Exploration" --mood "Peaceful" --depth Medium
uv run game-design-team-maf --json          # 要約+全セクションを JSON で
uv run pytest -m live                       # ライブスモーク

# HandoffBuilder 変種(比較検証・live 専用)
uv sync --extra orchestrations --extra live
uv run python examples/handoff_builder_variant.py
```

インフラ: 共有基盤のみで動作(`infra/main.bicep` は existing 参照+出力のみ)。

## 評価

`tests/eval_dataset.jsonl`(5 ケース)。全ケース共通の期待は「**4 役割全ての観点が最終出力に反映される**」ことで、各ケースはそれに加えて共有 context の効き方を測る: 非戦闘ジャンルで gameplay が既定の戦闘ループを出さないか(要約共有の価値)、予算・期間の制約が tech 以外にも波及するか、1 つの独自要素(筆致コンバット)が 4 役割×2 フェーズを貫通するか。ライブ評価を回す場合は `--json` 出力の `sections` に対し Foundry の Task Adherence / Coherence 評価器を役割ごとに適用すると「どの役割が仕様を落とすか」を切り分けられる。

## 検証結果(2026-07-31)

- オフラインテスト 30 passed(workflow 13 / prompts 7 / spec 3 / agents_build 3 / handoff_variant 構築 4)/ ruff clean / `az bicep build` OK(生成 json は削除)
- ライブスモークとトレース到達確認は未実施(呼び出し元で実施)。確認クエリ:

```bash
az monitor app-insights query --app appi-mafports -g rg-maf-ports \
  --analytics-query "dependencies | where timestamp > ago(30m) | summarize count() by name"
```

## 検証結果(2026-07-31 ライブ)

- オフライン **30 passed**(HandoffBuilder 構築テスト4件は `--extra orchestrations` 導入で有効化)
- ライブスモーク **1 passed(54s)**: 4役割リング+ tech→story ループエッジが実モデルで完走し、4観点入りの企画書を生成
- トレース: `executor.process` が story/gameplay/visuals/tech **各×2**(ループエッジの発火が
  スパン数でそのまま見える)+ deliver ×1、`invoke_agent` ×8 を App Insights で確認

## 学び(MAF vs 元構成)— Wave 1 handoff 系の総括を含む

1. **「Swarm」を名乗る元アプリの handoff は、実は 1 箇所も LLM が委譲先を選んでいない。**`SwarmResult(agent="gameplay_agent")` も `AFTER_WORK(next)` も**ターゲットは全部ハードコード**で、実態は「リングを 2 周する固定シーケンス」。だから MAF の明示グラフに 1:1 で写り、しかも決定的になった。ここで Port 3 と接続すると Wave 1 の handoff 系の総括が書ける: handoff には **(a) 委譲先を LLM が実行時に選ぶ動的 handoff**(Port 3 元アプリの triage、HandoffBuilder の思想)と **(b) 委譲先固定の「演出としての handoff」**(本ポートの AfterWork リング)の 2 種があり、元 FW が同じ「handoff」の語で両方を覆うため区別が見えにくい。(a) は Port 3 でやったように「判断を構造化出力に落として条件エッジで分岐」(委譲先が列挙できる場合)か HandoffBuilder(列挙できない会話の場合)、(b) はただの明示グラフでよい — **SI の技術選定でエージェント構成図を見たら、矢印ごとに「この委譲は LLM の判断が本当に必要か」を最初に問う**。必要な矢印が 1 本もなければ「マルチエージェント handoff 基盤」は要らず、Workflows(グラフ)だけで決定的・テスト可能に組める。本ポートはその実証で、8 ターンの協調全体がネットワークなしで 13 テストに固定できた。
2. **UPDATE_SYSTEM_MESSAGE という複雑装置は、AG2 の「長寿命エージェント+累積会話」モデルの必要悪で、ステートレス実行では消滅する。**元実装は毎ターン (a) system prompt 差し替え、(b) tool_choice で update 関数を強制/解除、(c) `_oai_messages[k][:1]` の履歴切り詰め、と 3 つの内部状態手術をしていた。MAF の `Agent.run` は毎回ステートレスなので、同じことが「context から文字列を組んで渡す」1 つの純関数(prompts.py)になり、単体テストも 7 件で済む。(b) の「引数 story_summary を強制的に呼ばせて回収」は実質**構造化出力の 90 年代的実装**であり、移植では応答テキストをそのまま回収するだけでよかった。(c) はステートレス実行の既定動作そのもの。**「フレームワークの高度な機能」に見えるものが、実は別のフレームワークでは存在しない問題への対症療法**である典型例 — 移植の見積りでは「この機構は相手側で何に対応するか」でなく「相手側でもこの問題は存在するか」を問うべき。
3. **状態を書くのが LLM か框架か — AG2 は「LLM の関数呼び出しが context を書く」、MAF は「Executor が決定的に書く」。**Port 4 の学び 1(LangGraph の共有 dict → 型付きメッセージ)と同型だが、AG2 は一段深く暗黙的で、状態の書き込み自体を LLM のツール実行(update 関数)に委ねる。書き込み内容・タイミングが LLM の挙動に依存するためテストは実質不可能で、しかも本アプリでは tool_choice で強制している=自由裁量は演出に過ぎない。移植では「LLM は文章を作る/框架が状態を書く」に責務分離され、`summaries` の蓄積(gameplay のプロンプトに story の要約が現れる、2 周目は全員が 4 要約を見る)を決定的にアサートできた。おまけに元コードの context_variables 渡し忘れ(dead code)も、型付きにした瞬間に発見された — **可変 dict の共有状態は「渡し忘れても偶然動く」ことを許す**。
4. **回数と添字の暗黙結合(max_rounds=13 + chat_history[-4:])は、データ条件の終了+型付き成果物で構造的に消えた。**13 という数は「1 task + 4×(関数呼び出し+関数結果) + 4 詳細」を数えて逆算した値で、エージェントが 1 回でも想定外のターンを使えば、swarm は静かに途中で止まり Streamlit は**別の役割のメッセージを story として表示する**(エラーにすらならない)。移植では「全セクションが揃ったら deliver へ」という switch-case のデータ条件が終了を決め、成果物は役割名キーの dict なので、ズレは即例外になる。Port 4 の「補正ループはループしない」と同じく、**グラフを書き直す作業が元アプリの暗黙の前提(ここでは『各役割はきっかり 1 ターンで応じる』)を洗い出す** — これが Wave 1 を通じて最も再現性の高かった移植の副産物。
5. **HandoffBuilder に同じ協調を載せる実験は「決定的な性質が確率的になる」ことの実地確認だった。**リング順・フェーズ判定・終了という主実装ではグラフと Executor が保証する性質が、HandoffBuilder では全部プロンプト(「1 回目は要約して handoff_to_* を呼べ、2 回目は詳細を書け」)+ autonomous mode + 終了述語に化ける。しかも participants は実 Agent 限定+`require_per_service_call_history_persistence=True` 必須で、実行のオフラインテストは構造的に組めない(構築のみ 4 件で固定)。Port 3 の「handoff という同じ語が SDK ごとに別のワークロードを指す」の続報として: **HandoffBuilder は『次に誰が話すかが本当に会話次第』な長寿命会話のための道具**であり、固定シーケンスに使うと「LLM がツールを呼び忘れない」ことを祈る羽目になる。逆に固定シーケンス派(MAF core)で動的委譲をやると条件エッジの事前列挙が要る(Port 3 学び 1)。この対称性が Wave 1 handoff 系の結論で、選定基準は一言に圧縮できる — **「委譲先が仕様で決まるならグラフ、会話で決まるなら handoff 基盤」**。
