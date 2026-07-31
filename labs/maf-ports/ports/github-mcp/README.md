# github-mcp — GitHub 自然言語照会 + リモート MCP(Port 6)

元: [`mcp_ai_agents/github_mcp_agent`](https://github.com/Shubhamsaboo/awesome-llm-apps/tree/main/mcp_ai_agents/github_mcp_agent)(agno + 公式 [github-mcp-server](https://github.com/github/github-mcp-server) を **Docker/stdio** で起動 + Streamlit、151 行)

## 元の構成(5行)

- Streamlit UI。サイドバーで OpenAI API キーと GitHub PAT を入力し、リポジトリ(owner/repo)とクエリ種別(Issues / PRs / Repository Activity / Custom)を選ぶ
- MCP 接続は `StdioServerParameters(command="docker", args=["run", "-i", "--rm", ..., "ghcr.io/github/github-mcp-server"])` — **公式 GitHub MCP サーバーをクエリのたびに Docker で起動**
- PAT は `GITHUB_PERSONAL_ACCESS_TOKEN`、ツール選択は `GITHUB_TOOLSETS=repos,issues,pull_requests` を**コンテナの環境変数**として注入
- agno の `async with MCPTools(server_params=...)` → `Agent(tools=[mcp_tools], instructions=...)` 単一エージェント。`asyncio.wait_for(agent.arun(query), timeout=120)` で実行
- リポジトリ指定がクエリ本文に無ければ `f"{query} in {repo}"` を連結。エラーは文字列にして UI に表示

## stdio(Docker)→ リモート MCP 対応表(本ポートの核心)

移植では **GitHub 公式リモート MCP サーバー(`https://api.githubcopilot.com/mcp/`、GA)** を第一経路にした。INVENTORY.md の評価どおり「stdio の Docker 依存を消せる」のが移植価値で、インフラ差分はゼロになる。

| 元(stdio / Docker) | 移植後(リモート / streamable HTTP) | 備考 |
| --- | --- | --- |
| `StdioServerParameters(command="docker", args=[...])` | `MCPStreamableHTTPTool(name, url="https://api.githubcopilot.com/mcp/", http_client=...)` | Docker デーモン・イメージ pull・コンテナ起動待ちが全部消える |
| PAT: `GITHUB_PERSONAL_ACCESS_TOKEN` 環境変数(コンテナへ) | PAT: `Authorization: Bearer <PAT>` **HTTP ヘッダー**(全リクエスト) | env `GITHUB_TOKEN`(未設定は ConfigError で `gh auth token` を案内) |
| `GITHUB_TOOLSETS=repos,issues,pull_requests` 環境変数 | `X-MCP-Toolsets: repos,issues,pull_requests` **ヘッダー** | 同名・同値の設定が「プロセス env → HTTP ヘッダー」へ移る 1:1 対応 |
| (相当なし。read-only はフラグ `--read-only`) | `X-MCP-Readonly: true` ヘッダー(既定 on) | 読み取り分析専用ポートなので書き込みツールをサーバー側で外す |
| agno `MCPTools(server_params=...)`(async context manager) | MAF `MCPStreamableHTTPTool`(async context manager だが **Agent が run 時に自動接続**) | 学び 2 参照 |
| `agent.arun(query)` + `asyncio.wait_for(120s)` | `Agent.run(query)` + `asyncio.wait_for(120s)`([query.py](./src/github_mcp_maf/query.py)) | タイムアウト値も忠実に移植 |
| Streamlit(キーを UI から env へ書く) | CLI(`--repo` / `--timeout`) | PORTING.md §7: UI は移植しない |

## MAF の MCP API 調査(installed agent_framework 1.12.1 の `_mcp.py` 精読)

- トランスポート別に 3 クラス: **`MCPStdioTool`**(command/args/env — 元アプリと同型)、**`MCPStreamableHTTPTool`**(url + httpx)、**`MCPWebsocketTool`**。いずれも `agent_framework` トップレベル export で、`MCPTool` 基底が接続・ツール/プロンプト読み込み・再接続(ping 失敗時)を持つ
- **`mcp` パッケージ(python-sdk)は agent-framework-core の optional 依存**(`mcp>=1.24,<2`、extra `all`)。個別インストールが必要 — 本ポートの pyproject に追加した
- **Agent への渡し方**: `Agent(client, tools=[mcp_tool])`。Agent は MCPTool を通常ツールと分離して `agent.mcp_tools` に保持し(_agents.py 841 行)、**run 時に未接続なら自分の exit stack で接続**して `tool.functions`(サーバーの全ツールを `FunctionTool` 化したもの)をツールリストへ展開する(同 1375 行)。`async with agent:` でも接続され、exit で切断される
- **ヘッダーの渡し方が 2 系統**あり、ここが最大の落とし穴だった(設計判断参照):
  - `header_provider=Callable[[kwargs], dict]` — **call_tool 時のみ**注入(オリジン一致チェック付き)。ミドルウェアで注入する per-request コンテキスト向け
  - `http_client=httpx.AsyncClient(headers=...)` — 全リクエスト(initialize / tools/list 含む)に付く。**静的な PAT はこちらでないと接続できない**。オリジン制限は利用者責務と docstring に明記
- セキュリティ既定が堅い: サーバー起点の sampling は**既定で全拒否**(`sampling_approval_callback` で明示 opt-in)、`approval_mode` / `allowed_tools` でツール実行の承認・許可リスト制御ができる

## 移植後の構成

```
質問(+ --repo)─▶ build_full_query("{query} in {repo}")
             ─▶ github_agent(MAF Agent, gpt-5.4-mini)
                   └─ MCPStreamableHTTPTool("github", https://api.githubcopilot.com/mcp/)
                        └─ httpx.AsyncClient(headers: Authorization / X-MCP-Toolsets / X-MCP-Readonly)
             ─▶ ツール呼び出し(list_issues / search_pull_requests / ...)× n ─▶ markdown 回答
```

- ツール定義の組み立ては [tools.py](./src/github_mcp_maf/tools.py)(ヘッダーは純関数 `build_headers`、ツールクラスは `tool_cls` コンストラクタ注入でテスト可能)
- 1 クエリの実行は [query.py](./src/github_mcp_maf/query.py)(連結規則・120 秒タイムアウト・「空応答は例外にしない」という元アプリの挙動をテストで固定)
- Streamlit → CLI(`github-mcp-maf "質問"` / `--repo owner/repo` / `--timeout`)

## 設計判断

### PAT は header_provider ではなく自前 http_client に載せる

MAF の `MCPStreamableHTTPTool` には per-call の `header_provider` があるが、精読の結果 **connect 時(initialize / tools/list)にはヘッダーが付かない**(注入フックは call_tool が設定する ContextVar / スナップショットだけを読む)。GitHub リモートサーバーは全リクエストに認証を要求するため、header_provider だけだと接続段階で 401 になる。よって静的 PAT は `httpx.AsyncClient(headers=...)` を `http_client` に渡す方式にした。docstring は「custom http_client のヘッダーはオリジン制限が利用者責務」とするため、**リダイレクト追従は無効(httpx 既定)のまま**にして別オリジンへの PAT 漏出を防ぎ、クライアントの後始末(`aclose`)も CLI / ライブスモークの finally で明示的に行う。

### 接続ライフサイクルは `async with agent:` に委ねる

agno は `async with MCPTools(...)` をユーザーコードに書かせる。MAF は Agent が run 時に未接続の MCP ツールを自動接続するので接続コードを書かないことも可能だが、その場合は切断が Agent の exit stack 任せになる。CLI は `async with agent:` で「enter = 接続、exit = 切断」を明示し、両者の中間(自動接続に頼らず、かといって MCP ツールを直接 enter しない)を取った。

### 読み取り専用ガード(X-MCP-Readonly)を既定 on にした

元アプリは PAT の権限に任せて書き込みツールもエージェントに見せていた。リモート版はヘッダー 1 つで**サーバー側からツール面を絞れる**ので既定 on にした(`GITHUB_MCP_READONLY=false` で解除)。「LLM に見せるツールを減らす」はプロンプトインジェクション対策の基本で、eval_dataset の 5 件目(書き込み依頼を断れるか)がこの検証ケース。MAF 側にも `allowed_tools` / `approval_mode` があるが、サーバー側で絞る方が「そもそも tools/list に現れない」ため強い。

### オフラインテストの境界は「ツールクラスのコンストラクタ」

実 MCP サーバーへの接続はライブスモークのみ。オフラインでは (a) `build_headers` / `make_http_client`(URL・ヘッダー・タイムアウト・リダイレクト無効)、(b) `tool_cls` に記録フェイクを注入した組み立て引数の検証+実 `MCPStreamableHTTPTool` の未接続構築(`functions == []`)、(c) 実 `Agent` の配線(`agent.mcp_tools` 分離、instructions 原文一致)、(d) ScriptedAgent での応答パス(連結・タイムアウト・空応答)を固定する。

## 実行

```bash
uv sync --extra dev
uv run pytest                      # オフライン(ネットワーク不要・21 件)

# --- ライブ(要 共有基盤 + ../../.env + GITHUB_TOKEN)---
az deployment group create -g rg-maf-ports -f infra/main.bicep -p baseName=mafports
#   (existing 参照のみ。新規リソースなし — 出力の endpoint 確認用)

export GITHUB_TOKEN="$(gh auth token)"   # または PAT を直接設定

uv run github-mcp-maf --repo microsoft/agent-framework "Show me recent merged PRs"
uv run github-mcp-maf "Find issues labeled as bugs in microsoft/agent-framework"

uv sync --extra dev --extra live && uv run pytest -m live   # ライブスモーク
```

インフラ: 共有基盤のみ(existing 参照)。MCP はクライアント側接続のため**本ポート固有の Azure リソースはゼロ**。GitHub 側の課金もなし(PAT のレート制限のみ)。

## 評価

[tests/eval_dataset.jsonl](./tests/eval_dataset.jsonl)(5 ケース)は元アプリのクエリテンプレート 3 種(Issues / PRs / Repository Activity)+レビュー待ち PR の絞り込み+**readonly ガード**(書き込み依頼を断れるか)。回答は実リポジトリの状態に依存するため期待値は traits(実データ準拠・リンク付与・表形式・捏造なし)で記述し、ライブ実行時は App Insights の MCP スパン(`tools/call`)でツール呼び出し列を突き合わせ、応答は Foundry の Task adherence / Relevance 評価器に渡せる形にしてある。

## 検証結果(2026-07-31)

- オフラインテスト 21 passed / ruff clean / `az bicep build` OK(生成 json は削除)
- ライブスモークは未実施(呼び出し元で実施)。手順: `export GITHUB_TOKEN=$(gh auth token)` → `uv run pytest -m live` → CLI 1 回 → トレース到達の確認クエリ:

```bash
az monitor app-insights query --app appi-mafports -g rg-maf-ports \
  --analytics-query "dependencies | where timestamp > ago(30m) | summarize count() by name"
```

## 検証結果(2026-07-31)

- オフラインテスト **21 passed** / ruff clean / bicep build OK
- ライブスモーク: **1 passed(18.8s、2026-07-31)**。gh の OAuth トークンでリモート MCP に接続し、microsoft/agent-framework への読み取りクエリが完走
- **追加の学び(実行時に発覚)**: `mcp>=1.24` 指定だと **mcp 2.0.0 が解決されて接続時に `InitializeResult.protocolVersion` AttributeError**。agent-framework-core の要求は `mcp<2,>=1.24` — **上限ピンは自分の pyproject にも必要**(推移的依存の extra 経由では強制されない)。`mcp>=1.24,<2` に修正済み
- 再実行方法:
  `gh auth login`(または PAT を発行)→ `GITHUB_TOKEN=$(gh auth token) uv run pytest -m live`
  期待動作: microsoft/agent-framework への読み取り質問 1 件が完走し、`invoke_agent` + MCP ツール呼び出しがトレースに乗る

## 学び(MAF/Foundry vs 元構成)

1. **stdio → リモート MCP 移行で消えるのは「プロセス管理」、残るのは「秘密と設定」— ただし置き場所が env から HTTP ヘッダーへ移る。**消えるもの: Docker デーモン依存、イメージ pull、クエリごとのコンテナ起動(元アプリは実行のたびに `docker run --rm` していた)、stdio の生存管理。残るもの: PAT の管理(むしろ**毎リクエスト送信**になるので漏出面は広がる)、ツールセット選択(`GITHUB_TOOLSETS` env → `X-MCP-Toolsets` ヘッダーの 1:1 対応)、タイムアウト設計。「ヘッダーが設定チャネルになる」ことの含意は大きく、認証(Authorization)・機能選択(X-MCP-Toolsets)・安全性(X-MCP-Readonly)が全部同じ場所に並ぶ。そして MAF ではそのヘッダーの注入経路が 2 系統(`http_client` / `header_provider`)あり、**静的 PAT は http_client でないと接続段階(initialize / tools/list)で 401 になる** — `header_provider` は call_tool 時のみ注入という実装を `_mcp.py` の精読で確認してから書いたので一発で正しく組めたが、ドキュメントだけでは踏む罠だと思う。SI 的には「リモート MCP の認証方式(静的キーか per-user トークンか)」が最初に確認すべき分岐点になる。
2. **MAF の MCP ツール DX は agno よりも「Agent に溶けている」— 接続管理を書かなくてよい代わりに、ライフサイクルの所有者を意識する必要がある。**agno は `async with MCPTools(server_params) as tools` → `Agent(tools=[tools])` と、接続スコープをユーザーコードが持つ。MAF は `Agent(client, tools=[MCPStreamableHTTPTool(...)])` と書くだけで、Agent が MCPTool を通常ツールと分離保持し(`agent.mcp_tools`)、**run 時に未接続なら自動接続してサーバーのツール群を `FunctionTool` として展開**する。1 行少なくなる一方、「いつ繋がり、いつ切れるか」が Agent の exit stack に隠れるので、CLI では `async with agent:` で明示した。また MAF はセキュリティ既定が agno より硬い: サーバー起点 sampling は既定全拒否、`approval_mode` / `allowed_tools` / progressive disclosure が最初から用意され、per-call ヘッダーはオリジン一致チェック付き。「MCP サーバーは信頼できない第三者」という前提がフレームワーク設計に織り込まれているのは、野良 MCP サーバーが増えている現状では選定理由になり得る。
3. **同じ「リモート MCP(GA)」でも、MAF クライアント実行と Foundry Agent Service の MCP ツール(サーバー側実行)は別物**([04-tools-knowledge.md](../../../../docs/survey/features/04-tools-knowledge.md) の MCP 行)。本ポートの構成では MCP 接続はローカルプロセスから GitHub へ直接張られ、PAT はクライアント環境(env)にあり、Azure 側リソースはゼロ(main.bicep が existing 参照のみなのはこのため)。Agent Service の MCP ツールでは接続定義とシークレット(キー / Entra マネージド ID / OAuth ID パススルー)が**プロジェクト接続としてサービス側**に置かれ、ツール呼び出しも Azure 内から実行される — エグレス制御・監査・シークレット管理を Azure に寄せられる代わりに、long-running 操作はまだプレビューという成熟度差がある。使い分けの軸は「MCP 呼び出しの実行点と秘密の置き場所をどこにしたいか」: 開発者マシン / 自前ランタイムなら MAF クライアント(本ポート)、マネージドエージェントに寄せるなら Agent Service ツール。**コードの書き換えなしに両者を行き来できるわけではない**(MAF はツールオブジェクト、Agent Service はエージェント定義)ことも、アーキテクチャ選定時に見落としやすい点。
4. **「ツール面をどこで絞るか」に 3 層できた: サーバー(ヘッダー)/ クライアント(allowed_tools)/ モデル(instructions)。**元アプリは `GITHUB_TOOLSETS` の 1 層だけだった。リモート化で `X-MCP-Toolsets` + `X-MCP-Readonly`(サーバーが tools/list 自体を絞る)、MAF 側で `allowed_tools` / `approval_mode`(クライアントが公開・承認を絞る)、instructions(モデルの振る舞いを絞る)の 3 層が明示的に選べる。強度はサーバー > クライアント > モデルの順で、本ポートは最強のサーバー側(readonly ヘッダー既定 on)を採った。eval の「Close issue #1」ケースはこの層構造の検証で、Foundry Agent Service でも同じ問い(接続定義で絞るか、エージェント定義で絞るか)が出る — MCP 統合の設計レビューで最初に描くべき図だと分かった。
