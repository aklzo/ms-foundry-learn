"""MCP ツール配線+Web fallback ツールのオフラインテスト。

実 knowledge base へは接続しない。MCP ツールクラスの境界は ``tool_cls`` の
コンストラクタ注入、MCP ハンドシェイクと DDG は httpx.MockTransport で置き
換える(PORTING.md §4 の scripted fake 方針)。"""

import json
from typing import Any

import httpx
import pytest

from db_routing_iq_maf.config import DbRoutingIqSettings
from db_routing_iq_maf.tools import (
    KB_RETRIEVE_TOOL,
    KB_TOOL_NAME,
    build_kb_headers,
    build_kb_mcp_tool,
    make_web_search_tool,
)


def make_settings(**overrides: Any) -> DbRoutingIqSettings:
    values: dict[str, Any] = {
        "openai_v1_endpoint": "https://aif-example.openai.azure.com/openai/v1",
        "model": "gpt-5.4-mini",
        "api_key": "foundry-key",
        "search_endpoint": "https://srch-example.search.windows.net",
        "search_api_key": "search-key",
        "kb_name": "db-routing-kb",
        "app_insights_connection_string": None,
    }
    values.update(overrides)
    return DbRoutingIqSettings(**values)


class FakeMcpTool:
    """MCPStreamableHTTPTool 互換のコンストラクタ記録フェイク。"""

    def __init__(self, name: str, url: str, **kwargs: Any) -> None:
        self.name = name
        self.url = url
        self.kwargs = kwargs


# --- ヘッダー(MCP エンドポイントの api-key 認証)---


def test_build_kb_headers_uses_api_key_header() -> None:
    """AI Search MCP の認証は Authorization: Bearer か api-key ヘッダー。
    ラボは管理キー(api-key)で統一(README)。"""
    assert build_kb_headers(make_settings()) == {"api-key": "search-key"}


# --- ツール定義の組み立て(コンストラクタ注入)---


def test_tool_cls_injection_receives_kb_mcp_url_and_static_headers() -> None:
    tool = build_kb_mcp_tool(make_settings(), tool_cls=FakeMcpTool)

    assert tool.name == KB_TOOL_NAME == "knowledge_base"
    assert tool.url == (
        "https://srch-example.search.windows.net/knowledgebases/db-routing-kb/mcp"
        "?api-version=2026-08-01-preview"
    )
    # api-key は static_headers(MAF 1.19 — 同一オリジン限定で全リクエストに付与)
    assert tool.kwargs["static_headers"] == {"api-key": "search-key"}
    # HTTP クライアントは既定で MAF に任せる(生成・破棄もツール側)
    assert tool.kwargs["http_client"] is None
    assert tool.kwargs["load_prompts"] is False


def test_tool_allow_list_is_knowledge_base_retrieve_only() -> None:
    """knowledge base の公開ツールは knowledge_base_retrieve のみ。allow-list
    で明示し、サービス側の将来のツール追加でも公開面が広がらないようにする。"""
    tool = build_kb_mcp_tool(make_settings(), tool_cls=FakeMcpTool)

    assert tool.kwargs["allowed_tools"] == [KB_RETRIEVE_TOOL] == ["knowledge_base_retrieve"]


def test_tool_url_follows_kb_name_override() -> None:
    tool = build_kb_mcp_tool(make_settings(kb_name="other-kb"), tool_cls=FakeMcpTool)

    assert "/knowledgebases/other-kb/mcp" in tool.url


# --- 実 MCPStreamableHTTPTool での配線(構築のみ。接続はしない)---


async def test_real_mcp_tool_offline_wiring() -> None:
    pytest.importorskip("agent_framework")
    from agent_framework import MCPStreamableHTTPTool

    tool = build_kb_mcp_tool(make_settings())

    assert isinstance(tool, MCPStreamableHTTPTool)
    assert tool.name == "knowledge_base"
    assert tool.allowed_tools == ["knowledge_base_retrieve"]
    # 未接続: サーバーのツール群は connect(Agent の run / __aenter__)まで空
    assert tool.is_connected is False
    assert tool.functions == []


