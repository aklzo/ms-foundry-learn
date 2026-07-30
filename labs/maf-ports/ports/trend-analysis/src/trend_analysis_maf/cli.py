"""CLI エントリポイント(元アプリの Streamlit UI の置き換え)。

    uv run trend-analysis-maf "AI エージェント向け開発ツール"
    uv run trend-analysis-maf --json topic ...   # 全段の出力を JSON で
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import sys

from .agents import build_agents, build_chat_client
from .config import ConfigError, FoundrySettings
from .observability import setup_tracing
from .search import default_http_client
from .workflow import StageDone, TrendReport, build_trend_workflow


def main() -> None:
    parser = argparse.ArgumentParser(
        description="スタートアップトレンド分析(MAF + Foundry 移植版)"
    )
    parser.add_argument("topic", help="関心領域(例: 'AI agent developer tools')")
    parser.add_argument("--json", action="store_true", help="全段の出力を JSON で出す")
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
    try:
        agents = build_agents(build_chat_client(settings), http)
        workflow = build_trend_workflow(agents)

        report: TrendReport | None = None
        async for event in workflow.run(args.topic, stream=True):
            if event.type == "intermediate" and isinstance(event.data, StageDone):
                print(
                    f"[{event.data.stage}] done ({event.data.chars} chars)",
                    file=sys.stderr,
                )
            elif event.type == "output":
                report = event.data
    finally:
        await http.aclose()

    if report is None:
        print("error: workflow produced no report", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(dataclasses.asdict(report), ensure_ascii=False, indent=2))
    else:
        print(report.analysis_md)


if __name__ == "__main__":
    main()
