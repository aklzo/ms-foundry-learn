"""eval_dataset.jsonl(8 ケース)を決定論パイプラインに流すデータ駆動検証。

LLM 2 段(抽出・分類)の**後段すべて**(検証→規則→チェックリスト→ゲート→
パケット→次質問)を、抽出済みクレーム+分類を入力に固定する。ライブ評価で
検証すべき残りは「transcript からこの claim/classification が抽出できるか」
だけに縮む(README の評価節参照)。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from claim_voice_live_maf.policies import build_intake_state
from claim_voice_live_maf.schemas import ClaimClassification, ClaimNarrative

DATASET = Path(__file__).parent / "eval_dataset.jsonl"


def load_cases() -> list[dict]:
    return [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line]


CASES = load_cases()


def test_dataset_has_enough_cases() -> None:
    assert len(CASES) >= 5
    assert len({case["id"] for case in CASES}) == len(CASES)


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_deterministic_pipeline_matches_expectations(case: dict) -> None:
    claim = ClaimNarrative(**case["claim"])
    classification = ClaimClassification(**case["classification"])
    state = build_intake_state(claim, classification)
    expect = case["expect"]

    assert state.route == expect["final_route"], case["id"]
    assert state.validation.intake_status == expect["intake_status"], case["id"]

    if "finding_rules" in expect:
        actual_rules = {f.rule_id for f in state.coverage.findings}
        if expect["finding_rules"]:
            assert set(expect["finding_rules"]) <= actual_rules, case["id"]
        else:
            assert actual_rules == set(), case["id"]

    if "signal_ids" in expect:
        actual_signals = {s.signal_id for s in state.gate.signals}
        if expect["signal_ids"]:
            assert set(expect["signal_ids"]) <= actual_signals, case["id"]
        else:
            assert actual_signals == set(), case["id"]

    if "next_question_contains" in expect:
        assert expect["next_question_contains"] in state.next_question, case["id"]

    # パケットは常に完全な Markdown を持つ(全ケース共通の不変条件)
    assert "# Insurance Claim Intake Packet" in state.packet.markdown
    assert state.packet.routing_decision == expect["final_route"]
