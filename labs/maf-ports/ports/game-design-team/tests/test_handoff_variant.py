"""HandoffBuilder 変種の**構築**のオフラインテスト。

実行のオフラインテストは組めない(participants が実 ``Agent`` 限定で
scripted fake を渡せないため — この制約自体が本ポートの学び)。ここでは
「構築が通ること」と「HandoffBuilder の制約(Agent 限定・
require_per_service_call_history_persistence 必須)」を固定する。

要 ``uv sync --extra orchestrations``(未導入ならスキップ)。
"""

import pytest

pytest.importorskip("agent_framework")
pytest.importorskip("agent_framework_orchestrations")

from game_design_team_maf.agents import build_chat_client
from game_design_team_maf.config import FoundrySettings
from game_design_team_maf.handoff_variant import (
    build_handoff_variant_agents,
    build_handoff_variant_workflow,
)
from game_design_team_maf.prompts import ROLE_ORDER


def make_client():
    return build_chat_client(
        FoundrySettings(
            openai_v1_endpoint="https://example.openai.azure.com/openai/v1",
            model="gpt-5.4-mini",
            api_key="dummy",
            app_insights_connection_string=None,
        )
    )


def test_variant_workflow_builds_offline() -> None:
    from agent_framework import Workflow

    workflow = build_handoff_variant_workflow(make_client())
    assert isinstance(workflow, Workflow)


def test_variant_agents_encode_ring_and_phases_in_instructions() -> None:
    """主実装ではグラフ+Executor が担うリング順・フェーズ判定・終了が、
    HandoffBuilder ではプロンプト(instructions)に載るしかないことを固定。"""
    agents = build_handoff_variant_agents(make_client())
    by_name = {agent.name: agent for agent in agents}

    assert set(by_name) == {f"{role}_agent" for role in ROLE_ORDER}
    story_instructions = by_name["story_agent"].default_options.get("instructions")
    assert "handoff_to_gameplay_agent" in story_instructions
    assert "FIRST time you speak" in story_instructions
    assert "SECOND time you speak" in story_instructions
    # tech だけは最後に handoff しない(終了)
    tech_instructions = by_name["tech_agent"].default_options.get("instructions")
    assert "do NOT call any handoff tool" in tech_instructions
    # HandoffBuilder の build() が全参加者に要求するフラグ
    for agent in agents:
        assert agent.require_per_service_call_history_persistence is True


def test_builder_rejects_agents_without_persistence_flag() -> None:
    """require_per_service_call_history_persistence が無い Agent は build() で
    弾かれる(HandoffBuilder のツール short-circuit と履歴整合の要件)。"""
    from agent_framework import Agent
    from agent_framework.orchestrations import HandoffBuilder

    client = make_client()
    plain = [Agent(client, instructions="x", name=f"{role}_agent") for role in ROLE_ORDER]
    builder = HandoffBuilder(participants=plain).with_start_agent(plain[0])

    with pytest.raises(ValueError, match="require_per_service_call_history_persistence"):
        builder.build()


def test_builder_rejects_scripted_fakes() -> None:
    """SupportsRun 相当の fake は participants にできない(実 Agent 限定)。
    → 実行のオフラインテストが構造的に不可能であることの証明。"""
    from agent_framework.orchestrations import HandoffBuilder

    class FakeAgent:
        name = "fake_agent"

        async def run(self, message: str):  # pragma: no cover - 呼ばれない
            return None

    with pytest.raises(TypeError, match="must be Agent instances"):
        HandoffBuilder().participants([FakeAgent()])  # type: ignore[list-item]
