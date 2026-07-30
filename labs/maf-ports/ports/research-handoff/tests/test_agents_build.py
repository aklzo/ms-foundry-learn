"""実 MAF ``Agent`` クラスでの配線のオフラインテスト(ネットワーク不要)。
Port 2 の test_build_agents_wires_personas_offline に相当。"""

import httpx
import pytest

pytest.importorskip("agent_framework")

from research_handoff_maf.agents import build_agents, build_chat_client
from research_handoff_maf.config import FoundrySettings
from research_handoff_maf.tools import FactStore


def make_settings() -> FoundrySettings:
    return FoundrySettings(
        openai_v1_endpoint="https://example.openai.azure.com/openai/v1",
        model="gpt-5.4-mini",
        api_key="dummy",
        app_insights_connection_string=None,
    )


def test_build_agents_wires_three_roles_offline() -> None:
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    agents = build_agents(build_chat_client(make_settings()), http, FactStore())

    assert agents.triage is not None
    assert agents.research is not None
    assert agents.editor is not None
    # 3 役割とも await run(...) できる面を持つ(SupportsRun)
    for agent in (agents.triage, agents.research, agents.editor):
        assert callable(agent.run)


def test_triage_and_editor_have_response_format() -> None:
    """元の ``output_type=`` に対応する response_format が設定されている。"""
    from research_handoff_maf.schemas import ResearchReport, TriageDecision

    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    agents = build_agents(build_chat_client(make_settings()), http, FactStore())

    assert agents.triage.default_options.get("response_format") is TriageDecision
    assert agents.editor.default_options.get("response_format") is ResearchReport


def test_research_agent_has_both_tools() -> None:
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    agents = build_agents(build_chat_client(make_settings()), http, FactStore())

    tools = agents.research.default_options.get("tools") or []
    tool_names = {getattr(t, "name", getattr(t, "__name__", "")) for t in tools}
    assert "search_web" in tool_names
    assert "save_important_fact" in tool_names
