"""ガバナンス層の MAF middleware(本ポートの核心)。

agent_framework 1.13 の middleware は 3 種(installed package `_middleware.py`
精読の結果 — 詳細は README「実装前調査」):

- ``AgentMiddleware``    : ``agent.run`` 全体を 1 回包む
- ``ChatMiddleware``     : モデル呼び出し(function-calling ループの各反復)を包む
- ``FunctionMiddleware`` : ツール呼び出し 1 件ごとに包む

いずれも ``async def process(context, call_next)`` のオニオン合成。short-circuit
は「``context.result`` をセットして ``call_next()`` を呼ばずに return」——
FunctionMiddleware ではその result がそのままツール結果(function_result)として
モデルに渡り、**ツール本体は実行されない**。``MiddlewareTermination`` を投げる
方法もあるが、あちらは function-calling ループ全体を停止させる(モデルに説明の
機会を与えない)ため、本ポートは「構造化拒否を返して続行」を採る。

配置(approver エージェント、外側から):
    ToolAuditMiddleware → PolicyEnforcementMiddleware → (ツール本体)
監査を外側に置くことで、**遮断された呼び出しも監査連鎖に残る**。判定は
``context.metadata``(middleware 間共有 dict)経由で監査側へ渡す。
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime
from typing import Any

from agent_framework import (
    AgentContext,
    AgentMiddleware,
    FunctionInvocationContext,
    FunctionMiddleware,
)

from .audit import AuditTrail
from .hitl import ApprovalQueue
from .policies import Decision, PolicyEngine, ToolCallRequest, build_policy_tool_result

#: middleware 間で判定を受け渡す metadata キー
POLICY_DECISION_KEY = "governed_agent.policy_decision"
HITL_TICKET_KEY = "governed_agent.hitl_ticket"


def _render_arguments(arguments: Any) -> str:
    if isinstance(arguments, Mapping):
        return json.dumps(dict(arguments), sort_keys=True, default=str)
    return str(arguments)


def _render_result(result: Any) -> str:
    """ツール結果を監査ハッシュ用テキストに正規化する。

    実行された場合の ``context.result`` は Content のリスト(フレームワークが
    正規化したもの)、short-circuit の場合は自前の dict。両方を吸収する。
    """
    if result is None:
        return ""
    if isinstance(result, Mapping):
        return json.dumps(dict(result), sort_keys=True, default=str)
    if isinstance(result, (list, tuple)):
        parts = []
        for item in result:
            text = getattr(item, "text", None)
            if text:
                parts.append(text)
            else:
                inner = getattr(item, "result", None)
                parts.append(str(inner) if inner is not None else str(item))
        return "\n".join(parts)
    return str(result)


class PolicyEnforcementMiddleware(FunctionMiddleware):
    """ツール実行前の決定論ポリシー検査(元 ``governed_tool`` デコレータの移植)。

    DENY / REQUIRE_APPROVAL では ``call_next()`` を呼ばない = ツールは実行されず、
    構造化された拒否/保留がツール結果としてモデルに返る。REQUIRE_APPROVAL は
    さらに人間承認キューへチケットを積む(HITL スタブ)。
    """

    def __init__(
        self,
        engine: PolicyEngine,
        queue: ApprovalQueue,
        clock: Callable[[], datetime],
    ) -> None:
        self._engine = engine
        self._queue = queue
        self._clock = clock

    async def process(
        self,
        context: FunctionInvocationContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        arguments = dict(context.arguments) if isinstance(context.arguments, Mapping) else {}
        request = ToolCallRequest(
            tool=context.function.name,
            arguments=arguments,
            requested_at=self._clock(),
        )
        decision = self._engine.evaluate(request)
        context.metadata[POLICY_DECISION_KEY] = decision  # 監査 middleware が読む

        if decision.decision is Decision.DENY:
            context.result = build_policy_tool_result(decision, request)
            return  # short-circuit: ツール本体は実行しない

        if decision.decision is Decision.REQUIRE_APPROVAL:
            ticket = self._queue.enqueue(
                kind="tool_call",
                subject=request.tool,
                reason=decision.reason,
                payload={"tool": request.tool, "arguments": arguments},
            )
            context.metadata[HITL_TICKET_KEY] = ticket.ticket_id
            context.result = build_policy_tool_result(decision, request, ticket_id=ticket.ticket_id)
            return  # short-circuit: 人間の承認が下りるまで実行しない

        await call_next()


class ToolAuditMiddleware(FunctionMiddleware):
    """全ツール呼び出し(遮断・保留を含む)をハッシュ連鎖に記録する。

    PolicyEnforcementMiddleware より**外側**に登録すること。内側の判定は
    ``context.metadata`` から回収する。
    """

    def __init__(self, audit: AuditTrail, *, actor: str) -> None:
        self._audit = audit
        self._actor = actor

    async def process(
        self,
        context: FunctionInvocationContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        input_text = _render_arguments(context.arguments)
        await call_next()
        decision = context.metadata.get(POLICY_DECISION_KEY)
        detail = decision.tag if decision is not None else "unpoliced"
        ticket_id = context.metadata.get(HITL_TICKET_KEY)
        if ticket_id:
            detail = f"{detail}:{ticket_id}"
        self._audit.record(
            actor=self._actor,
            action=f"tool:{context.function.name}",
            input_text=input_text,
            output_text=_render_result(context.result),
            detail=detail,
        )


class AgentAuditMiddleware(AgentMiddleware):
    """エージェント実行(入力メッセージ→最終応答)をハッシュ連鎖に記録する。"""

    def __init__(self, audit: AuditTrail) -> None:
        self._audit = audit

    async def process(
        self,
        context: AgentContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        input_text = "\n".join(f"{m.role}: {m.text}" for m in context.messages)
        await call_next()
        output_text = ""
        if context.result is not None and not context.stream:
            output_text = getattr(context.result, "text", "") or ""
        self._audit.record(
            actor=getattr(context.agent, "name", None) or "agent",
            action="agent_run",
            input_text=input_text,
            output_text=output_text,
            detail=f"messages={len(context.messages)}",
        )
