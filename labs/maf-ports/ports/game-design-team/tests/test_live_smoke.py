"""ライブスモーク(実 Foundry エンドポイント)。既定では除外され、
``uv run pytest -m live`` で実行する。要 labs/maf-ports/.env。

確認項目(PORTING.md §4):
1. 実モデルでリング 2 周(8 ターン)が正常完走し、4 セクションの企画書が
   得られること
2. トレースが App Insights に届くこと(このテストでは送信の有効化まで。
   到達確認は CLI 実行後に az monitor app-insights query で行う)
"""

import pytest

from game_design_team_maf.config import ConfigError, FoundrySettings

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def settings() -> FoundrySettings:
    try:
        return FoundrySettings.from_env()
    except ConfigError as exc:
        pytest.skip(f"live 設定なし: {exc}")


async def test_full_ring_live(settings: FoundrySettings) -> None:
    from game_design_team_maf.agents import build_agents, build_chat_client
    from game_design_team_maf.observability import setup_tracing
    from game_design_team_maf.prompts import ROLE_ORDER
    from game_design_team_maf.spec import GameSpec
    from game_design_team_maf.workflow import (
        GameDesignContext,
        GameDesignDocument,
        RoleSummaryDone,
        build_game_design_workflow,
    )

    setup_tracing(settings.app_insights_connection_string)
    agents = build_agents(build_chat_client(settings))
    workflow = build_game_design_workflow(agents)

    spec = GameSpec(
        platforms=("PC",),
        core_mechanics=("Exploration", "Crafting"),
        mood=("Whimsical",),
        depth="Low",  # ライブはトークン節約のため最小詳細度
    )
    result = None
    summaries: list[RoleSummaryDone] = []
    async for event in workflow.run(GameDesignContext(task=spec.to_task()), stream=True):
        if event.type == "intermediate" and isinstance(event.data, RoleSummaryDone):
            summaries.append(event.data)
        elif event.type == "output":
            result = event.data

    assert isinstance(result, GameDesignDocument)
    assert [s.role for s in summaries] == list(ROLE_ORDER)
    for role in ROLE_ORDER:
        assert result.summaries[role].strip()
        assert result.sections[role].strip()
        assert f"## {role.capitalize()} Design" in result.sections[role]
