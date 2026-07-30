"""GitHub 照会エージェントの組み立て(元アプリの agno Agent に対応)。

元: ``Agent(tools=[mcp_tools], instructions=dedent(...), markdown=True)`` —
モデル指定なし(agno 既定 = OpenAI)、instructions はリポジトリ分析の観点
(issues / PRs / activity)を列挙した固定文。

移植後: 同じ単一役割を MAF ``Agent`` として作る。instructions は原文のまま、
tools に MCP ツール(tools.py)を渡す。MAF の Agent は MCPTool を通常ツールと
分けて ``agent.mcp_tools`` に保持し、run 時に未接続なら接続してサーバーの
ツール群を展開する(agent_framework 1.12.1 _agents.py 1375 行)。モデルは
Foundry のデプロイ(既定 gpt-5.4-mini)。
"""

from __future__ import annotations

from typing import Any, Protocol

from .config import GithubMcpSettings

#: 元アプリの instructions(原文のまま。markdown=True 相当の整形指示も本文に含まれる)
INSTRUCTIONS = """\
You are a GitHub assistant. Help users explore repositories and their activity.
- Provide organized, concise insights about the repository
- Focus on facts and data from the GitHub API
- Use markdown formatting for better readability
- Present numerical data in tables when appropriate
- Include links to relevant GitHub pages when helpful
"""


class SupportsRun(Protocol):
    """クエリ実行が必要とする最小面: ``await run(text)`` → ``.text`` を持つ
    応答。テストでは scripted fake が置き換える。"""

    async def run(self, message: str) -> Any: ...


def build_chat_client(settings: GithubMcpSettings) -> Any:
    from agent_framework.openai import OpenAIChatClient

    return OpenAIChatClient(
        model=settings.model,
        api_key=settings.api_key,
        base_url=settings.openai_v1_endpoint,
    )


def build_github_agent(chat_client: Any, mcp_tool: Any) -> SupportsRun:
    from agent_framework import Agent

    return Agent(
        chat_client,
        name="github_agent",
        instructions=INSTRUCTIONS,
        tools=[mcp_tool],
    )
