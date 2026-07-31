"""CLI エントリポイント(元 Streamlit フォーム+5 タブ表示の置き換え)。

    uv run services-agency-maf "AI ノート共有 SaaS を作りたい。学生向け。"
    uv run services-agency-maf "..." --name NoteHub --type "Web Application" \\
        --budget "$25k-$50k" --timeline "3-4 months" --priority High
    uv run services-agency-maf "..." --json --output runs/report.json

進捗(ターン完了と通信イベントの逐次表示)は stderr、最終レポート
(5 セクション+通信ログ+共有状態の Markdown)は stdout。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .agency import build_agency, build_chat_client
from .comms import DEFAULT_MAX_DEPTH, CommEvent
from .config import ConfigError, FoundrySettings
from .observability import setup_tracing
from .project import BUDGET_RANGES, PRIORITIES, PROJECT_TYPES, TIMELINES, ProjectInfo
from .runner import run_agency


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="AI サービスエージェンシー(MAF + Foundry 移植版)。"
        "5 役(CEO/CTO/PM/Dev/CS)が通信グラフの制約下で相互相談しつつ"
        "プロジェクトを分析する。"
    )
    parser.add_argument("description", help="プロジェクト依頼文(元フォームの Project Description)")
    parser.add_argument("--name", default="Untitled Project", help="プロジェクト名")
    parser.add_argument(
        "--type", dest="project_type", choices=PROJECT_TYPES, default="Web Application",
        help="プロジェクト種別",
    )
    parser.add_argument("--timeline", choices=TIMELINES, default="3-4 months", help="想定期間")
    parser.add_argument("--budget", choices=BUDGET_RANGES, default="$25k-$50k", help="予算帯")
    parser.add_argument("--priority", choices=PRIORITIES, default="High", help="優先度")
    parser.add_argument("--tech-requirements", default="", help="技術要件(任意)")
    parser.add_argument("--special-considerations", default="", help="特記事項(任意)")
    parser.add_argument(
        "--max-depth", type=int, default=DEFAULT_MAX_DEPTH,
        help=f"エージェント間会話の再帰深度上限(既定 {DEFAULT_MAX_DEPTH})",
    )
    parser.add_argument("--json", action="store_true", help="最終レポートを JSON で出す")
    parser.add_argument("--output", type=Path, default=None, help="レポート JSON の書き出し先")
    return parser


def _truncate(text: str, limit: int = 96) -> str:
    flat = text.replace("\n", " ")
    return flat if len(flat) <= limit else flat[: limit - 3] + "..."


def comm_listener(event: CommEvent, phase: str) -> None:
    """通信イベントの逐次表示(stderr)。トレースを開かなくても
    「誰が誰に何を聞いたか」がその場で追える。"""
    indent = "  " * event.depth
    if phase == "ask":
        print(
            f"[comm] {indent}{event.sender} -> {event.recipient} "
            f"(depth {event.depth}): {_truncate(event.message)}",
            file=sys.stderr,
        )
    elif phase == "reply":
        print(
            f"[comm] {indent}{event.recipient} -> {event.sender}: "
            f"reply {len(event.reply or '')} chars",
            file=sys.stderr,
        )
    elif phase == "blocked":
        print(
            f"[comm] {indent}{event.sender} -> {event.recipient} BLOCKED "
            f"(depth {event.depth} exceeds limit)",
            file=sys.stderr,
        )


def main() -> None:
    args = make_parser().parse_args()
    try:
        asyncio.run(_run(args))
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        sys.exit(130)


async def _run(args: argparse.Namespace) -> None:
    settings = FoundrySettings.from_env()
    if setup_tracing(settings.app_insights_connection_string):
        print("tracing: App Insights 有効", file=sys.stderr)

    project = ProjectInfo(
        name=args.name,
        description=args.description,
        project_type=args.project_type,
        timeline=args.timeline,
        budget=args.budget,
        priority=args.priority,
        technical_requirements=args.tech_requirements,
        special_considerations=args.special_considerations,
    )
    agency = build_agency(
        build_chat_client(settings), max_depth=args.max_depth, listener=comm_listener
    )

    def on_turn(key: str, text: str) -> None:
        print(f"[turn] {key} done ({len(text)} chars)", file=sys.stderr)

    report = await run_agency(agency, project, on_turn=on_turn)

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[saved] {args.output}", file=sys.stderr)
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(report.to_markdown())


if __name__ == "__main__":
    main()
