"""MCP ツール定義の組み立て(URL / ヘッダー / 名前)のオフラインテスト。
実サーバーへは接続しない。ツールクラスの境界は ``tool_cls`` のコンストラクタ
注入で置き換える(PORTING.md §4 の scripted fake 方針の MCP 版)。"""

from typing import Any

import pytest

from github_mcp_maf.config import GithubMcpSettings
from github_mcp_maf.tools import (
    SSE_READ_TIMEOUT_SECONDS,
    TOOL_NAME,
    build_github_mcp_tool,
    build_headers,
    make_http_client,
)


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


def test_tool_cls_injection_receives_name_url_and_client() -> None:
    sentinel_client = object()

    tool = build_github_mcp_tool(make_settings(), sentinel_client, tool_cls=FakeMcpTool)

    assert tool.name == TOOL_NAME == "github"
    assert tool.url == "https://api.githubcopilot.com/mcp/"
    assert tool.kwargs["http_client"] is sentinel_client
    # 元アプリ(agno MCPTools)同様、公開面はツールのみ
    assert tool.kwargs["load_prompts"] is False


def test_tool_url_follows_settings_override() -> None:
    settings = make_settings(mcp_url="https://mcp.example.test/mcp/")

    tool = build_github_mcp_tool(settings, object(), tool_cls=FakeMcpTool)

    assert tool.url == "https://mcp.example.test/mcp/"


# --- httpx クライアント(PAT はここに載る。接続はしない)---


async def test_make_http_client_carries_headers_without_redirects() -> None:
    client = make_http_client(make_settings())
    try:
        assert client.headers["Authorization"] == "Bearer ghp_dummy"
        assert client.headers["X-MCP-Toolsets"] == "repos,issues,pull_requests"
        assert client.headers["X-MCP-Readonly"] == "true"
        # オリジン外への PAT 漏出防止: リダイレクト追従は無効(httpx 既定)のまま
        assert client.follow_redirects is False
        # SSE 読み取りは MAF 既定と同じ長め(300s)
        assert client.timeout.read == SSE_READ_TIMEOUT_SECONDS
    finally:
        await client.aclose()


# --- 実 MCPStreamableHTTPTool での配線(構築のみ。接続はしない)---


async def test_real_mcp_tool_offline_wiring() -> None:
    pytest.importorskip("agent_framework")
    from agent_framework import MCPStreamableHTTPTool

    client = make_http_client(make_settings())
    try:
        tool = build_github_mcp_tool(make_settings(), client)

        assert isinstance(tool, MCPStreamableHTTPTool)
        assert tool.name == "github"
        assert tool.url == "https://api.githubcopilot.com/mcp/"
        # 未接続: サーバーのツール群は connect(Agent の run / __aenter__)まで空
        assert tool.is_connected is False
        assert tool.functions == []
    finally:
        await client.aclose()
