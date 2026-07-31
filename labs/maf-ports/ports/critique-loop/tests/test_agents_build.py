"""実 MAF ``Agent`` クラスでの配線のオフラインテスト(ネットワーク不要)。
Port 4 の test_agents_build.py に相当。"""

import pytest

pytest.importorskip("agent_framework")

from critique_loop_maf.agents import CANDIDATE_ANGLES, build_agents, build_chat_client
from critique_loop_maf.config import FoundrySettings


def make_settings() -> FoundrySettings:
    return FoundrySettings(
        openai_v1_endpoint="https://example.openai.azure.com/openai/v1",
        model="gpt-5.4-mini",
        api_key="dummy",
        app_insights_connection_string=None,
    )


def test_three_candidate_angles_with_distinct_instructions() -> None:
    """元アプリの「temperature=0.9 ×3」の多様性をペルソナ差に置き換える
    (Port 2 の翻訳)。数は元実装の並列候補数 3 に合わせる。"""
    names = [name for name, _ in CANDIDATE_ANGLES]
    instructions = [text for _, text in CANDIDATE_ANGLES]

    assert len(CANDIDATE_ANGLES) == 3
    assert len(set(names)) == 3
    assert len(set(instructions)) == 3


def test_build_agents_wires_four_roles_offline() -> None:
    agents = build_agents(build_chat_client(make_settings()))

    assert [c.name for c in agents.candidates] == [name for name, _ in CANDIDATE_ANGLES]
    for role in (agents.synthesizer, agents.critic, agents.reviser):
        assert callable(role.run)
    for candidate in agents.candidates:
        assert callable(candidate.agent.run)


def test_critic_has_response_format() -> None:
    """元の「'•' 箇条書きの自由テキスト批評」を、ネイティブ構造化出力
    (response_format=CritiqueVerdict)+lenient フォールバックに強化している。"""
    from critique_loop_maf.schemas import CritiqueVerdict

    agents = build_agents(build_chat_client(make_settings()))

    assert agents.critic.default_options.get("response_format") is CritiqueVerdict


def test_other_roles_are_plain_text() -> None:
    """統合・改訂・候補は元実装同様プレーンテキスト応答(response_format なし)。"""
    agents = build_agents(build_chat_client(make_settings()))

    assert not (agents.synthesizer.default_options or {}).get("response_format")
    assert not (agents.reviser.default_options or {}).get("response_format")
    for candidate in agents.candidates:
        assert not (candidate.agent.default_options or {}).get("response_format")
