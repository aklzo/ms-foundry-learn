"""経費精算ケースの多段パイプライン(申請 → 信頼ゲート → 検査 → 信頼ゲート → 承認)。

元 trust_gated_agent_team の「検証済みエージェントだけで直列パイプラインを
回す」構造の移植。元はエージェントの静的スコアで参加可否を決めたが、移植では
**前段の出力**を決定論検査してスコア化し、閾値未満は人間承認キューへ
エスカレーションして停止する(trust.py / hitl.py)。

最終ステータスは 2 通りの経路で決まる:
- ライブ/実行経路: 承認エージェントのツール呼び出しが実際に起こした副作用
  (台帳・キュー・監査連鎖)から導出する(``_derive_status``)
- 決定論経路: ``adjudicate()`` — 構造化済みの claim/report/提案アクションから
  同じステータスを計算する純関数。eval_dataset.jsonl のデータ駆動検証と、
  実行経路との一致テスト(test_pipeline)に使う
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .agents import GovernanceRuntime, GovernedAgents
from .hitl import ApprovalTicket
from .policies import Decision, PolicyDecision, PolicyEngine, ToolCallRequest
from .schemas import ExpenseClaim, InspectionReport
from .tools import PaymentRecord
from .trust import TrustGate, TrustVerdict, score_inspection, score_intake

#: 最終ステータス
STATUS_PAID = "paid"
STATUS_PENDING = "pending_human_approval"
STATUS_BLOCKED = "blocked_by_policy"
STATUS_ESCALATED = "escalated_low_trust"
STATUS_NO_ACTION = "no_action"


@dataclass(frozen=True)
class CaseRoute:
    """決定論経路(``adjudicate``)の結果。"""

    intake_gate: TrustVerdict
    inspection_gate: TrustVerdict | None
    policy_decision: PolicyDecision | None
    final_status: str


def adjudicate(
    claim: ExpenseClaim,
    report: InspectionReport | None,
    proposed_action: tuple[str, dict[str, Any]] | None,
    *,
    engine: PolicyEngine,
    gate: TrustGate,
    now: datetime,
) -> CaseRoute:
    """ゲート 2 段+ポリシー判定を決定論で通し、最終ステータスを導く純関数。"""
    intake_gate = gate.check(score_intake(claim))
    if not intake_gate.passed:
        return CaseRoute(intake_gate, None, None, STATUS_ESCALATED)

    if report is None:
        return CaseRoute(intake_gate, None, None, STATUS_NO_ACTION)
    inspection_gate = gate.check(score_inspection(report))
    if not inspection_gate.passed:
        return CaseRoute(intake_gate, inspection_gate, None, STATUS_ESCALATED)

    if proposed_action is None:
        return CaseRoute(intake_gate, inspection_gate, None, STATUS_NO_ACTION)
    tool, arguments = proposed_action
    decision = engine.evaluate(ToolCallRequest(tool=tool, arguments=arguments, requested_at=now))
    if decision.decision is Decision.DENY:
        status = STATUS_BLOCKED
    elif decision.decision is Decision.REQUIRE_APPROVAL:
        status = STATUS_PENDING
    else:
        status = STATUS_PAID if tool == "submit_reimbursement" else STATUS_NO_ACTION
    return CaseRoute(intake_gate, inspection_gate, decision, status)


@dataclass
class CaseResult:
    case_id: str
    request_text: str
    status: str
    claim: ExpenseClaim
    intake_gate: TrustVerdict
    report: InspectionReport | None = None
    inspection_gate: TrustVerdict | None = None
    approver_reply: str = ""
    payments: list[PaymentRecord] = field(default_factory=list)
    tickets: list[ApprovalTicket] = field(default_factory=list)
    chain_valid: bool = False
    chain_error: str | None = None
    audit_entries: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "status": self.status,
            "claim": self.claim.model_dump(),
            "intake_trust": {
                "score": self.intake_gate.trust.score,
                "tier": self.intake_gate.trust.tier,
                "passed": self.intake_gate.passed,
                "deductions": list(self.intake_gate.trust.deductions),
            },
            "report": self.report.model_dump() if self.report else None,
            "inspection_trust": (
                {
                    "score": self.inspection_gate.trust.score,
                    "tier": self.inspection_gate.trust.tier,
                    "passed": self.inspection_gate.passed,
                    "deductions": list(self.inspection_gate.trust.deductions),
                }
                if self.inspection_gate
                else None
            ),
            "approver_reply": self.approver_reply,
            "payments": [p.__dict__ for p in self.payments],
            "tickets": [
                {"ticket_id": t.ticket_id, "kind": t.kind, "reason": t.reason}
                for t in self.tickets
            ],
            "audit": {
                "entries": self.audit_entries,
                "chain_valid": self.chain_valid,
                "chain_error": self.chain_error,
            },
        }


def _structured(response: Any, model_type: type) -> Any:
    """AgentResponse から構造化出力を取り出す(.value 優先、text の JSON にフォールバック)。"""
    value = getattr(response, "value", None)
    if isinstance(value, model_type):
        return value
    return model_type.model_validate_json(response.text)


class ExpenseCasePipeline:
    """1 ケース = 申請テキスト → CaseResult。"""

    def __init__(self, agents: GovernedAgents, gov: GovernanceRuntime) -> None:
        self.agents = agents
        self.gov = gov
        self._case_seq = 0

    async def process(self, request_text: str) -> CaseResult:
        gov = self.gov
        self._case_seq += 1
        case_id = f"case-{self._case_seq:03d}"
        gov.audit.record(
            actor="pipeline",
            action="case_opened",
            input_text=request_text,
            output_text=case_id,
        )

        # --- 段 1: 申請の構造化(LLM)→ 信頼ゲート ---
        intake_response = await self.agents.intake.run(request_text)
        claim = _structured(intake_response, ExpenseClaim)
        intake_gate = gov.trust_gate.check(score_intake(claim))
        gov.audit.record(
            actor="pipeline",
            action="trust_gate:intake",
            input_text=claim.model_dump_json(),
            output_text=intake_gate.reason,
            detail=intake_gate.tag,
        )
        if not intake_gate.passed:
            ticket = gov.queue.enqueue(
                kind="low_trust",
                subject=case_id,
                reason=intake_gate.reason,
                payload=claim.model_dump(),
            )
            return self._close(
                case_id,
                request_text,
                STATUS_ESCALATED,
                claim,
                intake_gate,
                tickets=[ticket],
            )

        # --- 段 2: 検査(LLM)→ 信頼ゲート ---
        inspector_prompt = (
            "Inspect this expense claim and return an InspectionReport.\n\n"
            f"ExpenseClaim JSON:\n{claim.model_dump_json(indent=2)}"
        )
        inspection_response = await self.agents.inspector.run(inspector_prompt)
        report = _structured(inspection_response, InspectionReport)
        inspection_gate = gov.trust_gate.check(score_inspection(report))
        gov.audit.record(
            actor="pipeline",
            action="trust_gate:inspection",
            input_text=report.model_dump_json(),
            output_text=inspection_gate.reason,
            detail=inspection_gate.tag,
        )
        if not inspection_gate.passed:
            ticket = gov.queue.enqueue(
                kind="low_trust",
                subject=case_id,
                reason=inspection_gate.reason,
                payload=report.model_dump(),
            )
            return self._close(
                case_id,
                request_text,
                STATUS_ESCALATED,
                claim,
                intake_gate,
                report=report,
                inspection_gate=inspection_gate,
                tickets=[ticket],
            )

        # --- 段 3: 承認(LLM+ツール。ポリシー強制はツール middleware 側)---
        payments_before = len(gov.ledger.payments)
        tickets_before = len(gov.queue.tickets)
        audit_before = len(gov.audit.entries)
        approver_prompt = (
            "Decide on this expense case and act with your tools.\n\n"
            f"ExpenseClaim JSON:\n{claim.model_dump_json(indent=2)}\n\n"
            f"InspectionReport JSON:\n{report.model_dump_json(indent=2)}"
        )
        approver_response = await self.agents.approver.run(approver_prompt)

        new_payments = gov.ledger.payments[payments_before:]
        new_tickets = gov.queue.tickets[tickets_before:]
        denied = [
            e
            for e in gov.audit.entries[audit_before:]
            if e.action.startswith("tool:") and e.detail.startswith("deny:")
        ]
        if new_payments:
            status = STATUS_PAID
        elif any(t.kind == "tool_call" for t in new_tickets):
            status = STATUS_PENDING
        elif denied:
            status = STATUS_BLOCKED
        else:
            status = STATUS_NO_ACTION

        return self._close(
            case_id,
            request_text,
            status,
            claim,
            intake_gate,
            report=report,
            inspection_gate=inspection_gate,
            approver_reply=approver_response.text or "",
            payments=new_payments,
            tickets=new_tickets,
        )

    def _close(
        self,
        case_id: str,
        request_text: str,
        status: str,
        claim: ExpenseClaim,
        intake_gate: TrustVerdict,
        *,
        report: InspectionReport | None = None,
        inspection_gate: TrustVerdict | None = None,
        approver_reply: str = "",
        payments: list[PaymentRecord] | None = None,
        tickets: list[ApprovalTicket] | None = None,
    ) -> CaseResult:
        gov = self.gov
        gov.audit.record(
            actor="pipeline",
            action="case_closed",
            input_text=case_id,
            output_text=status,
            detail=status,
        )
        chain_valid, chain_error = gov.audit.verify_chain()
        return CaseResult(
            case_id=case_id,
            request_text=request_text,
            status=status,
            claim=claim,
            intake_gate=intake_gate,
            report=report,
            inspection_gate=inspection_gate,
            approver_reply=approver_reply,
            payments=list(payments or []),
            tickets=list(tickets or []),
            chain_valid=chain_valid,
            chain_error=chain_error,
            audit_entries=len(gov.audit.entries),
        )
