"""決定論ポリシーエンジン(元 ai_agent_governance ``PolicyEngine`` の移植)。

元の構造を保存: ルール列を順に評価し、最初に確定判定(terminal)を返した
ルールが勝つ。どのルールにも当たらなければ既定 ALLOW。判定は 3 値
(ALLOW / DENY / REQUIRE_APPROVAL)。

元との差分:
- ドメイン移設: filesystem/network サンドボックス → 経費精算のツール統制
  (許可ツールリスト / 金額上限 / 営業時間)。ルール連鎖・3 値判定・
  「実行前に決定論で遮断」という骨格は同一
- YAML 設定 → 型付き dataclass ``GovernancePolicy``(検証済みの既定+CLI 上書き)
- 判定の執行場所がデコレータ(``governed_tool``)から **MAF FunctionMiddleware**
  に移った(middleware.py)。本モジュールはフレームワーク非依存の純関数のまま
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class Decision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


@dataclass(frozen=True)
class ToolCallRequest:
    """エージェントが実行しようとしているツール呼び出し(元 ``Action``)。"""

    tool: str
    arguments: Mapping[str, Any]
    requested_at: datetime


@dataclass(frozen=True)
class PolicyDecision:
    decision: Decision
    rule_id: str
    reason: str

    @property
    def tag(self) -> str:
        """監査ログの detail 欄に載せる短い表記(例 ``deny:AMT-001``)。"""
        return f"{self.decision.value}:{self.rule_id}"


@dataclass(frozen=True)
class GovernancePolicy:
    """決定論ルールの設定(元の YAML ポリシーに相当)。"""

    allowed_tools: tuple[str, ...] = (
        "lookup_expense_policy",
        "check_budget",
        "submit_reimbursement",
    )
    #: 支払い・削除など状態を変えるツール。金額・営業時間ルールの対象
    mutating_tools: tuple[str, ...] = ("submit_reimbursement", "delete_expense_record")
    auto_approve_limit_usd: float = 1_000.0
    hard_limit_usd: float = 5_000.0
    business_start_hour: int = 9  # 含む
    business_end_hour: int = 18  # 含まない
    business_days: tuple[int, ...] = (0, 1, 2, 3, 4)  # Mon-Fri(datetime.weekday())


class PolicyEngine:
    """ルールを順に評価し、最初の確定判定を返す(元 PolicyEngine.evaluate と同型)。

    ルール順は「許可リスト → 営業時間 → 金額」。順序は固定で、監査ログには
    確定判定を出したルール ID が残る。
    """

    def __init__(self, policy: GovernancePolicy) -> None:
        self.policy = policy
        self._rules = (
            self._check_allowlist,
            self._check_business_hours,
            self._check_amount,
        )

    def evaluate(self, request: ToolCallRequest) -> PolicyDecision:
        for rule in self._rules:
            result = rule(request)
            if result is not None:
                return result
        return PolicyDecision(
            decision=Decision.ALLOW,
            rule_id="POLICY-DEFAULT",
            reason="No policy rule blocked this tool call",
        )

    # --- 個別ルール(該当しなければ None = 次のルールへ)---

    def _check_allowlist(self, request: ToolCallRequest) -> PolicyDecision | None:
        if request.tool not in self.policy.allowed_tools:
            return PolicyDecision(
                decision=Decision.DENY,
                rule_id="TOOL-001",
                reason=f"Tool '{request.tool}' is not on the allowed tools list",
            )
        return None

    def _check_business_hours(self, request: ToolCallRequest) -> PolicyDecision | None:
        if request.tool not in self.policy.mutating_tools:
            return None  # 参照系ツールは時間帯を問わない
        now = request.requested_at
        in_hours = (
            now.weekday() in self.policy.business_days
            and self.policy.business_start_hour <= now.hour < self.policy.business_end_hour
        )
        if not in_hours:
            return PolicyDecision(
                decision=Decision.DENY,
                rule_id="HOURS-001",
                reason=(
                    f"Mutating tool '{request.tool}' is only allowed during business hours "
                    f"(weekdays {self.policy.business_start_hour:02d}:00-"
                    f"{self.policy.business_end_hour:02d}:00; "
                    f"requested at {now.isoformat(timespec='minutes')})"
                ),
            )
        return None

    def _check_amount(self, request: ToolCallRequest) -> PolicyDecision | None:
        if request.tool != "submit_reimbursement":
            return None
        raw = request.arguments.get("amount_usd")
        try:
            amount = float(raw) if raw is not None else None
        except (TypeError, ValueError):
            amount = None
        if amount is None or amount <= 0:
            return PolicyDecision(
                decision=Decision.DENY,
                rule_id="AMT-003",
                reason=f"Invalid reimbursement amount: {raw!r}",
            )
        if amount > self.policy.hard_limit_usd:
            return PolicyDecision(
                decision=Decision.DENY,
                rule_id="AMT-001",
                reason=(
                    f"Amount ${amount:,.2f} exceeds the hard limit "
                    f"${self.policy.hard_limit_usd:,.2f}"
                ),
            )
        if amount > self.policy.auto_approve_limit_usd:
            return PolicyDecision(
                decision=Decision.REQUIRE_APPROVAL,
                rule_id="AMT-002",
                reason=(
                    f"Amount ${amount:,.2f} exceeds the auto-approve limit "
                    f"${self.policy.auto_approve_limit_usd:,.2f}; human approval required"
                ),
            )
        return None


def build_policy_tool_result(
    decision: PolicyDecision,
    request: ToolCallRequest,
    *,
    ticket_id: str | None = None,
) -> dict[str, Any]:
    """遮断/保留時にモデルへ返す構造化ツール結果(実行はされていない)。

    元実装は ``PolicyViolation`` 例外を投げてエージェントループ自体を壊して
    いたが、移植では「構造化された拒否をツール結果として返し、モデルに事情を
    説明させる」— middleware の short-circuit(README 参照)。
    """
    status = (
        "pending_human_approval"
        if decision.decision is Decision.REQUIRE_APPROVAL
        else decision.decision.value
    )
    payload: dict[str, Any] = {
        "status": status,
        "rule_id": decision.rule_id,
        "reason": decision.reason,
        "tool": request.tool,
        "note": "This tool call was NOT executed. Do not retry; report this outcome.",
    }
    if ticket_id is not None:
        payload["ticket_id"] = ticket_id
    return payload
