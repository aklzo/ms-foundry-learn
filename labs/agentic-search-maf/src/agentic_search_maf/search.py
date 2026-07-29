"""Provider-agnostic web search, ported from ``crates/core/src/search/``.

MAF has no web-search abstraction of its own (search is expected to arrive
as agent tools or MCP servers), so this stays plain Python behind the same
three-provider surface as the Rust version.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import parse_qs, urlsplit

import httpx
from bs4 import BeautifulSoup

from .config import SearchConfig, SearchProviderKind, SecretKey
from .errors import SearchError

DDG_ENDPOINT = "https://html.duckduckgo.com/html/"
SERPER_ENDPOINT = "https://google.serper.dev/search"


@dataclass
class SearchHit:
    """One search engine result."""

    title: str
    url: str
    snippet: str


class SearchProvider(Protocol):
    """Provider-agnostic web search interface (the Rust ``SearchProvider``
    trait)."""

    async def search(self, query: str, limit: int) -> list[SearchHit]: ...


class DuckDuckGo:
    """Keyless search via DuckDuckGo's HTML endpoint. Default provider so
    the tool works out of the box; prefer SearXNG for heavier use."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def search(self, query: str, limit: int) -> list[SearchHit]:
        response = await self._http.get(DDG_ENDPOINT, params={"q": query})
        if response.status_code != 200:
            raise SearchError(f"duckduckgo returned HTTP {response.status_code}")
        return parse_ddg_results(response.text)[:limit]


class SearxNg:
    """Client for a self-hosted SearXNG instance (JSON API)."""

    def __init__(self, http: httpx.AsyncClient, base_url: str) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")

    async def search(self, query: str, limit: int) -> list[SearchHit]:
        response = await self._http.get(
            f"{self._base_url}/search", params={"q": query, "format": "json"}
        )
        if response.status_code != 200:
            raise SearchError(f"searxng returned HTTP {response.status_code}")
        results = response.json().get("results", [])
        return [
            SearchHit(
                title=result.get("title", ""),
                url=result["url"],
                snippet=result.get("content", ""),
            )
            for result in results[:limit]
            if "url" in result
        ]


class Serper:
    """Serper.dev client: a keyed wrapper over Google search results. High
    rate limits make it the production-grade alternative to scraping
    DuckDuckGo when parallel/high-frequency search is needed."""

    def __init__(self, http: httpx.AsyncClient, api_key: SecretKey) -> None:
        self._http = http
        self._api_key = api_key

    async def search(self, query: str, limit: int) -> list[SearchHit]:
        response = await self._http.post(
            SERPER_ENDPOINT,
            headers={"X-API-KEY": self._api_key.expose()},
            json={"q": query, "num": limit},
        )
        if response.status_code != 200:
            raise SearchError(f"serper returned HTTP {response.status_code}")
        organic = response.json().get("organic", [])
        return [
            SearchHit(
                title=result.get("title", ""),
                url=result["link"],
                snippet=result.get("snippet", ""),
            )
            for result in organic[:limit]
            if "link" in result
        ]


def build_provider(config: SearchConfig, http: httpx.AsyncClient | None = None) -> SearchProvider:
    http = http or default_http_client()
    if config.provider is SearchProviderKind.DUCKDUCKGO:
        return DuckDuckGo(http)
    if config.provider is SearchProviderKind.SEARXNG:
        return SearxNg(http, config.searxng_base_url)
    return Serper(http, config.serper_api_key)


def default_http_client() -> httpx.AsyncClient:
    from .fetch import USER_AGENT

    return httpx.AsyncClient(
        timeout=httpx.Timeout(20.0, connect=10.0),
        headers={"User-Agent": USER_AGENT},
    )


def parse_ddg_results(html: str) -> list[SearchHit]:
    """Parse the result list out of the DuckDuckGo HTML page."""
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
    """DuckDuckGo wraps result URLs in a ``/l/?uddg=<encoded>`` redirect."""
    absolute = f"https:{href}" if href.startswith("//") else href
    parts = urlsplit(absolute)
    if not parts.scheme:
        return None
    if parts.path == "/l/":
        targets = parse_qs(parts.query).get("uddg")
        return targets[0] if targets else None
    return absolute
