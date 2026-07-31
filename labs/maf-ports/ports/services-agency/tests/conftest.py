"""テスト共有部品: ScriptedAgent / ConsultingAgent(LLM の scripted fake)。

ConsultingAgent が本ポートの肝: run() のたびに「計画された相談」を
talk_to_* ツール経由で実行し、返答を自分の応答に統合する — LLM の
「ツール呼び出し → 結果統合」ループの決定論版。ツールは Agency 構築後に
``bind()`` で注入する(実 LLM ではフレームワークが担う配線)。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from services_agency_maf.project import ProjectInfo


@dataclass
class FakeResponse:
    text: str


class ScriptedAgent:
    """受け取ったメッセージを記録し、決められた応答列を順に返す。

    replies を使い切ったら最後の応答を繰り返す(再入呼び出しテスト用)。
    """

    def __init__(self, replies: list[str] | str) -> None:
        if isinstance(replies, str):
            replies = [replies]
        assert replies, "少なくとも 1 応答が必要"
        self._replies = list(replies)
        self._index = 0
        self.received: list[str] = []

    async def run(self, message: str) -> FakeResponse:
        self.received.append(message)
        reply = self._replies[min(self._index, len(self._replies) - 1)]
        self._index += 1
        return FakeResponse(text=reply)


class ConsultingAgent:
    """run() ごとに consults = [(recipient, message), ...] を順に相談し、
    相手の返答を組み込んだ応答を返す fake。

    応答形式: "[<key>] <base>" に、相談があれば " | consulted: <r1>=<reply1>;
    <r2>=<reply2>" を連結する(テストは containment で検証)。
    """

    def __init__(self, key: str, consults: list[tuple[str, str]], base: str = "") -> None:
        self.key = key
        self.consults = list(consults)
        self.base = base or f"{key} analysis"
        self.tools: dict[str, Callable[..., Any]] = {}
        self.received: list[str] = []
        self.replies_seen: list[str] = []

    def bind(self, tools: Iterable[Callable[..., Any]]) -> None:
        self.tools = {tool.__name__: tool for tool in tools}

    async def run(self, message: str) -> FakeResponse:
        self.received.append(message)
        collected: list[str] = []
        for recipient, consult_message in self.consults:
            tool = self.tools[f"talk_to_{recipient}"]
            reply = await tool(consult_message)
            self.replies_seen.append(reply)
            collected.append(f"{recipient}={reply}")
        text = f"[{self.key}] {self.base}"
        if collected:
            text += " | consulted: " + "; ".join(collected)
        return FakeResponse(text=text)


def sample_project(**overrides: Any) -> ProjectInfo:
    data: dict[str, Any] = {
        "name": "Project Phoenix",
        "description": "AI-assisted note sharing SaaS for university students.",
        "project_type": "Web Application",
        "timeline": "3-4 months",
        "budget": "$25k-$50k",
        "priority": "High",
        "technical_requirements": "Must integrate with campus SSO.",
        "special_considerations": "FERPA compliance.",
    }
    data.update(overrides)
    return ProjectInfo(**data)
