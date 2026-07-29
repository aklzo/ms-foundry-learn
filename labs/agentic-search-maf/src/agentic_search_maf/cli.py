"""CLI frontend, ported from ``crates/cli``.

Progress arrives as workflow events from ``run_stream`` instead of the Rust
``EventSink`` callback; the same events double as the JSON Lines audit trace
(``--trace``), which in the Rust version only the GUI produced.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from .config import Config, LlmProviderKind
from .events import (
    EvaluationDone,
    IterationDone,
    PageProcessed,
    PlanReady,
    QueryStarted,
    TraceRecord,
    to_jsonl,
)
from .fetch import HttpFetcher
from .llm import build_agents, build_chat_client, supports_structured_output
from .search import build_provider


def main() -> None:
    args = _parse_args()
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        sys.exit(130)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="agentic-search-maf",
        description=(
            "Agentic web research: plans searches, gathers sources, "
            "self-evaluates for freshness/correctness/coverage, and keeps "
            "searching until satisfied."
        ),
    )
    parser.add_argument("question", help="Research question to investigate.")
    parser.add_argument(
        "--provider",
        help="LLM provider: ollama (default), claude, openai, azure.",
    )
    parser.add_argument(
        "--model",
        help='Model name override (e.g. "llama3.2:3b", or an Azure deployment name).',
    )
    parser.add_argument("--max-iterations", type=int, help="Maximum gather/evaluate iterations.")
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the Markdown report to this file instead of stdout only.",
    )
    parser.add_argument(
        "--trace",
        type=Path,
        help="Write the run's progress events to this file as JSON Lines.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose progress logging.")
    return parser.parse_args()


def _build_config(args: argparse.Namespace) -> Config:
    """Environment configuration with CLI flags layered on top."""
    provider = LlmProviderKind.parse(args.provider) if args.provider else None
    config = Config.from_env(provider)
    if args.model:
        config.llm.model = args.model
    if args.max_iterations is not None:
        config.limits.max_iterations = args.max_iterations
    return config


async def _run(args: argparse.Namespace) -> None:
    from .events import AgentEventPayload
    from .workflow import build_research_workflow

    payload_types = tuple(AgentEventPayload.__args__)

    config = _build_config(args)
    chat_client = build_chat_client(config.llm)
    agents = build_agents(
        chat_client,
        config.report_language,
        structured_output=supports_structured_output(config.llm.provider),
    )
    search = build_provider(config.search)
    fetcher = HttpFetcher(config.limits)
    workflow = build_research_workflow(agents, search, fetcher, config.limits)

    report = None
    trace: list[TraceRecord] = []
    try:
        async for event in workflow.run(args.question, stream=True):
            if event.type == "intermediate" and isinstance(event.data, payload_types):
                trace.append(TraceRecord.now(event.data))
                print(_describe(event.data), file=sys.stderr)
            elif event.type == "output":
                report = event.data
    finally:
        await fetcher.aclose()

    if report is None:
        print("error: the workflow produced no report", file=sys.stderr)
        sys.exit(1)

    if args.output:
        args.output.write_text(report.markdown, encoding="utf-8")
        print(f"report written to {args.output}", file=sys.stderr)
    else:
        print(report.markdown)
    if args.trace:
        args.trace.write_text(to_jsonl(trace) + "\n", encoding="utf-8")
        print(f"trace written to {args.trace}", file=sys.stderr)

    evaluation = report.evaluation
    print(
        f"done: {report.finding_count} findings from {report.source_count} sources "
        f"in {report.iterations} iteration(s) | scores: "
        f"freshness {evaluation.freshness.score}, "
        f"correctness {evaluation.correctness.score}, "
        f"coverage {evaluation.coverage.score}",
        file=sys.stderr,
    )


def _describe(payload) -> str:
    if isinstance(payload, PlanReady):
        return f"plan ready: {len(payload.queries)} queries: {', '.join(payload.queries)}"
    if isinstance(payload, QueryStarted):
        return f"searching: {payload.query}"
    if isinstance(payload, PageProcessed):
        return f"  page {payload.url} (+{payload.new_findings})"
    if isinstance(payload, IterationDone):
        return (
            f"iteration {payload.iteration} done: "
            f"+{payload.new_findings} findings (total {payload.total_findings})"
        )
    if isinstance(payload, EvaluationDone):
        ev = payload.evaluation
        return (
            f"evaluation {payload.iteration}: freshness {ev.freshness.score}, "
            f"correctness {ev.correctness.score}, coverage {ev.coverage.score}, "
            f"sufficient={ev.sufficient()}"
        )
    return str(payload)


if __name__ == "__main__":
    main()
