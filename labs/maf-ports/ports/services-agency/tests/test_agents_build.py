"""実 MAF ``Agent`` クラスでの配線のオフラインテスト(ネットワーク不要)。

talk_to_* クロージャと役割固有ツールが実 Agent にそのまま載ること、
非許可ペアのツールが実 Agent にも存在しないことを確認する。
"""

import pytest

pytest.importorskip("agent_framework")

from services_agency_maf.agency import build_agency, build_chat_client
from services_agency_maf.config import FoundrySettings
from services_agency_maf.flows import AGENT_KEYS
from services_agency_maf.roles import INSTRUCTIONS


def make_settings() -> FoundrySettings:
    return FoundrySettings(
        openai_v1_endpoint="https://example.openai.azure.com/openai/v1",
        model="gpt-5.4-mini",
        api_key="dummy",
        app_insights_connection_string=None,
    )


def tool_names(agent) -> list[str]:
    tools = agent.default_options.get("tools") or []
    return [getattr(tool, "name", None) or tool.__name__ for tool in tools]


def test_build_agency_registers_five_roles() -> None:
    agency = build_agency(build_chat_client(make_settings()))
    for key in AGENT_KEYS:
        agent = agency.agent(key)
        assert callable(agent.run)
        assert agent.name == key


def test_real_agents_carry_graph_generated_tools() -> None:
    """実 Agent 上のツール = 役割固有ツール+許可ペアの talk_to_* のみ。"""
    agency = build_agency(build_chat_client(make_settings()))

    assert tool_names(agency.agent("ceo")) == [
        "analyze_project",
        "talk_to_cto",
        "talk_to_product_manager",
        "talk_to_developer",
        "talk_to_client_manager",
    ]
    assert tool_names(agency.agent("cto")) == ["create_technical_spec", "talk_to_developer"]
    assert tool_names(agency.agent("product_manager")) == [
        "talk_to_developer",
        "talk_to_client_manager",
    ]
    assert tool_names(agency.agent("developer")) == []
    assert tool_names(agency.agent("client_manager")) == []


def test_instructions_carry_original_text_plus_protocol() -> None:
    agency = build_agency(build_chat_client(make_settings()))

    for key in AGENT_KEYS:
        instructions = agency.agent(key).default_options.get("instructions")
        assert INSTRUCTIONS[key] in instructions

    ceo_instructions = agency.agent("ceo").default_options.get("instructions")
    assert "Team communication:" in ceo_instructions
    assert "talk_to_cto" in ceo_instructions

    # 出次数 0 の役割には通信案内が無い(ツールも無いので案内もしない)
    for key in ("developer", "client_manager"):
        instructions = agency.agent(key).default_options.get("instructions")
        assert "Team communication:" not in instructions
        assert "talk_to_" not in instructions


def test_custom_flows_reshape_real_agents() -> None:
    agency = build_agency(
        build_chat_client(make_settings()), flows=(("developer", "cto"),)
    )
    assert tool_names(agency.agent("developer")) == ["talk_to_cto"]
    assert tool_names(agency.agent("ceo")) == ["analyze_project"]
