"""決定論ランキングのオフラインテスト — 元実装(scout.py)との式互換を固定。

ゴールデン値は元リポジトリの scout.py を直接実行して得たもの
(sample_stories 5 篇のスコアと並び順)。式を触ればここが割れる。
"""

import random

import pytest
from conftest import SAMPLE_HITS, algolia_payload

from hn_briefing_maf.hn import parse_algolia_hits
from hn_briefing_maf.ranking import (
    clamp_top_n,
    curate_stories,
    is_noise,
    keyword_hits,
    score_story,
    summarize_story,
)


def sample_stories():
    return parse_algolia_hits(algolia_payload(SAMPLE_HITS))


#: 元 sample_stories の front-page rank(1, 4, 8, 12, 17)。Algolia 移植では
#: rank が応答リスト位置になるため、式のゴールデン検証では元の値を再現する。
ORIGINAL_RANKS = (1, 4, 8, 12, 17)


def original_sample_stories():
    from dataclasses import replace

    return [
        replace(story, rank=rank)
        for story, rank in zip(sample_stories(), ORIGINAL_RANKS, strict=True)
    ]


# --- keyword_hits / is_noise(元 _keyword_hits / _is_noise)---


def test_keyword_hits_normalizes_and_matches_substrings() -> None:
    hits = keyword_hits("Show HN: An open-source framework for reliable AI agent workflows")
    assert hits == {"agent", "framework", "workflow"}

    # 部分一致は元実装の仕様: "tool" は "tools" にヒットし "mcp" は綴りが無いと拾えない
    assert keyword_hits("Model Context Protocol adoption in developer tools") == {"tool"}
    # 記号は空白に正規化される
    assert "llm" in keyword_hits("Tool-using LLM apps")


def test_is_noise_matches_original_noise_words() -> None:
    assert is_noise("Ask HN: Who is hiring? (July 2026)")
    assert is_noise("We are hiring engineers")
    assert not is_noise("Lessons from running coding agents on production repositories")


# --- score_story(元 _score_story の式)---


def test_score_formula_components() -> None:
    story = sample_stories()[0]  # 3 hits / 116 comments / 428 points / rank 1
    assert score_story(story) == pytest.approx(3 * 16 + 116 / 3 + 428 / 10 + 34)


def test_score_caps_comments_points_and_rank() -> None:
    from dataclasses import replace

    capped = replace(
        sample_stories()[0], points=9999, comments=9999, rank=99
    )  # 上限: comments 150 / points 500 / freshness 下限 0
    assert score_story(capped) == pytest.approx(3 * 16 + 150 / 3 + 500 / 10 + 0)


def test_golden_scores_match_original_implementation() -> None:
    """元 scout.py の sample_stories を同一入力(rank 含む)で流したときの
    ゴールデン値(スコア・降順)と一致すること。式を触ればここが割れる。"""
    ranked = curate_stories(original_sample_stories())

    assert [round(score_story(story), 4) for story in ranked] == [
        163.4667,
        124.9333,
        106.2,
        73.7667,
        71.0667,
    ]
    assert [story.hn_url.split("=")[-1] for story in ranked] == [
        "40100001",  # framework/agent/workflow ×16 が効く
        "40100003",  # coding/agent/agents
        "40100002",  # tool のみだが points/comments が厚い
        "40100005",  # tool/llm
        "40100004",  # automation
    ]


# --- curate_stories(元 curate_stories のフィルタ+並べ替え)---


def test_curate_is_deterministic_under_input_shuffle() -> None:
    stories = sample_stories()
    baseline = curate_stories(stories)

    for seed in range(5):
        shuffled = stories[:]
        random.Random(seed).shuffle(shuffled)
        assert curate_stories(shuffled) == baseline


def test_curate_drops_noise_and_respects_top_n() -> None:
    from conftest import EXTRA_HITS

    stories = parse_algolia_hits(algolia_payload([*SAMPLE_HITS, *EXTRA_HITS]))
    curated = curate_stories(stories, top_n=3)

    assert len(curated) == 3
    assert all("who is hiring" not in story.title.lower() for story in curated)


def test_curate_annotates_summaries_with_original_wording() -> None:
    curated = curate_stories(sample_stories(), top_n=1)

    assert curated[0].summary == (
        "Strong Hacker News signal around agent, framework, workflow; review for "
        "architecture, tooling, or workflow ideas."
    )


def test_keywordless_story_passes_filter_via_fallback_summary() -> None:
    """移植で見つけた元実装の癖の文書化: キーワード 0 件でも fallback summary が
    "agent builders" を含むためフィルタを通過する(= フィルタは実質ノイズ除去のみ)。"""
    stories = parse_algolia_hits(
        algolia_payload([{"objectID": "1", "title": "A quiet story about databases",
                          "url": "https://example.com/q", "points": 10, "num_comments": 2}])
    )
    assert keyword_hits(stories[0].title) == set()
    assert summarize_story(stories[0]).startswith("Useful background item for agent builders")

    assert len(curate_stories(stories)) == 1


def test_clamp_top_n_ports_scheduler_bounds() -> None:
    """元 scheduler_api._as_top_n の 1〜10 クランプ。"""
    assert clamp_top_n(0) == 1
    assert clamp_top_n(5) == 5
    assert clamp_top_n(99) == 10
