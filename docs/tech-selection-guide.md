# 技術選定ガイド(実装検証ベース)

> **最終更新:** 2026-07-31 / **版:** 第3版(Wave 1+2+3 反映)
> **出典の分離:** 本ドキュメントは **labs/ での実装検証から得たナレッジのみ**を集約する。公式ドキュメント調査由来の知見は [docs/survey/](./survey/README.md)(features / architecture / proposal)にあり、混在させない。各主張には検証元(どのラボ/ポートで実証したか)を付す。
> **検証環境:** agent-framework 1.10〜1.13 / azure-ai-projects 2.4 / Microsoft Foundry(Japan East、gpt-5.4-mini)/ 2026-07 時点。フレームワークの進化が速いため、**版が変われば結論も変わりうる**。

## 1. 選定の実証済み判断基準

[learning-plan](./learning-plan.md) の問い「ポータルで足りるか / MAF が必要か / 他 FW を選ぶべきか」に対する、実装で裏が取れた範囲の回答。

### 1-1. マルチエージェント協調の分水嶺(Port 3・7・13 で実証 — 2軸3値)

協調の選び方は「**制御を誰が決めるか(コード/LLM)**」×「**制御が戻るか(戻る/移る)**」の2軸で整理できる:

| 型 | 制御 | 応答 | MAF での器 | 例 |
| --- | --- | --- | --- | --- |
| **グラフ** | コード(仕様で決まる) | — | Workflow(core のみ) | 直列・並列・分岐・ループ(Port 1-4, 7) |
| **相談型(agent-as-tool)** | LLM が選ぶ | **呼び出し元に戻る** | Agent+動的ツール生成(core のみ) | 通信グラフ制約下の協調(Port 13) |
| **担当交代(handoff)** | LLM が選ぶ | **制御ごと移る** | HandoffBuilder(別パッケージ・会話型) | サポートのエスカレーション等 |

- MAF core に first-class handoff は**ない**。`HandoffBuilder` は別パッケージ(agent-framework-orchestrations)で、全結線メッシュ+human-in-loop 既定の**会話型**設計。one-shot パイプラインに使うと「グラフなら決定的に保証される性質(順序・終了)が全部確率的になる」(Port 7 で比較実装して実証)
- 移植して分かった副次的事実: **元アプリの「handoff」の多くは LLM が委譲先を選んでいない固定シーケンス**(AG2 Swarm の AfterWork リング等)。この場合グラフ化で失うものはなく、得るもの(型付き state、テスト可能性、スパン可視化)だけがある
- 逆に「ユーザーとの会話中に、次に誰が話すかを LLM が決める」型(サポートのエスカレーション等)は OpenAI Agents SDK / AG2 / MAF orchestrations が本質的に楽
- 公式・業界のフレームワーク(AAC 5 パターン、CAF 単一 vs マルチ判断、LangChain 4 型)との対照は [survey/architecture/11 §6](./survey/architecture/11-decision-frameworks.md) 参照(2 軸 3 値と AAC の Routing 軸は同型)

### 1-2. グラフ化の対価は観測性(Port 1・4・7)

手続き的な直列呼び出しを MAF Workflow に「昇格」させるコストはほぼゼロ(Executor+エッジの定型)。見返りは:
- ノード単位のスパン(`executor.process`)、エージェント単位(`invoke_agent`)、ツール単位(`execute_tool`)が**自動で** App Insights に出る
- **ループの発火回数がスパン数でそのまま見える**(Port 7 のリング×2周、Port 4 の文書別採点×6)
- 進捗イベント(intermediate output)が UI/CLI の構造化された進捗表示になる

トレース配線は `configure_azure_monitor(connection_string=...)` の実質2行(Port 1)。**「Foundry に載せる動機は観測性が最初」**という survey 側の仮説は実装でも成立した。

### 1-3. フレームワーク書き換えコストの実測感(全ポート)

| 元 → MAF | 書き換えの実態 | 検証元 |
| --- | --- | --- |
| Agno(手続き直列) | 直訳。Executor 化のみ | Port 1 |
| 素 SDK(gather 並列) | `add_fan_out_edges` / `add_fan_in_edges` が first-class。むしろ堅くなる | Port 2 |
| OpenAI Agents SDK(handoff) | 構造化出力+switch-case で明示化。1行→数十行だがテスト可能に | Port 3 |
| LangGraph(StateGraph) | ノード→Executor、条件エッジ→switch-case、**無型共有 dict→型付きメッセージ**。規律が強制される | Port 4 |
| mem0(記憶) | ストア API の置換は素直。**同期 add→LRO+debounce の意味論差**が本丸 | Port 5 |
| AG2 旧 Swarm | UPDATE_SYSTEM_MESSAGE 等の「長寿命エージェントの必要悪」がステートレス Agent.run では純関数に縮退 | Port 7 |
| DuckDB ローカル分析 | Code Interpreter 置換は「データの行き先と課金対象」の置換。ツールは素の dict がパススルー | Port 8 |
| LangChain ルーター(3DB 振り分け) | 三段カスケード約150行が Foundry IQ の宣言+プロンプトに消滅。ただし可観測性・単体テスト可能性を失う | Port 10 |
| ADK + FastAPI(常時稼働) | hosted agent 化で変わるのは周辺3点(資格情報/観測/HTTP 面)。Routines で cron 配管が不要に | Port 11 |
| Google ADK + Gemini Live | Voice Live は Realtime API 互換+additive 拡張。音声非依存コアの分離が移植とテストの両方に効く | Port 12 |
| Agency Swarm(通信グラフ) | 1行の魔法が20行×3に分解される代わりにテスト可能性を獲得。「戻るか戻らないか」が Workflow に載るかの試金石 | Port 13 |
| ガバナンス層(素SDK 2本) | MAF middleware 3種で再現。short-circuit 2方式(見せて続行/全停止)の選択がガバナンス設計そのもの | Port 14 |

