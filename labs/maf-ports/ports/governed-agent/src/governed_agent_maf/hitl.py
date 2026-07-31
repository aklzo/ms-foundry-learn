"""人間承認キュー(HITL スタブ)。

元 ai_agent_governance は ``input()`` で対話承認していたが、非対話 CLI では
成立しないため「承認待ちチケットを積んで結果を保留にする」キューに置換。
実運用では Teams 承認フローやチケットシステムへの接続点になる。

MAF には ``@tool(approval_mode="always_require")`` というネイティブの承認
フローもある(README「実装前調査」参照)が、あれは**ツール単位の静的宣言**。
本ポートのポリシーは**引数の中身(金額)で承認要否が変わる**ため、
FunctionMiddleware 側で動的に判定してこのキューへ流す。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ApprovalTicket:
    ticket_id: str
    kind: str  # "tool_call"(ポリシー由来)| "low_trust"(信頼ゲート由来)
    subject: str
    reason: str
    payload: Mapping[str, Any]
    status: str = "pending"


@dataclass
class ApprovalQueue:
    """承認待ちチケットの置き場(インメモリのスタブ)。"""

    tickets: list[ApprovalTicket] = field(default_factory=list)

    def enqueue(
        self,
        *,
        kind: str,
        subject: str,
        reason: str,
        payload: Mapping[str, Any] | None = None,
    ) -> ApprovalTicket:
        ticket = ApprovalTicket(
            ticket_id=f"HITL-{len(self.tickets) + 1:04d}",
            kind=kind,
            subject=subject,
            reason=reason,
            payload=dict(payload or {}),
        )
        self.tickets.append(ticket)
        return ticket

    def pending(self) -> list[ApprovalTicket]:
        return [t for t in self.tickets if t.status == "pending"]
