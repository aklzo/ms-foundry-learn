"""直列ワークフローのオフラインテスト。LLM は ScriptedAgent、HN は
MockTransport(ネットワーク不要)。パターンは trend-analysis を踏襲。"""

import datetime as dt
from dataclasses import dataclass

import pytest

pytest.importorskip("agent_framework")

from conftest import EXTRA_HITS, SAMPLE_HITS, algolia_client, algolia_payload

from hn_briefing_maf.briefing import PACIFIC, Brief
from hn_briefing_maf.hn import CollectError
from hn_briefing_maf.workflow import BriefingRequest, StageDone, build_briefing_workflow

FIXED_NOW = dt.datetime(2026, 7, 31, 9, 0, tzinfo=PACIFIC)


@dataclass
class FakeResponse:
    text: str


class ScriptedAgent:
    def __init__(self, reply: str = "## Today's brief\n- because") -> None:
        self.reply = reply
        self.received: list[str] = []

    async def run(self, message: str) -> FakeResponse:
        self.received.append(message)
        return FakeResponse(text=self.reply)


async def run_workflow(payload=None, *, top_n: int = 5):
    agent = ScriptedAgent()
    http, _ = algolia_client(payload)
    try:
        workflow = build_briefing_workflow(agent, http, now=FIXED_NOW)
        brief = None
        stages: list[StageDone] = []
        async for event in workflow.run(BriefingRequest(top_n=top_n), stream=True):
            if event.type == "intermediate" and isinstance(event.data, StageDone):
                stages.append(event.data)
            elif event.type == "output":
                brief = event.data
        return brief, stages, agent
    finally:
        await http.aclose()


async def test_sequential_flow_collect_rank_brief() -> None:
    brief, stages, agent = await run_workflow()

    # 進捗イベント: collect(全 5 篇)→ rank(top 5)
    assert [(stage.stage, stage.count) for stage in stages] == [("collect", 5), ("rank", 5)]

    # LLM への入力は決定論 digest(ゴールデン 1 位が先頭)
    assert len(agent.received) == 1
    assert "deterministically ranked" in agent.received[0]
    assert "1. Show HN: An open-source framework" in agent.received[0]

    # 最終成果物: 決定論部分+LLM 本文+固定時刻の件名
    assert isinstance(brief, Brief)
    assert brief.subject == "AgentScout Hacker News brief - 2026-07-31"
    assert brief.brief_md == "## Today's brief\n- because"
    assert [story.hn_url.split("=")[-1] for story in brief.stories][:2] == [
        "40100001",
        "40100003",
    ]


async def test_top_n_is_clamped_and_applied_at_rank_stage() -> None:
    _brief, stages, _ = await run_workflow(top_n=99)  # クランプ → 10(記事は 5 篇)

    assert stages[1].count == 5
    brief3, stages3, _ = await run_workflow(top_n=3)
    assert stages3[1].count == 3
    assert len(brief3.stories) == 3


async def test_noise_and_empty_paths() -> None:
    # ノイズだけ → rank 0 件でも LLM は呼ばれ、digest はフォールバック行
    noise_only = algolia_payload([EXTRA_HITS[0]])
    brief, stages, agent = await run_workflow(noise_only)

    assert [(s.stage, s.count) for s in stages] == [("collect", 1), ("rank", 0)]
    assert "No high-signal agent-building stories found." in agent.received[0]
    assert brief.stories == []


async def test_collect_error_propagates() -> None:
    agent = ScriptedAgent()
    http, _ = algolia_client(status=500)
    try:
        workflow = build_briefing_workflow(agent, http)
        with pytest.raises(Exception) as excinfo:
            await workflow.run(BriefingRequest())
        # MAF がラップしても原因チェーンに CollectError が残ること
        cause = excinfo.value
        seen = False
        while cause is not None:
            if isinstance(cause, CollectError):
                seen = True
                break
            cause = cause.__cause__
        assert seen or isinstance(excinfo.value, CollectError)
    finally:
        await http.aclose()
    assert agent.received == []  # LLM 未到達


async def test_run_without_stream_returns_output() -> None:
    agent = ScriptedAgent()
    http, _ = algolia_client(algolia_payload(SAMPLE_HITS))
    try:
        workflow = build_briefing_workflow(agent, http, now=FIXED_NOW)
        result = await workflow.run(BriefingRequest(top_n=2))
    finally:
        await http.aclose()
    outputs = result.get_outputs() if hasattr(result, "get_outputs") else result
    briefs = outputs if isinstance(outputs, list) else [outputs]
    assert any(isinstance(item, Brief) for item in briefs)
