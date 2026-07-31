"""CLI エントリポイント(元アプリの Streamlit フォーム+expander 表示の置き換え)。

    uv run game-design-team-maf
    uv run game-design-team-maf --vibe "Cozy island life" --game-type Simulation \\
        --mechanics "Crafting,Exploration" --depth Medium
    uv run game-design-team-maf --json   # 要約+全セクションを JSON で

既定値は元 Streamlit ウィジェットの初期値(Epic fantasy with dragons / RPG /
Kids (7-12) / ...)。進捗(各役割の要約 = 元のサイドバー表示、セクション完了)
は stderr、最終企画書(4 セクションの markdown)は stdout。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from .agents import build_agents, build_chat_client
from .config import ConfigError, FoundrySettings
from .observability import setup_tracing
from .spec import GameSpec
from .workflow import (
    GameDesignContext,
    GameDesignDocument,
    RoleSectionDone,
    RoleSummaryDone,
    build_game_design_workflow,
)


def _csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def build_spec(args: argparse.Namespace) -> GameSpec:
    return GameSpec(
        background_vibe=args.vibe,
        game_type=args.game_type,
        game_goal=args.goal,
        target_audience=args.audience,
        player_perspective=args.perspective,
        multiplayer=args.multiplayer,
        art_style=args.art_style,
        platforms=_csv(args.platforms),
        development_time_months=args.months,
        budget_usd=args.budget,
        core_mechanics=_csv(args.mechanics),
        mood=_csv(args.mood),
        inspiration=args.inspiration,
        unique_features=args.unique_features,
        depth=args.depth,
    )


def make_parser() -> argparse.ArgumentParser:
    defaults = GameSpec()
    parser = argparse.ArgumentParser(
        description="AI ゲーム企画エージェントチーム(MAF + Foundry 移植版)。"
        "4 役割(story/gameplay/visuals/tech)がリングを 2 周して企画書を作る。"
    )
    parser.add_argument("--vibe", default=defaults.background_vibe, help="世界観・雰囲気")
    parser.add_argument("--game-type", default=defaults.game_type, help="ゲームジャンル")
    parser.add_argument("--goal", default=defaults.game_goal, help="ゲームの目標")
    parser.add_argument("--audience", default=defaults.target_audience, help="ターゲット層")
    parser.add_argument("--perspective", default=defaults.player_perspective, help="視点")
    parser.add_argument("--multiplayer", default=defaults.multiplayer, help="マルチプレイ対応")
    parser.add_argument("--art-style", default=defaults.art_style, help="アートスタイル")
    parser.add_argument("--platforms", default="", help="対象プラットフォーム(カンマ区切り)")
    parser.add_argument(
        "--months", type=int, default=defaults.development_time_months, help="開発期間(月)"
    )
    parser.add_argument("--budget", type=int, default=defaults.budget_usd, help="予算(USD)")
    parser.add_argument("--mechanics", default="", help="コアメカニクス(カンマ区切り)")
    parser.add_argument("--mood", default="", help="ムード/雰囲気(カンマ区切り)")
    parser.add_argument("--inspiration", default=defaults.inspiration, help="参考ゲーム")
    parser.add_argument(
        "--unique-features", default=defaults.unique_features, help="独自要素・要件"
    )
    parser.add_argument("--depth", default=defaults.depth, help="詳細度(Low/Medium/High)")
    parser.add_argument("--json", action="store_true", help="全出力を JSON で出す")
    return parser


def main() -> None:
    args = make_parser().parse_args()
    try:
        asyncio.run(_run(args))
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)


async def _run(args: argparse.Namespace) -> None:
    settings = FoundrySettings.from_env()
    if setup_tracing(settings.app_insights_connection_string):
        print("tracing: App Insights 有効", file=sys.stderr)

    spec = build_spec(args)
    agents = build_agents(build_chat_client(settings))
    workflow = build_game_design_workflow(agents)

    result: GameDesignDocument | None = None
    async for event in workflow.run(GameDesignContext(task=spec.to_task()), stream=True):
        if event.type == "intermediate" and isinstance(event.data, RoleSummaryDone):
            # 元アプリの st.sidebar.success('Story overview: ...') 相当
            print(f"[{event.data.role}] overview: {event.data.summary}", file=sys.stderr)
        elif event.type == "intermediate" and isinstance(event.data, RoleSectionDone):
            print(
                f"[{event.data.role}] section done ({event.data.chars} chars)",
                file=sys.stderr,
            )
        elif event.type == "output":
            result = event.data

    if result is None:
        print("error: workflow produced no document", file=sys.stderr)
        sys.exit(1)

    if args.json:
        payload = {"spec": spec.to_dict(), **result.to_dict()}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print(result.to_markdown())


if __name__ == "__main__":
    main()
