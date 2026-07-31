"""FNOL コアワークフローのオフラインテスト。LLM は ScriptedAgent(ネットワーク不要)。

検証項目:
- 抽出→検証→分類→規則→チェックリスト→ゲート→パケットの 7 段が順に流れ、
  IntakeState が 1 回だけ出力される
- 抽出プロンプトに transcript 全文、分類プロンプトに前段の JSON が渡る
- 構造化出力の lenient パース(散文包み)と、壊れた場合のフォールバック
- 空 transcript の短絡(LLM を呼ばない)
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("agent_framework")

from conftest import FakeResponse, ScriptedAgent, complete_flood_claim, flood_classification

from claim_voice_live_maf.agents import ClaimIntakeAgents
from claim_voice_live_maf.schemas import IntakeState
from claim_voice_live_maf.workflow import (
    EXTRACT_PROMPT_PREFIX,
    ClaimTurn,
    StageDone,
    build_intake_workflow,
    run_intake_turn,
)

TRANSCRIPT = (
    "I need to start a homeowners claim. Policyholder is Maya Singh, policy H0-44721. "
    "Basement flooded in Denver on March 18, 2026. We took photos and a short video."
)

EXTRACT_JSON = complete_flood_claim().model_dump_json()
CLASSIFY_JSON = flood_classification().model_dump_json()


def make_agents(
    extract_reply: str | FakeResponse = EXTRACT_JSON,
    classify_reply: str | FakeResponse = CLASSIFY_JSON,
) -> tuple[ClaimIntakeAgents, ScriptedAgent, ScriptedAgent]:
    extractor = ScriptedAgent(extract_reply)
    classifier = ScriptedAgent(classify_reply)
    return ClaimIntakeAgents(extractor=extractor, classifier=classifier), extractor, classifier


async def test_full_pipeline_produces_intake_state() -> None:
    agents, extractor, classifier = make_agents()
    state = await run_intake_turn(agents, TRANSCRIPT)

    assert isinstance(state, IntakeState)
    assert state.claim.policyholder_name == "Maya Singh"
    assert state.classification.claim_type == "home_water_damage"
    assert state.route == "needs_docs"  # 書類(mitigation invoice 等)が未提出
    assert "Mitigation or drying invoice" in state.next_question
    assert len(extractor.received) == 1
    assert len(classifier.received) == 1


async def test_extract_prompt_carries_full_transcript_with_source_prefix() -> None:
    agents, extractor, _ = make_agents()
    await run_intake_turn(agents, TRANSCRIPT)
    prompt = extractor.received[0]
    assert prompt.startswith(EXTRACT_PROMPT_PREFIX)
    assert TRANSCRIPT in prompt


async def test_classifier_prompt_carries_claim_and_validation_json() -> None:
    agents, _, classifier = make_agents()
    await run_intake_turn(agents, TRANSCRIPT)
    prompt = classifier.received[0]
    assert "Maya Singh" in prompt  # normalized claim JSON
    assert '"intake_status"' in prompt  # validation JSON
    assert '"valid"' in prompt


async def test_stage_events_flow_in_order() -> None:
    agents, _, _ = make_agents()
    stages: list[StageDone] = []
    await run_intake_turn(agents, TRANSCRIPT, on_stage=stages.append)
    assert [s.stage for s in stages] == [
        "extract",
        "validate",
        "classify",
        "rules",
        "checklist",
        "gate",
    ]
    assert stages[5].summary == "final_route=needs_docs"


async def test_native_structured_output_value_is_preferred() -> None:
    claim = complete_flood_claim()
    agents, _, _ = make_agents(
        extract_reply=FakeResponse(text="(not json)", value=claim)
    )
    state = await run_intake_turn(agents, TRANSCRIPT)
    assert state.claim.policyholder_name == "Maya Singh"


async def test_json_wrapped_in_prose_is_parsed() -> None:
    wrapped = f"Here is the extraction:\n```json\n{EXTRACT_JSON}\n```"
    agents, _, _ = make_agents(extract_reply=wrapped)
    state = await run_intake_turn(agents, TRANSCRIPT)
    assert state.claim.policy_number == "H0-44721"


async def test_extraction_failure_falls_back_to_blank_claim() -> None:
    agents, _, _ = make_agents(extract_reply="I could not extract anything useful.")
    state = await run_intake_turn(agents, TRANSCRIPT)
    # 空クレームとして決定論段が続行し、次質問はブロッキング項目の先頭
    assert state.validation.intake_status == "missing_info"
    assert state.next_question == "What is your full name as it appears on the policy?"


async def test_classification_failure_falls_back_to_initial() -> None:
    agents, _, _ = make_agents(classify_reply="It is probably a flood thing.")
    state = await run_intake_turn(agents, TRANSCRIPT)
    assert state.classification.claim_type == "other"
    assert state.classification.severity == "medium"


async def test_empty_transcript_short_circuits_without_llm() -> None:
    agents, extractor, classifier = make_agents()
    state = await run_intake_turn(agents, "   ")
    assert extractor.received == []
    assert classifier.received == []
    assert state.route == "needs_docs"
    assert state.validation.intake_status == "missing_info"


async def test_injury_scenario_reaches_emergency_escalation() -> None:
    claim = complete_flood_claim(
        loss_description="Another car ran a red light and hit my driver's side.",
        injuries_or_safety_concerns=["passenger neck pain, went to urgent care"],
        evidence_available=["photos", "police report number PDX-24-8811", "tow receipt"],
    )
    agents, _, _ = make_agents(
        extract_reply=claim.model_dump_json(),
        classify_reply=flood_classification(
            claim_type="auto_collision", severity="urgent"
        ).model_dump_json(),
    )
    state = await run_intake_turn(agents, "auto claim transcript")
    assert state.route == "emergency_escalation"
    assert "human representative" in state.next_question
    assert any(s.signal_id == "SAFETY-001" for s in state.gate.signals)


async def test_workflow_run_without_stream_returns_output() -> None:
    agents, _, _ = make_agents()
    workflow = build_intake_workflow(agents)
    result = await workflow.run(ClaimTurn(transcript=TRANSCRIPT))
    outputs = result.get_outputs() if hasattr(result, "get_outputs") else result
    if isinstance(outputs, list):
        assert any(isinstance(o, IntakeState) for o in outputs)
    else:
        assert isinstance(outputs, IntakeState)


async def test_intake_state_to_dict_is_json_serializable() -> None:
    agents, _, _ = make_agents()
    state = await run_intake_turn(agents, TRANSCRIPT)
    payload = json.loads(json.dumps(state.to_dict(), ensure_ascii=False))
    assert payload["gate"]["final_routing_decision"] == "needs_docs"
    assert payload["packet"]["claim_type"] == "home_water_damage"
