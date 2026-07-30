"""実 MAF ``Agent`` クラスでの配線のオフラインテスト(ネットワーク不要)。
Port 3 の test_agents_build.py に相当。"""

import pytest

pytest.importorskip("agent_framework")

from corrective_rag_maf.agents import build_agents, build_chat_client
from corrective_rag_maf.config import CorrectiveRagSettings


def make_settings() -> CorrectiveRagSettings:
    return CorrectiveRagSettings(
        openai_v1_endpoint="https://example.openai.azure.com/openai/v1",
        model="gpt-5.4-mini",
        api_key="dummy",
        embedding_model="text-embedding-3-small",
        search_endpoint="https://example.search.windows.net",
        search_api_key="dummy",
        search_index="corrective-rag",
        app_insights_connection_string=None,
    )


def test_build_agents_wires_three_roles_offline() -> None:
    agents = build_agents(build_chat_client(make_settings()))

    assert agents.grader is not None
    assert agents.rewriter is not None
    assert agents.generator is not None
    # 3 役割とも await run(...) できる面を持つ(SupportsRun)
    for agent in (agents.grader, agents.rewriter, agents.generator):
        assert callable(agent.run)


def test_grader_has_response_format() -> None:
    """元の「JSON を regex で拾う」採点を、ネイティブ構造化出力
    (response_format=GradeScore)+lenient フォールバックに強化している。"""
    from corrective_rag_maf.schemas import GradeScore

    agents = build_agents(build_chat_client(make_settings()))

    assert agents.grader.default_options.get("response_format") is GradeScore


def test_rewriter_and_generator_are_plain_text() -> None:
    """書換・生成は元実装同様プレーンテキスト応答(response_format なし)。"""
    agents = build_agents(build_chat_client(make_settings()))

    assert not (agents.rewriter.default_options or {}).get("response_format")
    assert not (agents.generator.default_options or {}).get("response_format")
