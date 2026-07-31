"""ライブスモーク(手動・要 .env)。

    uv sync --extra dev --extra live && uv run pytest -m live

1. ワークフロー(クライアント実行): 実 HN Algolia + 実 Foundry モデルで
   ブリーフを 1 本生成し、トレースがポータルに出ることを README のクエリで確認
2. hosted agent(デプロイ後のみ): HN_BRIEFING_HOSTED_SMOKE=1 のときだけ、
   デプロイ済みエージェントの Responses エンドポイントを 1 回叩く
   (要 hosting/deploy_hosted_agent.py 済+--extra hosting)
"""

import os

import pytest

from hn_briefing_maf.config import ConfigError, FoundrySettings

pytestmark = pytest.mark.live


@pytest.fixture()
def settings() -> FoundrySettings:
    try:
        return FoundrySettings.from_env()
    except ConfigError as exc:
        pytest.skip(f"live 設定なし: {exc}")


async def test_live_workflow_generates_brief(settings: FoundrySettings) -> None:
    from hn_briefing_maf.agents import build_briefing_agent, build_chat_client
    from hn_briefing_maf.briefing import Brief
    from hn_briefing_maf.hn import default_http_client
    from hn_briefing_maf.observability import setup_tracing
    from hn_briefing_maf.ranking import score_story
    from hn_briefing_maf.workflow import BriefingRequest, build_briefing_workflow

    setup_tracing(settings.app_insights_connection_string)

    http = default_http_client()
    try:
        workflow = build_briefing_workflow(
            build_briefing_agent(build_chat_client(settings)), http
        )
        result = await workflow.run(BriefingRequest(top_n=3))
    finally:
        await http.aclose()

    outputs = result.get_outputs() if hasattr(result, "get_outputs") else result
    briefs = [item for item in (outputs if isinstance(outputs, list) else [outputs])
              if isinstance(item, Brief)]
    assert briefs, "workflow produced no Brief"
    brief = briefs[0]

    assert brief.subject.startswith("AgentScout Hacker News brief - ")
    assert 1 <= len(brief.stories) <= 3
    # 決定論ランキングの検証: スコア降順で並んでいること
    scores = [score_story(story) for story in brief.stories]
    assert scores == sorted(scores, reverse=True)
    assert len(brief.brief_md.strip()) > 100  # LLM 本文が空でない


async def test_live_hosted_agent_responses_endpoint(settings: FoundrySettings) -> None:
    """デプロイ済み hosted agent の実呼び出し(呼び出し元が実施する段)。"""
    if os.environ.get("HN_BRIEFING_HOSTED_SMOKE") != "1":
        pytest.skip("HN_BRIEFING_HOSTED_SMOKE=1 のときだけ実行(要デプロイ済)")
    if not settings.project_endpoint:
        pytest.skip("FOUNDRY_PROJECT_ENDPOINT なし")
    pytest.importorskip("azure.ai.projects")

    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=settings.project_endpoint, credential=credential) as project,
        project.get_openai_client(agent_name=settings.agent_name) as openai_client,
    ):
        response = openai_client.responses.create(
            input="Give me today's AgentScout brief (top 3 stories)."
        )

    text = response.output_text
    assert len(text.strip()) > 100
    # digest 由来の構造(signal / ランク付き記事)が応答に現れること
    assert "1." in text or "Next actions" in text or "points" in text
