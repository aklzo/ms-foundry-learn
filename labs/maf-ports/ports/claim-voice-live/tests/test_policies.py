"""決定論ルール(policies.py)の網羅テスト。LLM もネットワークも不要。

元 ADK 実装の挙動互換を規則 ID 単位で固定する:
必須項目(INTAKE-001/002)、書類(DOC-001, THEFT-001)、高額(LOSS-001,
EVID-001)、安全(SAFE-001/002, SAFETY-001)、タイミング(TIMING-001/002)、
曖昧事実(FACTS-001)、盗難未届け(THEFT-002)、ルート優先順位、次質問生成。
"""

from __future__ import annotations

from conftest import complete_flood_claim, flood_classification

from claim_voice_live_maf.policies import (
    _document_provided,
    _next_claimant_message,
    _parse_date,
    apply_coverage_and_evidence_rules,
    build_intake_state,
    fraud_signal_and_safety_gate,
    generate_document_checklist,
    validate_required_claim_fields,
)
from claim_voice_live_maf.schemas import ClaimClassification, ClaimNarrative

# --- validate_required_claim_fields ----------------------------------------


def test_blank_claim_reports_all_required_fields_missing() -> None:
    validation = validate_required_claim_fields(ClaimNarrative())
    assert validation.intake_status == "missing_info"
    assert set(validation.missing_fields) == {
        "policyholder_name",
        "policy_number",
        "contact_method",
        "date_of_loss",
        "loss_location",
        "loss_description",
    }
    assert not validation.ready_for_policy_review
    assert validation.warnings == ["Estimated loss amount was not supplied."]


def test_complete_claim_is_valid() -> None:
    validation = validate_required_claim_fields(complete_flood_claim())
    assert validation.intake_status == "valid"
    assert validation.missing_fields == []
    assert validation.ready_for_policy_review


def test_blank_marker_variants_count_as_missing() -> None:
    claim = complete_flood_claim(policy_number="Unknown", contact_method="N/A")
    validation = validate_required_claim_fields(claim)
    assert "policy_number" in validation.missing_fields
    assert "contact_method" in validation.missing_fields


def test_uncertain_facts_are_merged_and_deduped() -> None:
    claim = complete_flood_claim(
        policy_number="not specified",
        missing_or_uncertain_facts=["policy_number", "exact time of failure"],
    )
    validation = validate_required_claim_fields(claim)
    assert validation.missing_fields.count("policy_number") == 1
    assert "exact time of failure" in validation.missing_fields


# --- apply_coverage_and_evidence_rules -------------------------------------


def test_missing_fields_trigger_intake_001_and_needs_docs() -> None:
    claim = ClaimNarrative()
    validation = validate_required_claim_fields(claim)
    coverage = apply_coverage_and_evidence_rules(claim, validation, ClaimClassification())
    assert any(f.rule_id == "INTAKE-001" for f in coverage.findings)
    assert coverage.routing_decision == "needs_docs"


def test_provided_documents_do_not_generate_doc_findings() -> None:
    claim = complete_flood_claim()
    validation = validate_required_claim_fields(claim)
    coverage = apply_coverage_and_evidence_rules(claim, validation, flood_classification())
    doc_findings = [f for f in coverage.findings if f.rule_id == "DOC-001"]
    # photos は提出済み(evidence に photo/video あり)なので要求されない
    assert all("Photos or video" not in (f.document or "") for f in doc_findings)
    # mitigation invoice は未提出なので要求される
    assert any("Mitigation or drying invoice" == f.document for f in doc_findings)
    assert coverage.routing_decision == "needs_docs"


def test_high_estimated_loss_triggers_loss_001() -> None:
    claim = complete_flood_claim(estimated_loss_usd=30000.0)
    validation = validate_required_claim_fields(claim)
    coverage = apply_coverage_and_evidence_rules(claim, validation, flood_classification())
    finding = next(f for f in coverage.findings if f.rule_id == "LOSS-001")
    assert finding.required_action == "adjuster_review"


def test_water_damage_hazard_language_triggers_safe_001_escalation() -> None:
    claim = complete_flood_claim(
        loss_description="Basement flooded, sewage backup made the room unsafe."
    )
    validation = validate_required_claim_fields(claim)
    coverage = apply_coverage_and_evidence_rules(claim, validation, flood_classification())
    assert any(f.rule_id == "SAFE-001" for f in coverage.findings)
    assert coverage.routing_decision == "emergency_escalation"


def test_auto_injury_triggers_safe_002_escalation() -> None:
    claim = complete_flood_claim(
        loss_description="Another car hit my driver's side.",
        injuries_or_safety_concerns=["passenger neck pain, went to urgent care"],
    )
    validation = validate_required_claim_fields(claim)
    classification = flood_classification(claim_type="auto_collision")
    coverage = apply_coverage_and_evidence_rules(claim, validation, classification)
    assert any(f.rule_id == "SAFE-002" for f in coverage.findings)
    assert coverage.routing_decision == "emergency_escalation"


