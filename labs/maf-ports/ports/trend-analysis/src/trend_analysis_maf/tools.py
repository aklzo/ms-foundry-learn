"""エージェントに渡す関数ツール。

元アプリのツール対応:
- ``DuckDuckGoTools``(news_collector)→ :func:`make_search_tool`
- ``Newspaper4kTools``(summary_writer)→ :func:`make_read_article_tool`

MAF の ``Agent(tools=[...])`` は素の callable を受け取り、シグネチャと
docstring からツールスキーマを推論する。クロージャで httpx クライアントを
束縛し、テストでは ``httpx.MockTransport`` を注入する。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import httpx
from bs4 import BeautifulSoup

from .search import ddg_search

ARTICLE_CHAR_BUDGET = 6_000


def make_search_tool(http: httpx.AsyncClient) -> Callable[..., Awaitable[str]]:
    async def search_news(query: str, max_results: int = 5) -> str:
        """Search the web for recent news articles. Returns a markdown list of
        title, URL and snippet for each hit.

        Args:
            query: Search query, e.g. "AI agent startups funding 2026".
            max_results: Number of results to return (1-10).
        """
        hits = await ddg_search(http, query, max(1, min(max_results, 10)))
        if not hits:
            return "(no results)"
        lines = [
            f"- **{hit.title}**\n  {hit.url}\n  {hit.snippet}" for hit in hits
        ]
        return "\n".join(lines)

    return search_news


def make_read_article_tool(http: httpx.AsyncClient) -> Callable[..., Awaitable[str]]:
    async def read_article(url: str) -> str:
        """Fetch a news article and return its readable text (truncated).

        Args:
            url: Absolute URL of the article to read.
        """
        try:
            response = await http.get(url)
        except httpx.HTTPError as exc:
            return f"(fetch failed: {exc})"
        if response.status_code != 200:
            return f"(fetch failed: HTTP {response.status_code})"
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()
        text = " ".join(soup.get_text(separator=" ").split())
        if len(text) > ARTICLE_CHAR_BUDGET:
            text = text[:ARTICLE_CHAR_BUDGET] + " …(truncated)"
        return text or "(empty page)"

    return read_article
