"""実 MAF ``Agent`` クラスでの配線のオフラインテスト(ネットワーク不要)。"""

import pytest

pytest.importorskip("agent_framework")

from game_design_team_maf.agents import build_agents, build_chat_client
from game_design_team_maf.config import FoundrySettings
from game_design_team_maf.prompts import ROLE_ORDER, SYSTEM_MESSAGES


def make_settings() -> FoundrySettings:
    return FoundrySettings(
        openai_v1_endpoint="https://example.openai.azure.com/openai/v1",
        model="gpt-5.4-mini",
        api_key="dummy",
        app_insights_connection_string=None,
    )


def test_build_agents_wires_four_roles_offline() -> None:
    agents = build_agents(build_chat_client(make_settings()))

    for role in ROLE_ORDER:
        agent = agents.for_role(role)
        assert agent is not None
        assert callable(agent.run)
        assert agent.name == f"{role}_agent"


def test_agents_carry_original_personas_as_instructions() -> None:
    """役割ペルソナ(元 system_messages 原文)が静的 instructions に載る。
    フェーズ別の動的部分は prompts.py が実行時に組み立てる(instructions には
    含まれない)。"""
    agents = build_agents(build_chat_client(make_settings()))

    for role in ROLE_ORDER:
        instructions = agents.for_role(role).default_options.get("instructions")
        assert instructions == SYSTEM_MESSAGES[role]
        assert "2-3 sentence summary" not in instructions


def test_agents_have_no_tools() -> None:
    """元アプリの update_*_overview(LLM の関数呼び出しで context 書き込み+
    ルーティング)は Executor の決定的処理に置き換えたため、ツールなし。"""
    agents = build_agents(build_chat_client(make_settings()))

    for role in ROLE_ORDER:
        tools = agents.for_role(role).default_options.get("tools") or []
        assert list(tools) == []