def test_negated_injury_mention_does_not_escalate() -> None:
    claim = complete_flood_claim(
        loss_description="Fender bender in a parking lot. No injuries were reported.",
        injuries_or_safety_concerns=["no injuries"],
    )
    validation = validate_required_claim_fields(claim)
    classification = flood_classification(claim_type="auto_collision")
    coverage = apply_coverage_and_evidence_rules(claim, validation, classification)
    assert not any(f.rule_id == "SAFE-002" for f in coverage.findings)
    assert coverage.routing_decision != "emergency_escalation"


def test_theft_without_police_report_triggers_theft_001() -> None:
    claim = complete_flood_claim(
        loss_description="Laptop stolen from my backpack at a coffee shop.",
        evidence_available=["purchase receipt", "serial number"],
    )
    validation = validate_required_claim_fields(claim)
    classification = flood_classification(claim_type="theft_property_loss")
    coverage = apply_coverage_and_evidence_rules(claim, validation, classification)
    finding = next(f for f in coverage.findings if f.rule_id == "THEFT-001")
    assert finding.document == "Police report number or theft report"


# --- generate_document_checklist -------------------------------------------


def test_checklist_marks_provided_and_required_items() -> None:
    claim = complete_flood_claim()
    validation = validate_required_claim_fields(claim)
    classification = flood_classification()
    coverage = apply_coverage_and_evidence_rules(claim, validation, classification)
    checklist = generate_document_checklist(claim, classification, coverage)

    by_item = {item.item: item for item in checklist.items}
    photos = by_item["Photos or video of damaged areas before cleanup"]
    assert photos.already_provided
    assert photos.priority == "recommended"  # 提出済みなので required_docs に入らない
    mitigation = by_item["Mitigation or drying invoice"]
    assert not mitigation.already_provided
    assert mitigation.priority == "required"


def test_auto_injury_adds_treatment_location_item() -> None:
    claim = complete_flood_claim(
        injuries_or_safety_concerns=["passenger went to urgent care"],
        loss_description="Collision at an intersection.",
    )
    validation = validate_required_claim_fields(claim)
    classification = flood_classification(claim_type="auto_collision")
    coverage = apply_coverage_and_evidence_rules(claim, validation, classification)
    checklist = generate_document_checklist(claim, classification, coverage)
    extra = next(i for i in checklist.items if i.item == "Names of injured people and treatment locations")
    assert extra.priority == "required"


# --- fraud_signal_and_safety_gate ------------------------------------------


def _gate_for(claim: ClaimNarrative, classification: ClaimClassification):
    validation = validate_required_claim_fields(claim)
    coverage = apply_coverage_and_evidence_rules(claim, validation, classification)
    return fraud_signal_and_safety_gate(claim, validation, classification, coverage)


def test_report_before_loss_triggers_timing_001_siu() -> None:
    claim = complete_flood_claim(date_of_loss="2026-03-18", reported_date="2026-03-01")
    gate = _gate_for(claim, flood_classification())
    assert any(s.signal_id == "TIMING-001" for s in gate.signals)
    assert gate.final_routing_decision == "special_investigation"


def test_late_report_triggers_timing_002_siu() -> None:
    claim = complete_flood_claim(date_of_loss="January 5, 2026", reported_date="May 20, 2026")
    gate = _gate_for(claim, flood_classification())
    assert any(s.signal_id == "TIMING-002" for s in gate.signals)
    assert gate.final_routing_decision == "special_investigation"


def test_vague_facts_trigger_facts_001_without_siu() -> None:
    claim = complete_flood_claim(
        loss_description="Something happened, I don't remember the exact date."
    )
    gate = _gate_for(claim, flood_classification())
    facts = next(s for s in gate.signals if s.signal_id == "FACTS-001")
    assert not facts.route_to_siu
    assert gate.final_routing_decision != "special_investigation"


def test_high_loss_without_evidence_triggers_evid_001_siu() -> None:
    claim = complete_flood_claim(
        estimated_loss_usd=15000.0, evidence_available=[], documents_mentioned=[]
    )
    gate = _gate_for(claim, flood_classification())
    assert any(s.signal_id == "EVID-001" for s in gate.signals)
    assert gate.final_routing_decision == "special_investigation"


def test_theft_unfiled_police_report_signals_theft_002() -> None:
    claim = complete_flood_claim(
        loss_description="Stolen laptop. I have not filed a police report yet.",
        evidence_available=["purchase receipt"],
    )
    gate = _gate_for(claim, flood_classification(claim_type="theft_property_loss"))
    theft = next(s for s in gate.signals if s.signal_id == "THEFT-002")
    assert not theft.route_to_siu


