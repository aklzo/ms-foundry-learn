"""HN 収集 — 元実装の HTML スクレイピングを HN Algolia API(キーレス)に置換。

元(scout.py)は ``news.ycombinator.com/news`` の table マークアップを
``HTMLParser`` で 100 行かけてパースしていた(``HNFrontPageParser``)。
移植では公式ミラーの Algolia Search API を使う:

    GET https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=30

- キー不要・JSON 応答(points / num_comments / objectID が構造化されて返る)
  のためパーサーが消え、``MockTransport`` でオフラインテストできる
- ``rank`` は応答リスト内の位置(1 始まり)。Algolia は「現在フロントページに
  ある記事」を返すが表示順位そのものは持たないため、元実装の front-page rank の
  **近似**になる(README の元との差分参照)
- Ask HN 等は ``url`` が null → HN アイテム URL にフォールバック(元実装の
  ``item?id=`` 絶対化と同じ役割)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

ALGOLIA_ENDPOINT = "https://hn.algolia.com/api/v1/search"
DEFAULT_HITS_PER_PAGE = 30
USER_AGENT = "hn-briefing-maf/0.1 (+https://github.com/aklzo/ms-foundry-learn)"


class CollectError(RuntimeError):
    pass


@dataclass(frozen=True)
class Story:
    """元実装の Story と同じ形(summary はランキング段が付与する)。"""

    title: str
    url: str
    hn_url: str
    points: int
    comments: int
    rank: int
    summary: str = ""


def default_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(20.0, connect=10.0),
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    )


def parse_algolia_hits(payload: Any) -> list[Story]:
    """Algolia の検索応答(``hits`` 配列)を Story 列に変換する(純関数)。"""
    hits = payload.get("hits", []) if isinstance(payload, dict) else []
    stories: list[Story] = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        title = str(hit.get("title") or "").strip()
        if not title:
            continue
        object_id = str(hit.get("objectID") or "")
        hn_url = f"https://news.ycombinator.com/item?id={object_id}" if object_id else ""
        stories.append(
            Story(
                title=title,
                url=str(hit.get("url") or "") or hn_url,  # Ask HN 等は url が null
                hn_url=hn_url,
                points=int(hit.get("points") or 0),
                comments=int(hit.get("num_comments") or 0),
                rank=len(stories) + 1,
                summary="",
            )
        )
    return stories


async def fetch_front_page(
    http: httpx.AsyncClient, *, hits_per_page: int = DEFAULT_HITS_PER_PAGE
) -> list[Story]:
    """現在フロントページにある記事を取得する(元 fetch_hn_front_page 相当)。"""
    try:
        response = await http.get(
            ALGOLIA_ENDPOINT,
            params={"tags": "front_page", "hitsPerPage": hits_per_page},
        )
    except httpx.HTTPError as exc:
        raise CollectError(f"Could not fetch Hacker News (Algolia): {exc}") from exc
    if response.status_code != 200:
        raise CollectError(f"HN Algolia API returned HTTP {response.status_code}")
    return parse_algolia_hits(response.json())
