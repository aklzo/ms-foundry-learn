"""共有フィクスチャ: Algolia 応答の scripted payload と MockTransport。

payload は tests 内で完結する固定データ(録画不要)。元実装の
sample_stories の 5 篇を Algolia の hit 形式に写し、ノイズ記事・URL null の
Ask HN・points null の記事を足して収集/フィルタの分岐を全部踏む。
"""

from __future__ import annotations

from typing import Any

import httpx

from hn_briefing_maf.hn import USER_AGENT

#: 元 scout.py sample_stories と同じ 5 篇(points/comments/並び順も同一)を
#: Algolia hit 形式にしたもの。ランキングのゴールデンテストの入力になる。
SAMPLE_HITS: list[dict[str, Any]] = [
    {
        "objectID": "40100001",
        "title": "Show HN: An open-source framework for reliable AI agent workflows",
        "url": "https://example.com/reliable-agent-workflows",
        "points": 428,
        "num_comments": 116,
    },
    {
        "objectID": "40100002",
        "title": "Model Context Protocol adoption in developer tools",
        "url": "https://example.com/mcp-developer-tools",
        "points": 312,
        "num_comments": 84,
    },
    {
        "objectID": "40100003",
        "title": "Lessons from running coding agents on production repositories",
        "url": "https://example.com/coding-agents-production",
        "points": 256,
        "num_comments": 73,
    },
    {
        "objectID": "40100004",
        "title": "Why long-running automation needs better human handoff states",
        "url": "https://example.com/automation-handoff-states",
        "points": 184,
        "num_comments": 41,
    },
    {
        "objectID": "40100005",
        "title": "A lightweight eval harness for tool-using LLM applications",
        "url": "https://example.com/tool-using-evals",
        "points": 141,
        "num_comments": 29,
    },
]

#: 収集の分岐用: ノイズ(who is hiring)/ URL null の Ask HN / points null
EXTRA_HITS: list[dict[str, Any]] = [
    {
        "objectID": "40100006",
        "title": "Ask HN: Who is hiring? (July 2026)",
        "url": None,
        "points": 500,
        "num_comments": 700,
    },
    {
        "objectID": "40100007",
        "title": "Ask HN: How do you test LLM agents?",
        "url": None,
        "points": 90,
        "num_comments": 60,
    },
    {
        "objectID": "40100008",
        "title": "A quiet story about databases",
        "url": "https://example.com/quiet-databases",
        "points": None,
        "num_comments": None,
    },
]


def algolia_payload(hits: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"hits": SAMPLE_HITS if hits is None else hits}


def algolia_client(
    payload: dict[str, Any] | None = None, *, status: int = 200
) -> tuple[httpx.AsyncClient, list[httpx.Request]]:
    """Algolia を演じる MockTransport クライアント(受信リクエストも返す)。"""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=payload if payload is not None else algolia_payload())

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), headers={"User-Agent": USER_AGENT}
    )
    return client, seen
