"""決定論ポリシーエンジンの単体テスト(境界値を含む)。"""

from __future__ import annotations

from datetime import datetime

from conftest import AFTER_HOURS, BUSINESS_NOW

from governed_agent_maf.policies import (
    Decision,
    GovernancePolicy,
    PolicyEngine,
    ToolCallRequest,
    build_policy_tool_result,
)


def _request(tool: str, arguments: dict | None = None, at: datetime = BUSINESS_NOW):
    return ToolCallRequest(tool=tool, arguments=arguments or {}, requested_at=at)


def _engine(**overrides) -> PolicyEngine:
    return PolicyEngine(GovernancePolicy(**overrides))


ENGINE = _engine()


# --- 許可ツールリスト ---


def test_unlisted_tool_is_denied() -> None:
    decision = ENGINE.evaluate(_request("delete_expense_record", {"record_id": "X-1"}))
    assert decision.decision is Decision.DENY
    assert decision.rule_id == "TOOL-001"


def test_unknown_tool_is_denied() -> None:
    decision = ENGINE.evaluate(_request("send_wire_transfer", {"amount_usd": 10}))
    assert decision.decision is Decision.DENY
    assert decision.rule_id == "TOOL-001"


def test_readonly_tools_are_allowed() -> None:
    for tool in ("lookup_expense_policy", "check_budget"):
        decision = ENGINE.evaluate(_request(tool, {"category": "meals"}))
        assert decision.decision is Decision.ALLOW, tool
        assert decision.rule_id == "POLICY-DEFAULT"


# --- 営業時間(mutating ツールのみ)---


def test_submit_outside_business_hours_is_denied() -> None:
    decision = ENGINE.evaluate(_request("submit_reimbursement", {"amount_usd": 100}, AFTER_HOURS))
    assert decision.decision is Decision.DENY
    assert decision.rule_id == "HOURS-001"


def test_submit_on_weekend_is_denied() -> None:
    saturday = datetime(2026, 8, 1, 10, 0)
    decision = ENGINE.evaluate(_request("submit_reimbursement", {"amount_usd": 100}, saturday))
    assert decision.rule_id == "HOURS-001"


def test_business_hour_boundaries() -> None:
    def rule_at(hour: int, minute: int) -> str:
        at = datetime(2026, 7, 29, hour, minute)
        return ENGINE.evaluate(_request("submit_reimbursement", {"amount_usd": 100}, at)).rule_id

    assert rule_at(9, 0) == "POLICY-DEFAULT"  # 開始時刻は含む
    assert rule_at(8, 59) == "HOURS-001"
    assert rule_at(17, 59) == "POLICY-DEFAULT"
    assert rule_at(18, 0) == "HOURS-001"  # 終了時刻は含まない


def test_readonly_tool_ignores_business_hours() -> None:
    decision = ENGINE.evaluate(_request("check_budget", {"department": "sales"}, AFTER_HOURS))
    assert decision.decision is Decision.ALLOW


# --- 金額上限 ---


def test_amount_within_auto_approve_is_allowed() -> None:
    decision = ENGINE.evaluate(_request("submit_reimbursement", {"amount_usd": 1000.0}))
    assert decision.decision is Decision.ALLOW  # 上限ちょうどは自動承認


def test_amount_above_auto_approve_requires_approval() -> None:
    decision = ENGINE.evaluate(_request("submit_reimbursement", {"amount_usd": 1000.01}))
    assert decision.decision is Decision.REQUIRE_APPROVAL
    assert decision.rule_id == "AMT-002"


def test_amount_at_hard_limit_requires_approval() -> None:
    decision = ENGINE.evaluate(_request("submit_reimbursement", {"amount_usd": 5000.0}))
    assert decision.decision is Decision.REQUIRE_APPROVAL


def test_amount_above_hard_limit_is_denied() -> None:
    decision = ENGINE.evaluate(_request("submit_reimbursement", {"amount_usd": 5000.01}))
    assert decision.decision is Decision.DENY
    assert decision.rule_id == "AMT-001"


def test_invalid_amounts_are_denied() -> None:
    for amount in (None, 0, -50, "not-a-number"):
        decision = ENGINE.evaluate(_request("submit_reimbursement", {"amount_usd": amount}))
        assert decision.decision is Decision.DENY, amount
        assert decision.rule_id == "AMT-003", amount


# --- ルールの優先順位(最初の確定判定が勝つ)---


def test_allowlist_wins_over_amount() -> None:
    # 非許可ツールは金額に関係なく TOOL-001
    decision = ENGINE.evaluate(_request("delete_expense_record", {"amount_usd": 999999}))
    assert decision.rule_id == "TOOL-001"


def test_business_hours_wins_over_amount() -> None:
    decision = ENGINE.evaluate(
        _request("submit_reimbursement", {"amount_usd": 999999}, AFTER_HOURS)
    )
    assert decision.rule_id == "HOURS-001"


# --- 構造化拒否ペイロード ---


def test_denied_tool_result_payload() -> None:
    request = _request("submit_reimbursement", {"amount_usd": 9000.0})
    decision = ENGINE.evaluate(request)
    payload = build_policy_tool_result(decision, request)
    assert payload["status"] == "deny"
    assert payload["rule_id"] == "AMT-001"
    assert payload["tool"] == "submit_reimbursement"
    assert "NOT executed" in payload["note"]
    assert "ticket_id" not in payload


def test_pending_tool_result_payload_includes_ticket() -> None:
    request = _request("submit_reimbursement", {"amount_usd": 3000.0})
    decision = ENGINE.evaluate(request)
    payload = build_policy_tool_result(decision, request, ticket_id="HITL-0001")
    assert payload["status"] == "pending_human_approval"
    assert payload["ticket_id"] == "HITL-0001"


def test_policy_overrides() -> None:
    engine = _engine(auto_approve_limit_usd=10.0, hard_limit_usd=20.0)
    assert (
        engine.evaluate(_request("submit_reimbursement", {"amount_usd": 15})).decision
        is Decision.REQUIRE_APPROVAL
    )
    assert (
        engine.evaluate(_request("submit_reimbursement", {"amount_usd": 25})).decision
        is Decision.DENY
    )


def test_decision_tag_format() -> None:
    decision = ENGINE.evaluate(_request("submit_reimbursement", {"amount_usd": 9000.0}))
    assert decision.tag == "deny:AMT-001"
