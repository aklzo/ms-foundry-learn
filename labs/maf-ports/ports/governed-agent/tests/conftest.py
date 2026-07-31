"""テスト共有部品。

本ポートの検証対象は MAF の middleware 機構そのものなので、fake の注入点を
他ポートの「エージェント境界(SupportsRun)」から一段下げ、**チャット
クライアント境界**に置く: ``ScriptedChatClient`` は実 ``Agent`` の下で
function-calling ループ・middleware パイプラインを本物のまま回し、モデル応答
だけを台本化する(OpenAIChatClient と同じ層合成:
FunctionInvocationLayer + ChatMiddlewareLayer + BaseChatClient)。
"""

from __future__ import annotations

import json
from datetime import datetime
from itertools import count
from typing import Any

from agent_framework import (
    BaseChatClient,
    ChatMiddlewareLayer,
    ChatResponse,
    Content,
    FunctionInvocationLayer,
    Message,
)

from governed_agent_maf.agents import GovernanceRuntime, build_governance
from governed_agent_maf.policies import GovernancePolicy
from governed_agent_maf.schemas import ExpenseClaim, InspectionReport

#: 営業時間内(水曜 10:30)/ 営業時間外(水曜 22:30)の固定時刻
BUSINESS_NOW = datetime(2026, 7, 29, 10, 30)
AFTER_HOURS = datetime(2026, 7, 29, 22, 30)


class ScriptedChatClient(FunctionInvocationLayer, ChatMiddlewareLayer, BaseChatClient):
    """決められた応答列を順に返すチャットクライアント(使い切ったら最後を繰り返す)。

    ``requests`` に各モデル呼び出しのメッセージ列を記録する — ツール結果が
    モデルに何として渡ったかの検証に使う。
    """

    OTEL_PROVIDER_NAME = "scripted"

    def __init__(self, replies: list[str | ChatResponse] | str | ChatResponse, **kwargs: Any):
        super().__init__(**kwargs)
        if not isinstance(replies, list):
            replies = [replies]
        assert replies, "少なくとも 1 応答が必要"
        self._replies = list(replies)
        self._index = 0
        self.requests: list[list[Message]] = []

    async def _inner_get_response(self, *, messages, stream, options, **kwargs):
        assert not stream, "本ポートは非ストリーミングのみ"
        self.requests.append(list(messages))
        reply = self._replies[min(self._index, len(self._replies) - 1)]
        self._index += 1
        if isinstance(reply, ChatResponse):
            return reply
        return ChatResponse(messages=[Message("assistant", [reply])])


def text_reply(text: str) -> ChatResponse:
    return ChatResponse(messages=[Message("assistant", [text])])


def tool_call_reply(*calls: tuple[str, dict[str, Any]]) -> ChatResponse:
    """モデルの function_call 応答(複数可)を組む。"""
    contents = [
        Content.from_function_call(
            call_id=f"call-{i + 1}",
            name=name,
            arguments=json.dumps(arguments),
        )
        for i, (name, arguments) in enumerate(calls)
    ]
    return ChatResponse(messages=[Message("assistant", contents)])


# --- ドメイン素材 ---


def complete_claim(**overrides: Any) -> ExpenseClaim:
    """信頼ゲートを通る完全な申請(client dinner $180)。"""
    data: dict[str, Any] = {
        "employee_id": "E-1042",
        "employee_name": "Mika Tanaka",
        "department": "sales",
        "amount_usd": 180.0,
        "category": "meals",
        "expense_date": "2026-07-24",
        "description": "Client dinner with Fabrikam after contract signing.",
        "has_receipt": True,
        "receipt_reference": "RCPT-2201",
        "missing_or_uncertain": [],
    }
    data.update(overrides)
    return ExpenseClaim(**data)


def vague_claim(**overrides: Any) -> ExpenseClaim:
    """信頼ゲートに落ちる申請(金額・社員 ID・領収書なし)。"""
    data: dict[str, Any] = {
        "description": "I spent some money on stuff last week, please pay me back.",
        "has_receipt": False,
        "missing_or_uncertain": ["amount", "date", "what was purchased"],
    }
    data.update(overrides)
    return ExpenseClaim(**data)


def approve_report(**overrides: Any) -> InspectionReport:
    data: dict[str, Any] = {
        "summary": "Documented client dinner, consistent with policy.",
        "findings": [],
        "recommendation": "approve",
        "confidence": 0.9,
    }
    data.update(overrides)
    return InspectionReport(**data)


def claim_reply(**overrides: Any) -> ChatResponse:
    return text_reply(complete_claim(**overrides).model_dump_json())


def report_reply(**overrides: Any) -> ChatResponse:
    return text_reply(approve_report(**overrides).model_dump_json())


def fixed_clock(moment: datetime):
    def clock() -> datetime:
        return moment

    return clock


def make_runtime(
    *,
    now: datetime = BUSINESS_NOW,
    threshold: int = 40,
    policy: GovernancePolicy | None = None,
) -> GovernanceRuntime:
    """決定論のガバナンスランタイム(監査時刻は 1000.0 から 1 秒刻み)。"""
    ticks = count()
    return build_governance(
        policy,
        threshold=threshold,
        clock=fixed_clock(now),
        time_fn=lambda: 1000.0 + next(ticks),
    )
