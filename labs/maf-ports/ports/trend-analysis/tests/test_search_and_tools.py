"""検索パーサとツール関数のオフラインテスト(httpx.MockTransport 使用)。"""

import httpx
import pytest

from trend_analysis_maf.search import parse_ddg_results
from trend_analysis_maf.tools import make_read_article_tool, make_search_tool

DDG_FIXTURE = """
<html><body>
<div class="result">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fnews1">Startup A raises $10M</a>
  <div class="result__snippet">Agent infrastructure startup A announced...</div>
</div>
<div class="result">
  <a class="result__a" href="https://example.com/news2">New AI framework launched</a>
  <div class="result__snippet">A new framework for building agents...</div>
</div>
<div class="result"><span>no link here</span></div>
</body></html>
"""


def test_parse_ddg_results_resolves_redirects() -> None:
    hits = parse_ddg_results(DDG_FIXTURE)
    assert len(hits) == 2
    assert hits[0].title == "Startup A raises $10M"
    assert hits[0].url == "https://example.com/news1"  # uddg リダイレクト解決
    assert hits[1].url == "https://example.com/news2"
    assert "framework" in hits[1].snippet


async def test_search_tool_formats_markdown() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert "html.duckduckgo.com" in str(request.url)
        return httpx.Response(200, text=DDG_FIXTURE)

    http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    search_news = make_search_tool(http)
    result = await search_news(query="ai startups", max_results=5)
    assert "**Startup A raises $10M**" in result
    assert "https://example.com/news1" in result


async def test_read_article_strips_boilerplate_and_truncates() -> None:
    page = (
        "<html><body><nav>menu</nav><script>x()</script>"
        "<article>" + ("Important sentence. " * 500) + "</article></body></html>"
    )

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=page)

    http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    read_article = make_read_article_tool(http)
    text = await read_article(url="https://example.com/a")
    assert "menu" not in text and "x()" not in text
    assert text.endswith("…(truncated)")


async def test_read_article_reports_http_error() -> None:
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(404))
    )
    read_article = make_read_article_tool(http)
    assert "HTTP 404" in await read_article(url="https://example.com/gone")


def test_tool_signatures_are_introspectable() -> None:
    """MAF はシグネチャからツールスキーマを推論するため、クロージャでも
    __name__ とアノテーションが保たれていることを保証する。"""
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    search_news = make_search_tool(http)
    read_article = make_read_article_tool(http)
    from typing import get_type_hints

    assert search_news.__name__ == "search_news"
    assert read_article.__name__ == "read_article"
    assert get_type_hints(search_news)["query"] is str
    assert get_type_hints(read_article)["url"] is str
    assert search_news.__doc__ and "Search the web" in search_news.__doc__


@pytest.mark.parametrize("bad", ["", "/relative/only"])
def test_parse_ddg_skips_unresolvable_hrefs(bad: str) -> None:
    html = f'<div class="result"><a class="result__a" href="{bad}">t</a></div>'
    assert parse_ddg_results(html) == []
