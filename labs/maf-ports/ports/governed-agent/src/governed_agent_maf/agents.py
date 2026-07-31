"""3 エージェント(申請の構造化・検査・承認)とガバナンスランタイムの組み立て。

3 体とも**実 MAF ``Agent``** として組む(他ポートの SupportsRun fake 注入と
違い、本ポートの検証対象は MAF の middleware 機構そのものなので、オフライン
テストも実 Agent + scripted チャットクライアントで middleware を通す)。

- intake / inspector: 構造化出力(``ChatOptions(response_format=...)``)+
  実行監査 middleware
- approver: ツール束+ポリシー強制/ツール監査/実行監査 middleware
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .audit import AuditTrail
from .config import FoundrySettings
from .hitl import ApprovalQueue
from .middleware import (
    AgentAuditMiddleware,
    PolicyEnforcementMiddleware,
    ToolAuditMiddleware,
)
from .policies import GovernancePolicy, PolicyEngine
from .tools import ExpenseLedger, build_tools
from .trust import DEFAULT_TRUST_THRESHOLD, TrustGate

INTAKE_INSTRUCTIONS = """\
You are the intake clerk for Contoso's expense reimbursement desk.

Read the employee's free-text expense request and produce a structured
ExpenseClaim. Preserve facts exactly. Do not invent employee ids, amounts,
dates, or receipt references.

Extraction rules:
- employee_id / employee_name / department: only if stated, otherwise "not specified".
- amount_usd: numeric USD amount only if supplied; otherwise null.
- category: one of travel, meals, equipment, software, training; use "other" only
  when none clearly applies.
- expense_date: as stated, otherwise "not specified".
- has_receipt: true only if the request explicitly mentions a receipt, invoice,
  or proof of payment. receipt_reference: the reference if given.
- missing_or_uncertain: list key facts that are absent, vague, or contradictory.

This is intake normalization only. Do not approve or reject.
"""

INSPECTOR_INSTRUCTIONS = """\
You are the expense inspector. You receive a structured expense claim as JSON.

Check it for consistency and completeness:
- Does the description match the category?
- Is the amount plausible for the category?
- Is documentation (receipt) present?
- Are there missing or suspicious facts (vague dates, round numbers with no
  receipt, duplicate-looking submissions)?

Produce an InspectionReport:
- findings: each with finding_id "INS-<nnn>", severity info/warning/critical, and a short note.
- recommendation: "approve" when documentation and consistency are acceptable,
  "needs_information" when facts are missing, "reject" for clear policy abuse.
  Do not reject solely because the amount is large; spending limits are enforced
  by a separate governance layer.
- confidence: 0.0-1.0, your confidence in this inspection.

Return only the structured InspectionReport.
"""

APPROVER_INSTRUCTIONS = """\
You are the final approver for Contoso expense reimbursements. You receive an
expense claim and an inspection report as JSON.

Act with your tools:
- If the recommendation is "approve", call submit_reimbursement with the claim's
  employee_id, amount_usd, category, and a one-line description.
- Use lookup_expense_policy or check_budget first if you need context.
- If the recommendation is "reject" or "needs_information", do not submit;
  explain the reason briefly instead.

A separate governance layer inspects every tool call BEFORE it executes. If a
tool returns status "deny" or "pending_human_approval", the call was not
executed: do not retry it, and report the rule_id and reason in your reply.

Keep the final reply to a few factual sentences.
"""


@dataclass
class GovernanceRuntime:
    """ガバナンス層の共有状態(ポリシー・監査連鎖・承認キュー・台帳・時計)。"""

    policy: GovernancePolicy
    engine: PolicyEngine
    audit: AuditTrail
    queue: ApprovalQueue
    ledger: ExpenseLedger
    trust_gate: TrustGate
    clock: Callable[[], datetime]


def build_governance(
    policy: GovernancePolicy | None = None,
    *,
    threshold: int = DEFAULT_TRUST_THRESHOLD,
    clock: Callable[[], datetime] = datetime.now,
    time_fn: Callable[[], float] | None = None,
) -> GovernanceRuntime:
    """ガバナンスランタイムを組み立てる。``clock`` は営業時間判定と監査時刻の源。"""
    policy = policy or GovernancePolicy()
    audit = AuditTrail(time_fn=time_fn) if time_fn is not None else AuditTrail()
    return GovernanceRuntime(
        policy=policy,
        engine=PolicyEngine(policy),
        audit=audit,
        queue=ApprovalQueue(),
        ledger=ExpenseLedger(),
        trust_gate=TrustGate(threshold=threshold),
        clock=clock,
    )


@dataclass
class GovernedAgents:
    intake: Any
    inspector: Any
    approver: Any


def build_chat_client(settings: FoundrySettings) -> Any:
    """共有基盤の OpenAI v1 互換エンドポイント+API キーのチャットクライアント。"""
    from agent_framework.openai import OpenAIChatClient

    return OpenAIChatClient(
        model=settings.model,
        api_key=settings.api_key,
        base_url=settings.openai_v1_endpoint,
    )


def build_agents(
    client: Any,
    gov: GovernanceRuntime,
    *,
    inspector_client: Any = None,
    approver_client: Any = None,
) -> GovernedAgents:
    """3 エージェントを middleware 込みで組み立てる。

    オフラインテストは 3 つの scripted クライアントを個別注入する(ライブは
    同一クライアントを共有)。middleware は Agent 構築時に渡す —
    function/chat middleware は実行時にフレームワークがチャットクライアントへ
    転送する(_middleware.py ``AgentMiddlewareLayer.run`` の仕組み)。
    """
    from agent_framework import Agent, ChatOptions

    from .schemas import ExpenseClaim, InspectionReport

    audit_mw = AgentAuditMiddleware(gov.audit)
    return GovernedAgents(
        intake=Agent(
            client,
            instructions=INTAKE_INSTRUCTIONS,
            name="expense_intake",
            default_options=ChatOptions(response_format=ExpenseClaim),
            middleware=[audit_mw],
        ),
        inspector=Agent(
            inspector_client if inspector_client is not None else client,
            instructions=INSPECTOR_INSTRUCTIONS,
            name="expense_inspector",
            default_options=ChatOptions(response_format=InspectionReport),
            middleware=[audit_mw],
        ),
        approver=Agent(
            approver_client if approver_client is not None else client,
            instructions=APPROVER_INSTRUCTIONS,
            name="expense_approver",
            tools=build_tools(gov.ledger),
            middleware=[
                audit_mw,
                # function middleware は列挙順がそのまま外→内(監査が外側 =
                # 遮断された呼び出しも連鎖に残る)
                ToolAuditMiddleware(gov.audit, actor="expense_approver"),
                PolicyEnforcementMiddleware(gov.engine, gov.queue, gov.clock),
            ],
        ),
    )
