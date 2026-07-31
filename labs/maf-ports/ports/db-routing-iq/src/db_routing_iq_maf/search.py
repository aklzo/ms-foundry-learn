"""キーレス Web 検索(DuckDuckGo HTML)— 元アプリの Web fallback の置き換え。

元アプリの ``DuckDuckGoSearchRun``(langchain-community)は LangGraph ReAct
エージェントのツールとして単発呼び出し(リトライなし・失敗時は文字列を返す)
だった。移植でも同じく単発呼び出しにする(補正 RAG のような tenacity リトライ
は元に存在しないため持ち込まない)。

実装は ports/corrective-rag/src/corrective_rag_maf/search.py のコピー
(出典: ports/trend-analysis)。変更は User-Agent とリトライ関数の削除のみ。
knowledge base の web knowledge source を使わない判断は README 参照。
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

import httpx
from bs4 import BeautifulSoup

DDG_ENDPOINT = "https://html.duckduckgo.com/html/"
USER_AGENT = "db-routing-iq-maf/0.1 (+https://github.com/aklzo/ms-foundry-learn)"


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
