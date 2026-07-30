"""検索パーサとツール関数のオフラインテスト(httpx.MockTransport 使用)。
検索まわりは ports/trend-analysis/tests/test_search_and_tools.py を踏襲。"""

import re

import httpx

from research_handoff_maf.search import parse_ddg_results
from research_handoff_maf.tools import FactStore, make_save_fact_tool, make_search_tool

DDG_FIXTURE = """
<html><body>
<div class="result">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Freview1">Best budget espresso machines</a>
  <div class="result__snippet">We tested 12 machines under $500...</div>
</div>
<div class="result">
  <a class="result__a" href="https://example.com/review2">Espresso for beginners</a>
  <div class="result__snippet">Upgrading from a French press...</div>
</div>
<div class="result"><span>no link here</span></div>
</body></html>
"""


def test_parse_ddg_results_resolves_redirects() -> None:
    hits = parse_ddg_results(DDG_FIXTURE)
    assert len(hits) == 2
    assert hits[0].title == "Best budget espresso machines"
    assert hits[0].url == "https://example.com/review1"  # uddg リダイレクト解決
    assert hits[1].url == "https://example.com/review2"
    assert "French press" in hits[1].snippet


async def test_search_tool_formats_markdown() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert "html.duckduckgo.com" in str(request.url)
        return httpx.Response(200, text=DDG_FIXTURE)

    http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    search_web = make_search_tool(http)
    result = await search_web(query="espresso machines", max_results=5)
    assert "**Best budget espresso machines**" in result
    assert "https://example.com/review1" in result


def test_save_fact_tool_records_to_store() -> None:
    store = FactStore()
    save_important_fact = make_save_fact_tool(store)

    confirmation = save_important_fact(
        fact="Machine X costs $450", source="https://example.com/review1"
    )
    assert confirmation == "Fact saved: Machine X costs $450"

    facts = store.snapshot()
    assert len(facts) == 1
    assert facts[0].fact == "Machine X costs $450"
    assert facts[0].source == "https://example.com/review1"
    assert re.fullmatch(r"\d{2}:\d{2}:\d{2}", facts[0].timestamp)


def test_save_fact_tool_defaults_source_like_original() -> None:
    """元アプリと同じく、出典未指定は "Not specified" と記録される。"""
    store = FactStore()
    save_important_fact = make_save_fact_tool(store)
    save_important_fact(fact="Fact without a source")
    assert store.snapshot()[0].source == "Not specified"


def test_fact_store_clear_and_snapshot_isolation() -> None:
    store = FactStore()
    store.add("a", "s")
    snapshot = store.snapshot()
    store.clear()
    assert store.snapshot() == []
    assert len(snapshot) == 1  # snapshot はコピー(clear の影響を受けない)


def test_tool_signatures_are_introspectable() -> None:
    """MAF はシグネチャからツールスキーマを推論するため、クロージャでも
    __name__ とアノテーションが保たれていることを保証する。"""
    from typing import get_type_hints

    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    search_web = make_search_tool(http)
    save_important_fact = make_save_fact_tool(FactStore())

    assert search_web.__name__ == "search_web"
    assert save_important_fact.__name__ == "save_important_fact"
    assert get_type_hints(search_web)["query"] is str
    assert get_type_hints(save_important_fact)["fact"] is str
    assert search_web.__doc__ and "Search the web" in search_web.__doc__
    assert save_important_fact.__doc__ and "Save an important fact" in save_important_fact.__doc__
