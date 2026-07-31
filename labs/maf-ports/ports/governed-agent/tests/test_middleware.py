"""MAF middleware 経由のガバナンス層テスト(本ポートの核心)。

実 ``Agent`` + ScriptedChatClient で本物の function-calling ループと
middleware パイプラインを回し、以下を証明する:

1. ポリシー違反のツール呼び出しは**実行されない**(台帳の生記録が空)
2. モデルには構造化された拒否がツール結果として渡り、ループは続行する
3. 遮断された呼び出しも監査連鎖に残る(監査が外側の合成順)
4. middleware の発火順序(agent → chat → function のオニオン)
5. ``MiddlewareTermination`` はループ全体を止める(short-circuit との対比)
"""

from __future__ import annotations

import json

from agent_framework import (
    AgentContext,
    ChatContext,
    FunctionInvocationContext,
    MiddlewareTermination,
    agent_middleware,
    chat_middleware,
    function_middleware,
)
from conftest import (
    AFTER_HOURS,
    ScriptedChatClient,
    make_runtime,
    text_reply,
    tool_call_reply,
)

from governed_agent_maf.agents import GovernanceRuntime, build_agents


def make_approver(replies, gov: GovernanceRuntime):
    """approver エージェントだけを scripted クライアントで組む。"""
    client = ScriptedChatClient(replies)
    agents = build_agents(ScriptedChatClient("unused"), gov, approver_client=client)
    return agents.approver, client


def _tool_results(client: ScriptedChatClient, request_index: int = 1) -> list[str]:
    """n 回目のモデル呼び出しに含まれる function_result のテキストを集める。"""
    results = []
    for message in client.requests[request_index]:
        for content in message.contents:
            if content.type == "function_result":
                value = content.result
                if isinstance(value, list):
                    results.extend(getattr(item, "text", str(item)) for item in value)
                else:
                    results.append(str(value))
    return results


# --- 1. DENY: 遮断(実行されないことの証明)---


async def test_denied_tool_is_never_executed() -> None:
    gov = make_runtime()
    approver, client = make_approver(
        [
            tool_call_reply(("delete_expense_record", {"record_id": "EXP-7"})),
            text_reply("The deletion was blocked by policy TOOL-001."),
        ],
        gov,
    )
    response = await approver.run("Please clean up record EXP-7.")

    # ツール本体は実行されていない(台帳の生記録・削除リストとも空)
    assert gov.ledger.executed_calls == []
    assert gov.ledger.deletions == []
    # モデルは構造化拒否をツール結果として受け取り、ループは続行した
    payload = json.loads(_tool_results(client)[0])
    assert payload["status"] == "deny"
    assert payload["rule_id"] == "TOOL-001"
    assert response.text == "The deletion was blocked by policy TOOL-001."


async def test_hard_limit_denial_blocks_payment() -> None:
    gov = make_runtime()
    approver, client = make_approver(
        [
            tool_call_reply(
                (
                    "submit_reimbursement",
                    {
                        "employee_id": "E-1042",
                        "amount_usd": 9000.0,
                        "category": "equipment",
                        "description": "workstation",
                    },
                )
            ),
            text_reply("Blocked: AMT-001."),
        ],
        gov,
    )
    await approver.run("Approve the workstation purchase.")

    assert gov.ledger.payments == []
    assert gov.ledger.executed_calls == []
    payload = json.loads(_tool_results(client)[0])
    assert payload["rule_id"] == "AMT-001"


async def test_after_hours_denial() -> None:
    gov = make_runtime(now=AFTER_HOURS)
    approver, client = make_approver(
        [
            tool_call_reply(
                (
                    "submit_reimbursement",
                    {
                        "employee_id": "E-1042",
                        "amount_usd": 100.0,
                        "category": "meals",
                        "description": "dinner",
                    },
                )
            ),
            text_reply("Blocked: HOURS-001."),
        ],
        gov,
    )
    await approver.run("Approve the dinner.")
    assert gov.ledger.payments == []
    assert json.loads(_tool_results(client)[0])["rule_id"] == "HOURS-001"


# --- 2. REQUIRE_APPROVAL: HITL キューへ ---


async def test_approval_band_enqueues_hitl_ticket() -> None:
    gov = make_runtime()
    approver, client = make_approver(
        [
            tool_call_reply(
                (
                    "submit_reimbursement",
                    {
                        "employee_id": "E-1042",
                        "amount_usd": 3200.0,
                        "category": "travel",
                        "description": "conference trip",
                    },
                )
            ),
            text_reply("Held for human approval (HITL-0001)."),
        ],
        gov,
    )
    await approver.run("Approve the trip.")

    assert gov.ledger.payments == []  # 承認が下りるまで実行されない
    assert len(gov.queue.pending()) == 1
    ticket = gov.queue.pending()[0]
    assert ticket.kind == "tool_call"
    assert ticket.payload["arguments"]["amount_usd"] == 3200.0
    payload = json.loads(_tool_results(client)[0])
    assert payload["status"] == "pending_human_approval"
    assert payload["ticket_id"] == ticket.ticket_id


# --- 3. ALLOW: 実行される+読み取り系はキュー無関係 ---


async def test_allowed_submission_executes_and_pays() -> None:
    gov = make_runtime()
    approver, client = make_approver(
        [
            tool_call_reply(
                (
                    "submit_reimbursement",
                    {
                        "employee_id": "E-1042",
                        "amount_usd": 180.0,
                        "category": "meals",
                        "description": "client dinner",
                    },
                )
            ),
            text_reply("Paid: PAY-0001."),
        ],
        gov,
    )
    await approver.run("Approve the dinner.")

    assert [name for name, _ in gov.ledger.executed_calls] == ["submit_reimbursement"]
    assert len(gov.ledger.payments) == 1
    assert gov.ledger.payments[0].amount_usd == 180.0
    assert gov.queue.pending() == []
    assert '"payment_id": "PAY-0001"' in _tool_results(client)[0]


