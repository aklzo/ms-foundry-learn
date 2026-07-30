"""収集 → 要約 → 分析の直列 3 段を MAF workflow グラフで表現する。

元アプリは Streamlit のボタンハンドラ内で 3 回 ``agent.run()`` を手続き的に
呼ぶだけだった。移植では同じ制御フローを ``WorkflowBuilder`` の直列グラフに
載せ、各段の完了を intermediate output(進捗イベント)として流す。

    topic ──▶ Collector ──▶ Summarizer ──▶ Analyzer ──▶ TrendReport
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Never

from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler

from .agents import TrendAgents

# --- グラフを流れるメッセージ ---------------------------------------------


@dataclass
class CollectedNews:
    topic: str
    articles_md: str


@dataclass
class SummarizedNews:
    topic: str
    articles_md: str
    summaries_md: str


@dataclass
class TrendReport:
    """最終成果物。"""

    topic: str
    articles_md: str
    summaries_md: str
    analysis_md: str


@dataclass
class StageDone:
    """進捗イベント(intermediate output)。"""

    stage: str
    chars: int


# --- Executors -------------------------------------------------------------


class CollectorExecutor(Executor):
    def __init__(self, agents: TrendAgents) -> None:
        super().__init__(id="collector")
        self._agents = agents

    @handler
    async def collect(
        self, topic: str, ctx: WorkflowContext[CollectedNews, StageDone]
    ) -> None:
        response = await self._agents.news_collector.run(
            f"Collect recent news on: {topic}"
        )
        articles = response.text
        await ctx.yield_output(StageDone(stage="collect", chars=len(articles)))
        await ctx.send_message(CollectedNews(topic=topic, articles_md=articles))


class SummarizerExecutor(Executor):
    def __init__(self, agents: TrendAgents) -> None:
        super().__init__(id="summarizer")
        self._agents = agents

    @handler
    async def summarize(
        self, news: CollectedNews, ctx: WorkflowContext[SummarizedNews, StageDone]
    ) -> None:
        response = await self._agents.summary_writer.run(
            "Summarize the following articles:\n\n" + news.articles_md
        )
        summaries = response.text
        await ctx.yield_output(StageDone(stage="summarize", chars=len(summaries)))
        await ctx.send_message(
            SummarizedNews(
                topic=news.topic,
                articles_md=news.articles_md,
                summaries_md=summaries,
            )
        )


class AnalyzerExecutor(Executor):
    def __init__(self, agents: TrendAgents) -> None:
        super().__init__(id="analyzer")
        self._agents = agents

    @handler
    async def analyze(
        self, news: SummarizedNews, ctx: WorkflowContext[Never, TrendReport]
    ) -> None:
        response = await self._agents.trend_analyzer.run(
            f"Topic: {news.topic}\n\n"
            "Analyze trends from the following summaries:\n\n" + news.summaries_md
        )
        await ctx.yield_output(
            TrendReport(
                topic=news.topic,
                articles_md=news.articles_md,
                summaries_md=news.summaries_md,
                analysis_md=response.text,
            )
        )


# --- 組み立て ---------------------------------------------------------------


def build_trend_workflow(agents: TrendAgents):
    """``await workflow.run(topic)`` で実行する単発ワークフローを組み立てる。
    進捗は ``workflow.run(topic, stream=True)`` の intermediate イベント。"""
    collector = CollectorExecutor(agents)
    summarizer = SummarizerExecutor(agents)
    analyzer = AnalyzerExecutor(agents)

    return (
        WorkflowBuilder(
            start_executor=collector,
            output_from=[analyzer],
            intermediate_output_from=[collector, summarizer],
        )
        .add_edge(collector, summarizer)
        .add_edge(summarizer, analyzer)
        .build()
    )