def test_emergency_beats_siu_in_final_route() -> None:
    # 負傷(SAFE-002 → SAFETY-001)と高額無証憑(EVID-001 SIU)が同時でも emergency が勝つ
    claim = complete_flood_claim(
        estimated_loss_usd=20000.0,
        evidence_available=[],
        documents_mentioned=[],
        injuries_or_safety_concerns=["driver was hurt and taken to hospital"],
    )
    gate = _gate_for(claim, flood_classification(claim_type="auto_collision"))
    ids = {s.signal_id for s in gate.signals}
    assert {"SAFETY-001", "EVID-001"} <= ids
    assert gate.final_routing_decision == "emergency_escalation"


def test_missing_core_facts_signal_intake_002() -> None:
    gate = _gate_for(ClaimNarrative(), ClaimClassification())
    assert any(s.signal_id == "INTAKE-002" for s in gate.signals)


# --- 日付パーサ --------------------------------------------------------------


def test_parse_date_supported_formats() -> None:
    for text in ["2026-03-18", "3/18/2026", "March 18, 2026", "Mar 18 2026", "March 18th, 2026"]:
        parsed = _parse_date(text)
        assert parsed is not None, text
        assert (parsed.year, parsed.month, parsed.day) == (2026, 3, 18), text


def test_parse_date_unparseable_returns_none() -> None:
    assert _parse_date("last week sometime") is None
    assert _parse_date("") is None


# --- 次質問生成 --------------------------------------------------------------


def test_next_message_emergency_overrides_questions() -> None:
    message = _next_claimant_message("emergency_escalation", ["policyholder_name"], ["Photos"])
    assert "human representative" in message


def test_next_message_asks_blocking_field_first() -> None:
    message = _next_claimant_message(
        "needs_docs", ["policy_number", "date_of_loss"], ["Photos of vehicles and scene"]
    )
    assert message == "What is the policy number, if you have it available?"


def test_next_message_falls_back_to_non_blocking_then_documents() -> None:
    clarify = _next_claimant_message("needs_docs", ["exact time of failure"], ["Photos"])
    assert "exact time of failure" in clarify
    docs = _next_claimant_message("needs_docs", [], ["Mitigation or drying invoice"])
    assert "Mitigation or drying invoice" in docs


def test_next_message_ready_for_adjuster() -> None:
    message = _next_claimant_message("ready_for_adjuster", [], [])
    assert "core information needed for adjuster assignment" in message


# --- パケット / 一括実行 -----------------------------------------------------


def test_build_intake_state_blank_produces_packet_skeleton() -> None:
    state = build_intake_state()
    assert state.route == "needs_docs"
    assert state.validation.intake_status == "missing_info"
    assert state.next_question == "What is your full name as it appears on the policy?"
    assert "# Insurance Claim Intake Packet" in state.packet.markdown


def test_packet_markdown_contains_all_sections_and_route_label() -> None:
    claim = complete_flood_claim()
    state = build_intake_state(claim, flood_classification())
    md = state.packet.markdown
    for section in [
        "## Missing Information",
        "## Required Documents Checklist",
        "## Coverage Considerations and Disclaimer",
        "## Adjuster Handoff Summary",
        "## Claimant-Friendly Next Message",
        "## Deterministic Findings",
        "## Fraud, Timing, and Safety Signals",
        "## Audit Trail",
    ]:
        assert section in md
    assert "**Routing decision:** Needs Docs" in md
    assert "Maya Singh reported a home water damage loss at Denver" in state.packet.adjuster_handoff_summary


def test_document_provided_or_fallback_quirk_is_preserved() -> None:
    """元実装の癖: 書類名の先頭 3 語(カンマ付き)での部分文字列照合。

    "Refund, voucher, or credit documentation" はどのキーワード群にも
    掛からず、先頭 3 語 ["refund,", "voucher,", "or"] のフォールバックに
    落ちる。3 語目 "or" は "major" や "storm" のような語に**部分文字列**で
    ヒットするため、旅行クレームではほぼ常に「提出済み」になる。挙動互換の
    ため保存し、ここで文書化する(README「学び」参照)。
    """
    claim = complete_flood_claim(
        loss_description="A major winter storm caused the disruption.",
        evidence_available=[],
        documents_mentioned=[],
        raw_narrative_summary="Trip disrupted.",
    )
    assert _document_provided("Refund, voucher, or credit documentation", claim)

    # "or" を含む語が無ければフォールバックは成立しない(対照)
    control = complete_flood_claim(
        loss_description="The trip was delayed by heavy snow.",
        evidence_available=[],
        documents_mentioned=[],
        raw_narrative_summary="Trip delayed.",
    )
    assert not _document_provided("Refund, voucher, or credit documentation", control)
