"""ライブスモーク(実 Foundry エンドポイント)。既定では除外され、
``uv run pytest -m live`` で実行する。要 labs/maf-ports/.env。

確認項目(PORTING.md §4):
1. 実モデルで 1 シナリオ(triage → research → editor)が正常完走すること
2. トレースが App Insights に届くこと(このテストでは送信の有効化まで。
   到達確認は CLI 実行後に az monitor app-insights query で行う)
"""

import pytest

from research_handoff_maf.config import ConfigError, FoundrySettings

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def settings() -> FoundrySettings:
    try:
        return FoundrySettings.from_env()
    except ConfigError as exc:
        pytest.skip(f"live 設定なし: {exc}")


async def test_full_workflow_live(settings: FoundrySettings) -> None:
    from research_handoff_maf.agents import build_agents, build_chat_client
    from research_handoff_maf.observability import setup_tracing
    from research_handoff_maf.search import default_http_client
    from research_handoff_maf.tools import FactStore
    from research_handoff_maf.workflow import (
        HandoffDecided,
        ResearchHandoffResult,
        build_research_workflow,
    )

    setup_tracing(settings.app_insights_connection_string)
    http = default_http_client()
    fact_store = FactStore()
    try:
        agents = build_agents(build_chat_client(settings), http, fact_store)
        workflow = build_research_workflow(agents, fact_store)

        result = None
        decisions: list[HandoffDecided] = []
        async for event in workflow.run(
            # research 分岐が期待されるトピック(鮮度依存の情報)
            "Recent developments in AI coding agents for enterprises",
            stream=True,
        ):
            if event.type == "intermediate" and isinstance(event.data, HandoffDecided):
                decisions.append(event.data)
            elif event.type == "output":
                result = event.data
    finally:
        await http.aclose()

    assert isinstance(result, ResearchHandoffResult)
    assert len(decisions) == 1
    assert result.handoff_to in ("research", "editor")
    assert result.plan.topic.strip()
    assert result.report.title.strip()
    assert len(result.report.report) > 500
    if result.handoff_to == "research":
        assert result.research_md and result.research_md.strip()
