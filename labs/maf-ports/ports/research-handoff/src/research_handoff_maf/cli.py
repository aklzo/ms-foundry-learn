"""CLI エントリポイント(元アプリの Streamlit UI の置き換え)。

    uv run research-handoff-maf "best affordable espresso machines"
    uv run research-handoff-maf --show-facts topic ...  # 保存ファクトも表示
    uv run research-handoff-maf --json topic ...        # 全出力を JSON で
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from .agents import build_agents, build_chat_client
from .config import ConfigError, FoundrySettings
from .observability import setup_tracing
from .search import default_http_client
from .tools import FactStore
from .workflow import (
    HandoffDecided,
    ResearchHandoffResult,
    StageDone,
    build_research_workflow,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="リサーチエージェント handoff 型(MAF + Foundry 移植版)"
    )
    parser.add_argument("topic", help="リサーチトピック(例: 'best cruise lines for first-timers')")
    parser.add_argument(
        "--show-facts",
        action="store_true",
        help="research 中に保存されたファクトも表示(元アプリの Collected Facts 相当)",
    )
    parser.add_argument("--json", action="store_true", help="全出力を JSON で出す")
    args = parser.parse_args()
    try:
        asyncio.run(_run(args))
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)


async def _run(args: argparse.Namespace) -> None:
    settings = FoundrySettings.from_env()
    if setup_tracing(settings.app_insights_connection_string):
        print("tracing: App Insights 有効", file=sys.stderr)

    http = default_http_client()
    fact_store = FactStore()
    try:
        agents = build_agents(build_chat_client(settings), http, fact_store)
        workflow = build_research_workflow(agents, fact_store)

        result: ResearchHandoffResult | None = None
        async for event in workflow.run(args.topic, stream=True):
            if event.type == "intermediate" and isinstance(event.data, HandoffDecided):
                print(
                    f"[triage] handoff → {event.data.handoff_to} ({event.data.reason})",
                    file=sys.stderr,
                )
            elif event.type == "intermediate" and isinstance(event.data, StageDone):
                print(
                    f"[{event.data.stage}] done ({event.data.chars} chars)",
                    file=sys.stderr,
                )
            elif event.type == "output":
                result = event.data
    finally:
        await http.aclose()

    if result is None:
        print("error: workflow produced no report", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return

    if args.show_facts and result.facts:
        print("## Collected facts\n")
        for fact in result.facts:
            print(f"- {fact.fact} (source: {fact.source}, at {fact.timestamp})")
        print()

    report = result.report
    print(f"# {report.title}\n")
    if report.outline:
        print("## Outline\n")
        for i, section in enumerate(report.outline, start=1):
            print(f"{i}. {section}")
        print()
    print(report.report)
    if report.sources:
        print("\n## Sources\n")
        for i, source in enumerate(report.sources, start=1):
            print(f"{i}. {source}")
    print(f"\n(word count: {report.word_count})", file=sys.stderr)


if __name__ == "__main__":
    main()
