"""ライブスモーク(実 Foundry エンドポイント)。既定では除外され、
``uv run pytest -m live`` で実行する。要 labs/maf-ports/.env。

確認項目(PORTING.md §4):
1. 実モデルで 1 シナリオ(proposer 4体 並列 → 集約)が正常完走すること
2. トレースが App Insights に届くこと(このテストでは送信の有効化まで。
   到達確認は CLI 実行後に az monitor app-insights query で行う)
"""

import pytest

from mixture_of_agents_maf.config import ConfigError, FoundrySettings

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def settings() -> FoundrySettings:
    try:
        return FoundrySettings.from_env()
    except ConfigError as exc:
        pytest.skip(f"live 設定なし: {exc}")


async def test_full_workflow_live(settings: FoundrySettings) -> None:
    from mixture_of_agents_maf.agents import build_agents
    from mixture_of_agents_maf.observability import setup_tracing
    from mixture_of_agents_maf.workflow import MoAResult, ProposerDone, build_moa_workflow

    setup_tracing(settings.app_insights_connection_string)
    agents = build_agents(settings)
    workflow = build_moa_workflow(agents)

    result = None
    progressed: list[str] = []
    async for event in workflow.run(
        "In 3 bullet points, when should a team choose a monolith over microservices?",
        stream=True,
    ):
        if event.type == "intermediate" and isinstance(event.data, ProposerDone):
            progressed.append(event.data.proposer)
        elif event.type == "output":
            result = event.data

    assert isinstance(result, MoAResult)
    assert sorted(progressed) == sorted(p.name for p in agents.proposers)
    assert len(result.proposals) == len(agents.proposers)
    assert all(proposal.answer.strip() for proposal in result.proposals)
    assert len(result.final_md) > 100
