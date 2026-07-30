"""検索パーサとリトライのオフラインテスト(httpx.MockTransport 使用)。
DDG パーサは ports/research-handoff/tests/test_search_and_tools.py を踏襲。
リトライは元アプリの tenacity retry(stop_after_attempt(3),
wait_exponential(min=4, max=10)) の移植(search_with_retry)を検証する。
"""

import httpx
import pytest

from corrective_rag_maf.search import (
    MAX_SEARCH_ATTEMPTS,
    SearchError,
    SearchHit,
    ddg_search,
    parse_ddg_results,
    search_with_retry,
)

DDG_FIXTURE = """
<html><body>
<div class="result">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpricing">Azure AI Search pricing</a>
  <div class="result__snippet">Basic tier starts at...</div>
</div>
<div class="result">
  <a class="result__a" href="https://example.com/docs">Vector search docs</a>
  <div class="result__snippet">HNSW configuration...</div>
</div>
<div class="result"><span>no link here</span></div>
</body></html>
"""


def test_parse_ddg_results_resolves_redirects() -> None:
    hits = parse_ddg_results(DDG_FIXTURE)
    assert len(hits) == 2
    assert hits[0].title == "Azure AI Search pricing"
    assert hits[0].url == "https://example.com/pricing"  # uddg リダイレクト解決
    assert hits[1].url == "https://example.com/docs"
    assert "HNSW" in hits[1].snippet


async def test_ddg_search_limits_results() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert "html.duckduckgo.com" in str(request.url)
        return httpx.Response(200, text=DDG_FIXTURE)

    http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    hits = await ddg_search(http, "azure ai search pricing", limit=1)
    assert len(hits) == 1


async def test_ddg_search_raises_on_http_error() -> None:
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    with pytest.raises(SearchError):
        await ddg_search(http, "q", limit=3)


# --- search_with_retry(元 tenacity 相当)---------------------------------


def make_sleeper(record: list[float]):
    async def sleeper(seconds: float) -> None:
        record.append(seconds)

    return sleeper


async def test_retry_succeeds_after_transient_failures() -> None:
    calls: list[str] = []
    sleeps: list[float] = []

    async def flaky(query: str) -> list[SearchHit]:
        calls.append(query)
        if len(calls) < 3:
            raise SearchError("transient")
        return [SearchHit(title="t", url="u", snippet="s")]

    hits = await search_with_retry(flaky, "q", sleep=make_sleeper(sleeps))
    assert len(hits) == 1
    assert len(calls) == 3
    # wait_exponential(multiplier=1, min=4, max=10) の実効待ち: 4s, 8s
    assert sleeps == [4.0, 8.0]


async def test_retry_gives_up_after_max_attempts() -> None:
    """試行は元実装と同じ 3 回で打ち切り(無限リトライしない)。"""
    calls: list[str] = []
    sleeps: list[float] = []

    async def always_fails(query: str) -> list[SearchHit]:
        calls.append(query)
        raise SearchError("down")

    with pytest.raises(SearchError):
        await search_with_retry(always_fails, "q", sleep=make_sleeper(sleeps))
    assert len(calls) == MAX_SEARCH_ATTEMPTS == 3
    assert sleeps == [4.0, 8.0]  # 最終試行の後には待たない


async def test_retry_first_try_success_does_not_sleep() -> None:
    sleeps: list[float] = []

    async def ok(query: str) -> list[SearchHit]:
        return []

    assert await search_with_retry(ok, "q", sleep=make_sleeper(sleeps)) == []
    assert sleeps == []