# --- 実 MCPStreamableHTTPTool のハンドシェイク(MockTransport の偽 KB サーバー)---


def fake_kb_mcp_server(seen: list[tuple[str, str | None]]):
    """KB の MCP エンドポイントを模した JSON-RPC ハンドラ(streamable HTTP の
    JSON 応答形)。公開ツールは knowledge_base_retrieve と、allow-list の効き目を
    見るための余計なツール 1 つ。受けたリクエストの (method, api-key) を記録する。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method != "POST":
            seen.append((request.method, request.headers.get("api-key")))
            return httpx.Response(405)
        message = json.loads(request.content)
        seen.append((message.get("method", "?"), request.headers.get("api-key")))
        if "id" not in message:  # notifications/initialized 等
            return httpx.Response(202)
        if message["method"] == "initialize":
            result: dict[str, Any] = {
                "protocolVersion": message["params"]["protocolVersion"],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fake-knowledge-base", "version": "0"},
            }
        elif message["method"] == "tools/list":
            schema = {"type": "object", "properties": {"queries": {"type": "array"}}}
            result = {
                "tools": [
                    {"name": KB_RETRIEVE_TOOL, "description": "retrieve", "inputSchema": schema},
                    {"name": "unexpected_tool", "description": "x", "inputSchema": schema},
                ]
            }
        else:
            result = {}
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": message["id"], "result": result},
            headers={"mcp-session-id": "session-1"},
        )

    return handler


async def test_handshake_carries_api_key_and_exposes_only_retrieve() -> None:
    """接続段階(initialize / tools/list)から api-key が付くこと — 1.12 系の
    header_provider で踏んだ罠(接続時にヘッダーが付かない)が static_headers
    で起きないことを、実 MCPStreamableHTTPTool のハンドシェイクで固定する。"""
    pytest.importorskip("agent_framework")
    seen: list[tuple[str, str | None]] = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake_kb_mcp_server(seen))) as http:
        tool = build_kb_mcp_tool(make_settings(), http_client=http)
        async with tool:
            assert tool.is_connected
            assert [f.name for f in tool.functions] == [KB_RETRIEVE_TOOL]

    methods = [method for method, _ in seen]
    assert "initialize" in methods
    assert "tools/list" in methods
    assert all(api_key == "search-key" for _, api_key in seen), seen


# --- Web fallback ツール(自前 DDG。MockTransport)---

DDG_HTML = """
<html><body>
  <div class="result">
    <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fnews">
      Example headline</a>
    <div class="result__snippet">Example snippet text.</div>
  </div>
</body></html>
"""


def ddg_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_web_search_formats_hits_as_markdown_list() -> None:
    async with ddg_client(lambda request: httpx.Response(200, text=DDG_HTML)) as http:
        web_search = make_web_search_tool(http)
        result = await web_search("latest news")

    assert "**Example headline**" in result
    assert "https://example.com/news" in result
    assert "Example snippet text." in result


async def test_web_search_reports_empty_results() -> None:
    async with ddg_client(lambda request: httpx.Response(200, text="<html></html>")) as http:
        result = await make_web_search_tool(http)("nothing")

    assert result == "(no results)"


async def test_web_search_turns_failures_into_text() -> None:
    """元アプリの web_research は失敗を例外にせず文字列で返す(ReAct 続行用)。"""
    async with ddg_client(lambda request: httpx.Response(503)) as http:
        result = await make_web_search_tool(http)("anything")

    assert result.startswith("Search failed:")
    assert "general knowledge" in result


def test_web_search_schema_surface() -> None:
    """MAF はシグネチャ+docstring からツールスキーマを推論する。ツール名と
    「KB が空振りのときだけ使う」という説明が公開面に残ることを固定。"""
    web_search = make_web_search_tool(object())

    assert web_search.__name__ == "web_search"
    assert "knowledge base" in (web_search.__doc__ or "")