共通パターン: **書き換えで元コードの欠陥が見つかる**(質問本文がアグリゲータに未達 / dead code の context_variables / 「補正ループ」が実は単発 DAG)。型付きグラフへの移植自体がコードレビューとして機能する。

## 2. 実装ナレッジ集(ハマりどころ)

運が悪いと半日〜1日溶ける系。すべて実測。

1. **Bicep 作成の Foundry プロジェクトは MI にモデルのデータプレーン権限が付かない**(ポータル作成は自動付与)。Memory(プレビュー)がストア構成のモデルをプロジェクト MI で呼ぶため 401 ResourceError になる。`Cognitive Services OpenAI User` をプロジェクト/アカウント MI に割り当てる(shared.bicep 参照)。**RBAC 伝播は5〜15分・ノード間で不均一**(片方のプローブが通った後もテストが数分 401 を返した)— Port 5
2. **データプレーンは Bicep の外**。AI Search のインデックス、Memory のストアは ARM で作れず、「Bicep → セットアップスクリプト」の**2段デプロイが定型**。IaC 完結を前提にした見積もりは崩れる — Port 4・5
3. **依存の版ピン3点**: (a) `mcp>=1.24,<2` — agent-framework の上限要求は推移的依存では強制されず、mcp 2.0 が入ると接続時 AttributeError(`InitializeResult.protocolVersion`)。(b) async の azure-search-documents は `aiohttp` が別途必要。(c) `from __future__ import annotations` はツールスキーマ推論・テストに `get_type_hints` 前提を強いる — Port 6・4・1
4. **MCP のヘッダー注入**: MAF の `MCPStreamableHTTPTool` の `header_provider` は **call_tool 時のみ**で接続時(initialize / tools/list)に付かない。全リクエスト認証のサーバー(GitHub リモート MCP 等)では `httpx.AsyncClient(headers=...)` を `http_client` に渡す — Port 6
5. **Foundry Memory の意味論**: mem0 の同期 `add` と違い **LRO+debounce(update_delay 既定300秒)**。「書いた直後に読む」は成立しない前提で UX・テストを設計する(`update_delay=0`+`previous_update_id` チェーン+完了待ちで吸収可能)。認証は Entra のみ・API キー不可 — Port 5
6. **reasoning 系モデルは temperature を受け付けない**。「温度で多様性」は死んだ技法 — ペルソナ差し替えで翻訳する(MoA 系の移植で必須)— Port 2
7. **検索をどの層で持つかは契約論点**。Foundry の Web search ツールは DPA 対象外・別課金(survey 側の調査結果)。ラボでは自前 DDG 検索を既定にした — クロージャ+`MockTransport` でテスト可能になる副次メリットもある — Port 1・3・4
8. **Foundry プロジェクトの MI は再デプロイでローテーションしうる**。ARM 制約でロール割り当て名に実行時値を使えないため、id 固定名だと**旧 principal への孤児割り当てが名前一致で温存**され PermissionDenied の温床になる。対策: RBAC を principalId パラメータの第2段テンプレート(roles.bicep)に分離 — Port 9
9. **クラウド評価の権限は3層**: builtin 評価器の `initialization_parameters.deployment_name`(ジャッジ用デプロイ=評価コストは自分持ち)/ プロジェクト MI(Foundry User + OpenAI User)/ **提出ユーザー自身の Foundry User**。エラーは一律 PermissionDenied で actor が分からず、切り分けに時間を溶かす — Port 9
10. **Routines の REST は `?api-version=v1` 必須**(Learn の例に記載なし・欠くと BadRequest)。プレビュー機能はサブ機能ごとにリージョン集合が違う(Routines 8 / Memory 19 / hosted agents 31) — Port 11
11. **Voice Live のリージョンは「機能×モデル×事前デプロイ」の3段で読む**: Japan East は Voice Live 対応だが gpt-realtime 系ネイティブ音声モデル非提供。マネージド提供モデルはデプロイ不要(Bicep 差分ゼロ) — Port 12
12. **middleware の関数形態は `from __future__ import annotations` で型判定が壊れる**(MiddlewareException)。デコレータ明示(`@function_middleware` 等)が必須 — 罠3(c)の middleware 版。short-circuit は2方式で意味が別: `context.result` セット=拒否をモデルに見せてループ続行 / `MiddlewareTermination`=全停止 — Port 14
13. **オフラインテスト戦略は Protocol 注入で統一できる**: LLM は `SupportsRun`(`.run()→.text`)、外部サービスはコンストラクタ注入 — ScriptedAgent / MockTransport / fake ストアで **約470テストをネットワークなしで回せた**(14ポート合計)。「エージェントはテストできない」は設計の問題 — 全ポート

