"""収集 → ランキング → ブリーフ生成の直列 3 段を MAF workflow で表現する。

元アプリは ``run_ambient_scout()`` が手続き的に curate → render を呼ぶだけ
だった(スケジューラ経路は LLM 不使用)。移植では:

    BriefingRequest ─▶ Collect(HN Algolia) ─▶ Rank(決定論) ─▶ Brief(LLM) ─▶ Brief

- Collect / Rank は純関数(hn.py / ranking.py)を Executor に包んだだけ。
  進捗は intermediate output(StageDone)で流す(trend-analysis の型)
- Brief 段だけが LLM(agents.py の briefing agent)。テストでは
  ScriptedAgent に置換
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Never

import httpx
from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler

from .agents import SupportsRun
from .briefing import Brief, build_brief, render_digest
from .hn import Story, fetch_front_page
from .ranking import DEFAULT_TOP_N, clamp_top_n, curate_stories

# --- グラフを流れるメッセージ ---------------------------------------------


@dataclass
class BriefingRequest:
    """ワークフロー入力(元 scheduler ペイロードの top_n に対応)。"""

    top_n: int = DEFAULT_TOP_N


@dataclass
class CollectedStories:
    request: BriefingRequest
    stories: list[Story] = field(default_factory=list)


@dataclass
class RankedStories:
    request: BriefingRequest
    stories: list[Story] = field(default_factory=list)


@dataclass
class StageDone:
    """進捗イベント(intermediate output)。"""

    stage: str
    count: int


# --- Executors -------------------------------------------------------------


class CollectExecutor(Executor):
    """HN Algolia からフロントページ記事を収集する(hn.py の薄い包み)。"""

    def __init__(self, http: httpx.AsyncClient) -> None:
        super().__init__(id="collect")
        self._http = http

    @handler
    async def collect(
        self, request: BriefingRequest, ctx: WorkflowContext[CollectedStories, StageDone]
    ) -> None:
        stories = await fetch_front_page(self._http)
        await ctx.yield_output(StageDone(stage="collect", count=len(stories)))
        await ctx.send_message(CollectedStories(request=request, stories=stories))


class RankExecutor(Executor):
    """決定論ランキング(ranking.py の純関数。LLM もネットワークも無し)。"""

    def __init__(self) -> None:
        super().__init__(id="rank")

    @handler
    async def rank(
        self, collected: CollectedStories, ctx: WorkflowContext[RankedStories, StageDone]
    ) -> None:
        curated = curate_stories(
            collected.stories, top_n=clamp_top_n(collected.request.top_n)
        )
        await ctx.yield_output(StageDone(stage="rank", count=len(curated)))
        await ctx.send_message(RankedStories(request=collected.request, stories=curated))


class BriefExecutor(Executor):
    """digest を LLM に渡してブリーフ本文を書かせ、Brief を出力する。"""

    def __init__(self, agent: SupportsRun, *, now: dt.datetime | None = None) -> None:
        super().__init__(id="brief")
        self._agent = agent
        self._now = now  # テスト用の固定時刻シーム

    @handler
    async def brief(self, ranked: RankedStories, ctx: WorkflowContext[Never, Brief]) -> None:
        digest = render_digest(ranked.stories)
        response = await self._agent.run(
            "Today's deterministically ranked Hacker News digest:\n\n"
            f"{digest}\n\n"
            "Write today's engineering brief."
        )
        await ctx.yield_output(build_brief(ranked.stories, response.text, now=self._now))


# --- 組み立て ---------------------------------------------------------------


def build_briefing_workflow(
    briefing_agent: SupportsRun,
    http: httpx.AsyncClient,
    *,
    now: dt.datetime | None = None,
):
    """``await workflow.run(BriefingRequest(...))`` で実行する単発ワークフロー。
    進捗は ``workflow.run(request, stream=True)`` の intermediate イベント。"""
    collect = CollectExecutor(http)
    rank = RankExecutor()
    brief = BriefExecutor(briefing_agent, now=now)

    return (
        WorkflowBuilder(
            start_executor=collect,
            output_from=[brief],
            intermediate_output_from=[collect, rank],
        )
        .add_edge(collect, rank)
        .add_edge(rank, brief)
        .build()
    )
