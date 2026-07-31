"""テキスト対話層のオフラインテスト(ScriptedAgent。ネットワーク不要)。

検証項目: 初期状態(挨拶+パケット骨格)、ターン蓄積(transcript 全文が
コアに渡る)、エージェント応答が決定論の次質問であること、ターンをまたぐ
ルート遷移、スクリプト再生。
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("agent_framework")

from conftest import ScriptedAgent, complete_flood_claim, flood_classification

from claim_voice_live_maf.agents import ClaimIntakeAgents
from claim_voice_live_maf.conversation import (
    GREETING,
    ClaimIntakeConversation,
    load_script,
    run_script,
)

PARTIAL_CLAIM = complete_flood_claim(
    policy_number="not specified",
    contact_method="not specified",
).model_dump_json()
FULL_CLAIM = complete_flood_claim().model_dump_json()
CLASSIFY = flood_classification().model_dump_json()


def make_conversation(
    extract_replies: list[str], classify_replies: list[str] | None = None
) -> tuple[ClaimIntakeConversation, ScriptedAgent]:
    extractor = ScriptedAgent(list(extract_replies))
    classifier = ScriptedAgent(list(classify_replies or [CLASSIFY]))
    conversation = ClaimIntakeConversation(
        agents=ClaimIntakeAgents(extractor=extractor, classifier=classifier)
    )
    return conversation, extractor


def test_initial_state_has_greeting_and_packet_skeleton() -> None:
    conversation, _ = make_conversation([FULL_CLAIM])
    assert conversation.transcript[0].speaker == "Agent"
    assert conversation.transcript[0].text == GREETING
    assert conversation.state.route == "needs_docs"
    assert conversation.claimant_text() == ""


async def test_single_turn_appends_claimant_and_agent_reply() -> None:
    conversation, _ = make_conversation([FULL_CLAIM])
    state = await conversation.claimant_turn("I need to start a homeowners claim.")

    speakers = [t.speaker for t in conversation.transcript]
    assert speakers == ["Agent", "Claimant", "Agent"]
    # エージェント応答は決定論パケットの次質問そのもの
    assert conversation.transcript[-1].text == state.next_question


async def test_multi_turn_passes_accumulated_transcript_to_core() -> None:
    conversation, extractor = make_conversation([PARTIAL_CLAIM, FULL_CLAIM])
    await conversation.claimant_turn("My basement flooded on March 18.")
    await conversation.claimant_turn("Policy H0-44721, phone 415-555-0134.")

    assert len(extractor.received) == 2
    # 2 ターン目のプロンプトには 1 ターン目と 2 ターン目の両方の発話が入る
    assert "My basement flooded on March 18." in extractor.received[1]
    assert "Policy H0-44721, phone 415-555-0134." in extractor.received[1]
    # エージェント発話(挨拶・質問)はコア入力に混ざらない
    assert GREETING not in extractor.received[1]


async def test_route_and_question_evolve_across_turns() -> None:
    conversation, _ = make_conversation([PARTIAL_CLAIM, FULL_CLAIM])
    first = await conversation.claimant_turn("My basement flooded.")
    # 1 ターン目: policy_number が欠けている → ブロッキング質問
    assert "policy number" in first.next_question.lower()

    second = await conversation.claimant_turn("Policy H0-44721, phone 415-555-0134.")
    # 2 ターン目: 必須項目が揃い、質問は書類要求へ進む
    assert second.validation.intake_status == "valid"
    assert "Mitigation or drying invoice" in second.next_question


async def test_empty_turn_is_ignored() -> None:
    conversation, extractor = make_conversation([FULL_CLAIM])
    before = conversation.state
    state = await conversation.claimant_turn("   ")
    assert state is before
    assert extractor.received == []
    assert len(conversation.transcript) == 1


async def test_run_script_plays_all_lines_and_reports_states() -> None:
    conversation, _ = make_conversation([PARTIAL_CLAIM, FULL_CLAIM])
    seen: list[str] = []
    final = await run_script(
        conversation,
        ["My basement flooded.", "Policy H0-44721, phone 415-555-0134."],
        on_state=lambda line, state: seen.append(state.route),
    )
    assert len(seen) == 2
    assert final.validation.intake_status == "valid"
    claimant_turns = [t for t in conversation.transcript if t.speaker == "Claimant"]
    assert len(claimant_turns) == 2


def test_load_script_skips_blank_and_comment_lines(tmp_path: Path) -> None:
    script = tmp_path / "scenario.txt"
    script.write_text("# comment\n\nfirst line\n  \nsecond line\n", encoding="utf-8")
    assert load_script(script) == ["first line", "second line"]


def test_bundled_auto_injury_script_loads() -> None:
    path = Path(__file__).parent / "data" / "fnol_auto_injury.txt"
    lines = load_script(path)
    assert len(lines) == 3
    assert "Jordan Lee" in lines[0]
