# hn-briefing-hosted — 常時稼働 HN ブリーフィングの hosted agent 化 + Routines(Port 11)

元: [`always_on_agents/always_on_hn_briefing_agent`](https://github.com/Shubhamsaboo/awesome-llm-apps/tree/main/always_on_agents/always_on_hn_briefing_agent)(Google ADK + FastAPI、約 700 行)

Wave 2 で唯一の「**Foundry に載せる**」実証ポート。これまでの 10 ポートは全部 MAF を**クライアント実行**してきた(tech-selection-guide §4 の未検証領域)。本ポートは同じロジックを **hosted agent** として Foundry Agent Service にデプロイし、**Routines(プレビュー)**で日次スケジュール起動する構成まで作る。

## 元の構成(5行)

- AgentScout: HN を監視して AI エージェント関連の日次エンジニアリングブリーフを生成・配信する「常時稼働」エージェント。ADK Web(対話)と FastAPI(スケジューラ)の 2 面構成
- 収集: `news.ycombinator.com/news` の HTML を `HTMLParser` 100 行でスクレイプ(またはハードコードされた 5 篇のサンプルデータ)
- ランキング: 決定論スコア式(キーワードヒット×16 + min(comments,150)/3 + min(points,500)/10 + max(0, 35−rank))でフィルタ・降順・top_n
- ブリーフ: text/HTML を決定論レンダリング(LLM 不使用)。ADK の `LlmAgent` は `preview_agent_builder_brief` ツールとしてこのパイプラインを呼ぶだけ
- 配信・起動: Cloud Scheduler → FastAPI(`/trigger`・Pub/Sub push)→ Gmail API or webhook。dry_run 既定・資格情報が揃ったときだけ送信

## 本ポートの核心 = 「常時稼働の運用グルー」を全部 Foundry 側へ移す

元アプリが自前で持っていた常時稼働の 3 点セットを、それぞれ Foundry のマネージド機能に置き換える:

| 元(自前の運用グルー) | 移植後(Foundry 側) |
| --- | --- |
| Cloud Run 等に置く FastAPI サーバー(`scheduler_api.py`) | **hosted agent**(コンテナ化・HTTP サーバー・ヘルスチェック・スケールゼロを `ResponsesHostServer` とプラットフォームが持つ) |
| Cloud Scheduler + Pub/Sub push 配管 | **Routine**(schedule トリガー、プロジェクト内のオブジェクト) |
| 認証(OIDC 検証等は元実装では未実装=誰でも叩ける) | agent identity(専用 Entra ID)+ プロジェクト RBAC |
| HTML スクレイパー 100 行 | HN **Algolia API**(キーレス・JSON)+ httpx |
| ADK Web(対話面) | 同じ hosted agent の playground / Responses エンドポイント |
| Gmail / webhook 配信 | **スコープ外**(下記の設計判断) |

二層構成:

1. **ロジック層(MAF・クライアント実行)**: 収集 → 決定論ランキング → LLM ブリーフ生成の直列ワークフロー。CLI で実行でき、全段オフラインテスト可能
2. **ホスティング層(hosting/ + scripts/)**: 同じロジックを Responses protocol で包むエントリポイント+SDK デプロイスクリプト+Routine 作成スクリプト

## 実装前調査の結果(2026-07、Learn ドキュメント+installed package 精読)

### hosted agent のデプロイ方式(quickstart-hosted-agent / concepts/hosted-agents)

- サービスは **GA**(azure-ai-projects 2.3.0〜)。リージョンは 31 で **Japan East を含む** → 共有基盤のままでよい
- デプロイ経路は 5 つ(azd 拡張 `microsoft.foundry` / **Python SDK** / VS Code Foundry Toolkit / Foundry Canvas / Foundry Skill)。本ポートは SDK の **`create_version_from_code`** を採用: zip(**ルートに `main.py` と `requirements.txt` 必須**、パッケージも同梱)+ `HostedAgentDefinition`(cpu/memory + `CodeConfiguration(runtime, entry_point, dependency_resolution=REMOTE_BUILD)` + 環境変数 + `protocol_versions`)を投げ、provisioning をポーリング → `update_details` でエンドポイントをそのバージョンへ向ける(**1 バージョン 100% のみ・トラフィック分割不可**)
- **コンテナプロトコルは responses 2.0.0**(1.0.0 は非推奨で猶予期間後ブロック)。コンテナは :8088 で待ち受け、`POST /responses` を受ける
- 環境変数がコンテナへの唯一の構成手段(バージョンごとに不変)。**App Insights 接続文字列はプラットフォームが自動注入**し、protocol ライブラリが OTel を既定発信 — クライアント実行で書いていた `configure_azure_monitor` の配線が消える
- 課金は推論+**アクティブセッション中の CPU/メモリ**(セッション毎 VM 分離サンドボックス、アイドル 15 分でスケールゼロ、セッション状態は $HOME 永続)

### MAF アプリを hosted agent プロトコルで包む方法(installed package の grep)

- `agent_framework.foundry` 名前空間が **`agent-framework-foundry-hosting`**(PyPI プレリリース `1.0.0b260730`)から `ResponsesHostServer` / `InvocationsHostServer` / `FoundryToolbox` / `FoundrySessionStore` を lazy re-export している
- foundry-samples の `hosted-agents/agent-framework/responses/01-basic` が規約の一次資料: `main.py` で `Agent` を作り `ResponsesHostServer(agent).run()`。モデルは `FoundryChatClient(project_endpoint, model, DefaultAzureCredential())`(= agent identity・キーレス)。`default_options={"store": False}`(履歴はホスティング基盤の conversation ID 管理)
- `ResponsesHostServer` は `WorkflowAgent` も受ける(import に現れる)ため**ワークフローをそのまま載せる選択肢もある**が、本ポートは元 ADK 実装と同型の「関数ツール 1 本持ちエージェント」を採用(下記の設計判断)

### ツール直付け不可の制約の実地判断(タスクの検証項目)

survey features/03 の「hosted agent はエージェント定義にツールを直付けできない(`create_version` の `tools` パラメータは削除済み)→ Toolbox 前提」は、**Foundry 管理ツール**(Code Interpreter / Web Search / MCP 接続等)を定義レベルでアタッチする話。concepts ページの原文は「The platform doesn't inject tools automatically」— つまり**コンテナ内の自前コードが持つツールは制約の対象外**。本ポートのツールは HN Algolia へのキーレス GET 1 本なので、**MAF の関数ツール(エージェント内部の httpx 呼び出し)として実装すれば Toolbox 不要=制約に該当しない**([hosted.py](./src/hn_briefing_maf/hosted.py) の docstring に判断を記録)。Toolbox(MCP エンドポイント+`FoundryToolbox`)が要るのは認証付きの Foundry 管理ツールを hosted から使うときだけ。

### Routines(プレビュー)のリージョンと契約(concepts/routines / how-to/use-routines)

- 対応リージョンは 8 つ: East US / East US 2 / West US / West US 2 / West Central US / North Central US / Sweden Central / **Japan East** — **共有基盤(japaneast)で使える**(タスクの「不可なら代替」分岐は不要だった)
- REST 契約: `PUT {project_endpoint}/routines/{name}`(api-version クエリなし)、全リクエストに **`Foundry-Features: Routines=V1Preview`** ヘッダー、トークンリソースは `https://ai.azure.com`。トリガーは `{"type": "schedule", "cron_expression": ..., "time_zone": ...}`(**最小間隔 5 分**)、アクションは `{"type": "invoke_agent_responses_api", "agent_name": ..., "input": ...}`(1 トリガー+1 アクション固定)。操作は `POST :enable/:disable/:dispatch_async`(手動テストの公開契約は `:dispatch_async` のみ)、履歴は `GET /runs`
- SDK は `client.beta.routines.create_or_update`(azure-ai-projects>=2.2)にもあるが、プレビューの一次契約はヘッダー込みの REST なので REST で実装

## 移植後の構成

```
【ロジック層(CLI・クライアント実行)】
BriefingRequest ─▶ collect(HN Algolia・httpx) ─▶ rank(決定論・元式) ─▶ brief(MAF Agent) ─▶ Brief
                    └ StageDone 進捗イベント(intermediate output)         └ digest を編集した brief_md

【ホスティング層(Foundry)】
Routine(schedule 平日 9:00 JST, Routines=V1Preview)
  └─▶ invoke_agent_responses_api ─▶ hosted agent "hn-briefing-agent"
        hosting/main.py: ResponsesHostServer(Agent(FoundryChatClient(agent identity)))
          └ 関数ツール collect_ranked_stories(コンテナ内 httpx → Algolia → 決定論ランク → digest)
```

- 決定論部分(collect/rank/digest)は両層で**同一のコード**([hn.py](./src/hn_briefing_maf/hn.py) / [ranking.py](./src/hn_briefing_maf/ranking.py) / [briefing.py](./src/hn_briefing_maf/briefing.py))。層で違うのは LLM の呼び方だけ — ワークフローは digest を直接 LLM に渡し、hosted はツール経由で digest を取らせる
- デプロイ zip のステージング・バージョン定義・Routine ペイロードは純関数([hosting_setup.py](./src/hn_briefing_maf/hosting_setup.py) / [routine_setup.py](./src/hn_briefing_maf/routine_setup.py))で組み立ててオフラインテストで固定。HTTP/SDK を貼るのは [hosting/deploy_hosted_agent.py](./hosting/deploy_hosted_agent.py) と [scripts/setup_routine.py](./scripts/setup_routine.py) のみ(db-routing-iq の kb_setup 方針)

## 設計判断

### hosted 面は「ワークフローの直載せ」ではなく「ツール持ちエージェント」

`ResponsesHostServer` は `WorkflowAgent` を受けるのでワークフローをそのまま載せることもできたが、(1) 元 ADK 実装がまさに「LlmAgent + パイプラインツール」の形でその同型移植になる、(2) Responses は会話面なので Routine のプロンプト以外に playground での自由な問いかけ(「top 3 だけ」「MCP の話題ある?」)にも同じ定義で応えられる、(3) `WorkflowAgent` を hosted で使うにはチェックポイントストレージ構成が要る(`_responses.py` が要求)— の 3 点でツール持ちエージェントにした。決定論部分が共有コードなので、二形態の差分は「LLM への渡し方」だけに閉じる。

### HTML スクレイパー → Algolia API(rank は近似になる)

元の `HNFrontPageParser`(100 行)は `tags=front_page` の Algolia 検索 1 本で消える。ただし Algolia は「現在フロントページにある記事」を返すが**表示順位そのものは返さない**ため、`rank`(freshness 項)は応答リスト位置の近似になる。式そのものは元実装と同一で、ゴールデンテスト(元 scout.py を実行して得たスコア値)は元の rank を再現した入力で固定した。

### 配信(Gmail / webhook)はスコープ外

元 delivery.py は Gmail OAuth のリフレッシュトークン運用と任意 webhook への POST。移植の学習目的は「常時稼働の**起動と実行**を Foundry がどう肩代わりするか」であり、配信チャネルは Google 固有の OAuth 配管の再現になって学びがない。CLI は stdout / `--output`(JSON ファイル)まで、hosted は Responses 応答(= run history から辿れる)まで。実運用で足すなら Routine ではなくエージェント側ツール(Logic Apps / Teams webhook)になる。

### 元実装の癖の発見と保存

ライブ経路ではキーワード 0 件の記事の fallback summary が必ず "agent builders" を含むため、curate のフィルタ `keyword_hits or "agent" in summary` は**実質ノイズ除去だけに縮退**している(誰も気づかないまま全記事がランキングへ進む)。挙動互換を優先してそのまま移植し、テスト(`test_keywordless_story_passes_filter_via_fallback_summary`)で文書化した — 「移植はコードレビュー」の今回分。ほか、キーワード照合が部分一致("tool" が "tools" にヒット)なのも仕様として保存。

## 実行

```bash
uv sync --extra dev --extra hosting
uv run pytest                      # オフライン(ネットワーク不要・48 件)

# --- ロジック層ライブ(要 共有基盤 + ../../.env)---
uv run hn-briefing-maf --top-n 3               # 実 HN + 実モデルでブリーフ生成
uv run hn-briefing-maf --json --output runs/brief.json
uv sync --extra dev --extra live && uv run pytest -m live

# --- ホスティング層(実デプロイ。呼び出し元が実施)---
az login    # Foundry Project Manager 以上
uv run python hosting/deploy_hosted_agent.py --dry-run          # zip 内容と定義の確認
uv run python hosting/deploy_hosted_agent.py --invoke "Give me today's brief."
HN_BRIEFING_HOSTED_SMOKE=1 uv run pytest -m live -k hosted      # デプロイ済み面のスモーク

# --- Routines(プレビュー)---
uv run python scripts/setup_routine.py create --dry-run
uv run python scripts/setup_routine.py create                   # 平日 9:00 JST
uv run python scripts/setup_routine.py dispatch                 # 手動テスト発火(:dispatch_async)
uv run python scripts/setup_routine.py runs                     # 実行履歴
uv run python scripts/setup_routine.py disable                  # 一時停止(delete で削除)
```

ローカルでコンテナ相当を立てる(デプロイ前検証):

```bash
FOUNDRY_PROJECT_ENDPOINT=... FOUNDRY_MODEL_NAME=... uv run python hosting/main.py   # :8088
curl -sS -H "Content-Type: application/json" -X POST http://localhost:8088/responses \
  -d '{"input": "Give me today'\''s brief (top 3).", "stream": false}'
```

**コスト注意**: hosted agent は**アクティブセッション中の CPU/メモリ課金**(0.5vCPU/1GiB・アイドル 15 分でスケールゼロ)。Routine を有効のまま放置すると平日ごとにセッション+モデル呼び出しが発生する — 検証後は `setup_routine.py disable`(または RG 削除)。

## 評価

[tests/eval_dataset.jsonl](./tests/eval_dataset.jsonl)(8 ケース)は決定論部分のデータ駆動検証: keyword(部分一致の仕様含む 4)/ noise(2)/ rank_order(「キーワード×16 は points の厚みに勝つ」「freshness のタイブレーク」の 2)。`test_eval_dataset.py` がランキング実装との整合をオフラインで固定する。LLM 部分(brief_md)の品質は `--output` で保存した Brief を critique-loop の `run_cloud_eval.py` の型(evals API + coherence/rubric)に渡せば定量化できる — 決定論部分をデータセットで固めたので、ライブ評価は「digest に忠実か(並び替え・捏造がないか)」の rubric 1 本に絞れる。

## 検証結果(2026-07-31)

- オフラインテスト **48 passed**(収集パース 6 / ランキング決定論 10 / digest・Brief 4 / ワークフロー 5 / hosted 配線 6 / デプロイ・Routine ペイロード 5 / 設定 3 / データセット 9)/ ruff clean / `az bicep build` OK(生成 json は削除)
- hosted 配線は**実 import まで**検証済み: `hosting/main.py` のモジュールロード+実 MAF `Agent` を `ResponsesHostServer` に実構築(`run()` なし)。`azure-ai-projects` 2.3.0 の `create_version_from_code` / `HostedAgentDefinition` / `CodeDependencyResolution.REMOTE_BUILD` の型面もオフラインで構築確認済み
- 実デプロイ・Routine 作成・ライブスモークは未実施(呼び出し元で実施)。手順は上記「実行」節。**未検証の残リスク**:
  1. `create_version_from_code`(REMOTE_BUILD)のイメージビルド先 — azd フローはプロジェクト用 ACR をプロビジョニングするが SDK 経路の quickstart は ACR に言及しない。ACR 不在で失敗する場合は `azd ai agent init` フローへ切替(azure.yaml は SDK 定義と 1:1 なので書き起こしは容易)
  2. `agent-framework-foundry-hosting` はプレリリース(b260730)— REMOTE_BUILD 時の解決が将来版でズレる可能性(requirements.txt に下限ピン済み)
  3. Routines は Japan East 対応リストに載っているが「リージョンまたはサブスクリプションで未有効」の但し書きがポータル節にある — `create` が 4xx を返す場合はアカウントチームへの申請経路
  4. Routine → hosted agent 呼び出しは Responses API 経由なので、**コールドスタート**(スケールゼロからの再開)が cron 時刻に毎回入る。実測は run history の所要時間で確認する

## 検証結果(2026-07-31 ライブ)

- ロジック層: ローカル完動(実 HN データ→ランキング→ブリーフ生成)
- **hosted agent デプロイ成功**: `create_version_from_code`(REMOTE_BUILD)で creating→active、version 1 に 100% ルーティング、Entra 認証。`--invoke` でコンテナ内からの HN 収集+ブリーフ生成を確認(= コンテナ内 httpx 関数ツールは「ツール直付け不可」制約の対象外という設計判断が実証された)
- **Routines 実証**: 日次 cron(21:00 JST)のルーチン作成 → `:dispatch_async` 手動起動 → run が **Finished**。スケジュール→hosted agent 呼び出しのループが Foundry 上で成立
- **実測での発見**: Routines REST は **`?api-version=v1` クエリが必須**(欠くと BadRequest。Learn の例では省略されており、実装前調査だけでは気づけない)→ routine_url に反映
- 検証後、定期実行による無人課金を避けるためルーチンは **disable** 済み(再開は `setup_routine.py enable`)

## 学び(MAF/Foundry vs 元構成)

1. **「クライアント実行 MAF」→「hosted agent 化」で書き換わったのはエージェントコードではなく周辺 3 点 — 資格情報・観測・HTTP 面。**エージェント本体(instructions+ツール)は完全共有で、hosted 化の差分は hosting/main.py の 60 行に閉じた。(a) **資格情報**: クライアント実行の「OpenAI v1 エンドポイント+API キー」が「`FoundryChatClient` + agent identity(デプロイ時に自動付与される専用 Entra ID)」になり、**コンテナに秘密を 1 つも持ち込まない**構成が既定になる(環境変数はエンドポイントとモデル名だけ)。(b) **観測**: 全ポートで書いてきた `configure_azure_monitor` の配線が消える — 接続文字列はプラットフォームが注入し、protocol ライブラリが OTel を既定発信。逆にオフラインテストでは既定の observability 構成が IMDS(169.254.169.254)を突く副作用があり、`configure_observability=None` で切る必要があった(コンストラクタ引数として公開されているのは良設計)。(c) **HTTP 面**: 元アプリが FastAPI で自作した trigger/pubsub/health エンドポイントは `ResponsesHostServer` が標準の Responses 契約として持つ。**元 scheduler_api.py の約 120 行と Cloud Run 運用がまるごと消えた**一方、デプロイは「zip 規約+provisioning ポーリング+バージョン即時不変」という新しい運用語彙を要求する — サーバー運用の消滅とデプロイ工程の増加のトレードオフ。
2. **Routines は「Cloud Scheduler 相当をプロジェクト内オブジェクトにした」もので、契約は素直だがプレビューの割り切りが濃い。**REST は PUT 1 本+フィーチャーヘッダーで、元構成の Scheduler ジョブ+Pub/Sub トピック+push サブスクリプション+OIDC 設定より明確に少ない。run history がエージェント応答・トレースにリンクされるのはスケジューラ側からは得られなかった観測性。一方で (a) 1 トリガー+1 アクション固定(元 README がやっていた「複数チャネルへの配信分岐」は routine では組めずエージェント側の責務)、(b) `Foundry-Features` ヘッダー必須の API は SDK でも beta 名前空間で、**「機能の成熟度がヘッダー名で分かる」**段階、(c) 対応 8 リージョンに Japan East が入っていたのは幸運の部類(Memory は 19、hosted は 31、Routines は 8 — **同じ「新 Foundry」でもサブ機能ごとにリージョン集合が違う**ので、リージョン選定は使いたいサブ機能の積集合で決める必要がある)。実デプロイでの使用感(コールドスタート込みの発火遅延、失敗時のリトライ有無)は残リスク 4 の実測待ち。
3. **「ツール直付け不可」の制約は実際には二層に分解して読む必要がある — 「定義にアタッチする Foundry 管理ツール」は不可(Toolbox 経由)、「コンテナ内の自前コードのツール」は無関係。**survey の一文だけ読むと「hosted にするとツールが使えない」ように見えるが、本ポートの HN 収集ツールはコンテナ内 httpx 呼び出しなので何の制約も受けなかった。制約が効くのは Code Interpreter / Web Search / 認証付き MCP 等を hosted から使いたいときで、その場合は Toolbox MCP エンドポイント+`FoundryToolbox` クライアントという追加ホップが入る。**選定軸: hosted agent 化の摩擦は「ツールの出所」で決まる** — 自前 API 呼び出し中心のエージェントはほぼ無摩擦、Foundry 管理ツール中心のエージェントは Toolbox 設計が先に要る。prompt agent なら定義に直接ツールを書ける(ここは prompt/hosted で非対称)。
4. **常時稼働型の運用観点 — 元実装の「常時稼働」は実はサーバー常駐で、Foundry 版は「常時*予約*・実行時のみ稼働」になる。**元構成は Cloud Run の最小インスタンス設定次第で 24h 課金がありえた。hosted agent はセッション毎サンドボックス+アイドル 15 分スケールゼロ+状態($HOME)の自動退避/復元で、日次ブリーフのような**低頻度バッチには構造的に安い**。ただし運用上の含意が 3 つ: (a) cron 発火のたびにコールドスタートを踏む(日次ブリーフでは許容、対話 UX では要考慮)、(b) バージョンは不変オブジェクトなので「環境変数を 1 個変える」にも新バージョン+ルーティング切替が要る — 元の「Cloud Run の env を書き換えて再起動」よりも重いが、ロールバックは routing の付け替えで確実、(c) 「止める」操作は Routine の disable(トリガー停止)とエージェント削除(定義ごと)の二段があり、コスト停止の単位が明確。ラボのステートレス規約(RG 削除で全撤去 → スクリプト再構築)は hosted agent でも成立する — デプロイもルーチンもスクリプト化してあるので再現は 2 コマンド。
5. **決定論パイプラインと LLM の境界を「digest 文字列」1 点に固定すると、二形態(ワークフロー/ツール持ちエージェント)の共存がタダになる。**収集→ランク→digest までを純関数にし、ワークフローは digest を LLM に渡し、hosted はツールが digest を返す — LLM に触れさせる面が 1 つの文字列に収まっているので、オフラインテストはゴールデン値(元実装実行で採取したスコア)で決定論部分を完全固定でき、LLM 側の検証は「digest に忠実か」だけに縮む。元実装が LLM を「使っても使わなくても同じ出力」の飾りにしていた(スケジューラ経路は LLM 非経由)のと対照的に、移植版は静的テンプレート(next_actions 3 行固定)を LLM の編集に置き換えつつ、正確性が要る部分(順位・数値)は決定論のまま残した。**「どこまでを式にしてどこから LLM か」の線引きを移植時に引き直せる**のは、フレームワーク移植の隠れた価値だと思う。
