"""実 MAF ``Agent`` + 実 ``MCPStreamableHTTPTool`` + 素の callable の配線
オフラインテスト(ネットワーク不要)。

MAF の Agent は tools=[...] の MCPTool を通常ツールと分離して
``agent.mcp_tools`` に保持し、素の callable は通常ツールとしてスキーマ推論
する。ここでは**接続前の配線**だけを固定する(github-mcp の方針)。"""

import pytest

pytest.importorskip("agent_framework")

from test_tools import make_settings

from db_routing_iq_maf.agents import INSTRUCTIONS, build_chat_client, build_routing_agent
from db_routing_iq_maf.tools import build_kb_mcp_tool, make_http_client, make_web_search_tool


async def test_agent_separates_mcp_tool_from_web_search() -> None:
    settings = make_settings()
    client = make_http_client(settings)
    try:
        kb_tool = build_kb_mcp_tool(settings, client)
        agent = build_routing_agent(
            build_chat_client(settings), kb_tool, make_web_search_tool(object())
        )

        # MCP ツールは mcp_tools 側、web_search は通常ツール側
        assert agent.mcp_tools == [kb_tool]
        plain_tools = agent.default_options.get("tools") or []
        assert len(plain_tools) == 1
        tool = plain_tools[0]
        name = getattr(tool, "name", None) or getattr(tool, "__name__", None)
        assert name == "web_search"
        assert callable(agent.run)
    finally:
        await client.aclose()


async def test_agent_instructions_encode_the_cascade() -> None:
    """元アプリの三段カスケードの残滓が instructions に現れることを固定:
    KB 優先(段 1+2 はサービス側)/ 空振り時のみ web_search(段 3)/
    "Web Search Result:" プレフィックス(元 _handle_web_fallback の表示規約)。"""
    settings = make_settings()
    client = make_http_client(settings)
    try:
        kb_tool = build_kb_mcp_tool(settings, client)
        agent = build_routing_agent(
            build_chat_client(settings), kb_tool, make_web_search_tool(object())
        )

        assert agent.default_options.get("instructions") == INSTRUCTIONS
    finally:
        await client.aclose()

    assert "knowledge_base_retrieve" in INSTRUCTIONS
    assert "web_search" in INSTRUCTIONS
    assert "Web Search Result:" in INSTRUCTIONS
    # 元 query_database の system prompt の回答規約(strictly on the context)
    assert "strictly" in INSTRUCTIONS


async def test_agent_is_async_context_manager() -> None:
    """CLI の ``async with agent:`` が MCP 接続ライフサイクルを担える面を固定。"""
    settings = make_settings()
    client = make_http_client(settings)
    try:
        kb_tool = build_kb_mcp_tool(settings, client)
        agent = build_routing_agent(
            build_chat_client(settings), kb_tool, make_web_search_tool(object())
        )

        assert hasattr(agent, "__aenter__")
        assert hasattr(agent, "__aexit__")
    finally:
        await client.aclose()
