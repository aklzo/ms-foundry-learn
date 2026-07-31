"""決定論ランキング — 元実装(scout.py)のスコア式をそのまま移植。

式(_score_story):

    keyword_score    = キーワードヒット数 × 16
    discussion_score = min(comments, 150) / 3
    points_score     = min(points, 500) / 10
    freshness_score  = max(0, 35 - rank)

キーワード照合は「正規化タイトル文字列への部分一致」(元実装のまま)。
つまり "tool" は "tools" にも "toolchain" にもヒットする — 仕様として保存し
テストで固定する。ノイズ語・要約文(signal note)の文言も元実装と同一。

移植で見つけた元実装の癖(README の学びにも記載): ライブ経路では
キーワード 0 件の記事の要約が必ず "agent builders" を含むため、curate の
フィルタ ``keyword_hits or "agent" in summary`` は実質ノイズ除去だけに
縮退している。挙動互換を優先してそのまま移植し、テストで文書化する。
"""

from __future__ import annotations

import re
from dataclasses import replace

from .hn import Story

AGENT_KEYWORDS = frozenset(
    {
        "agent",
        "agents",
        "agentic",
        "automation",
        "autonomous",
        "coding",
        "framework",
        "llm",
        "mcp",
        "orchestration",
        "tool",
        "workflow",
    }
)

NOISE_WORDS = ("ask hn: who is hiring", "freelance", "hiring")

DEFAULT_TOP_N = 5


def keyword_hits(title: str) -> set[str]:
    normalized = re.sub(r"[^a-z0-9]+", " ", title.lower())
    return {keyword for keyword in AGENT_KEYWORDS if keyword in normalized}


def is_noise(title: str) -> bool:
    lowered = title.lower()
    return any(noise in lowered for noise in NOISE_WORDS)


def score_story(story: Story) -> float:
    keyword_score = len(keyword_hits(story.title)) * 16
    discussion_score = min(story.comments, 150) / 3
    points_score = min(story.points, 500) / 10
    freshness_score = max(0, 35 - story.rank)
    return keyword_score + discussion_score + points_score + freshness_score


def summarize_story(story: Story) -> str:
    """記事ごとの決定論 signal note(元 _summarize_story の文言を保存)。"""
    hits = sorted(keyword_hits(story.title))
    if hits:
        signal = ", ".join(hits[:3])
        return (
            f"Strong Hacker News signal around {signal}; review for architecture, "
            "tooling, or workflow ideas."
        )
    return (
        "Useful background item for agent builders; monitor discussion before "
        "promoting it to the daily brief."
    )


def curate_stories(stories: list[Story], *, top_n: int = DEFAULT_TOP_N) -> list[Story]:
    """signal note 付与 → フィルタ → スコア降順 → 上位 top_n(元 curate_stories)。"""
    annotated = [
        story if story.summary else replace(story, summary=summarize_story(story))
        for story in stories
    ]
    candidates = [
        story
        for story in annotated
        if not is_noise(story.title)
        and (keyword_hits(story.title) or "agent" in story.summary.lower())
    ]
    return sorted(candidates, key=score_story, reverse=True)[:top_n]


def clamp_top_n(value: int) -> int:
    """元 scheduler_api._as_top_n の 1〜10 クランプを移植。"""
    return max(1, min(int(value), 10))
