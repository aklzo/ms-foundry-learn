"""キーレス Web 検索(DuckDuckGo HTML)。

元アプリの ``WebSearchTool``(OpenAI Agents SDK 組み込み・OpenAI ホスト実行)
の置き換え。実装は ports/trend-analysis/src/trend_analysis_maf/search.py の
コピー(相対 import できないためファイルコピー。変更は User-Agent のみ)。
Foundry の Web search ツール(Agent Service 組み込み)は DPA 対象外・別課金の
ため、本ポートでも自前検索を既定とする(README 参照)。
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

import httpx
from bs4 import BeautifulSoup

DDG_ENDPOINT = "https://html.duckduckgo.com/html/"
USER_AGENT = "research-handoff-maf/0.1 (+https://github.com/aklzo/ms-foundry-learn)"


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
