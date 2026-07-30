"""ワークフローのオフラインテスト。LLM は scripted fake(ネットワーク不要)。
パターンは labs/agentic-search-maf/tests/test_workflow.py の ScriptedAgent を踏襲。"""

from dataclasses import dataclass

import pytest

pytest.importorskip("agent_framework")

from trend_analysis_maf.agents import TrendAgents
from trend_analysis_maf.workflow import (
    StageDone,
    TrendReport,
    build_trend_workflow,
)


@dataclass
class FakeResponse:
    text: str


class ScriptedAgent:
    """受け取ったメッセージを記録し、決められた応答を返す。"""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.received: list[str] = []

    async def run(self, message: str) -> FakeResponse:
        self.received.append(message)
        return FakeResponse(text=self.reply)


def make_agents() -> tuple[TrendAgents, ScriptedAgent, ScriptedAgent, ScriptedAgent]:
    collector = ScriptedAgent("- **Article A**\n  https://a.example\n  snippet A")
    summarizer = ScriptedAgent("## Article A\nSummary of A. https://a.example")
    analyzer = ScriptedAgent("## Emerging trends\n- Trend X\n## Startup opportunities\n- Idea Y")
    return (
        TrendAgents(
            news_collector=collector,
            summary_writer=summarizer,
            trend_analyzer=analyzer,
        ),
        collector,
        summarizer,
        analyzer,
    )


async def test_sequential_flow_and_prompt_chaining() -> None:
    agents, collector, summarizer, analyzer = make_agents()
    workflow = build_trend_workflow(agents)

    report = None
    stages: list[str] = []
    async for event in workflow.run("AI agent developer tools", stream=True):
        if event.type == "intermediate" and isinstance(event.data, StageDone):
            stages.append(event.data.stage)
        elif event.type == "output":
            report = event.data

    # 3段が順に1回ずつ呼ばれる
    assert [len(collector.received), len(summarizer.received), len(analyzer.received)] == [1, 1, 1]
    assert stages == ["collect", "summarize"]

    # プロンプトの連鎖: トピック → 収集結果 → 要約結果
    assert "AI agent developer tools" in collector.received[0]
    assert "Article A" in summarizer.received[0]  # 収集結果が要約に渡る
    assert "Summary of A" in analyzer.received[0]  # 要約結果が分析に渡る
    assert "AI agent developer tools" in analyzer.received[0]  # トピックも渡る

    # 最終成果物に全段の出力が残る
    assert isinstance(report, TrendReport)
    assert report.topic == "AI agent developer tools"
    assert "Article A" in report.articles_md
    assert "Summary of A" in report.summaries_md
    assert "Trend X" in report.analysis_md


async def test_run_without_stream_returns_output() -> None:
    agents, *_ = make_agents()
    workflow = build_trend_workflow(agents)
    result = await workflow.run("fintech")
    outputs = result.get_outputs() if hasattr(result, "get_outputs") else result
    # API 差異に耐える: 何らかの形で TrendReport が取れること
    if isinstance(outputs, list):
        assert any(isinstance(o, TrendReport) for o in outputs)
    else:
        assert isinstance(outputs, TrendReport)
