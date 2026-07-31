"""収集(HN Algolia)のオフラインテスト — パース分岐と HTTP 契約を固定。"""

import pytest
from conftest import EXTRA_HITS, algolia_client, algolia_payload

from hn_briefing_maf.hn import (
    ALGOLIA_ENDPOINT,
    CollectError,
    fetch_front_page,
    parse_algolia_hits,
)

# --- parse_algolia_hits(純関数)---


def test_parse_maps_hit_fields_and_assigns_positional_rank() -> None:
    stories = parse_algolia_hits(algolia_payload())

    assert len(stories) == 5
    first = stories[0]
    assert first.title == "Show HN: An open-source framework for reliable AI agent workflows"
    assert first.url == "https://example.com/reliable-agent-workflows"
    assert first.hn_url == "https://news.ycombinator.com/item?id=40100001"
    assert (first.points, first.comments) == (428, 116)
    # rank は応答リスト内の位置(1 始まり)— 元実装の front-page rank の近似
    assert [story.rank for story in stories] == [1, 2, 3, 4, 5]
    # summary はランキング段が付与する(収集段では空)
    assert all(story.summary == "" for story in stories)


def test_parse_falls_back_to_hn_url_when_url_is_null() -> None:
    """Ask HN 等は url が null → HN アイテム URL(元 _absolute_hn_url の役割)。"""
    stories = parse_algolia_hits(algolia_payload(EXTRA_HITS))

    ask_hn = stories[1]
    assert ask_hn.title == "Ask HN: How do you test LLM agents?"
    assert ask_hn.url == "https://news.ycombinator.com/item?id=40100007"


def test_parse_treats_null_counts_as_zero_and_skips_titleless_hits() -> None:
    stories = parse_algolia_hits(
        algolia_payload([*EXTRA_HITS, {"objectID": "40100009", "title": None}])
    )

    quiet = next(story for story in stories if "databases" in story.title)
    assert (quiet.points, quiet.comments) == (0, 0)
    assert len(stories) == 3  # title null の hit は捨てる


def test_parse_tolerates_malformed_payloads() -> None:
    assert parse_algolia_hits({}) == []
    assert parse_algolia_hits({"hits": ["oops", 1]}) == []
    assert parse_algolia_hits(None) == []


# --- fetch_front_page(MockTransport)---


async def test_fetch_requests_front_page_tag_and_parses() -> None:
    http, seen = algolia_client()
    try:
        stories = await fetch_front_page(http, hits_per_page=30)
    finally:
        await http.aclose()

    assert len(stories) == 5
    request = seen[0]
    assert str(request.url).startswith(ALGOLIA_ENDPOINT)
    params = dict(request.url.params)
    assert params == {"tags": "front_page", "hitsPerPage": "30"}
    assert "hn-briefing-maf" in request.headers["User-Agent"]


async def test_fetch_raises_collect_error_on_http_error() -> None:
    http, _ = algolia_client(status=503)
    try:
        with pytest.raises(CollectError, match="503"):
            await fetch_front_page(http)
    finally:
        await http.aclose()
