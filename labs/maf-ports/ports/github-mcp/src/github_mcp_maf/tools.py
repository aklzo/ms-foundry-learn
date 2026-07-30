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

ヘッダーの渡し方(installed agent_framework 1.12.1 の _mcp.py 精読の結論):

- ``header_provider`` は **call_tool 時のみ**ヘッダーを注入する(接続時の
  initialize / tools/list には付かない)。全リクエストに認証を要求する
  GitHub リモートサーバーでは接続段階で 401 になるため使えない
- よって **自前 ``httpx.AsyncClient(headers=...)`` を ``http_client`` に渡す**。
  _mcp.py の docstring は「custom http_client のヘッダーのオリジン制限は利用者
  責務」とするため、リダイレクト追従は無効(httpx 既定)のままにして別
  オリジンへの PAT 漏出を防ぐ。クライアントの後始末(aclose)も呼び出し側の
  責務(CLI / ライブスモークが finally で閉じる)

オフラインテストは実サーバーへ接続せず、``tool_cls`` のコンストラクタ注入で
組み立て引数(URL / ヘッダー / 名前)を検証する。
"""

from __future__ import annotations

from typing import Any

from .config import GithubMcpSettings

#: MAF の MCPStreamableHTTPTool が自前クライアントを作るときの既定と同値
#: (MCP_DEFAULT_TIMEOUT=30 / MCP_DEFAULT_SSE_READ_TIMEOUT=300)。ヘッダー付き
#: クライアントを差し替えてもタイムアウト特性が変わらないよう明示する。
HTTP_TIMEOUT_SECONDS = 30
SSE_READ_TIMEOUT_SECONDS = 300

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


def make_http_client(settings: GithubMcpSettings) -> Any:
    """PAT ヘッダー付きの httpx.AsyncClient を作る。

    follow_redirects は httpx 既定の False のまま(オリジン外への PAT 漏出
    防止)。呼び出し側が ``await client.aclose()`` すること。
    """
    from httpx import AsyncClient, Timeout

    return AsyncClient(
        headers=build_headers(settings),
        timeout=Timeout(HTTP_TIMEOUT_SECONDS, read=SSE_READ_TIMEOUT_SECONDS),
    )


def build_github_mcp_tool(
    settings: GithubMcpSettings,
    http_client: Any,
    *,
    tool_cls: type | None = None,
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
        http_client=http_client,
        load_prompts=False,  # 元アプリ(agno MCPTools)同様、公開面はツールのみ
    )
