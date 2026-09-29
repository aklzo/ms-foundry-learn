"""MCP ツール定義の組み立て(URL / ヘッダー / 名前)のオフラインテスト。
実サーバーへは接続しない。ツールクラスの境界は ``tool_cls`` のコンストラクタ
注入で置き換える(PORTING.md §4 の scripted fake 方針の MCP 版)。

2026-09-29: PAT の載せ方を自前 httpx クライアントから MAF 1.19 の
``static_headers`` に切り替えたため、「接続段階(initialize / tools/list)にも
ヘッダーが付く」ことを httpx MockTransport のスタブ MCP サーバーで固定する
(旧版の README が記録した「header_provider では接続時 401」の罠の回帰防止)。
"""

import json
from functools import partial
from typing import Any

import httpx
import pytest

from github_mcp_maf.config import GithubMcpSettings
from github_mcp_maf.tools import TOOL_NAME, build_github_mcp_tool, build_headers


def make_settings(**overrides: Any) -> GithubMcpSettings:
    values: dict[str, Any] = {
        "openai_v1_endpoint": "https://example.openai.azure.com/openai/v1",
        "model": "gpt-5.4-mini",
        "api_key": "dummy",
        "github_token": "ghp_dummy",
        "mcp_url": "https://api.githubcopilot.com/mcp/",
        "toolsets": "repos,issues,pull_requests",
        "readonly": True,
        "app_insights_connection_string": None,
    }
    values.update(overrides)
    return GithubMcpSettings(**values)


class FakeMcpTool:
    """MCPStreamableHTTPTool 互換のコンストラクタ記録フェイク。"""

    def __init__(self, name: str, url: str, **kwargs: Any) -> None:
        self.name = name
        self.url = url
        self.kwargs = kwargs


# --- ヘッダー(元アプリの Docker env → リモートの HTTP ヘッダー対応)---


def test_build_headers_bearer_pat_and_toolsets() -> None:
    headers = build_headers(make_settings())

    assert headers["Authorization"] == "Bearer ghp_dummy"
    # 元アプリの GITHUB_TOOLSETS 環境変数 → X-MCP-Toolsets ヘッダー
    assert headers["X-MCP-Toolsets"] == "repos,issues,pull_requests"
    assert headers["X-MCP-Readonly"] == "true"


def test_build_headers_omits_readonly_when_disabled() -> None:
    headers = build_headers(make_settings(readonly=False))

    assert "X-MCP-Readonly" not in headers


def test_build_headers_omits_toolsets_when_empty() -> None:
    headers = build_headers(make_settings(toolsets=""))

    assert "X-MCP-Toolsets" not in headers
    assert headers["Authorization"] == "Bearer ghp_dummy"


# --- ツール定義の組み立て(コンストラクタ注入)---


def test_tool_cls_injection_receives_name_url_and_static_headers() -> None:
    tool = build_github_mcp_tool(make_settings(), tool_cls=FakeMcpTool)

    assert tool.name == TOOL_NAME == "github"
    assert tool.url == "https://api.githubcopilot.com/mcp/"
    # PAT とツール選択は static_headers(MAF 1.19+。同一オリジンのみに注入)
    assert tool.kwargs["static_headers"] == build_headers(make_settings())
    # 自前 httpx クライアントは渡さない(ツールが生成・破棄する)
    assert "http_client" not in tool.kwargs
    # 元アプリ(agno MCPTools)同様、公開面はツールのみ
    assert tool.kwargs["load_prompts"] is False


def test_tool_url_follows_settings_override() -> None:
    settings = make_settings(mcp_url="https://mcp.example.test/mcp/")

    tool = build_github_mcp_tool(settings, tool_cls=FakeMcpTool)

    assert tool.url == "https://mcp.example.test/mcp/"


# --- 実 MCPStreamableHTTPTool での配線(構築のみ。接続はしない)---


def test_real_mcp_tool_offline_wiring() -> None:
    pytest.importorskip("agent_framework")
    from agent_framework import MCPStreamableHTTPTool

    tool = build_github_mcp_tool(make_settings())

    assert isinstance(tool, MCPStreamableHTTPTool)
    assert tool.name == "github"
    assert tool.url == "https://api.githubcopilot.com/mcp/"
    # 未接続: サーバーのツール群は connect(Agent の run / __aenter__)まで空
    assert tool.is_connected is False
    assert tool.functions == []


# --- ハンドシェイクのヘッダー(httpx MockTransport のスタブ MCP サーバー)---


class StubMcpServer:
    """streamable HTTP の最小スタブ。受けたリクエストの JSON-RPC メソッドと
    ヘッダーを記録し、initialize / ping / tools/list に JSON で応答する。"""

    def __init__(self) -> None:
        self.requests: list[tuple[str, str | None, httpx.Headers]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        self.requests.append((request.method, body.get("method"), request.headers))
        if request.method != "POST":
            return httpx.Response(405)  # SSE の GET / セッション終了の DELETE は非対応
        if "id" not in body:
            return httpx.Response(202)  # notifications/initialized
        results = {
            "initialize": {
                "protocolVersion": body.get("params", {}).get("protocolVersion", "2025-06-18"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "stub-github", "version": "0"},
            },
            "tools/list": {
                "tools": [
                    {
                        "name": "list_issues",
                        "description": "List issues",
                        "inputSchema": {"type": "object", "properties": {}},
                    }
                ]
            },
        }
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": body["id"], "result": results.get(body["method"], {})},
        )


async def test_static_headers_reach_initialize_and_tools_list() -> None:
    """接続段階(initialize / tools/list)にも PAT・ツールセット・readonly が載る。

    旧実装が自前 http_client を必要とした理由(header_provider は call_tool 時
    のみ注入 → 接続で 401)の回帰防止。ネットワークには出ない(MockTransport)。"""
    pytest.importorskip("agent_framework")
    from agent_framework import MCPStreamableHTTPTool

    server = StubMcpServer()
    transport_client = httpx.AsyncClient(transport=httpx.MockTransport(server))
    try:
        tool = build_github_mcp_tool(
            make_settings(),
            tool_cls=partial(MCPStreamableHTTPTool, http_client=transport_client),
        )
        async with tool:
            assert [function.name for function in tool.functions] == ["list_issues"]
    finally:
        await transport_client.aclose()

    methods = [method for _, method, _ in server.requests]
    assert "initialize" in methods
    assert "tools/list" in methods
    for http_method, _, headers in server.requests:
        if http_method == "POST":
            assert headers["authorization"] == "Bearer ghp_dummy"
            assert headers["x-mcp-toolsets"] == "repos,issues,pull_requests"
            assert headers["x-mcp-readonly"] == "true"
