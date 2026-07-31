"""信頼スコアリングとゲートの単体テスト。"""

from __future__ import annotations

from conftest import approve_report, complete_claim, vague_claim

from governed_agent_maf.schemas import InspectionFinding
from governed_agent_maf.trust import (
    TrustGate,
    score_inspection,
    score_intake,
    score_to_tier,
)


def test_tier_boundaries_match_original() -> None:
    assert score_to_tier(60) == "gold"
    assert score_to_tier(59) == "silver"
    assert score_to_tier(40) == "silver"
    assert score_to_tier(39) == "bronze"
    assert score_to_tier(20) == "bronze"
    assert score_to_tier(19) == "none"


def test_complete_claim_scores_gold() -> None:
    trust = score_intake(complete_claim())
    assert trust.score == 75
    assert trust.tier == "gold"
    assert trust.deductions == ()


def test_vague_claim_scores_none_tier() -> None:
    trust = score_intake(vague_claim())
    # 75 - 25(金額) - 20(社員ID) - 15(領収書) - 10(カテゴリ) - 15(不確定3件)
    assert trust.score == 0
    assert trust.tier == "none"
    assert len(trust.deductions) == 5


def test_missing_receipt_only_still_passes_default_gate() -> None:
    trust = score_intake(complete_claim(has_receipt=False, receipt_reference="not specified"))
    assert trust.score == 60
    assert TrustGate().check(trust).passed


def test_confident_clean_report_scores_high() -> None:
    trust = score_inspection(approve_report())
    assert trust.score == 70
    assert trust.tier == "gold"


def test_low_confidence_with_critical_findings_fails_gate() -> None:
    report = approve_report(
        confidence=0.3,
        findings=[
            InspectionFinding(
                finding_id="INS-001", severity="critical", note="amount contradicts receipt"
            )
        ],
    )
    trust = score_inspection(report)
    # 70 - 30(低確信) - 15(critical 1 件)
    assert trust.score == 25
    verdict = TrustGate().check(trust)
    assert not verdict.passed
    assert verdict.tag == "escalate:25"
    assert "below threshold" in verdict.reason


def test_warning_findings_cap() -> None:
    findings = [
        InspectionFinding(finding_id=f"INS-{i:03d}", severity="warning", note="minor")
        for i in range(5)
    ]
    trust = score_inspection(approve_report(findings=findings))
    # warning 減点は 15 でキャップ → 70 - 15
    assert trust.score == 55


def test_gate_threshold_is_configurable() -> None:
    trust = score_intake(complete_claim(has_receipt=False))  # 60
    assert TrustGate(threshold=40).check(trust).passed
    assert not TrustGate(threshold=70).check(trust).passed


def test_pass_tag_format() -> None:
    verdict = TrustGate().check(score_intake(complete_claim()))
    assert verdict.tag == "pass:75"
