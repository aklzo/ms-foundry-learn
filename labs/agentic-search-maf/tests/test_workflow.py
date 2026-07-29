"""Integration tests for the workflow loop, mirroring the Rust tests in
``agent/mod.rs``. All external dependencies (LLM roles, search, fetch) are
scripted fakes; no network or model is needed."""

from dataclasses import dataclass
from typing import Any

import pytest

pytest.importorskip("agent_framework")

from agentic_search_maf.config import Limits  # noqa: E402
from agentic_search_maf.fetch import PageContent  # noqa: E402
from agentic_search_maf.llm import ResearchAgents  # noqa: E402
from agentic_search_maf.search import SearchHit  # noqa: E402
from agentic_search_maf.workflow import Report, build_research_workflow  # noqa: E402


@dataclass
class FakeResponse:
    text: str
    value: Any = None


class ScriptedAgent:
    """Returns queued responses in order, repeating the last one."""

    def __init__(self, *responses: str) -> None:
        self._responses = list(responses)
        self.calls = 0

    async def run(self, message: str) -> FakeResponse:
        index = min(self.calls, len(self._responses) - 1)
        self.calls += 1
        return FakeResponse(text=self._responses[index])


class FakeSearch:
    async def search(self, query: str, limit: int) -> list[SearchHit]:
        slug = query.replace(" ", "-")
        return [
            SearchHit(
                title=f"Result for {query}",
                url=f"https://example.com/{slug}",
                snippet="snippet",
            )
        ]


class FakeFetcher:
    async def fetch(self, url: str) -> PageContent:
        return PageContent(url=url, text="Some page text")


def make_agents(evaluator: ScriptedAgent) -> ResearchAgents:
    return ResearchAgents(
        planner=ScriptedAgent('{"sub_questions": ["q1"], "queries": ["first query"]}'),
        extractor=ScriptedAgent(
            '{"findings": [{"statement": "Mock fact", "published_hint": "2026-06-01"}]}'
        ),
        evaluator=evaluator,
        reporter=ScriptedAgent("# Mock report"),
    )


async def run_workflow(agents: ResearchAgents) -> tuple[Report, list]:
    workflow = build_research_workflow(agents, FakeSearch(), FakeFetcher(), Limits(max_retries=0))
    report = None
    progress = []
    async for event in workflow.run("test question", stream=True):
        if event.type == "intermediate":
            progress.append(event.data)
        elif event.type == "output":
            report = event.data
    assert report is not None, "workflow must yield a report"
    return report, progress


async def test_loop_runs_followup_iteration_then_stops_when_sufficient():
    evaluator = ScriptedAgent(
        # Insufficient on the first pass, sufficient on the second.
        '{"freshness": {"score": 80, "issues": []},'
        ' "correctness": {"score": 80, "issues": []},'
        ' "coverage": {"score": 40, "issues": ["missing detail"]},'
        ' "is_sufficient": false, "followup_queries": ["second query"]}',
        '{"freshness": {"score": 85, "issues": []},'
        ' "correctness": {"score": 85, "issues": []},'
        ' "coverage": {"score": 90, "issues": []},'
        ' "is_sufficient": true, "followup_queries": []}',
    )
    report, progress = await run_workflow(make_agents(evaluator))
    assert report.iterations == 2, "should iterate once more to fill the gap"
    assert report.evaluation.sufficient()
    assert "Mock report" in report.markdown
    assert "Self-assessment" in report.markdown
    assert report.finding_count == 1, "duplicate mock facts must dedupe"

    from agentic_search_maf.events import EvaluationDone, PlanReady, QueryStarted

    kinds = [type(p) for p in progress]
    assert kinds.count(PlanReady) == 1
    assert kinds.count(QueryStarted) == 2, "one query per iteration"
    assert kinds.count(EvaluationDone) == 2, "one evaluation per iteration"


async def test_evaluator_failure_still_produces_a_report():
    evaluator = ScriptedAgent("{ this is not valid json")
    report, _ = await run_workflow(make_agents(evaluator))
    assert report.finding_count == 1, "a broken evaluator must not discard gathered findings"
    assert "Mock report" in report.markdown
    assert not report.evaluation.sufficient(), "falls back to default scores"
