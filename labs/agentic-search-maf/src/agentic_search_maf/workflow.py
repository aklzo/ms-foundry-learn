"""The research loop as a MAF workflow, replacing ``agent/mod.rs``,
``planner.rs``, ``gatherer.rs``, ``evaluator.rs``, and ``reporter.rs``.

The Rust ``ResearchAgent`` drove the plan → gather → evaluate loop with a
hand-written ``while``; here the same control flow is a cyclic workflow
graph, which is the MAF-native way to express it:

    question ──▶ Planner ──▶ Gatherer ──▶ Evaluator ──▶ Reporter ──▶ Report
                                 ▲             │
                                 └─(不足あり)──┘

Edges out of the evaluator are conditional on the message type: a
``GatherTask`` loops back for another iteration, a ``ReportTask`` exits to
the reporter. The LLM stays confined to the nodes; the transitions are
deterministic code — the "graph orchestration" pattern from
docs/agentic-architecture.md §2.3, wrapped around the original's
single-loop design.

Each call to :func:`build_research_workflow` returns a single-use workflow:
the executors share one :class:`KnowledgeStore` for the run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from agent_framework import (
    Executor,
    WorkflowBuilder,
    WorkflowContext,
    handler,
)
from typing_extensions import Never

from . import prompts
from .config import Limits
from .events import (
    EvaluationDone,
    IterationDone,
    PageProcessed,
    PlanReady,
    QueryStarted,
)
from .fetch import PageFetcher
from .knowledge import Finding, KnowledgeStore
from .llm import ResearchAgents
from .retry import with_backoff
from .schemas import Evaluation, Plan, parse_extraction, parse_structured
from .search import SearchHit, SearchProvider

logger = logging.getLogger(__name__)

#: Character budget for the findings digest passed to evaluator/reporter,
#: sized for small local-model context windows.
DIGEST_BUDGET = 12_000


# Progress reporting: the planner/gatherer/evaluator are designated as
# intermediate-output executors, so their ``ctx.yield_output(payload)`` calls
# surface as ``type="intermediate"`` events on the run stream — MAF's
# replacement for the Rust ``EventSink`` callback. The payloads are the
# :mod:`events` models.


# --- Messages flowing along the graph edges -------------------------------


@dataclass
class GatherTask:
    question: str
    queries: list[str]
    iteration: int


@dataclass
class GatherResult:
    question: str
    iteration: int
    new_findings: int


@dataclass
class ReportTask:
    question: str
    evaluation: Evaluation
    iterations: int


@dataclass
class Report:
    """Final deliverable of a research run."""

    markdown: str
    evaluation: Evaluation
    finding_count: int
    source_count: int
    iterations: int


# --- Executors -------------------------------------------------------------

#: The gatherer sends GatherResult along the graph and yields three kinds of
#: progress payloads as intermediate outputs.
GatherContext = WorkflowContext[GatherResult, QueryStarted | IterationDone | PageProcessed]


class PlannerExecutor(Executor):
    """Plan-and-execute step: turn the research question into sub-questions
    and initial search queries."""

    def __init__(self, agents: ResearchAgents, limits: Limits, today: str) -> None:
        super().__init__(id="planner")
        self._agents = agents
        self._limits = limits
        self._today = today

    @handler
    async def plan(self, question: str, ctx: WorkflowContext[GatherTask, PlanReady]) -> None:
        response = await with_backoff(
            self._limits.max_retries,
            lambda: self._agents.planner.run(prompts.planner_user(question, self._today)),
        )
        plan: Plan = parse_structured(response, Plan)
        if not plan.queries:
            # Degenerate planner output: fall back to searching the question verbatim.
            plan.queries = [question]
        logger.info("plan ready: sub_questions=%s queries=%s", plan.sub_questions, plan.queries)
        await ctx.yield_output(PlanReady(queries=plan.queries))
        await ctx.send_message(GatherTask(question=question, queries=plan.queries, iteration=1))


class GathererExecutor(Executor):
    """Executes every pending query end-to-end: search, fetch unvisited
    pages, extract findings into the store. Per-query failures are logged
    and do not abort the run."""

    def __init__(
        self,
        agents: ResearchAgents,
        search: SearchProvider,
        fetcher: PageFetcher,
        limits: Limits,
        store: KnowledgeStore,
    ) -> None:
        super().__init__(id="gatherer")
        self._agents = agents
        self._search = search
        self._fetcher = fetcher
        self._limits = limits
        self._store = store

    @handler
    async def gather(self, task: GatherTask, ctx: GatherContext) -> None:
        added = 0
        # Queries stay sequential (search API rate limits, DuckDuckGo 429s);
        # pages within a query run concurrently below.
        for query in task.queries[: self._limits.max_queries_per_iteration]:
            if not self._store.mark_query(query):
                continue
            await ctx.yield_output(QueryStarted(query=query))
            try:
                added += await self._gather_query(task.question, query, ctx)
            except Exception as exc:
                logger.warning("query %r failed: %s", query, exc)
        logger.info(
            "gather done: iteration=%d new_findings=%d total=%d",
            task.iteration,
            added,
            len(self._store.findings),
        )
        await ctx.yield_output(
            IterationDone(
                iteration=task.iteration,
                new_findings=added,
                total_findings=len(self._store.findings),
            )
        )
        await ctx.send_message(
            GatherResult(question=task.question, iteration=task.iteration, new_findings=added)
        )

    async def _gather_query(self, question: str, query: str, ctx: GatherContext) -> int:
        import asyncio

        hits = await self._search.search(query, self._limits.max_results_per_query)
        logger.debug("search complete: query=%r hits=%d", query, len(hits))

        # Select the unvisited pages to process this query (sequential, so
        # visited-marking and the per-query cap stay deterministic), then
        # fetch + extract them concurrently. Sharing only happens at the
        # merge step below, which is sequential — no locking needed.
        selected: list[SearchHit] = []
        for hit in hits:
            if len(selected) >= self._limits.max_pages_per_query:
                break
            if self._store.is_visited(hit.url):
                continue
            self._store.mark_visited(hit.url)
            selected.append(hit)

        semaphore = asyncio.Semaphore(max(1, self._limits.max_concurrent_pages))

        async def bounded_extract(hit: SearchHit) -> list[Finding] | Exception:
            async with semaphore:
                try:
                    return await self._extract_page(question, hit)
                except Exception as exc:
                    return exc

        # asyncio.gather preserves input order, matching futures::buffered.
        results = await asyncio.gather(*(bounded_extract(hit) for hit in selected))

        # Merge sequentially: dedup is order-sensitive (keeps first), so a
        # single-threaded merge keeps results reproducible.
        new_findings = 0
        for hit, outcome in zip(selected, results, strict=True):
            if isinstance(outcome, Exception):
                # One bad page must not abort the whole research run.
                logger.warning("skipping page %s: %s", hit.url, outcome)
                continue
            page_added = sum(1 for finding in outcome if self._store.add_finding(finding))
            new_findings += page_added
            await ctx.yield_output(PageProcessed(url=hit.url, new_findings=page_added))
        return new_findings

    async def _extract_page(self, question: str, hit: SearchHit) -> list[Finding]:
        """Fetch and extract a single page into findings. Store-independent
        so it can run concurrently; the caller merges results."""
        page = await self._fetcher.fetch(hit.url)
        if not page.text.strip():
            return []
        response = await with_backoff(
            self._limits.max_retries,
            lambda: self._agents.extractor.run(
                prompts.extractor_user(question, page.url, page.text)
            ),
        )
        return [
            Finding(
                statement=item.statement,
                source_url=page.url,
                source_title=hit.title,
                published_hint=item.published_hint,
                retrieved_at=datetime.now(timezone.utc),
            )
            for item in parse_extraction(response)
        ]


class EvaluatorExecutor(Executor):
    """Reflection step: critique the current findings, then either loop back
    to the gatherer with follow-up queries or exit to the reporter."""

    def __init__(
        self,
        agents: ResearchAgents,
        limits: Limits,
        store: KnowledgeStore,
        today: str,
    ) -> None:
        super().__init__(id="evaluator")
        self._agents = agents
        self._limits = limits
        self._store = store
        self._today = today
        self._last_evaluation = Evaluation()

    @handler
    async def evaluate(
        self,
        result: GatherResult,
        ctx: WorkflowContext[GatherTask | ReportTask, EvaluationDone],
    ) -> None:
        try:
            response = await with_backoff(
                self._limits.max_retries,
                lambda: self._agents.evaluator.run(
                    prompts.evaluator_user(
                        result.question, self._store.digest(DIGEST_BUDGET), self._today
                    )
                ),
            )
            evaluation: Evaluation = parse_structured(response, Evaluation)
        except Exception as exc:
            # A single failed evaluation (e.g. malformed JSON from a small
            # model) must not discard the findings gathered so far: stop
            # iterating and write the report with the last good evaluation.
            logger.warning(
                "evaluation failed; writing report with the last successful evaluation: %s",
                exc,
            )
            await ctx.send_message(
                ReportTask(
                    question=result.question,
                    evaluation=self._last_evaluation,
                    iterations=result.iteration,
                )
            )
            return

        self._last_evaluation = evaluation
        logger.info(
            "evaluation done: freshness=%d correctness=%d coverage=%d sufficient=%s",
            evaluation.freshness.score,
            evaluation.correctness.score,
            evaluation.coverage.score,
            evaluation.sufficient(),
        )
        await ctx.yield_output(EvaluationDone(iteration=result.iteration, evaluation=evaluation))

        followups = evaluation.followup_queries[: self._limits.max_queries_per_iteration]
        no_progress = not followups and result.new_findings == 0
        if (
            evaluation.sufficient()
            or result.iteration >= self._limits.max_iterations
            or no_progress
        ):
            if no_progress and not evaluation.sufficient():
                logger.info("no follow-up queries and no new findings; stopping early")
            await ctx.send_message(
                ReportTask(
                    question=result.question,
                    evaluation=evaluation,
                    iterations=result.iteration,
                )
            )
            return
        await ctx.send_message(
            GatherTask(
                question=result.question,
                queries=followups,
                iteration=result.iteration + 1,
            )
        )


class ReporterExecutor(Executor):
    """Synthesize the final Markdown report from the knowledge store,
    appending a transparency section with the agent's own quality
    assessment."""

    def __init__(
        self,
        agents: ResearchAgents,
        limits: Limits,
        store: KnowledgeStore,
        today: str,
    ) -> None:
        super().__init__(id="reporter")
        self._agents = agents
        self._limits = limits
        self._store = store
        self._today = today

    @handler
    async def report(self, task: ReportTask, ctx: WorkflowContext[Never, Report]) -> None:
        digest = self._store.digest(DIGEST_BUDGET)
        try:
            response = await with_backoff(
                self._limits.max_retries,
                lambda: self._agents.reporter.run(
                    prompts.reporter_user(task.question, digest, self._today)
                ),
            )
            markdown = f"{response.text}\n\n{_quality_footer(task.evaluation)}"
        except Exception as exc:
            # Never lose a long gathering run to a failed synthesis call:
            # fall back to a mechanical digest dump.
            logger.warning("report synthesis failed; emitting fallback report: %s", exc)
            markdown = (
                "# 調査結果(自動整形)\n\n"
                f"> レポート合成に失敗したため({exc})、収集した findings を"
                "整形せずに出力しています。\n\n"
                f"質問: {task.question}\n\n"
                f"## 収集した findings\n\n{digest}\n\n"
                f"{_quality_footer(task.evaluation)}"
            )
        await ctx.yield_output(
            Report(
                markdown=markdown,
                evaluation=task.evaluation,
                finding_count=len(self._store.findings),
                source_count=self._store.source_count(),
                iterations=task.iterations,
            )
        )


def _quality_footer(evaluation: Evaluation) -> str:
    footer = [
        "---\n\n## Self-assessment\n\n",
        "| Axis | Score |\n|---|---|\n",
        f"| Freshness | {evaluation.freshness.score} |\n",
        f"| Correctness | {evaluation.correctness.score} |\n",
        f"| Coverage | {evaluation.coverage.score} |\n",
    ]
    issues = (
        evaluation.freshness.issues + evaluation.correctness.issues + evaluation.coverage.issues
    )
    if issues:
        footer.append("\nKnown limitations:\n")
        footer.extend(f"- {issue}\n" for issue in issues)
    return "".join(footer)


# --- Workflow factory -------------------------------------------------------


def build_research_workflow(
    agents: ResearchAgents,
    search: SearchProvider,
    fetcher: PageFetcher,
    limits: Limits,
):
    """Assemble the single-use research workflow (fresh KnowledgeStore per
    call). Run it with ``await workflow.run(question)`` or stream progress
    events with ``workflow.run(question, stream=True)``."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    store = KnowledgeStore()

    planner = PlannerExecutor(agents, limits, today)
    gatherer = GathererExecutor(agents, search, fetcher, limits, store)
    evaluator = EvaluatorExecutor(agents, limits, store, today)
    reporter = ReporterExecutor(agents, limits, store, today)

    return (
        WorkflowBuilder(
            start_executor=planner,
            output_from=[reporter],
            intermediate_output_from=[planner, gatherer, evaluator],
        )
        .add_edge(planner, gatherer)
        .add_edge(gatherer, evaluator)
        # The self-evaluation loop: insufficient findings cycle back.
        .add_edge(evaluator, gatherer, condition=lambda msg: isinstance(msg, GatherTask))
        .add_edge(evaluator, reporter, condition=lambda msg: isinstance(msg, ReportTask))
        .build()
    )
