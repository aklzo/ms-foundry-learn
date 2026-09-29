"""GitHub リモート MCP サーバーへの MAF MCP ツールの組み立て。

元(agno): ``MCPTools(server_params=StdioServerParameters(command="docker",
args=["run", ..., "ghcr.io/github/github-mcp-server"], env={...}))`` — PAT は
``GITHUB_PERSONAL_ACCESS_TOKEN``、ツール選択は ``GITHUB_TOOLSETS`` を
**環境変数としてコンテナへ**渡していた。

移植後(MAF): ``MCPStreamableHTTPTool`` で GitHub 公式リモート MCP サーバー
(https://api.githubcopilot.com/mcp/)へ streamable HTTP 接続。Docker 依存が
消える代わりに、PAT とツール選択は **HTTP ヘッダー**になる:

- ``Authorization: Bearer <PAT>``
- ``X-MCP-Toolsets: repos,issues,pull_requests``(元の GITHUB_TOOLSETS と 1:1)
- ``X-MCP-Readonly: true``(リモート版で追加できる読み取り専用ガード)

ヘッダーの渡し方(2026-09-29 に agent-framework-core 1.19.0 の _mcp.py で再確認):

- **``static_headers``(1.19.0 で追加)を使う。** 固定ヘッダーを構築時にコピーし、
  接続中の全リクエスト(initialize / tools/list / ping / tools/call)に付ける。
  注入は設定した ``url`` と同一オリジンのリクエストに限られ、別オリジンへの
  リダイレクトでは外される — PAT 漏出防止をフレームワークが肩代わりする
- 旧実装(2026-07-31)は ``httpx.AsyncClient(headers=...)`` を ``http_client`` に
  渡していた。当時(1.12.1)の ``header_provider`` は call_tool 時にしか注入され
  ず、接続段階で 401 になったため。1.13.0 で header_provider も接続時に呼ばれる
  ようになり、1.19.0 で static_headers が入ったので回避策は不要になった
  (_mcp.py の docstring も「自前クライアントでヘッダーを付けるとオリジン制限は
  利用者責務」と注意している)
- HTTP クライアントは MCP ツールが自前で生成・破棄する(タイムアウト 30 秒 /
  SSE 読み取り 300 秒、レスポンス Cookie 非保持)。接続・切断は
  ``async with agent:``(または Agent の run 時自動接続)が担う

オフラインテストは実サーバーへ接続せず、``tool_cls`` のコンストラクタ注入で
組み立て引数(URL / ヘッダー / 名前)を検証し、httpx の MockTransport で
ハンドシェイク(initialize / tools/list)にヘッダーが載ることを固定する。
"""

from __future__ import annotations

from typing import Any

from .config import GithubMcpSettings

#: エージェントから見た MCP ツール群の論理名
TOOL_NAME = "github"


def build_headers(settings: GithubMcpSettings) -> dict[str, str]:
    """リモート MCP サーバーへ送る全リクエスト共通ヘッダー(純関数)。"""
    headers = {"Authorization": f"Bearer {settings.github_token}"}
    if settings.toolsets:
        headers["X-MCP-Toolsets"] = settings.toolsets
    if settings.readonly:
        headers["X-MCP-Readonly"] = "true"
    return headers


def build_github_mcp_tool(
    settings: GithubMcpSettings,
    *,
    tool_cls: Any | None = None,
) -> Any:
    """GitHub リモート MCP サーバーを指す MAF MCP ツールを組み立てる。

    ``tool_cls`` はテスト用の注入シーム(既定は MAF の MCPStreamableHTTPTool)。
    接続はここでは行わない — Agent が run 時に(または ``async with agent:``
    が)ツールをコンテキストとして enter した時点で initialize / tools/list が
    走り、サーバーのツール群が ``tool.functions`` に展開される。
    """
    if tool_cls is None:
        from agent_framework import MCPStreamableHTTPTool as tool_cls  # type: ignore[no-redef]

    return tool_cls(
        TOOL_NAME,
        settings.mcp_url,
        description="GitHub repositories, issues and pull requests via the official remote MCP server",
        static_headers=build_headers(settings),
        load_prompts=False,  # 元アプリ(agno MCPTools)同様、公開面はツールのみ
    )
