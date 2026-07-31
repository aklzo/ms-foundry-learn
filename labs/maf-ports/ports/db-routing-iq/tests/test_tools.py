"""MCP ツール配線+Web fallback ツールのオフラインテスト。

実 knowledge base へは接続しない。MCP ツールクラスの境界は ``tool_cls`` の
コンストラクタ注入、DDG は httpx.MockTransport で置き換える
(PORTING.md §4 の scripted fake 方針)。"""

from typing import Any

import httpx
import pytest

from db_routing_iq_maf.config import DbRoutingIqSettings
from db_routing_iq_maf.tools import (
    KB_RETRIEVE_TOOL,
    KB_TOOL_NAME,
    SSE_READ_TIMEOUT_SECONDS,
    build_kb_headers,
    build_kb_mcp_tool,
    make_http_client,
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


def test_tool_cls_injection_receives_kb_mcp_url_and_client() -> None:
    sentinel_client = object()

    tool = build_kb_mcp_tool(make_settings(), sentinel_client, tool_cls=FakeMcpTool)

    assert tool.name == KB_TOOL_NAME == "knowledge_base"
    assert tool.url == (
        "https://srch-example.search.windows.net/knowledgebases/db-routing-kb/mcp"
        "?api-version=2026-05-01-preview"
    )
    assert tool.kwargs["http_client"] is sentinel_client
    assert tool.kwargs["load_prompts"] is False


def test_tool_allow_list_is_knowledge_base_retrieve_only() -> None:
    """knowledge base の公開ツールは knowledge_base_retrieve のみ。allow-list
    で明示し、サービス側の将来のツール追加でも公開面が広がらないようにする。"""
    tool = build_kb_mcp_tool(make_settings(), object(), tool_cls=FakeMcpTool)

    assert tool.kwargs["allowed_tools"] == [KB_RETRIEVE_TOOL] == ["knowledge_base_retrieve"]


def test_tool_url_follows_kb_name_override() -> None:
    tool = build_kb_mcp_tool(
        make_settings(kb_name="other-kb"), object(), tool_cls=FakeMcpTool
    )

    assert "/knowledgebases/other-kb/mcp" in tool.url


# --- httpx クライアント(api-key はここに載る。接続はしない)---


async def test_make_http_client_carries_api_key_without_redirects() -> None:
    client = make_http_client(make_settings())
    try:
        assert client.headers["api-key"] == "search-key"
        # オリジン外へのキー漏出防止: リダイレクト追従は無効(httpx 既定)のまま
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
        tool = build_kb_mcp_tool(make_settings(), client)

        assert isinstance(tool, MCPStreamableHTTPTool)
        assert tool.name == "knowledge_base"
        assert tool.allowed_tools == ["knowledge_base_retrieve"]
        # 未接続: サーバーのツール群は connect(Agent の run / __aenter__)まで空
        assert tool.is_connected is False
        assert tool.functions == []
    finally:
        await client.aclose()


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
