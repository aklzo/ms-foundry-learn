"""旅行相談エージェントの組み立て(元アプリの OpenAI 呼び出しに対応)。

元: ``client.chat.completions.create(model="gpt-4o", messages=[system, user])``
を毎ターン直接呼ぶ。system prompt は固定文、user メッセージは
「記憶コンテキスト+質問」を連結した 1 本のプロンプト。

移植後: 同じ 1 役割を MAF ``Agent`` として作る。system prompt は
``instructions`` に写し、プロンプト連結は chat.py が担う。モデルは Foundry
のデプロイ(既定 gpt-5.4-mini)。
"""

from __future__ import annotations

from typing import Any, Protocol

from .config import TravelMemorySettings

#: 元アプリの system prompt(原文のまま)
SYSTEM_INSTRUCTIONS = "You are a travel assistant with access to past conversations."


class SupportsRun(Protocol):
    """チャットループが必要とする最小面: ``await run(text)`` → ``.text`` を
    持つ応答。テストでは scripted fake が置き換える。"""

    async def run(self, message: str) -> Any: ...


def build_chat_client(settings: TravelMemorySettings) -> Any:
    from agent_framework.openai import OpenAIChatClient

    return OpenAIChatClient(
        model=settings.model,
        api_key=settings.api_key,
        base_url=settings.openai_v1_endpoint,
    )


def build_travel_agent(chat_client: Any) -> SupportsRun:
    from agent_framework import Agent

    return Agent(chat_client, name="travel_agent", instructions=SYSTEM_INSTRUCTIONS)
