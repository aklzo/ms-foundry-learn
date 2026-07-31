"""CLI エントリポイント(元アプリの Streamlit UI の置き換え)。

    uv run critique-loop-maf "Explain recursion with examples."
    uv run critique-loop-maf --max-rounds 3 --show-history "..."
    uv run critique-loop-maf --json "..."
    uv run critique-loop-maf --save-run runs/recursion.json "..."   # クラウド評価入力

進捗(候補生成・統合・批評 verdict・改訂)は stderr にストリーム表示 —
元アプリの st.spinner / expander 相当。``--save-run`` の JSON は
scripts/run_cloud_eval.py がそのまま読める(版ごとの中間出力を含む)。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .agents import build_agents, build_chat_client
from .config import ConfigError, FoundrySettings
from .observability import setup_tracing
from .workflow import (
    DEFAULT_MAX_ROUNDS,
    CandidateDone,
    CritiqueDecided,
    CritiqueLoopResult,
    DraftSynthesized,
    RevisionDone,
    build_critique_loop_workflow,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="批評・改善ループ(MAF + Foundry 移植版)"
    )
    parser.add_argument("prompt", help="質問(例: 'Explain recursion with examples.')")
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=DEFAULT_MAX_ROUNDS,
        help=f"改善周回の上限(1〜3。既定 {DEFAULT_MAX_ROUNDS} — 元アプリのスライダーと同じ)",
    )
    parser.add_argument(
        "--show-history",
        action="store_true",
        help="各周回の批評と改訂も表示(元アプリの Improvement History expander 相当)",
    )
    parser.add_argument("--json", action="store_true", help="全出力を JSON で出す")
    parser.add_argument(
        "--save-run",
        metavar="PATH",
        help="実行結果 JSON の保存先(scripts/run_cloud_eval.py のクラウド評価入力)",
    )
    args = parser.parse_args()
    try:
        asyncio.run(_run(args))
    except (ConfigError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)


async def _run(args: argparse.Namespace) -> None:
    settings = FoundrySettings.from_env()
    if setup_tracing(settings.app_insights_connection_string):
        print("tracing: App Insights 有効", file=sys.stderr)

    agents = build_agents(build_chat_client(settings))
    workflow = build_critique_loop_workflow(agents, max_rounds=args.max_rounds)

    result: CritiqueLoopResult | None = None
    async for event in workflow.run(args.prompt, stream=True):
        if event.type == "intermediate":
            _print_progress(event.data)
        elif event.type == "output":
            result = event.data

    if result is None:
        print("error: workflow produced no result", file=sys.stderr)
        sys.exit(1)

    if args.save_run:
        path = Path(args.save_run)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[save] {path}", file=sys.stderr)

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return

    if args.show_history:
        print("## Initial answer\n")
        print(result.initial_answer)
        for revision in result.revisions:
            print(f"\n## Iteration {revision.round} critiques\n")
            for critique in revision.critiques:
                print(f"- {critique}")
            print(f"\n## Iteration {revision.round} improved answer\n")
            print(revision.answer)
        print("\n## Final answer\n")
    print(result.final_answer)
    # 元アプリのサマリーメトリクス(Total Iterations / Rounds / Length)相当
    print(
        f"[summary] iterations={result.total_iterations} "
        f"revisions={len(result.revisions)}/{result.max_rounds} "
        f"stop={result.stop_reason} final_chars={len(result.final_answer)}",
        file=sys.stderr,
    )


def _print_progress(data: object) -> None:
    if isinstance(data, CandidateDone):
        print(f"[candidate:{data.name}] done ({data.chars} chars)", file=sys.stderr)
    elif isinstance(data, DraftSynthesized):
        print(f"[synthesize] initial draft ({data.chars} chars)", file=sys.stderr)
    elif isinstance(data, CritiqueDecided):
        print(
            f"[critic] round {data.round}: {data.verdict} "
            f"({data.critique_count} critiques)",
            file=sys.stderr,
        )
    elif isinstance(data, RevisionDone):
        print(f"[revise] round {data.round}: revised ({data.chars} chars)", file=sys.stderr)


if __name__ == "__main__":
    main()
