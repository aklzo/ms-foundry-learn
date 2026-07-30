"""ライブスモーク(実 Foundry エンドポイント)。既定では除外され、
``uv run pytest -m live`` で実行する。要 labs/maf-ports/.env。

確認項目(PORTING.md §4):
1. 実モデルで 1 シナリオが正常完走すること
2. トレースが App Insights に届くこと(このテストでは送信の有効化まで。
   到達確認は CLI 実行後に az monitor app-insights query で行う)
"""

import pytest

from trend_analysis_maf.config import ConfigError, FoundrySettings

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def settings() -> FoundrySettings:
    try:
        return FoundrySettings.from_env()
    except ConfigError as exc:
        pytest.skip(f"live 設定なし: {exc}")


async def test_full_workflow_live(settings: FoundrySettings) -> None:
    from trend_analysis_maf.agents import build_agents, build_chat_client
    from trend_analysis_maf.observability import setup_tracing
    from trend_analysis_maf.search import default_http_client
    from trend_analysis_maf.workflow import TrendReport, build_trend_workflow

    setup_tracing(settings.app_insights_connection_string)
    http = default_http_client()
    try:
        agents = build_agents(build_chat_client(settings), http)
        workflow = build_trend_workflow(agents)
        report = None
        async for event in workflow.run("AI coding agents", stream=True):
            if event.type == "output":
                report = event.data
    finally:
        await http.aclose()

    assert isinstance(report, TrendReport)
    assert len(report.analysis_md) > 200
    assert "trend" in report.analysis_md.lower() or "トレンド" in report.analysis_md
