"""CLI エントリポイント(元アプリの Streamlit UI の置き換え)。

    uv run mixture-of-agents-maf "量子コンピュータは何に使えるか?"
    uv run mixture-of-agents-maf --show-proposals question ...  # 個別回答も表示
    uv run mixture-of-agents-maf --json question ...            # 全出力を JSON で
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import sys

from .agents import build_agents
from .config import ConfigError, FoundrySettings
from .observability import setup_tracing
from .workflow import MoAResult, ProposerDone, build_moa_workflow


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mixture-of-Agents 並列合議(MAF + Foundry 移植版)"
    )
    parser.add_argument("question", help="質問(例: 'What are the trade-offs of microservices?')")
    parser.add_argument(
        "--show-proposals",
        action="store_true",
        help="個別 proposer の回答も表示(元アプリの expander 相当)",
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

    agents = build_agents(settings)
    workflow = build_moa_workflow(agents)
    print(
        f"proposers: {', '.join(p.name for p in agents.proposers)}",
        file=sys.stderr,
    )

    result: MoAResult | None = None
    async for event in workflow.run(args.question, stream=True):
        if event.type == "intermediate" and isinstance(event.data, ProposerDone):
            print(
                f"[{event.data.proposer}] done ({event.data.chars} chars)",
                file=sys.stderr,
            )
        elif event.type == "output":
            result = event.data

    if result is None:
        print("error: workflow produced no result", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(dataclasses.asdict(result), ensure_ascii=False, indent=2))
        return

    if args.show_proposals:
        for proposal in result.proposals:
            print(f"## Response from {proposal.proposer}\n\n{proposal.answer}\n")
        print("## Aggregated response\n")
    print(result.final_md)


if __name__ == "__main__":
    main()
