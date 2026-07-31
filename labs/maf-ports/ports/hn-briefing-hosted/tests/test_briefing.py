"""digest レンダリングと Brief ペイロードのオフラインテスト。"""

import datetime as dt

from conftest import SAMPLE_HITS, algolia_payload

from hn_briefing_maf.briefing import (
    EMPTY_DIGEST_LINE,
    PACIFIC,
    build_brief,
    render_digest,
    subject_for,
)
from hn_briefing_maf.hn import parse_algolia_hits
from hn_briefing_maf.ranking import curate_stories

FIXED_NOW = dt.datetime(2026, 7, 31, 9, 0, tzinfo=PACIFIC)


def ranked_stories():
    return curate_stories(parse_algolia_hits(algolia_payload(SAMPLE_HITS)))


def test_subject_keeps_original_wording_and_date() -> None:
    assert subject_for(FIXED_NOW) == "AgentScout Hacker News brief - 2026-07-31"


def test_digest_lists_stories_in_rank_order_with_signal_lines() -> None:
    stories = ranked_stories()
    digest = render_digest(stories)

    # 先頭はゴールデン 1 位の framework 記事
    assert "1. Show HN: An open-source framework" in digest
    assert "2. Lessons from running coding agents" in digest
    # signal 行は元 render_brief の文言(points / comments / front-page rank)
    assert "Signal: 428 points, 116 comments, front-page rank 1" in digest
    assert "Link: https://example.com/reliable-agent-workflows" in digest
    assert "HN: https://news.ycombinator.com/item?id=40100001" in digest
    # signal note(決定論 summary)も載る
    assert "Strong Hacker News signal around" in digest


def test_digest_renders_fallback_line_when_no_stories() -> None:
    assert EMPTY_DIGEST_LINE in render_digest([])


def test_build_brief_assembles_payload_with_fixed_now() -> None:
    stories = ranked_stories()
    brief = build_brief(stories, "## Brief body\n- why it matters", now=FIXED_NOW)

    assert brief.generated_at == FIXED_NOW.isoformat(timespec="seconds")
    assert brief.subject.endswith("2026-07-31")
    assert brief.brief_md.startswith("## Brief body")
    assert brief.digest_text == render_digest(stories)

    payload = brief.to_dict()
    assert payload["subject"] == brief.subject
    assert len(payload["stories"]) == 5
    assert payload["stories"][0]["points"] == 428  # dataclass が dict 化される
