"""HandoffBuilder 変種のライブ実行サンプル(比較検証・live 専用)。

    uv sync --extra orchestrations --extra live
    uv run python examples/handoff_builder_variant.py
    uv run python examples/handoff_builder_variant.py --vibe "Cozy island life" \\
        --game-type Simulation

主実装(`uv run game-design-team-maf`)と同じ 4 役割・同じタスクを、
agent-framework-orchestrations の HandoffBuilder(LLM がツール呼び出しで
委譲先を選ぶ方式)で流す。観察ポイント:

- handoff_sent イベントがリング順(story→gameplay→visuals→tech→story→…)に
  出るか(LLM が呼び忘れると autonomous mode の nudge が挟まる)
- 要約→詳細の 2 周フェーズを LLM が会話履歴から正しく数えられるか
  (主実装では Executor が決定的に判定していた部分)
- 最終的に 4 セクションが揃うか(主実装は構造的に保証、こちらは確率的)

オフラインでは実行不可(participants が実 Agent 限定のため。構築のみ
tests/test_handoff_variant.py で検証)。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from game_design_team_maf.agents import build_chat_client
from game_design_team_maf.config import ConfigError, FoundrySettings
from game_design_team_maf.handoff_variant import build_handoff_variant_workflow
from game_design_team_maf.observability import setup_tracing
from game_design_team_maf.spec import GameSpec


def main() -> None:
    defaults = GameSpec()
    parser = argparse.ArgumentParser(description="HandoffBuilder 変種(live 専用)")
    parser.add_argument("--vibe", default=defaults.background_vibe)
    parser.add_argument("--game-type", default=defaults.game_type)
    parser.add_argument("--goal", default=defaults.game_goal)
    args = parser.parse_args()

    spec = GameSpec(
        background_vibe=args.vibe, game_type=args.game_type, game_goal=args.goal
    )
    try:
        asyncio.run(_run(spec))
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)


async def _run(spec: GameSpec) -> None:
    settings = FoundrySettings.from_env()
    if setup_tracing(settings.app_insights_connection_string):
        print("tracing: App Insights 有効", file=sys.stderr)

    workflow = build_handoff_variant_workflow(build_chat_client(settings))

    # HandoffBuilder では各エージェントの応答がそのまま workflow の output
    # イベントになる(終端イベントはない)。会話順に全応答を表示する。
    async for event in workflow.run(spec.to_task(), stream=True):
        if event.type == "handoff_sent":
            data = event.data
            print(f"[handoff] {data.source} -> {data.target}", file=sys.stderr)
        elif event.type == "output":
            response = event.data
            author = getattr(response, "author_name", None) or getattr(
                event, "executor_id", "?"
            )
            text = getattr(response, "text", str(response))
            print(f"\n----- {author} -----\n{text}")
        elif event.type in ("request_info",):
            # autonomous mode でも turn limit 到達時などに出得る。one-shot
            # 実行ではここで打ち切る(会話型セマンティクスが残る証左)。
            print("[request_info] ユーザー入力要求 — one-shot 実行のため終了", file=sys.stderr)
            return


if __name__ == "__main__":
    main()