async def test_readonly_tool_runs_without_gate() -> None:
    gov = make_runtime(now=AFTER_HOURS)  # 参照系は営業時間外でも通る
    approver, _client = make_approver(
        [
            tool_call_reply(("lookup_expense_policy", {"category": "meals"})),
            text_reply("Policy looked up."),
        ],
        gov,
    )
    await approver.run("What is the meals policy?")
    assert [name for name, _ in gov.ledger.executed_calls] == ["lookup_expense_policy"]


# --- 4. 監査連鎖: 遮断も許可も同じ連鎖に載る ---


async def test_audit_chain_records_denied_and_allowed_calls() -> None:
    gov = make_runtime()
    approver, _client = make_approver(
        [
            tool_call_reply(("delete_expense_record", {"record_id": "EXP-7"})),
            tool_call_reply(
                (
                    "submit_reimbursement",
                    {
                        "employee_id": "E-1042",
                        "amount_usd": 180.0,
                        "category": "meals",
                        "description": "dinner",
                    },
                )
            ),
            text_reply("Done."),
        ],
        gov,
    )
    await approver.run("Delete EXP-7 then pay the dinner.")

    tool_entries = [e for e in gov.audit.entries if e.action.startswith("tool:")]
    assert [(e.action, e.detail) for e in tool_entries] == [
        ("tool:delete_expense_record", "deny:TOOL-001"),
        ("tool:submit_reimbursement", "allow:POLICY-DEFAULT"),
    ]
    # エージェント実行自体も記録され、連鎖は検証可能
    agent_entries = [e for e in gov.audit.entries if e.action == "agent_run"]
    assert len(agent_entries) == 1
    assert agent_entries[0].actor == "expense_approver"
    assert gov.audit.verify_chain() == (True, None)


async def test_pending_call_detail_includes_ticket_id() -> None:
    gov = make_runtime()
    approver, _client = make_approver(
        [
            tool_call_reply(
                (
                    "submit_reimbursement",
                    {
                        "employee_id": "E-1042",
                        "amount_usd": 3200.0,
                        "category": "travel",
                        "description": "trip",
                    },
                )
            ),
            text_reply("Held."),
        ],
        gov,
    )
    await approver.run("Approve the trip.")
    entry = next(e for e in gov.audit.entries if e.action == "tool:submit_reimbursement")
    # metadata 経由でポリシー判定+チケット ID が監査側へ渡った
    assert entry.detail == "require_approval:AMT-002:HITL-0001"


# --- 5. 発火順序(agent → chat → function のオニオン)---


async def test_middleware_firing_order() -> None:
    events: list[str] = []

    # 注意: `from __future__ import annotations` 下では型注釈が文字列になり、
    # 関数 middleware の型推定(第1引数の注釈名で agent/chat/function を判別)が
    # 失敗する — デコレータ明示が必須(README 実装前調査・既知の罠 3(c) の再現)

    @agent_middleware
    async def agent_probe(context: AgentContext, call_next) -> None:
        events.append("agent_pre")
        await call_next()
        events.append("agent_post")

    @chat_middleware
    async def chat_probe(context: ChatContext, call_next) -> None:
        events.append("chat_pre")
        await call_next()
        events.append("chat_post")

    @function_middleware
    async def function_probe(context: FunctionInvocationContext, call_next) -> None:
        events.append(f"function_pre:{context.function.name}")
        await call_next()
        events.append("function_post")

    gov = make_runtime()
    client = ScriptedChatClient(
        [
            tool_call_reply(("lookup_expense_policy", {"category": "meals"})),
            text_reply("done"),
        ]
    )
    agents = build_agents(ScriptedChatClient("unused"), gov, approver_client=client)
    await agents.approver.run(
        "What is the meals policy?", middleware=[agent_probe, chat_probe, function_probe]
    )

    # chat はモデル呼び出しごと(ループ各反復)、function はツール呼び出しごと、
    # agent は run 全体で 1 回 — がオニオンで確定する
    assert events == [
        "agent_pre",
        "chat_pre",
        "chat_post",
        "function_pre:lookup_expense_policy",
        "function_post",
        "chat_pre",
        "chat_post",
        "agent_post",
    ]


# --- 6. MiddlewareTermination(kill switch)との対比 ---


async def test_middleware_termination_stops_the_whole_loop() -> None:
    """short-circuit(判定を返して続行)と違い、例外はループ全体を止める。

    2 回目のモデル呼び出しが発生せず、モデルに拒否を説明する機会は無い。
    エージェントの kill switch(予算超過・暴走停止)にはこちらを使う。
    """

    @function_middleware
    async def kill_switch(context: FunctionInvocationContext, call_next) -> None:
        context.result = {"status": "terminated", "reason": "emergency stop"}
        raise MiddlewareTermination("emergency stop")

    gov = make_runtime()
    client = ScriptedChatClient(
        [
            tool_call_reply(("lookup_expense_policy", {"category": "meals"})),
            text_reply("unreachable"),
        ]
    )
    agents = build_agents(ScriptedChatClient("unused"), gov, approver_client=client)
    response = await agents.approver.run("What is the meals policy?", middleware=[kill_switch])

    assert gov.ledger.executed_calls == []  # ツールは実行されない
    assert len(client.requests) == 1  # 2 回目のモデル呼び出しが無い
    assert response.text == ""  # 最終応答も生成されない
    content_types = [c.type for m in response.messages for c in m.contents]
    assert "function_result" in content_types  # 中断時の result は messages に残る
