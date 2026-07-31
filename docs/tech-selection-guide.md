# 技術選定ガイド(実装検証ベース)

> **最終更新:** 2026-07-31 / **版:** 初版(Wave 1 反映)
> **出典の分離:** 本ドキュメントは **labs/ での実装検証から得たナレッジのみ**を集約する。公式ドキュメント調査由来の知見は [docs/survey/](./survey/README.md)(features / architecture / proposal)にあり、混在させない。各主張には検証元(どのラボ/ポートで実証したか)を付す。
> **検証環境:** agent-framework 1.10〜1.13 / azure-ai-projects 2.4 / Microsoft Foundry(Japan East、gpt-5.4-mini)/ 2026-07 時点。フレームワークの進化が速いため、**版が変われば結論も変わりうる**。

## 1. 選定の実証済み判断基準

[learning-plan](./learning-plan.md) の問い「ポータルで足りるか / MAF が必要か / 他 FW を選ぶべきか」に対する、実装で裏が取れた範囲の回答。

### 1-1. handoff / マルチエージェント協調の分水嶺(Port 3・7 で実証)

**「委譲先が仕様で決まるならグラフ、会話の流れで決まるなら handoff 基盤」** — これが最重要の分岐。

- MAF core に first-class handoff は**ない**。`HandoffBuilder` は別パッケージ(agent-framework-orchestrations)で、全結線メッシュ+human-in-loop 既定の**会話型**設計。one-shot パイプラインに使うと「グラフなら決定的に保証される性質(順序・終了)が全部確率的になる」(Port 7 で比較実装して実証)
- 移植して分かった副次的事実: **元アプリの「handoff」の多くは LLM が委譲先を選んでいない固定シーケンス**(AG2 Swarm の AfterWork リング等)。この場合グラフ化で失うものはなく、得るもの(型付き state、テスト可能性、スパン可視化)だけがある
- 逆に「ユーザーとの会話中に、次に誰が話すかを LLM が決める」型(サポートのエスカレーション等)は OpenAI Agents SDK / AG2 / MAF orchestrations が本質的に楽

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
8. **オフラインテスト戦略は Protocol 注入で統一できる**: LLM は `SupportsRun`(`.run()→.text`)、外部サービスはコンストラクタ注入 — ScriptedAgent / MockTransport / fake ストアで **164テストをネットワークなしで回せた**。「エージェントはテストできない」は設計の問題 — 全ポート

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

先行実装: [agentic-search-maf](../labs/agentic-search-maf/)(評価ループ付きリサーチ。Rust からの移植)。

## 4. 未検証領域(次の実験候補)

実装で確かめていないため、本ガイドではまだ語れないもの(Wave 2 候補 → [INVENTORY.md](../labs/maf-ports/INVENTORY.md)):

- **Code Interpreter**(E2B 置換の実際の DX・セッション課金の実測)
- **Voice Live**(リアルタイム音声+状態管理の複合)
- **Foundry IQ**(複数ナレッジソースの agentic retrieval — AI Search 直結との品質差)
- **Routines / ホステッドエージェント**(常時稼働の運用感・スケールゼロの実際)
- **Foundry Agent Service へのデプロイ**(今回は MAF をクライアント実行。hosted agent 化した際の差分 — 特にツール直付け不可・Toolbox 前提の制約)
- ポータル(prompt agents)だけでどこまで組めるかの限界線(コード無しの上限)

## 更新履歴

| 日付 | 内容 |
| --- | --- |
| 2026-07-31 | 初版。Wave 1(7ポート+agentic-search-maf)の実装ナレッジを集約 |
