"""エージェントに渡す関数ツール+収集ファクトの保管庫。

元アプリのツール対応:
- ``WebSearchTool``(research_agent・OpenAI ホスト実行)→ :func:`make_search_tool`
  (自前 DDG 検索。ports/trend-analysis/src/trend_analysis_maf/tools.py の
  ``make_search_tool`` のコピー。ツール名のみ search_news → search_web)
- ``save_important_fact``(research_agent・Streamlit session_state へ保存)
  → :func:`make_save_fact_tool` + :class:`FactStore`(クロージャで束縛した
  明示的なストア。UI のセッション状態という暗黙の共有メモリを型付きに置換)

MAF の ``Agent(tools=[...])`` は素の callable を受け取り、シグネチャと
docstring からツールスキーマを推論する。クロージャで依存(httpx / store)を
束縛し、テストでは ``httpx.MockTransport`` や素の FactStore を注入する。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from .search import ddg_search


@dataclass
class SavedFact:
    """research 中に保存されたファクト(元アプリの collected_facts の1件)。"""

    fact: str
    source: str
    timestamp: str


class FactStore:
    """1 回のワークフロー実行中に収集したファクトの保管庫。"""

    def __init__(self) -> None:
        self._facts: list[SavedFact] = []

    def add(self, fact: str, source: str) -> None:
        self._facts.append(
            SavedFact(
                fact=fact,
                source=source or "Not specified",
                timestamp=datetime.now(UTC).strftime("%H:%M:%S"),
            )
        )

    def snapshot(self) -> list[SavedFact]:
        return list(self._facts)

    def clear(self) -> None:
        self._facts.clear()


def make_search_tool(http: httpx.AsyncClient) -> Callable[..., Awaitable[str]]:
    async def search_web(query: str, max_results: int = 5) -> str:
        """Search the web for information on a query. Returns a markdown list
        of title, URL and snippet for each hit.

        Args:
            query: Search query, e.g. "best espresso machines under $500".
            max_results: Number of results to return (1-10).
        """
        hits = await ddg_search(http, query, max(1, min(max_results, 10)))
        if not hits:
            return "(no results)"
        lines = [
            f"- **{hit.title}**\n  {hit.url}\n  {hit.snippet}" for hit in hits
        ]
        return "\n".join(lines)

    return search_web


def make_save_fact_tool(store: FactStore) -> Callable[..., str]:
    # 元アプリのシグネチャは ``source: str = None``(型と既定値が不整合)。
    # 空文字を「未指定」として扱う形に直し、既定の表示は元と同じ
    # "Not specified" にする。
    def save_important_fact(fact: str, source: str = "") -> str:
        """Save an important fact discovered during research.

        Args:
            fact: The important fact to save.
            source: Optional source of the fact (URL or publication name).
        """
        store.add(fact, source)
        return f"Fact saved: {fact}"

    return save_important_fact
