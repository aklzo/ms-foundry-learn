"""3 役割エージェントの組み立て(元アプリの Agent 定義に対応)。

元(Agno): news_collector / summary_writer / trend_analyzer をすべて
Gemini 2.5 Flash で作り、手続きコードで直列に ``run()``。
移植後: 同じ 3 役割を MAF ``Agent`` として作り、直列実行は workflow.py の
グラフに移す。モデルは Foundry のデプロイ(既定 gpt-5.4-mini)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from .config import FoundrySettings
from .tools import make_read_article_tool, make_search_tool


class SupportsRun(Protocol):
    """workflow が必要とする最小面: ``await run(text)`` → ``.text`` を持つ応答。
    テストでは scripted fake が置き換える。"""

    async def run(self, message: str) -> Any: ...


@dataclass
class TrendAgents:
    news_collector: SupportsRun
    summary_writer: SupportsRun
    trend_analyzer: SupportsRun


COLLECTOR_INSTRUCTIONS = (
    "You are the News Collector. Use the search_news tool to gather the latest "
    "news articles on the topic the user gives you. Run 2-3 focused queries "
    "(different angles: funding, product launches, market shifts). Return a "
    "markdown list of the most relevant articles: title, URL, and a one-line "
    "note on why it matters. Collect 5-10 articles. Do not analyze trends yet."
)

SUMMARIZER_INSTRUCTIONS = (
    "You are the Summary Writer. You receive a markdown list of news articles "
    "(title, URL, snippet). For the 3-5 most substantive articles, use the "
    "read_article tool to fetch the full text, then write a concise summary "
    "per article (3-4 sentences, keep the URL). If fetching fails, summarize "
    "from the snippet and note it. Output: one markdown section per article."
)

ANALYZER_INSTRUCTIONS = (
    "You are the Trend Analyzer. From the article summaries you receive, "
    "identify emerging trends and concrete startup opportunities. Output "
    "markdown with three sections: '## Emerging trends' (3-5 bullet points "
    "with evidence from the summaries), '## Startup opportunities' (2-4 "
    "specific ideas with target user and why now), '## Risks & unknowns'."
)


def build_chat_client(settings: FoundrySettings) -> Any:
    from agent_framework.openai import OpenAIChatClient

    return OpenAIChatClient(
        model=settings.model,
        api_key=settings.api_key,
        base_url=settings.openai_v1_endpoint,
    )


def build_agents(chat_client: Any, http: httpx.AsyncClient) -> TrendAgents:
    from agent_framework import Agent

    return TrendAgents(
        news_collector=Agent(
            chat_client,
            instructions=COLLECTOR_INSTRUCTIONS,
            name="news_collector",
            tools=[make_search_tool(http)],
        ),
        summary_writer=Agent(
            chat_client,
            instructions=SUMMARIZER_INSTRUCTIONS,
            name="summary_writer",
            tools=[make_read_article_tool(http)],
        ),
        trend_analyzer=Agent(
            chat_client,
            instructions=ANALYZER_INSTRUCTIONS,
            name="trend_analyzer",
        ),
    )
