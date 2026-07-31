"""eval_dataset.jsonl(7 ケース)を決定論経路 ``adjudicate`` に流すデータ駆動検証。

LLM 3 段の**後段すべて**(信頼スコア → ゲート → ポリシー判定 → 最終ステータス)
を、構造化済みの claim / inspection / 提案アクションを入力に固定する。ライブ
評価で見るべき残余は「申請テキストからこの claim / inspection が出るか」に縮む。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from conftest import BUSINESS_NOW

from governed_agent_maf.pipeline import adjudicate
from governed_agent_maf.policies import GovernancePolicy, PolicyEngine
from governed_agent_maf.schemas import ExpenseClaim, InspectionReport
from governed_agent_maf.trust import TrustGate

DATASET = Path(__file__).parent / "eval_dataset.jsonl"


def load_cases() -> list[dict]:
    return [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line]


CASES = load_cases()


def test_dataset_has_enough_cases() -> None:
    assert len(CASES) >= 6
    assert len({case["id"] for case in CASES}) == len(CASES)


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_deterministic_route_matches_expectations(case: dict) -> None:
    claim = ExpenseClaim(**case["claim"])
    report = InspectionReport(**case["inspection"]) if case.get("inspection") else None
    proposed = case.get("proposed_action")
    action = (proposed["tool"], proposed["arguments"]) if proposed else None
    now = datetime.fromisoformat(case["now"]) if case.get("now") else BUSINESS_NOW

    route = adjudicate(
        claim,
        report,
        action,
        engine=PolicyEngine(GovernancePolicy()),
        gate=TrustGate(),
        now=now,
    )
    expect = case["expect"]

    assert route.final_status == expect["final_status"], case["id"]

    gate_state = "pass" if route.intake_gate.passed else "escalate"
    assert gate_state == expect["intake_gate"], case["id"]

    if expect["inspection_gate"] is None:
        assert route.inspection_gate is None, case["id"]
    else:
        gate_state = "pass" if route.inspection_gate.passed else "escalate"
        assert gate_state == expect["inspection_gate"], case["id"]

    if expect["policy"] is None:
        assert route.policy_decision is None, case["id"]
    else:
        assert route.policy_decision is not None, case["id"]
        assert route.policy_decision.decision.value == expect["policy"]["decision"], case["id"]
        assert route.policy_decision.rule_id == expect["policy"]["rule_id"], case["id"]
