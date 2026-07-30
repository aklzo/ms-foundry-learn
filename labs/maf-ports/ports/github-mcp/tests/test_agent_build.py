"""実 MAF ``Agent`` + 実 ``MCPStreamableHTTPTool`` の配線オフラインテスト
(ネットワーク不要)。

MAF の Agent は tools=[...] に混ぜた MCPTool を通常ツールと分離して
``agent.mcp_tools`` に保持し、run 時(または ``async with agent:``)に接続して
サーバーのツール群を展開する(agent_framework 1.12.1 _agents.py 841 / 1375 行)。
ここでは**接続前の配線**だけを固定する。"""

import pytest

pytest.importorskip("agent_framework")

from test_tool_build import make_settings

from github_mcp_maf.agents import INSTRUCTIONS, build_chat_client, build_github_agent
from github_mcp_maf.tools import build_github_mcp_tool, make_http_client


async def test_agent_holds_mcp_tool_separately_from_plain_tools() -> None:
    settings = make_settings()
    client = make_http_client(settings)
    try:
        tool = build_github_mcp_tool(settings, client)
        agent = build_github_agent(build_chat_client(settings), tool)

        # MCP ツールは通常ツール(default_options["tools"])ではなく mcp_tools 側
        assert agent.mcp_tools == [tool]
        assert not agent.default_options.get("tools")
        assert callable(agent.run)
    finally:
        await client.aclose()


async def test_agent_instructions_match_original_app() -> None:
    settings = make_settings()
    client = make_http_client(settings)
    try:
        tool = build_github_mcp_tool(settings, client)
        agent = build_github_agent(build_chat_client(settings), tool)

        assert agent.default_options.get("instructions") == INSTRUCTIONS
        assert INSTRUCTIONS.startswith("You are a GitHub assistant.")
    finally:
        await client.aclose()


async def test_agent_is_async_context_manager() -> None:
    """CLI の ``async with agent:`` が MCP 接続ライフサイクルを担える面を固定。"""
    settings = make_settings()
    client = make_http_client(settings)
    try:
        tool = build_github_mcp_tool(settings, client)
        agent = build_github_agent(build_chat_client(settings), tool)

        assert hasattr(agent, "__aenter__")
        assert hasattr(agent, "__aexit__")
    finally:
        await client.aclose()
