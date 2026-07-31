"""CLI エントリポイント(ロジック層のクライアント実行)。

    uv run hn-briefing-maf                      # 今日のブリーフを stdout へ
    uv run hn-briefing-maf --top-n 3 --json     # Brief ペイロードを JSON で
    uv run hn-briefing-maf --output runs/brief.json

配信は stdout / ファイル出力まで(元の Gmail/webhook はスコープ外 —
理由は README)。元 scheduler_api の dry-run 応答に相当するのが --json。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .agents import build_briefing_agent, build_chat_client
from .briefing import Brief
from .config import ConfigError, FoundrySettings
from .hn import CollectError, default_http_client
from .observability import setup_tracing
from .ranking import DEFAULT_TOP_N
from .workflow import BriefingRequest, StageDone, build_briefing_workflow

#: 元アプリに全体タイムアウトは無い(Cloud Scheduler 任せ)。CLI の運用上の
#: 安全弁として追加した移植差分。
DEFAULT_TIMEOUT_SECONDS = 180.0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="常時稼働 HN ブリーフィング(MAF + Foundry hosted agent 移植版)"
    )
    parser.add_argument(
        "--top-n", type=int, default=DEFAULT_TOP_N, help="ブリーフに含める記事数(1〜10)"
    )
    parser.add_argument("--json", action="store_true", help="Brief ペイロードを JSON で出す")
    parser.add_argument("--output", type=Path, default=None, help="Brief JSON の書き出し先")
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"全体タイムアウト秒(既定 {DEFAULT_TIMEOUT_SECONDS:.0f})",
    )
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
        workflow = build_briefing_workflow(
            build_briefing_agent(build_chat_client(settings)), http
        )
        try:
            brief = await asyncio.wait_for(
                _consume(workflow, BriefingRequest(top_n=args.top_n)), args.timeout
            )
        except TimeoutError:
            print(f"error: timed out after {args.timeout:.0f} seconds", file=sys.stderr)
            sys.exit(1)
        except CollectError as exc:
            print(f"error: {exc}", file=sys.stderr)
            sys.exit(1)
    finally:
        await http.aclose()

    if brief is None:
        print("error: workflow produced no brief", file=sys.stderr)
        sys.exit(1)

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(brief.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[saved] {args.output}", file=sys.stderr)

    if args.json:
        print(json.dumps(brief.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"{brief.subject}\n\n{brief.brief_md}")


async def _consume(workflow, request: BriefingRequest) -> Brief | None:
    brief: Brief | None = None
    async for event in workflow.run(request, stream=True):
        if event.type == "intermediate" and isinstance(event.data, StageDone):
            print(f"[{event.data.stage}] {event.data.count} stories", file=sys.stderr)
        elif event.type == "output":
            brief = event.data
    return brief


if __name__ == "__main__":
    main()
