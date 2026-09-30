# 技術選定ガイド(実装検証ベース)

> **最終更新:** 2026-09-04 / **版:** 第5版(Wave 1+2+3 + 外部案件 v3 / v4 反映)/ 2026-09-26 注記追加(実測内容は書き換えず、公式側の変化で前提が崩れた箇所に「※2026-09-26」を付記: 罠 10・21・22)/ 2026-09-29 全ラボを agent-framework 1.19 / openai 3.20 でオフライン再検証 / 2026-09-30 §7 委任アクセス(Port 15)を追加し同日ライブ検証の結果を反映(版の変化で前提が変わった箇所に「※2026-09-29」を付記: 罠 3・4・10)
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
3. **依存の版ピン3点**: (a) `mcp>=1.24,<2` — agent-framework の上限要求は推移的依存では強制されず、mcp 2.0 が入ると接続時 AttributeError(`InitializeResult.protocolVersion`)。(b) async の azure-search-documents は `aiohttp` が別途必要。(c) `from __future__ import annotations` はツールスキーマ推論・テストに `get_type_hints` 前提を強いる — Port 6・4・1。※2026-09-29: MAF 1.19 でも `mcp<2` は必要(`agent-framework-core[all]` / `-foundry-hosting` 自身が `mcp<2` を宣言。mcp 2.2 で同じ AttributeError を再現 — Port 6・10)。加えて **`agent-framework-foundry` 1.13.1 は `azure-ai-projects<2.7.0` を要求**し、MAF の Foundry 連携と同居させると projects は 2.6.1 止まり(2.7.0 の新機能は入らない)。同パッケージは廃止済みの `azure-ai-inference` も依存に持ち続ける — Port 11
4. **MCP のヘッダー注入**: MAF の `MCPStreamableHTTPTool` の `header_provider` は **call_tool 時のみ**で接続時(initialize / tools/list)に付かない。全リクエスト認証のサーバー(GitHub リモート MCP 等)では `httpx.AsyncClient(headers=...)` を `http_client` に渡す — Port 6。※2026-09-29: この癖は 1.12.1 固有で **1.13.0 で解消**(接続時にも注入)。1.19.0 で**同一オリジンにだけ注入する `static_headers`** が追加され、自前 `http_client` にヘッダーを持たせる方式は MAF の docstring 上「漏洩しうる」扱いになった。Port 6・10 は `static_headers` に移行済み(1.18 以前は未知の引数を黙って捨てるため無認証接続になる — 下限 1.19 が必須。ライブ未検証)
5. **Foundry Memory の意味論**: mem0 の同期 `add` と違い **LRO+debounce(update_delay 既定300秒)**。「書いた直後に読む」は成立しない前提で UX・テストを設計する(`update_delay=0`+`previous_update_id` チェーン+完了待ちで吸収可能)。認証は Entra のみ・API キー不可 — Port 5
6. **reasoning 系モデルは temperature を受け付けない**。「温度で多様性」は死んだ技法 — ペルソナ差し替えで翻訳する(MoA 系の移植で必須)— Port 2
7. **検索をどの層で持つかは契約論点**。Foundry の Web search ツールは DPA 対象外・別課金(survey 側の調査結果)。ラボでは自前 DDG 検索を既定にした — クロージャ+`MockTransport` でテスト可能になる副次メリットもある — Port 1・3・4
8. **Foundry プロジェクトの MI は再デプロイでローテーションしうる**。ARM 制約でロール割り当て名に実行時値を使えないため、id 固定名だと**旧 principal への孤児割り当てが名前一致で温存**され PermissionDenied の温床になる。対策: RBAC を principalId パラメータの第2段テンプレート(roles.bicep)に分離 — Port 9
9. **クラウド評価の権限は3層**: builtin 評価器の `initialization_parameters.deployment_name`(ジャッジ用デプロイ=評価コストは自分持ち)/ プロジェクト MI(Foundry User + OpenAI User)/ **提出ユーザー自身の Foundry User**。エラーは一律 PermissionDenied で actor が分からず、切り分けに時間を溶かす — Port 9
10. **Routines の REST は `?api-version=v1` 必須**(Learn の例に記載なし・欠くと BadRequest)。プレビュー機能はサブ機能ごとにリージョン集合が違う(Routines 8 / Memory 19 / hosted agents 31) — Port 11。※2026-09-26 注記: Routines は 2026-09-24 に GA。use-routines(ms.date 2026-08-27)は `api-version=v1` 必須を本文に明記し、リージョンも「UK West / Switzerland West / Japan West / UAE North / Norway East を除く全リージョン」に拡大(8 リージョン限定は解消)。Python SDK 面は `client.beta.routines` のまま([casebook 02 P-A11](./survey/casebook/02-pitfalls-index.md#b-agent-service-コア))。※2026-09-29: `Foundry-Features: Routines=V1Preview` は現行の REST 仕様から消え(任意ヘッダーの値は `V2Preview`、SDK 2.5.0 以降が自動付与)、Port 11 はヘッダーを外した(ライブ未検証)
11. **Voice Live のリージョンは「機能×モデル×事前デプロイ」の3段で読む**: Japan East は Voice Live 対応だが gpt-realtime 系ネイティブ音声モデル非提供。マネージド提供モデルはデプロイ不要(Bicep 差分ゼロ) — Port 12
12. **middleware の関数形態は `from __future__ import annotations` で型判定が壊れる**(MiddlewareException)。デコレータ明示(`@function_middleware` 等)が必須 — 罠3(c)の middleware 版。short-circuit は2方式で意味が別: `context.result` セット=拒否をモデルに見せてループ続行 / `MiddlewareTermination`=全停止 — Port 14
13. **オフラインテスト戦略は Protocol 注入で統一できる**: LLM は `SupportsRun`(`.run()→.text`)、外部サービスはコンストラクタ注入 — ScriptedAgent / MockTransport / fake ストアで **約470テストをネットワークなしで回せた**(14ポート合計)。「エージェントはテストできない」は設計の問題 — 全ポート。※2026-09-29: 依存を最新化(agent-framework 1.19 / openai 3.20)した時点の 14 ポート合計は **544 件 passed**(+hosting extra 込みで 1 件。いずれもネットワーク不要)

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
- **閉域 × VNet 注入つき hosted agent の構築**(外部案件では注入なしでの失敗を実証したのみ。§6-16)

## 5. 外部案件検証からの追記(foundry-servicenow-helpdesk、2026-08-05)

社内ヘルプデスク案件(別リポジトリ)の Azure 実環境検証で得た、labs 未収録の実証
ナレッジ。出典は同リポジトリの docs/v2/reports/(精度・非機能・コスト)。
foundry-probes(01/02/08)の発見とは独立検証で一致を確認済み。

1. **gpt-5-mini は実質 reasoning 系挙動**(定量実測)。同一プロンプトで出力トークンの
   約 7 割が推論トークン(平均出力 1,612 中 1,109)、回答 p50 10.5 秒。gpt-5.4-mini は
   推論 0・出力 239・p50 3.0 秒、gpt-5.6-luna は軽量適応推論(≈50)・p50 3.2 秒。
   **「mini 級 = 軽量」の前提は gpt-5-mini には当てはまらない**。チャット UX の既定
   モデルには 5.4 系 / 5.6-luna が適する
2. **リタイア間隔はモデル系列で 12〜18 か月に割れる**(Models API `deprecation.inference`
   実測)。gpt-5.4 系・5.6-sol/terra = 12 か月、gpt-5-mini・5.6-luna = 18 か月。
   提案の温度感は「リリースから 18 か月・安全側の計画は 12 か月」で置く(survey
   features/02 に反映済み)
3. **azure-ai-evaluation SDK は gpt-5 系ジャッジで動作しない**(内部 prompty が
   `max_tokens` を送り 400 `unsupported_parameter`)。classic 隔離の survey 知見の
   具体的な壊れ方。**代替の evals API(`client.evals` + `builtin.groundedness`)は
   gpt-5 系ジャッジで動作し、file_content の一括投入でバッチ採点できる**ことを実証
4. Bicep でのプロジェクト作成は `allowProjectManagement: true` が必須(欠くと
   `Project can only created under AIServices Kind account ...` で失敗)。Terraform の
   `project_management_enabled` と同じ要件
5. ACA(Container Apps)からの参考実測: フォームターン(LLM 3 呼び出し)E2E p50
   11.1 秒(gpt-5-mini)、scale-to-zero のコールドスタートは 44.8 秒で 60 秒
   タイムアウトに接近 — minReplicas=1 か高速モデルへの切替が必要

## 6. 外部案件検証からの追記 第 2 弾(foundry-servicenow-helpdesk v4、2026-08-30)

同案件で hosted agent + Conversations(standard setup / BYO)の対案(v4)を構築し、公開環境と閉域 Lv3 の
2 ラウンドで実測した。判断の変遷(フル活用 → 意図的撤退 → hosted agent 再挑戦)と全実測は
[casebook 03](./survey/casebook/03-case-helpdesk.md)、詰まりどころとしての索引は
[casebook 02](./survey/casebook/02-pitfalls-index.md)。ここでは §2 の続きとして実装ナレッジの要点のみ。

14. **エージェント面エンドポイント(`/agents/{name}/endpoint/protocols/openai/responses`)は `?api-version=v1`
    必須**(欠くと 400)。プロジェクトの `/openai/v1` 面は逆にクエリを拒否する非対称。罠 10(Routines)と同型 — v4
15. **agent identity の既定アクセスに Conversations の読み取りは含まれない。**履歴フェッチ失敗 → コンテナ内 500。
    Azure AI User + Cognitive Services OpenAI User を第 2 段テンプレートで明示付与。**RBAC 伝播は 15〜45 分規模で
    MI ごとに不均一**(罠 1 の 5〜15 分より長い) — v4
16. **閉域 × hosted agent はアウトバウンド VNet 注入(作成時のみ)が実質必須。**注入なし Lv3 ではコンテナ
    (顧客 VNet 外)が PNA Disabled の自プロジェクト / BYO Search に戻れず「デプロイ成功・実行だけ失敗」になる。
    閉域ツール表の「PE 経由」は注入前提 — v4 ラウンド 2
17. **File Search に素の検索 API はない**(`vector_stores.search` = 全面 404)。モデル内ツール専用で決定的ヒット列に
    写像できない。`.xlsx` / 画像は投入不可。閉域作成アカウントでは vector store 作成自体が 500 — v4
18. **Conversations BYO の実プロビジョニングは 5 コンテナ × autoscale 最大 1,000 RU/s**(アイドル月 6〜7 千円規模)。
    v2 期の「固定 3,000〜5,000 RU/s」より大幅に軽い — v4
19. **hosted agent は cold 12.4 秒 / warm 8.1 秒(provisioning 初回 125 秒・2 回目 45 秒)で keep-warm 不要。**
    ACA scale-to-zero の 44.8 秒(§5 の 5)とは別物 — v4
20. **project → App Insights 接続がないと hosted agent へ接続文字列が注入されず内部ログが消える。**capabilityHost の
    再 PUT は冪等。閉域の Key Vault 参照は PE / DNS 完成後でないと ACA デプロイが失敗(dependsOn 必須) — v4
21. **公式ホスティングライブラリ(`agent-framework-foundry-hosting`)はプレリリース版のみ。**プレリリース不使用の
    顧客制約下では FastAPI で Responses protocol 2.0.0 を自前実装し、`azure-ai-projects`(GA)の
    `create_version_from_code`(zip + REMOTE_BUILD、ACR 不要)でデプロイする構成が成立する — v4。
    ※2026-09-26 注記: MAF 用の `agent-framework-foundry-hosting` は依然プレリリースのみだが、フレームワーク非依存の公式
    プロトコルライブラリ `azure-ai-agentserver-responses` 2.0.0(2026-08-11)/ `-invocations` 1.0.0 / `-core` 2.0.0 は
    PyPI で stable。プレリリース不使用の制約下でも、自前実装の前にこちらが選択肢になる([casebook 02 P-H20](./survey/casebook/02-pitfalls-index.md#a-hosted-agent))
22. **`openai` SDK 3.x は `httpx2`(改名フォーク)を使い `respx` でモック不能** → `openai<3` にピン
    (azure-ai-projects と両立) — v4。※2026-09-26 注記: 両立は `azure-ai-projects` 2.4.x まで。2.5.0(2026-08-20)以降は
    `openai>=3.0.0` 必須([casebook 02 P-F12・F14](./survey/casebook/02-pitfalls-index.md#i-maf-とフレームワーク))
23. **同一データセットで v3 脳(自前 function calling on ACA)vs v4 脳(hosted agent)を比較し品質劣化なし**
    (retrieval hit@3 0.708 → 0.667 は誤差域、unanswerable は 0.0 → 0.2 に改善)。載せ替え判断は評価ハーネスが
    あれば 1 日で決まる — v4

## 7. 委任アクセス(利用者の権限でエージェントを動かす)— Port 15、2026-09-30

[labs/maf-ports/ports/delegated-access-hosted](../labs/maf-ports/ports/delegated-access-hosted/README.md)。hosted agent × アプリ管理の OBO(2026-09-28 公開の公式手順)で、社内文書(AI Search のセキュリティフィルター)と基幹 API(MCP)への操作を利用者のロールで変える。最終判定点を **APIM(方式 A)** と **MCP サーバー自身(方式 B)** の両方で実装して比較した。オフライン検証(239 テスト)と SDK ソースの確認に加え、**2026-09-30 にライブ検証済み**(japaneast・gpt-5.4-mini・新規テスト用ユーザー 2 人 × 方式 A / B。検証後に Azure・Entra のリソースは全削除)。1〜7 は実装時の知見、8〜11 はライブで分かったこと。

1. **「エージェントの権限 = 利用者の権限」は Foundry の機能ではなく部品間の契約で作る。**Foundry は `x-client-*` の転送と `x-ms-user-identity` による利用者の識別(会話の分離)だけを担い、トークンの取得・同意・更新・再認証・下流の判定はアプリ側に残る。ヘッダー名・スコープ・ロール名の綴りが 1 つずれると例外でなく「権限なし」で黙って動くので、名前を 1 モジュールに集め Bicep・ポリシー・`.env.example` との一致までテストで固定する — Port 15
2. **MAF の `ResponsesHostServer` は利用者ごとの資格情報が要るツールに使えない**(エージェントと MCP ツールを起動時に 1 回だけ接続し、要求ヘッダーをツールへ渡さない)。Agent Server SDK(`azure-ai-agentserver-responses`)のハンドラーで要求ごとに MAF Agent を組む。hosted 化の摩擦は「ツールの出所」(Port 11)に加えて「ツールの資格情報が誰のものか」でも決まる — Port 15
3. **トークンの露出面は 7 か所**(プロンプト・ツール引数・ツール結果・ログ・例外・GenAI メッセージのトレース記録・resilient モードの永続化)。特に **resilient / durable background モードは `client_headers` を復旧用に永続化**し、**GenAI のメッセージ内容のトレース記録は SDK 既定で有効**(ツール結果がミドルウェアより前に span に載る)。前者は起動拒否、後者は `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=false` を既定にした — Port 15
4. **mcp 1.30 + MAF 1.19 では `tools/call` の HTTP 401 / 403 がツール結果にならず、セッションが死んで再接続・再送でハングする。**エージェントの HTTP トランスポートで 401 / 403 を JSON-RPC エラーに写し、403 は「権限がありません」、401 は再認証要求として中間層へ返す(アプリ権限へは切り替えない)— Port 15
5. **ゲートウェイ判定(方式 A)は「バックエンドを APIM 以外から呼べないこと」を別途保証して初めて成立する。**APIM Consumption は VNet も静的 IP も持たないので、共有シークレットのヘッダーで迂回を塞いだ(より強い手段は APIM のマネージド ID トークン、または v2 / Premium + VNet)。APIM は本文を見ないため判定粒度は API(= MCP サーバー)単位 → **MCP サーバーの分け方が権限境界になる**。実務の結論は「入口 A(宛先・スコープ・サーバー単位のロール)+ 中身 B(文書の絞り込み・ドメイン判定・監査)」の併用 — Port 15
6. **リードタイムはコードより管理者作業に出る。**アプリ登録 2 つ・管理者同意 3 件・アプリロール割り当て(Entra)と、`UserIdentityImpersonation/action` を含むカスタムロール(組み込みロールに無い)・Foundry Agent Consumer の割り当て(Azure RBAC)で、顧客側の担当ロールが最低 3 種類に分かれる。セットアップスクリプトを「既定 dry-run で全 Graph / ARM 呼び出しを表示」にして申請書に貼れるようにした — Port 15
7. **一覧の取得コスト:** 利用者に見えている MCP サーバー 1 つにつき、ツール呼び出し前に約 5 要求(疎通確認+MAF の initialize / initialized / ping / tools/list)。経理担当で 1 ターン 15 要求 — APIM Consumption の呼び出し課金とレイテンシに効く — Port 15
8. **権限による出し分けは方式 A / B ともライブで期待どおり、1 問の所要時間に差は出なかった**(A 9.7〜11.9 秒 / B 10.5〜13.7 秒、同じ質問 ×3)。時間はモデルの推論とツール往復が支配し、APIM のホップは誤差に埋もれる → **判定点の選定にレイテンシは効かない**。選定軸は統制の所有者(セキュリティ担当がポリシーを持つか)と判定の粒度(サーバー単位で足りるか)。ポリシー XML(2 段の validate-jwt・on-error の `WWW-Authenticate`・Named Values)も実 APIM で受け付けられた — Port 15
9. **hosted agent のプラットフォーム側トレースは会話全文を記録し、コンテナ側では止められない。**コンテナで `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=false` にしても、`cloud_RoleName == "responsesapi"` の `chat` / `invoke_agent` スパンが `gen_ai.input.messages` / `gen_ai.output.messages` にツール結果まで残し、経理担当にしか見えない文書 ID が App Insights に出た(トークンは 0 件)。公式と突き合わせると、プロジェクトへの App Insights の**接続**が「プラットフォーム側トレースの有効化」と「同じ接続文字列のコンテナへの注入(コンテナのログも自動で同じ先へ)」を同時に起こし、止め方は接続の解除だけ。→ **設計の最初に「中身を残してよいか・誰が読めるか」を決め、App Insights を集約 / 2 つに分離(接続先 = 中身入りで閲覧者を絞る、別の App Insights = コンテナのログで運用)/ 接続しない、から選ぶ**。判断基準は [architecture 09 §3.6](./survey/architecture/09-operations.md#36-トレースに会話の中身を残すかhosted-agent-の選定基準)、ヒアリング項目は proposal 01 の 4-7(casebook P-O12)— Port 15
10. **会話の続きは利用者ごと・agent ごとに分かれる。**`x-ms-user-identity` が違うと他人の response ID は 404、同じ利用者でも別の hosted agent(方式 A ↔ B)で作った ID は 404。中間層はこれを 502 に丸めず「会話が見つからない」として返す。前段ルーターで別の agent に切り替える blue-green は会話を引き継げない前提になる(casebook P-H24)— Port 15。**同じ agent の版更新なら会話は続く**が、応答する版はセッションのコンテナで決まり、起動中(idle_timeout 以内)は旧版のまま・休止明けに現行版へ移る。ロールバックも同じで、旧版はセッションが残る限り `force=true` なしでは削除できない(`force=true` なら同じセッション ID のまま現行版で続き、履歴も `$HOME` も残った)。版の明示固定も休止明けは効かなかった(公式と食い違い)→ 全会話をすぐ移す修正は旧版の `force=true` 削除で行い、新版は旧版の履歴・`$HOME` に後方互換を持たせる([architecture 09 §6.3](./survey/architecture/09-operations.md#63-エージェントのバージョニングとリリース)、casebook P-H25)— foundry-probes probe 10(2026-09-30)
11. **デプロイで踏むもの:** hosted agent の作成にはデプロイ実行者の **Foundry User** が要る(サブスクリプション所有者でも自動では付かず `agents/write` で拒否、反映まで約 5 分 — P-I01)。Foundry アカウント配下のプロジェクトとモデルデプロイを 1 つの Bicep で作ると並列実行で **RequestConflict** になり、再実行でも直らない → `dependsOn` で順序を固定(maf-ports 共有基盤を修正、P-C12)。条件付きアクセスの claims チャレンジと呼び出し中のトークン失効はライブでも未確認(P1 ライセンス・トークン寿命の都合)— Port 15

## 更新履歴

| 日付 | 内容 |
| --- | --- |
| 2026-07-31 | 初版。Wave 1(7ポート+agentic-search-maf)の実装ナレッジを集約 |
| 2026-07-31 | 第2版。Wave 2(5ポート: Code Interpreter / クラウド評価 / Foundry IQ / hosted agent+Routines / Voice Live)の実装ナレッジを追加。ハマりどころを8点→12点に拡充 |
| 2026-07-31 | 第3版。Wave 3(services-agency / governed-agent)を反映。**協調の分水嶺を2軸3値に改訂**(グラフ/相談型 agent-as-tool/担当交代)、middleware の知見を追加、全ポートにアーキテクチャ図を整備 |
| 2026-09-30 | §7 を追加: 委任アクセス(Port 15 delegated-access-hosted。hosted agent × アプリ管理 OBO、判定点 APIM / MCP サーバーの比較)の実装ナレッジ 7 点。オフライン検証のみ(ライブ未検証と明記) |
| 2026-09-30 | §7 にライブ検証の結果 4 点(8〜11: 方式 A / B のレイテンシ差なし、プラットフォーム側トレースの会話全文記録、会話継続の分離、デプロイ時の Foundry User と RequestConflict)を追加 |
| 2026-09-30 | §7 の 10 に、hosted agent の版更新をまたぐ会話の継続(foundry-probes probe 10 の実測)を追記 |
| 2026-09-30 | §7 の 9・10 を選定基準として整理: 9 はトレースの「接続」の仕組み(プラットフォーム側の記録+接続文字列の注入)と 3 案(集約 / 分離 / 接続しない)を architecture 09 §3.6・proposal 01 の 4-7 に接続、10 は版更新・agent 切り替えをまたぐ会話の扱いを追記 |
| 2026-09-26 | 注記のみ追加(本文の実測は不変): 罠 10(Routines GA・リージョン拡大・`api-version=v1` の Learn 明記)、罠 21(公式プロトコルライブラリ `azure-ai-agentserver-*` の stable 化)、罠 22(`azure-ai-projects` 2.5.0 以降は `openai>=3` 必須) |
| 2026-09-04 | 第5版。§6 外部案件検証 第 2 弾(v4: hosted agent + standard setup、公開+閉域 Lv3 の 2 ラウンド)を追加: api-version=v1、agent identity の Conversations 権限、閉域の VNet 注入必須、File Search の検索 API 不在、BYO Cosmos の実 RU、cold start、App Insights 接続、プレリリース lib 回避、SDK ピン、v3 / v4 品質比較。§4 に未検証領域(注入つき hosted agent)を追記。casebook(docs/survey/casebook)を新設 |
| 2026-08-05 | 第4版。§5 外部案件検証(foundry-servicenow-helpdesk)を追加: gpt-5-mini の reasoning 系挙動、リタイア間隔 12〜18 か月の実測、evals API による groundedness バッチ、allowProjectManagement、ACA 実測値 |