## 3. パターン別リファレンス(どこを見るか)

| 作りたいもの | 実証済みの型 | コード |
| --- | --- | --- |
| 直列パイプライン | Executor+エッジ、進捗は intermediate output | [trend-analysis](../labs/maf-ports/ports/trend-analysis/) |
| 並列実行+合流 | `add_fan_out_edges` / `add_fan_in_edges`(fan-in はエッジ定義順で決定的) | [mixture-of-agents](../labs/maf-ports/ports/mixture-of-agents/) |
| ルーティング/トリアージ | 構造化出力(Literal ルート)+`add_switch_case_edge_group` | [research-handoff](../labs/maf-ports/ports/research-handoff/) |
| 自己補正 RAG | 採点→分岐→書換→フォールバックのグラフ+AI Search | [corrective-rag](../labs/maf-ports/ports/corrective-rag/) |
| 長期記憶 | `beta.memory_stores`(SDK)+Protocol 注入 | [travel-memory](../labs/maf-ports/ports/travel-memory/) |
| 外部システム連携 | リモート MCP+`http_client` 認証 | [github-mcp](../labs/maf-ports/ports/github-mcp/) |
| 役割リング(旧 Swarm) | 型付き context を運ぶ明示グラフ+ループエッジ | [game-design-team](../labs/maf-ports/ports/game-design-team/) |
| サーバー側コード実行 | `get_code_interpreter_tool` + Files API | [data-analysis-ci](../labs/maf-ports/ports/data-analysis-ci/) |
| 評価駆動の品質ループ | サイクリックグラフ+クラウド評価(evals API) | [critique-loop](../labs/maf-ports/ports/critique-loop/) |
| マルチソース RAG 委譲 | Foundry IQ(KS×N→KB→MCP) | [db-routing-iq](../labs/maf-ports/ports/db-routing-iq/) |
| 常時稼働+スケジュール | hosted agent(ResponsesHostServer)+ Routines | [hn-briefing-hosted](../labs/maf-ports/ports/hn-briefing-hosted/) |
| 音声エージェント | Voice Live(3層分離: コア/テキスト/音声) | [claim-voice-live](../labs/maf-ports/ports/claim-voice-live/) |
| 相談型協調(通信制約) | agent-as-tool(許可ペア分の talk_to_* 動的生成) | [services-agency](../labs/maf-ports/ports/services-agency/) |
| ガバナンス/監査 | middleware(ポリシー割込+信頼ゲート+ハッシュ連鎖監査) | [governed-agent](../labs/maf-ports/ports/governed-agent/) |

先行実装: [agentic-search-maf](../labs/agentic-search-maf/)(評価ループ付きリサーチ。Rust からの移植)。

各ポートの **Azure アイコン付きアーキテクチャ図**(リソース配置・認証・課金注記)は `ports/<port>/docs/architecture.png`(README 冒頭に埋め込み済み。再生成手順は [tools/README.md](../labs/maf-ports/tools/README.md))。

## 4. 未検証領域(次の実験候補)

実装で確かめていないため、本ガイドではまだ語れないもの(Wave 2 候補 → [INVENTORY.md](../labs/maf-ports/INVENTORY.md)):

- ~~Code Interpreter / Voice Live / Foundry IQ / Routines / hosted agent 化~~ → **Wave 2 で検証済み**(上記参照)
- ポータル(prompt agents)だけでどこまで組めるかの限界線(コード無しの上限)
- 音声入出力の実機検証(Wave 2 は WebSocket 接続+ツールループまで。マイク環境が必要)
- Toolbox 経由のツール共有、エージェント向けガードレール(プレビュー)の実運用
- マルチリージョン・高可用構成の実証(現状は単一リージョンのラボ構成)

## 更新履歴

| 日付 | 内容 |
| --- | --- |
| 2026-07-31 | 初版。Wave 1(7ポート+agentic-search-maf)の実装ナレッジを集約 |
| 2026-07-31 | 第2版。Wave 2(5ポート: Code Interpreter / クラウド評価 / Foundry IQ / hosted agent+Routines / Voice Live)の実装ナレッジを追加。ハマりどころを8点→12点に拡充 |
| 2026-07-31 | 第3版。Wave 3(services-agency / governed-agent)を反映。**協調の分水嶺を2軸3値に改訂**(グラフ/相談型 agent-as-tool/担当交代)、middleware の知見を追加、全ポートにアーキテクチャ図を整備 |
