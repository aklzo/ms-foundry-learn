"""トップレベル実行(元 Streamlit main() の 5 連続 get_response_sync)と
最終レポートの組み立て。

元アプリは 5 ターンの結果を 5 つのタブに表示していた。移植は同じ 5 ターンを
同じ順で実行し、タブの代わりに Markdown セクション+**通信ログ**+共有状態を
1 レポートにまとめる。5 ターンは同一 Agency を共有するため、CEO のターンで
書かれた分析を CTO のターンのツールが読める(元の shared context と同じ)。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .agency import Agency
from .comms import CommEvent
from .flows import AGENT_KEYS
from .project import ProjectInfo
from .roles import entry_prompt

#: 元 Streamlit のタブ見出し(表示順 = AGENT_KEYS = 実行順)
TAB_TITLES: dict[str, str] = {
    "ceo": "CEO's Strategic Analysis",
    "cto": "CTO's Technical Specification",
    "product_manager": "Product Manager's Plan",
    "developer": "Lead Developer's Development Plan",
    "client_manager": "Client Success Strategy",
}


@dataclass
class AgencyReport:
    """1 回の実行の全成果: 5 応答+通信ログ+共有状態。"""

    project: ProjectInfo
    responses: dict[str, str]
    events: tuple[CommEvent, ...]
    state: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "project": self.project.to_message_dict(),
            "responses": dict(self.responses),
            "communications": [event.to_dict() for event in self.events],
            "state": dict(self.state),
        }

    def to_markdown(self) -> str:
        parts = [f"# AI Services Agency — {self.project.name}"]
        parts.extend(
            f"## {TAB_TITLES[key]}\n\n{self.responses[key]}" for key in AGENT_KEYS
        )
        comm_lines = "\n".join(event.render() for event in self.events) or "(none)"
        parts.append(f"## Communication Log\n\n```\n{comm_lines}\n```")
        parts.append(
            "## Shared Project State\n\n```json\n"
            + json.dumps(self.state, ensure_ascii=False, indent=2)
            + "\n```"
        )
        return "\n\n".join(parts)


async def run_agency(
    agency: Agency,
    project: ProjectInfo,
    on_turn: Callable[[str, str], None] | None = None,
) -> AgencyReport:
    """5 ターンを元アプリと同じ順(ceo → cto → pm → developer → cs)で実行する。

    エージェント間通信(talk_to_*)は各ターンの**中で** LLM の裁量により発生し、
    CommLog に蓄積される。``on_turn(key, text)`` はターン完了ごとの進捗通知。
    """
    responses: dict[str, str] = {}
    for key in AGENT_KEYS:
        text = await agency.get_response(key, entry_prompt(key, project))
        responses[key] = text
        if on_turn is not None:
            on_turn(key, text)
    return AgencyReport(
        project=project,
        responses=responses,
        events=agency.log.events,
        state=agency.state.to_dict(),
    )
