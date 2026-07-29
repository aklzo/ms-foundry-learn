"""Page retrieval with SSRF guard, redirect re-validation, response size
cap, and timeout. Ported from ``fetch/mod.rs``.

One deliberate structural difference: ``reqwest`` lets a custom redirect
*policy* validate every hop inside the client; httpx has no equivalent hook,
so redirects are followed manually here (``follow_redirects=False`` plus an
explicit loop) to preserve the same security property — a public URL cannot
bounce the client into a private address via ``Location`` headers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urljoin

import httpx

from .. import __version__
from ..config import Limits
from ..errors import FetchError
from ..retry import with_backoff
from . import guard
from .extract import html_to_text

USER_AGENT = f"agentic-search-maf/{__version__}"

MAX_REDIRECTS = 5


@dataclass
class PageContent:
    """A fetched page reduced to plain text."""

    url: str
    text: str


class PageFetcher(Protocol):
    """Abstraction over page retrieval so the agent loop can be tested
    offline (the Rust ``PageFetcher`` trait)."""

    async def fetch(self, url: str) -> PageContent: ...


class HttpFetcher:
    """Real HTTP fetcher implementing :class:`PageFetcher`."""

    def __init__(self, limits: Limits) -> None:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(limits.fetch_timeout_secs, connect=10.0),
            headers={"User-Agent": USER_AGENT},
            follow_redirects=False,
        )
        self._max_content_chars = limits.max_content_chars
        self._max_response_bytes = limits.max_response_bytes
        self._max_retries = limits.max_retries

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch(self, url: str) -> PageContent:
        # Validation is deterministic, so it stays outside the retry loop;
        # only the network attempt is retried.
        guard.validate_url(url)
        await guard.ensure_public_host(url)

        final_url, body = await with_backoff(self._max_retries, lambda: self._fetch_once(url))
        html = body.decode("utf-8", errors="replace")
        return PageContent(url=final_url, text=html_to_text(html, self._max_content_chars))

    async def _fetch_once(self, url: str) -> tuple[str, bytes]:
        """One network attempt: GET with manual redirect following (each hop
        re-validated), reject non-2xx and non-textual bodies, then read the
        capped body."""
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            async with self._client.stream("GET", current) as response:
                if response.is_redirect:
                    location = response.headers.get("location", "")
                    current = urljoin(current, location)
                    # Re-validate every redirect hop (scheme, host, DNS).
                    guard.validate_url(current)
                    await guard.ensure_public_host(current)
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if content_type and not _is_textual(content_type):
                    raise FetchError(f"{current} has unsupported content type '{content_type}'")
                return current, await self._read_capped(response)
        raise FetchError(f"{url}: too many redirects")

    async def _read_capped(self, response: httpx.Response) -> bytes:
        body = bytearray()
        async for chunk in response.aiter_bytes():
            remaining = self._max_response_bytes - len(body)
            if len(chunk) >= remaining:
                body.extend(chunk[:remaining])
                break
            body.extend(chunk)
        return bytes(body)


def _is_textual(content_type: str) -> bool:
    lowered = content_type.lower()
    return lowered.startswith("text/") or "html" in lowered or "xml" in lowered or "json" in lowered
