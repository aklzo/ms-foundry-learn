"""キーレス Web 検索(DuckDuckGo HTML)。

元アプリの ``TavilySearchResults``(Tavily API・要 API キー)の置き換え。
実装は ports/research-handoff/src/research_handoff_maf/search.py のコピー
(出典: ports/trend-analysis/src/trend_analysis_maf/search.py。相対 import
できないためファイルコピー。変更は User-Agent のみ)。

元実装の tenacity ``retry(stop_after_attempt(3), wait_exponential(multiplier=1,
min=4, max=10))`` に対応するリトライは :func:`search_with_retry` として移植
(sleep 注入でオフラインテスト可能にする)。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

import httpx
from bs4 import BeautifulSoup

DDG_ENDPOINT = "https://html.duckduckgo.com/html/"
USER_AGENT = "corrective-rag-maf/0.1 (+https://github.com/aklzo/ms-foundry-learn)"

#: 元実装の stop_after_attempt(3)
MAX_SEARCH_ATTEMPTS = 3

#: 元実装の wait_exponential(multiplier=1, min=4, max=10)の実効待ち秒
#: (試行間は 2 回: 4s, 8s。10s キャップには達しない)
RETRY_WAITS = (4.0, 8.0)


class SearchError(RuntimeError):
    pass


@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str


def default_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(20.0, connect=10.0),
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    )


async def ddg_search(http: httpx.AsyncClient, query: str, limit: int) -> list[SearchHit]:
    response = await http.get(DDG_ENDPOINT, params={"q": query})
    if response.status_code != 200:
        raise SearchError(f"duckduckgo returned HTTP {response.status_code}")
    return parse_ddg_results(response.text)[:limit]


async def search_with_retry(
    search: Callable[[str], Awaitable[list[SearchHit]]],
    query: str,
    *,
    attempts: int = MAX_SEARCH_ATTEMPTS,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> list[SearchHit]:
    """検索をリトライ付きで実行する(元アプリの execute_tavily_search 相当)。

    最終試行まで失敗したら最後の例外を送出する。呼び出し側(web_search
    ノード)は元実装同様、失敗しても文書リストを変えずに続行する。
    """
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return await search(query)
        except Exception as exc:  # noqa: BLE001 - 元実装は検索の全例外をリトライ対象にしていた
            last_error = exc
            if attempt < attempts - 1:
                wait = RETRY_WAITS[min(attempt, len(RETRY_WAITS) - 1)]
                await sleep(wait)
    assert last_error is not None
    raise last_error


def parse_ddg_results(html: str) -> list[SearchHit]:
    soup = BeautifulSoup(html, "html.parser")
    hits: list[SearchHit] = []
    for result in soup.select("div.result"):
        link = result.select_one("a.result__a")
        if link is None:
            continue
        href = link.get("href")
        if not href:
            continue
        url = _resolve_redirect(str(href))
        if url is None:
            continue
        snippet_el = result.select_one(".result__snippet")
        hits.append(
            SearchHit(
                title=link.get_text(strip=True),
                url=url,
                snippet=snippet_el.get_text(strip=True) if snippet_el else "",
            )
        )
    return hits


def _resolve_redirect(href: str) -> str | None:
    """DuckDuckGo は結果 URL を ``/l/?uddg=<encoded>`` リダイレクトで包む。"""
    absolute = f"https:{href}" if href.startswith("//") else href
    parts = urlsplit(absolute)
    if not parts.scheme:
        return None
    if parts.path == "/l/":
        targets = parse_qs(parts.query).get("uddg")
        return targets[0] if targets else None
    return absolute
