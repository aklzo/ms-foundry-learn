"""多段パイプライン(申請 → ゲート → 検査 → ゲート → 承認)の統合テスト。

3 エージェントすべて実 ``Agent``(scripted クライアント)で回し、実行経路の
最終ステータスが決定論経路 ``adjudicate()`` と一致することも確認する。
"""

from __future__ import annotations

import json

from conftest import (
    BUSINESS_NOW,
    ScriptedChatClient,
    approve_report,
    claim_reply,
    complete_claim,
    make_runtime,
    report_reply,
    text_reply,
    tool_call_reply,
    vague_claim,
)

from governed_agent_maf.agents import build_agents
from governed_agent_maf.audit import load_entries, verify_entries
from governed_agent_maf.pipeline import (
    STATUS_BLOCKED,
    STATUS_ESCALATED,
    STATUS_NO_ACTION,
    STATUS_PAID,
    STATUS_PENDING,
    ExpenseCasePipeline,
    adjudicate,
)
from governed_agent_maf.schemas import InspectionFinding


def make_pipeline(gov, intake_replies, inspector_replies, approver_replies):
    agents = build_agents(
        ScriptedChatClient(intake_replies),
        gov,
        inspector_client=ScriptedChatClient(inspector_replies),
        approver_client=ScriptedChatClient(approver_replies),
    )
    return ExpenseCasePipeline(agents, gov), agents


def submit_call(amount: float = 180.0):
    return tool_call_reply(
        (
            "submit_reimbursement",
            {
                "employee_id": "E-1042",
                "amount_usd": amount,
                "category": "meals",
                "description": "client dinner",
            },
        )
    )


async def test_happy_path_is_paid() -> None:
    gov = make_runtime()
    pipeline, _ = make_pipeline(
        gov,
        claim_reply(),
        report_reply(),
        [submit_call(180.0), text_reply("Approved and paid (PAY-0001).")],
    )
    result = await pipeline.process("Client dinner $180 with receipt RCPT-2201, E-1042, sales.")

    assert result.status == STATUS_PAID
    assert result.intake_gate.passed and result.inspection_gate.passed
    assert [p.payment_id for p in result.payments] == ["PAY-0001"]
    assert result.tickets == []
    assert result.approver_reply.startswith("Approved")
    assert result.chain_valid

    # 監査連鎖にケースの全イベントが順に載っている
    actions = [e.action for e in gov.audit.entries]
    assert actions == [
        "case_opened",
        "agent_run",  # intake
        "trust_gate:intake",
        "agent_run",  # inspector
        "trust_gate:inspection",
        "tool:submit_reimbursement",
        "agent_run",  # approver
        "case_closed",
    ]

    # 決定論経路(adjudicate)と実行経路の一致
    route = adjudicate(
        complete_claim(),
        approve_report(),
        ("submit_reimbursement", {"amount_usd": 180.0}),
        engine=gov.engine,
        gate=gov.trust_gate,
        now=BUSINESS_NOW,
    )
    assert route.final_status == result.status


async def test_low_trust_intake_escalates_before_inspection() -> None:
    gov = make_runtime()
    pipeline, agents = make_pipeline(
        gov,
        text_reply(vague_claim().model_dump_json()),
        report_reply(),  # 使われないはず
        text_reply("unused"),
    )
    result = await pipeline.process("I spent some money on stuff, pay me back.")

    assert result.status == STATUS_ESCALATED
    assert not result.intake_gate.passed
    assert result.report is None  # 検査段まで到達していない
    assert agents.inspector.client.requests == []  # 検査モデルは呼ばれていない
    assert len(result.tickets) == 1
    assert result.tickets[0].kind == "low_trust"
    assert result.chain_valid


async def test_low_trust_inspection_escalates_before_approval() -> None:
    gov = make_runtime()
    low_trust_report = approve_report(
        confidence=0.3,
        findings=[
            InspectionFinding(finding_id="INS-001", severity="critical", note="contradiction")
        ],
    )
    pipeline, agents = make_pipeline(
        gov,
        claim_reply(),
        text_reply(low_trust_report.model_dump_json()),
        text_reply("unused"),
    )
    result = await pipeline.process("Client dinner $180 with receipt.")

    assert result.status == STATUS_ESCALATED
    assert result.intake_gate.passed
    assert not result.inspection_gate.passed
    assert agents.approver.client.requests == []  # 承認段は呼ばれていない
    assert gov.ledger.payments == []


async def test_over_hard_limit_is_blocked() -> None:
    gov = make_runtime()
    pipeline, _ = make_pipeline(
        gov,
        claim_reply(amount_usd=9000.0, category="equipment"),
        report_reply(),
        [submit_call(9000.0), text_reply("Blocked by AMT-001.")],
    )
    result = await pipeline.process("Workstation $9,000 with invoice, E-1042.")

    assert result.status == STATUS_BLOCKED
    assert gov.ledger.payments == []
    assert result.chain_valid


async def test_approval_band_goes_to_hitl() -> None:
    gov = make_runtime()
    pipeline, _ = make_pipeline(
        gov,
        claim_reply(amount_usd=3200.0, category="travel"),
        report_reply(),
        [submit_call(3200.0), text_reply("Held for approval.")],
    )
    result = await pipeline.process("Conference trip $3,200 with receipts, E-1042.")

    assert result.status == STATUS_PENDING
    assert gov.ledger.payments == []
    assert [t.kind for t in result.tickets] == ["tool_call"]


async def test_reject_recommendation_without_tools_is_no_action() -> None:
    gov = make_runtime()
    pipeline, _ = make_pipeline(
        gov,
        claim_reply(),
        report_reply(recommendation="reject", summary="Duplicate submission."),
        text_reply("Rejected: duplicate of last week's claim."),
    )
    result = await pipeline.process("Client dinner $180 (again).")

    assert result.status == STATUS_NO_ACTION
    assert gov.ledger.payments == []
    assert result.approver_reply.startswith("Rejected")


async def test_multi_case_audit_chain_stays_verifiable_and_exportable() -> None:
    gov = make_runtime()
    pipeline, _ = make_pipeline(
        gov,
        [claim_reply(), claim_reply(amount_usd=9000.0)],
        [report_reply(), report_reply()],
        [
            submit_call(180.0),
            text_reply("Paid."),
            submit_call(9000.0),
            text_reply("Blocked."),
        ],
    )
    first = await pipeline.process("Dinner $180.")
    second = await pipeline.process("Workstation $9,000.")

    assert (first.case_id, second.case_id) == ("case-001", "case-002")
    assert (first.status, second.status) == (STATUS_PAID, STATUS_BLOCKED)
    assert second.chain_valid
    # エクスポート → 独立検証(dict 列のみで完結)
    entries = load_entries(gov.audit.to_json())
    assert verify_entries(entries) == (True, None)
    assert len(entries) == second.audit_entries


async def test_case_result_to_dict_is_json_serializable() -> None:
    gov = make_runtime()
    pipeline, _ = make_pipeline(
        gov, claim_reply(), report_reply(), [submit_call(180.0), text_reply("Paid.")]
    )
    result = await pipeline.process("Dinner $180.")
    payload = json.loads(json.dumps(result.to_dict(), default=str))
    assert payload["status"] == STATUS_PAID
    assert payload["intake_trust"]["tier"] == "gold"
    assert payload["audit"]["chain_valid"] is True
