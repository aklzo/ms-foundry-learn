"""ライブスモーク(実 Foundry エンドポイント)。既定では除外され、
``uv run pytest -m live`` で実行する。要 labs/maf-ports/.env。

確認項目(PORTING.md §4):
1. 5 ターンが正常完走し、CEO の分析(shared state)が書かれること
2. エージェント間通信(talk_to_*)が少なくとも 1 回発生し、
   すべて通信グラフの許可ペア内であること ← 本ポートの核心
3. トレースが App Insights に届くこと(このテストでは送信の有効化まで。
   到達確認は CLI 実行後に az monitor app-insights query で行う。見どころは
   execute_tool(talk_to_*)の下に invoke_agent がぶら下がる入れ子スパン)
"""

import sys

import pytest

from services_agency_maf.config import ConfigError, FoundrySettings

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def settings() -> FoundrySettings:
    try:
        return FoundrySettings.from_env()
    except ConfigError as exc:
        pytest.skip(f"live 設定なし: {exc}")


async def test_full_agency_live(settings: FoundrySettings) -> None:
    from services_agency_maf.agency import build_agency, build_chat_client
    from services_agency_maf.flows import AGENT_KEYS, COMMUNICATION_FLOWS
    from services_agency_maf.observability import setup_tracing
    from services_agency_maf.project import ProjectInfo
    from services_agency_maf.runner import run_agency

    setup_tracing(settings.app_insights_connection_string)
    agency = build_agency(build_chat_client(settings))

    # トークン節約のため小さめの案件(eval_dataset の web_app_mvp 相当)
    project = ProjectInfo(
        name="NoteHub",
        description="AI-assisted note sharing SaaS for university students.",
        project_type="Web Application",
        timeline="3-4 months",
        budget="$25k-$50k",
        priority="High",
    )
    report = await run_agency(agency, project)

    # 1. 5 応答+shared state
    for key in AGENT_KEYS:
        assert report.responses[key].strip(), key
    assert report.state["project_analysis"] is not None, "CEO が analyze_project を呼ぶべき"
    assert report.state["project_analysis"]["name"] == "NoteHub"

    # 2. 動的通信: 少なくとも 1 回発生し、全てグラフ内(構造上グラフ外は不可能
    #    だが、ログとしても確認する)
    pairs = agency.log.agent_pairs()
    assert pairs, "エージェント間通信(talk_to_*)が 1 回も発生しなかった"
    assert set(pairs) <= set(COMMUNICATION_FLOWS)

    # 評価データセットの期待(web_app_mvp: ceo→cto など)は情報として出力
    print(f"\n[live] communications: {pairs}", file=sys.stderr)
    print(agency.log.render(), file=sys.stderr)
